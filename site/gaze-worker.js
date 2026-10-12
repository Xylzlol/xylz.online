/* The gaze estimate off the main thread: the learned model (gaze-net.js with gaze-net.bin, 43 KB) or,
   if its weights cannot load, the particle filter (gaze.js); the belief's picture (LED cells, on an
   OffscreenCanvas the page handed over); and the fixation-like decision of when the tracker jumps.
   The page only hears about real jumps. With no input for 1.5s the loop stops and the picture holds
   still; any input wakes it. */
importScripts("gaze.js?v=20261013n39");
const createParticles = self.createGaze;
importScripts("gaze-net.js?v=20261013n39");
const createNet = self.createGaze;
importScripts("gaze-dyn.js?v=20261013n39");
// the moving-content layer runs only when the page asks for it (?dyn), until its certificate passes
self.GAZE_DYN = false;
let netReady = null; // a promise of the parsed weights, or null when they failed
netReady = fetch("gaze-net.bin?v=20261013n39").then((r) => (r.ok ? r.arrayBuffer() : Promise.reject(r.status)))
  .then((buf) => { createNet.setNet(createNet.parse(buf)); return true; }).catch(() => false);

let g = null;
let canvas = null, ctx = null;
let pitch = 8, ink = "#050506";
let view = { x: 0, y: 0, w: 1440, h: 900 };
let lastInput = 0;
let running = false;
let paused = false;
let lastDraw = 0;
let shown = null;
let awaySince = 0;
let labelRect = null;
let lastLayout = null;
const IDLE_MS = 1500;

const raf = self.requestAnimationFrame ? (fn) => self.requestAnimationFrame(fn) : (fn) => setTimeout(() => fn(performance.now()), 16);

function wake() {
  if (paused) return;
  lastInput = performance.now();
  if (!running && g) {
    running = true;
    raf(loop);
  }
}

function draw(est) {
  if (!ctx) return;
  const p = pitch;
  // only the belief close to the estimate is drawn, however wide the uncertainty: the label states it
  const reach = Math.min(110, Math.max(50, est.r50 * 1.6)), reach2 = reach * reach;
  const mass = new Map();
  if (g.samples) {
    // the learned model: 512 points drawn from its mixture, binned like the particles were
    for (const [x, y] of g.samples(512)) {
      if ((x - est.x) ** 2 + (y - est.y) ** 2 > reach2) continue;
      const k = Math.floor(x / p) * 100000 + Math.floor(y / p);
      mass.set(k, (mass.get(k) || 0) + 1);
    }
  }
  const { P, N } = g;
  for (let i = 0; i < N; i++) {
    if ((P.x[i] - est.x) ** 2 + (P.y[i] - est.y) ** 2 > reach2) continue;
    const k = Math.floor(P.x[i] / p) * 100000 + Math.floor(P.y[i] / p);
    mass.set(k, (mass.get(k) || 0) + P.w[i]);
  }
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  ctx.fillStyle = ink;
  let top = 0;
  for (const m of mass.values()) if (m > top) top = m;
  const lines = g.lines();
  for (const [k, m] of mass) {
    if (m < top * 0.15) continue;
    const c = Math.floor(k / 100000);
    const r = k - c * 100000;
    const x = c * p + p / 2, y = r * p + p / 2;
    // the belief shows only in open field: never on top of a line of text
    let onText = false;
    for (let i = 0; i < lines.length; i++) {
      const l = lines[i];
      if (x > l.x - 3 && x < l.x + l.w + 3 && Math.abs(y - l.y) < l.ch * 1.3) { onText = true; break; }
    }
    if (onText) continue;
    // and never under the gaze label
    if (labelRect && x > labelRect.x && x < labelRect.x + labelRect.w && y > labelRect.y && y < labelRect.y + labelRect.h) continue;
    ctx.globalAlpha = 0.08 + 0.52 * Math.pow(m / top, 0.6);
    ctx.beginPath();
    ctx.arc(x - view.x, y - view.y, p * 0.38, 0, Math.PI * 2);
    ctx.fill();
  }
  ctx.globalAlpha = 1;
}

