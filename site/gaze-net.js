/* Where is the visitor looking? A learned estimate, from no camera at all.

   A small network (trained on AdSERP: 47 people browsing with a 150 Hz eye tracker and their mouse
   logged; ml/gaze_mdn.py) reads the pointer's last two seconds, how long the hand has been still,
   recent clicks and scrolling, and the text around the cursor, and outputs a mixture of Gaussians
   over where the eyes are relative to the cursor. The estimate is the mixture's densest point; its
   stated precision is the radius around it that holds half of the mixture.

   Same interface as gaze.js, so the gaze worker and the certificate (ml/gaze_cert.mjs) use either:
   createGaze(N) -> { layout, view, move, click, step, estimate, ... }. Inference is hand-written:
   three dense layers on 8-bit weights with a scale per output row, evaluated every 100 ms. */
(() => {
  const LAGS = [100, 200, 400, 700, 1000, 1500, 2000];
  const LC = 9, LR = 7, CELL = 80, VC = 8, VR = 6;

  // ---- the network: filled by load() from gaze-net.bin, or by the certificate harness ----
  let NET = null;
  function setNet(net) { NET = net; }
  // binary layout: "GZN1", u32 nLayers, u32 K, u32 flags; per layer: u32 in, u32 out, f32[out] scale,
  // f32[out] bias, i8[out*in] weights (row major); flags bit0 = abs features dropped, bit1 = view grid
  // dropped, bit2 = no layout features at all (a pointer-only model)
  function parse(buf) {
    const dv = new DataView(buf);
    if (String.fromCharCode(dv.getUint8(0), dv.getUint8(1), dv.getUint8(2), dv.getUint8(3)) !== "GZN1") throw new Error("bad gaze net");
    let o = 4;
    const nl = dv.getUint32(o, true); o += 4;
    const K = dv.getUint32(o, true); o += 4;
    const flags = dv.getUint32(o, true); o += 4;
    const layers = [];
    for (let l = 0; l < nl; l++) {
      const nin = dv.getUint32(o, true); o += 4;
      const nout = dv.getUint32(o, true); o += 4;
      const scale = new Float32Array(buf.slice(o, o + 4 * nout)); o += 4 * nout;
      const bias = new Float32Array(buf.slice(o, o + 4 * nout)); o += 4 * nout;
      const w = new Int8Array(buf.slice(o, o + nin * nout)); o += nin * nout;
      layers.push({ nin, nout, scale, bias, w });
    }
    return { layers, K, dropAbs: !!(flags & 1), dropView: !!(flags & 2), noLayout: !!(flags & 4) };
  }

  const gelu = (x) => 0.5 * x * (1 + Math.tanh(0.7978845608 * (x + 0.044715 * x * x * x)));
  function forward(x) {
    let a = x;
    const L = NET.layers;
    for (let l = 0; l < L.length; l++) {
      const { nin, nout, scale, bias, w } = L[l];
      const out = new Float32Array(nout);
      for (let j = 0; j < nout; j++) {
        let s = 0;
        const row = j * nin;
        for (let i = 0; i < nin; i++) s += w[row + i] * a[i];
        s = s * scale[j] + bias[j];
        out[j] = l < L.length - 1 ? gelu(s) : s;
      }
      a = out;
    }
    return a;
  }

  // ---- text coverage: line boxes -> a 20 px raster with a summed-area table ----
  function textGrid(lines, docW, docH) {
    const res = 20, w = Math.ceil(docW / res) + 2, h = Math.ceil(docH / res) + 2;
    const g = new Float32Array(w * h);
    for (const l of lines) {
      const x0 = Math.max(0, Math.floor(l.x / res)), y0 = Math.max(0, Math.floor(l.y / res));
      const x1 = Math.min(w, Math.floor((l.x + l.w) / res) + 1), y1 = Math.min(h, Math.floor((l.y + l.h) / res) + 1);
      for (let y = y0; y < y1; y++) g.fill(1, y * w + x0, y * w + x1);
    }
    const S = new Float32Array((w + 1) * (h + 1));
    for (let y = 1; y <= h; y++) {
      let row = 0;
      for (let x = 1; x <= w; x++) {
        row += g[(y - 1) * w + (x - 1)];
        S[y * (w + 1) + x] = S[(y - 1) * (w + 1) + x] + row;
      }
    }
    return {
      cover(x0, y0, x1, y1) {
        const cl = (v, m) => Math.min(m, Math.max(0, v));
        const a = cl(Math.floor(x0 / res), w), b = cl(Math.floor(y0 / res), h);
        const c = cl(Math.floor(x1 / res), w), d = cl(Math.floor(y1 / res), h);
        if (c <= a || d <= b) return 0;
        const W1 = w + 1;
        return (S[d * W1 + c] - S[b * W1 + c] - S[d * W1 + a] + S[b * W1 + a]) / ((c - a) * (d - b));
      },
    };
  }

  self.createGaze = function createGaze() {
    let view = { x: 0, y: 0, w: 1440, h: 900 };
    let grid = null;
    const hist = []; // [t, x, y] viewport px
    const scrolls = [[0, 0]];
    let lastMove = -1e9, lastClick = -1e9, click = [0, 0];
    const t0 = performance.now(); // features count time from page load, as in training
    let mix = null; // { pi, mx, my, sx, sy } relative to the cursor, viewport px
    let lastEval = -1e9;
    let est = { x: view.w / 2, y: view.h / 2, r50: 400 };
    let at = [0, 0];      // the cursor in page px when the mixture was computed
    let textLines = [];   // for the display: the belief is never drawn over text

    function features(now) {
      const w = view.w, h = view.h;
      const [, cx, cy] = hist[hist.length - 1];
      const f = [];
      if (!NET.dropAbs) f.push(cx / w, cy / h);
      let j = hist.length - 1;
      for (const L of LAGS) {
        while (j > 0 && hist[j][0] > now - L) j--;
        f.push((hist[j][1] - cx) / w, (hist[j][2] - cy) / h);
      }
      f.push(Math.log1p(Math.max(0, now - lastMove)) / 8);
      const dc = now - lastClick;
      f.push(Math.log1p(Math.min(dc, 60000)) / 11, dc < 3000 ? (click[0] - cx) / w : 0, dc < 3000 ? (click[1] - cy) / h : 0);
      let k = scrolls.length - 1;
      while (k > 0 && scrolls[k][0] > now - 500) k--;
      const sy = view.y;
      f.push(sy / 3000, (sy - scrolls[k][1]) / 500, Math.log1p(Math.min(now - scrolls[scrolls.length - 1][0], 60000)) / 11);
      f.push(Math.log1p(now - t0) / 11);
      if (NET.noLayout) return f;
      const px = cx + view.x, py = cy + view.y;
      for (let r = 0; r < LR; r++) {
        for (let c = 0; c < LC; c++) {
          const x0 = px + (c - LC / 2) * CELL, y0 = py + (r - LR / 2) * CELL;
          f.push(grid ? grid.cover(x0, y0, x0 + CELL, y0 + CELL) : 0);
        }
      }
      if (!NET.dropView) {
        for (let r = 0; r < VR; r++) {
          for (let c = 0; c < VC; c++) {
            const x0 = view.x + (c * w) / VC, y0 = view.y + (r * h) / VR;
            f.push(grid ? grid.cover(x0, y0, x0 + w / VC, y0 + h / VR) : 0);
          }
        }
      }
      return f;
    }

    function evaluate(now) {
      const o = forward(features(now));
      const K = NET.K;
      const pi = new Float32Array(K), mx = new Float32Array(K), my = new Float32Array(K), sx = new Float32Array(K), sy = new Float32Array(K);
      let m = -Infinity;
      for (let k = 0; k < K; k++) m = Math.max(m, o[k * 5]);
      let z = 0;
      for (let k = 0; k < K; k++) {
        pi[k] = Math.exp(o[k * 5] - m); z += pi[k];
        mx[k] = o[k * 5 + 1] * 1000; my[k] = o[k * 5 + 2] * 1000;
        sx[k] = Math.exp(Math.min(2, Math.max(-5, o[k * 5 + 3]))) * 1000;
        sy[k] = Math.exp(Math.min(2, Math.max(-5, o[k * 5 + 4]))) * 1000;
      }
      for (let k = 0; k < K; k++) pi[k] /= z;
      mix = { pi, mx, my, sx, sy, K };
      // the densest point: start at each component mean, keep the best
      const dens = (x, y) => {
        let s = 0;
        for (let k = 0; k < K; k++) {
          const a = (x - mx[k]) / sx[k], b = (y - my[k]) / sy[k];
          s += (pi[k] / (sx[k] * sy[k])) * Math.exp(-0.5 * (a * a + b * b));
        }
        return s;
      };
      let bx = mx[0], by = my[0], bd = -1;
      for (let k = 0; k < K; k++) { const d = dens(mx[k], my[k]); if (d > bd) { bd = d; bx = mx[k]; by = my[k]; } }
      // the radius around it that holds half the mixture: 512 deterministic samples (fixed normal draws)
      const r = new Float32Array(SAMPLES.length);
      for (let i = 0; i < SAMPLES.length; i++) {
        const [u, n1, n2] = SAMPLES[i];
        let k = 0, acc = pi[0];
        while (u > acc && k < K - 1) acc += pi[++k];
        r[i] = Math.hypot(mx[k] + sx[k] * n1 - bx, my[k] + sy[k] * n2 - by);
      }
      r.sort();
      const [, cx, cy] = hist[hist.length - 1];
      at = [cx + view.x, cy + view.y];
      est = { x: at[0] + bx, y: at[1] + by, r50: r[r.length >> 1] };
    }

    return {
      N: 0, P: { x: [], y: [], w: [] },
      layout(l) {
        view = l.view;
        const lines = l.textLines || [];
        textLines = l.lines || [];
        let dw = view.x + view.w, dh = view.y + view.h;
        for (const b of lines) { dw = Math.max(dw, b.x + b.w); dh = Math.max(dh, b.y + (b.h || 0)); }
        grid = textGrid(lines.map((b) => ({ x: b.x, y: b.h != null ? b.y : b.y - b.ch, w: b.w, h: b.h != null ? b.h : b.ch * 2 })), dw, dh);
      },
      view(v) {
        if (v.y !== view.y) scrolls.push([performance.now(), v.y]);
        view = v;
      },
      move(x, y) {
        const now = performance.now();
        hist.push([now, x, y]);
        if (hist.length > 400) hist.splice(0, hist.length - 300);
        lastMove = now;
      },
      click(x, y) { lastClick = performance.now(); click = [x, y]; },
      intent() {}, onset() {}, saliency() {},
      step(now) {
        if (!NET || !hist.length || now - lastEval < 100) return;
        lastEval = now;
        evaluate(now);
      },
      estimate() { return est; },
      mixture() { return mix; },
      // the mixture's density at a page point, for drawing the belief
      densityAt(x, y) {
        if (!mix) return 0;
        const dx = x - at[0], dy = y - at[1];
        let d = 0;
        for (let k = 0; k < mix.K; k++) {
          const a = (dx - mix.mx[k]) / mix.sx[k], b = (dy - mix.my[k]) / mix.sy[k];
          d += (mix.pi[k] / (mix.sx[k] * mix.sy[k])) * Math.exp(-0.5 * (a * a + b * b));
        }
        return d;
      },
      // points drawn from the mixture with fixed random draws: the belief as a sparse cloud of dots
      // that only moves when the belief does
      samples(n) {
        if (!mix) return [];
        const out = [];
        for (let i = 0; i < Math.min(n, SAMPLES.length); i++) {
          const [u, n1, n2] = SAMPLES[i];
          let k = 0, acc = mix.pi[0];
          while (u > acc && k < mix.K - 1) acc += mix.pi[++k];
          out.push([at[0] + mix.mx[k] + mix.sx[k] * n1, at[1] + mix.my[k] + mix.sy[k] * n2]);
        }
        return out;
      },
      lines: () => textLines,
    };
  };
  self.createGaze.setNet = setNet;
  self.createGaze.parse = parse;

  // fixed draws for the 50% radius, so the stated precision does not flicker between frames
  const SAMPLES = (() => {
    let a = 0x9e3779b9;
    const rnd = () => { a |= 0; a = (a + 0x6d2b79f5) | 0; let t = Math.imul(a ^ (a >>> 15), 1 | a); t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t; return ((t ^ (t >>> 14)) >>> 0) / 4294967296; };
    const out = [];
    for (let i = 0; i < 512; i++) {
      const u1 = 1 - rnd(), u2 = rnd();
      const m = Math.sqrt(-2 * Math.log(u1));
      out.push([rnd(), m * Math.cos(2 * Math.PI * u2), m * Math.sin(2 * Math.PI * u2)]);
    }
    return out;
  })();
})();
