/* Runs the UI saliency network (UNISAL fine-tuned on UEyes UI eye-tracking) off the main thread.
   In: a 448x288 RGBA picture of the viewport. Out: a 112x72 map of where people look, summing to 1. */
import * as ort from "./vendor/ort/ort.wasm.min.mjs";

ort.env.wasm.wasmPaths = new URL("./vendor/ort/", import.meta.url).href;
ort.env.wasm.numThreads = self.crossOriginIsolated ? Math.min(4, navigator.hardwareConcurrency || 2) : 1;

const W = 448, H = 288;
const MEAN = [0.485, 0.456, 0.406], STD = [0.229, 0.224, 0.225];
let session = null;
let busy = false;
let pending = null;

async function init(url) {
  session = await ort.InferenceSession.create(url, { executionProviders: ["wasm"], graphOptimizationLevel: "all" });
  postMessage({ type: "ready" });
}

const pic = new OffscreenCanvas(W, H);
const pctx = pic.getContext("2d", { willReadFrequently: true });
let debug = false;

async function run(job) {
  busy = true;
  // the page sends an ImageBitmap; the pixels are read here, off the main thread
  pctx.drawImage(job.bitmap, 0, 0);
  job.bitmap.close();
  const px = pctx.getImageData(0, 0, W, H).data;
  const input = new Float32Array(3 * H * W);
  for (let i = 0, n = H * W; i < n; i++) {
    input[i] = (px[i * 4] / 255 - MEAN[0]) / STD[0];
    input[n + i] = (px[i * 4 + 1] / 255 - MEAN[1]) / STD[1];
    input[2 * n + i] = (px[i * 4 + 2] / 255 - MEAN[2]) / STD[2];
  }
  const t0 = performance.now();
  const out = await session.run({ image: new ort.Tensor("float32", input, [1, 3, H, W]) });
  const map = out.saliency.data;
  postMessage({ type: "map", map, w: 112, h: 72, view: job.view, ms: performance.now() - t0, pic: debug ? px : null }, [map.buffer]);
  busy = false;
  if (pending) {
    const next = pending;
    pending = null;
    run(next);
  }
}

onmessage = (e) => {
  const m = e.data;
  if (m.type === "init") debug = !!m.debug, init(m.url).catch((err) => postMessage({ type: "error", message: String(err) }));
  else if (m.type === "frame") {
    // only the newest picture matters; one in flight, one waiting
    if (!session || busy) {
      if (pending && pending.bitmap) pending.bitmap.close();
      pending = m;
    }
    else run(m);
  }
};