function loop(now) {
  if (!running || paused) return;
  g.step(now);
  // going still: the last picture and the last fixation must agree, so a pending jump is made now
  const stopping = now - lastInput > IDLE_MS;
  if (stopping || now - lastDraw >= 33) {
    lastDraw = now;
    const est = g.estimate();
    draw(est);
    // the tracker holds still (a fixation) and jumps (a saccade) only once the estimate has moved
    // clearly away and stayed there for ~90ms
    // the jump rule follows the 50% radius (up to 130px; past that it follows the drawn cloud)
    const wide = est.r50 > 130;
    const size = wide ? 30 : Math.max(30, est.r50 * 2);
    // when only the cloud and label show (wide), the label follows the drawn cloud closely
    const moveTol = wide ? 24 : Math.max(18, est.r50 * 0.4);
    const far = !shown || Math.hypot(est.x - shown.x, est.y - shown.y) > moveTol || Math.abs(size - shown.size) > Math.max(24, shown.size * 0.35);
    if (!far) awaySince = 0;
    else if (!awaySince) awaySince = now;
    if (!shown || (far && (stopping || now - awaySince > 90))) {
      awaySince = 0;
      shown = { x: est.x, y: est.y, size };
      postMessage({ type: "show", x: est.x, y: est.y, size, r50: est.r50, reach: Math.min(110, Math.max(50, est.r50 * 1.6)) });
    }
  }
  if (stopping) {
    running = false; // still: nothing is drawn or computed until the next input
    return;
  }
  raf(loop);
}

/* What moves on screen, straight from the wall worker: a block grid of brightness change per
   second, in document coordinates (see sampleMotion in wall.js). Kept as the latest map; the
   model reads it when it estimates. */
let motion = null;
self.__motionLog = null; // with ?debug the page can ask for the recent maps
function onMotion(m) {
  motion = m;
  if (self.__motionLog) { self.__motionLog.push({ t: m.t, by0: m.by0, nbx: m.nbx, nby: m.nby, B: m.B, pitch: m.pitch, e: Array.from(m.e) }); if (self.__motionLog.length > 400) self.__motionLog.shift(); }
  if (g && g.motion && self.GAZE_DYN !== false) {
    g.motion(m);
    wake(); // the maps only come while the wall moves, so this wakes the loop only then
  }
}

onmessage = (e) => {
  const m = e.data;
  switch (m.type) {
    case "motionPort":
      m.port.onmessage = (ev) => onMotion(ev.data);
      return;
    case "motionLog":
      if (m.on) self.__motionLog = [];
      else postMessage({ type: "motionLog", log: self.__motionLog || [] });
      return;
    case "reduce":
      paused = !!m.reduce;
      if (paused) {
        running = false;
        if (ctx) ctx.clearRect(0, 0, canvas.width, canvas.height);
        return;
      }
      break;
    case "init":
      if (m.dyn) self.GAZE_DYN = m.dynParams || null;
      // the learned model when its weights are in, the particle filter otherwise; the first layout
      // message usually arrives after the weights, and a late load swaps the model in then
      g = createParticles(m.N);
      netReady.then((ok) => {
        postMessage({ type: "model", net: ok });
        if (!ok) return;
        const last = g;
        g = createNet(m.N);
        if (lastLayout) g.layout(lastLayout);
        if (last && lastLayout) g.view(lastLayout.view);
        wake();
      });
      canvas = m.canvas;
      ctx = canvas.getContext("2d");
      pitch = m.pitch;
      ink = m.ink;
      break;
    case "size":
      if (canvas) { canvas.width = m.w; canvas.height = m.h; }
      pitch = m.pitch || pitch;
      break;
    case "layout":
      view = m.view;
      lastLayout = m;
      g.layout(m);
      break;
    case "view":
      view = m.view;
      g.view(m.view);
      break;
    case "move": g.move(m.x, m.y); break;
    case "click": g.click(m.x, m.y); break;
    case "intent": g.intent(m.intent); break;
    case "onset": g.onset(m.box); break;
    case "saliency": g.saliency(m.map, m.w, m.h, m.view); break;
    case "ink": ink = m.ink; break;
    case "label": labelRect = m.rect; if (g && ctx) draw(g.estimate()); return; // redraw once, no wake
  }
  wake();
};
