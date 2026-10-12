/* The LED wall.
   One panel of LED cells behind the page. Each render fills a tiny signal buffer, one pixel per
   cell, and the page scales it up with `image-rendering: pixelated` under a round-cell mask.
   The canvas is anchored to the document (not the viewport), so the panel scrolls on the
   compositor with the text and never swims; it covers the viewport plus half a viewport above
   and below, and is re-centred only after a new frame has been committed.
   Runs in a worker on an OffscreenCanvas where available, otherwise on the main thread.

   - Pour (on every field change): the new field spreads from the selected target cell by cell
     along least-cost paths (Dijkstra over the cell grid, smooth noise as uneven ground, the name's
     lit cells as slow ground), so the colour floods around the letters and seeps through them last.
   - Fluid (pointer): a stable-fluids solver (semi-Lagrangian advection, Jacobi pressure projection)
     on a half-resolution grid; the pointer stirs it and the panel's sampling positions ride the
     flow, so the lit cells smear and swirl, then spring back. */
(function (scope) {
  function hash(i, j) {
    let h = (i * 374761393 + j * 668265263) | 0;
    h = Math.imul(h ^ (h >>> 13), 1274126177);
    return ((h ^ (h >>> 16)) >>> 0) / 4294967295;
  }

  function vnoise(x, y) {
    const xi = Math.floor(x), yi = Math.floor(y);
    const xf = x - xi, yf = y - yi;
    const u = xf * xf * (3 - 2 * xf), v = yf * yf * (3 - 2 * yf);
    const a = hash(xi, yi), b = hash(xi + 1, yi), c = hash(xi, yi + 1), d = hash(xi + 1, yi + 1);
    return a + (b - a) * u + (c - a) * v + (a - b - c + d) * u * v;
  }

  /* A cell of a crisp mask is lit when its centre and at least two of its four near samples are
     inside the letter: a lone anti-aliased pixel never lights a cell. Shared with the page. */
  function litAt(m, mx, my, q) {
    const at = (x, y) => {
      x |= 0; y |= 0;
      return x >= 0 && y >= 0 && x < m.w && y < m.h && m.data[y * m.w + x] > 127;
    };
    if (!at(mx, my)) return false;
    let k = 0;
    if (at(mx - q, my)) k++;
    if (at(mx + q, my)) k++;
    if (at(mx, my - q)) k++;
    if (at(mx, my + q)) k++;
    return k >= 2;
  }

  /* ---------- fluid: stable fluids on a coarse grid ---------- */

  function createFluid(w, h) {
    const n = w * h;
    const F = {
      w, h,
      u: new Float32Array(n), v: new Float32Array(n),
      u0: new Float32Array(n), v0: new Float32Array(n),
      p: new Float32Array(n), div: new Float32Array(n),
      dx: new Float32Array(n), dy: new Float32Array(n),
      dx0: new Float32Array(n), dy0: new Float32Array(n),
      // the displacement one step back, so each display frame can show the state between steps
      pdx: new Float32Array(n), pdy: new Float32Array(n),
      acc: 0,
      active: false,
    };
    return F;
  }

  function bilerp(a, w, h, x, y) {
    if (x < 0) x = 0; else if (x > w - 1.001) x = w - 1.001;
    if (y < 0) y = 0; else if (y > h - 1.001) y = h - 1.001;
    const x0 = x | 0, y0 = y | 0;
    const fx = x - x0, fy = y - y0;
    const i = y0 * w + x0;
    return (a[i] * (1 - fx) + a[i + 1] * fx) * (1 - fy) + (a[i + w] * (1 - fx) + a[i + w + 1] * fx) * fy;
  }

  function fluidSplat(F, x, y, fx, fy, rad) {
    const r2 = rad * rad;
    const x0 = Math.max(1, Math.floor(x - rad * 2)), x1 = Math.min(F.w - 2, Math.ceil(x + rad * 2));
    const y0 = Math.max(1, Math.floor(y - rad * 2)), y1 = Math.min(F.h - 2, Math.ceil(y + rad * 2));
    for (let j = y0; j <= y1; j++) {
      for (let i = x0; i <= x1; i++) {
        const g = Math.exp(-((i - x) * (i - x) + (j - y) * (j - y)) / r2);
        const k = j * F.w + i;
        F.u[k] += fx * g;
        F.v[k] += fy * g;
      }
    }
    F.active = true;
  }

  function fluidStep(F, cellPx) {
    const { w, h } = F;
    let { u, v, u0, v0 } = F;
    // advect velocity by itself
    u0.set(u); v0.set(v);
    for (let j = 1; j < h - 1; j++) {
      for (let i = 1; i < w - 1; i++) {
        const k = j * w + i;
        const x = i - u0[k], y = j - v0[k];
        u[k] = bilerp(u0, w, h, x, y);
        v[k] = bilerp(v0, w, h, x, y);
      }
    }
    // project: make the flow divergence-free so it swirls instead of piling up
    const { p, div } = F;
    for (let j = 1; j < h - 1; j++) {
      for (let i = 1; i < w - 1; i++) {
        const k = j * w + i;
        div[k] = -0.5 * (u[k + 1] - u[k - 1] + v[k + w] - v[k - w]);
        p[k] = 0;
      }
    }
    for (let it = 0; it < 18; it++) {
      for (let j = 1; j < h - 1; j++) {
        for (let i = 1; i < w - 1; i++) {
          const k = j * w + i;
          p[k] = (div[k] + p[k - 1] + p[k + 1] + p[k - w] + p[k + w]) * 0.25;
        }
      }
    }
    let energy = 0;
    for (let j = 1; j < h - 1; j++) {
      for (let i = 1; i < w - 1; i++) {
        const k = j * w + i;
        u[k] = (u[k] - 0.5 * (p[k + 1] - p[k - 1])) * 0.982;
        v[k] = (v[k] - 0.5 * (p[k + w] - p[k - w])) * 0.982;
        energy += u[k] * u[k] + v[k] * v[k];
      }
    }
    // advect the displacement map: each cell's sampling position rides the flow, then springs home
    const { dx, dy, dx0, dy0 } = F;
    dx0.set(dx); dy0.set(dy);
    let spread = 0;
    for (let j = 0; j < h; j++) {
      for (let i = 0; i < w; i++) {
        const k = j * w + i;
        const x = i - u[k], y = j - v[k];
        dx[k] = (bilerp(dx0, w, h, x, y) + u[k] * cellPx) * 0.972;
        dy[k] = (bilerp(dy0, w, h, x, y) + v[k] * cellPx) * 0.972;
        spread += Math.abs(dx[k]) + Math.abs(dy[k]);
      }
    }
    F.active = energy > 0.02 || spread > w * h * 0.02;
    if (!F.active) { u.fill(0); v.fill(0); dx.fill(0); dy.fill(0); F.pdx.fill(0); F.pdy.fill(0); F.acc = 0; }
  }

  /* The fluid runs on a fixed 60 Hz clock of real time, whatever the display's refresh rate: each
     display frame advances it by as many whole steps as have elapsed (at most four, so a stalled tab
     never fast-forwards), and draws the state between the last two steps. A 540 Hz display gets 540
     different frames of exactly the motion a 60 Hz display shows. */
  const FLUID_DT = 1000 / 60;
  function fluidAdvance(F, cellPx, dt) {
    F.acc += dt;
    let n = 0;
    while (F.acc >= FLUID_DT && n < 4 && F.active) {
      F.pdx.set(F.dx); F.pdy.set(F.dy);
      fluidStep(F, cellPx);
      F.steps = (F.steps || 0) + 1;
      F.acc -= FLUID_DT;
      n++;
    }
    if (n === 4) F.acc = 0;
    return F.active ? F.acc / FLUID_DT : 0;
  }

  function createWall(schedule, notify, pourer) {
    const S = {
      ctx: null,
      bctx: null,
      canvas: null,
      bloom: null,
      img: null,
      cols: 0,
      rows: 0,
      pitch: 8,
      rowStart: 0,
      wantStart: 0,
      scrollY: 0,
      field: [247, 249, 250],
      ink: [5, 5, 6],
      base: 0.1,
      amp: 0.05,
      glow: 0,
      old: null,
      masks: [],
      lens: null,
      lensPrev: null,
      lensR: 150,
      lock: null,
      reduce: false,
      visible: true,
      prev: null,
      fluid: null,
      flood: null,
      vw: 1440,
      vh: 900,
      lastChange: 0,
      queued: false,
      // poison: pockets the pours enclose but never reach keep their colour for good, per document
      // row (palette index + 1); every pour can leave more
      isl: [],
      cellOld: null,
      fpal: [],
      pal: [],
      keep: [],
      keepFixed: [],
      prepared: null,
    };

    function maskAt(m, x, y) {
      if (m.cells) {
        // the name: an exact set of lit cells on the wall's own grid, cleaned on the page
        const cx = Math.floor(x / S.pitch) - m.c0;
        const cy = Math.floor(y / S.pitch) - m.r0;
        if (cx < 0 || cy < 0 || cx >= m.cols || cy >= m.rows) return 0;
        return m.cells[cy * m.cols + cx] ? m.t : 0;
      }
      const mx = (x - m.x) / m.scale;
      const my = (y - m.y - S.scrollY * (1 - m.depth)) / m.scale;
      if (mx < -2 || my < -2 || mx >= m.w + 2 || my >= m.h + 2) return 0;
      if (m.soft) {
        // a deep plane: coverage averaged over a cell and a half, so its cells come out soft-edged
        const r = (S.pitch * 0.8) / m.scale;
        let n = 0;
        let k = 0;
        for (let dy = -1; dy <= 1; dy++) {
          for (let dx = -1; dx <= 1; dx++) {
            const sx = (mx + dx * r) | 0;
            const sy = (my + dy * r) | 0;
            k++;
            if (sx >= 0 && sy >= 0 && sx < m.w && sy < m.h && m.data[sy * m.w + sx] > 127) n++;
          }
        }
        return (n / k) * m.t;
      }
      return litAt(m, mx, my, S.pitch / 3) ? m.t : 0;
    }

    /* How far the point (x, y) can move, in page px, before cover() there could change. Every mask
       is a grid of on/off pixels (the name: its cells; an image mask: its data > 127), and a lookup
       can only change when a sample crosses into a pixel of the other value. A chessboard distance
       map per mask (built once per masks message) gives, for each pixel, how many pixels away the
       nearest one of the other value is; a sample can then move by that many, less one, plus its
       distance to its own pixel's edge, and still read the same. Within the smallest such margin
       of a cell's samples, cover() is provably unchanged, so a cell the fluid nudges by less shows
       exactly what it shows at rest. */
    const edge = (v) => { const f = v - Math.floor(v); return f < 1 - f ? f : 1 - f; };
    function chess(on, w, h) {
      // distance from each pixel to the nearest pixel of the other value (outside counts as off),
      // in pixels, capped at 255: two chamfer passes over the 8-neighbourhood
      const big = 255;
      const d0 = new Uint8Array(w * h), d1 = new Uint8Array(w * h); // to the nearest off / on pixel
      for (let y = 0, k = 0; y < h; y++) {
        for (let x = 0; x < w; x++, k++) {
          const edgeD = Math.min(x + 1, y + 1, w - x, h - y, big);
          d0[k] = on[k] ? edgeD : 0;
          d1[k] = on[k] ? 0 : big;
        }
      }
      for (const d of [d0, d1]) {
        for (let y = 0; y < h; y++) {
          for (let x = 0; x < w; x++) {
            const k = y * w + x;
            let v = d[k];
            if (!v) continue;
            if (x > 0 && d[k - 1] + 1 < v) v = d[k - 1] + 1;
            if (y > 0) {
              if (d[k - w] + 1 < v) v = d[k - w] + 1;
              if (x > 0 && d[k - w - 1] + 1 < v) v = d[k - w - 1] + 1;
              if (x < w - 1 && d[k - w + 1] + 1 < v) v = d[k - w + 1] + 1;
            }
            d[k] = v;
          }
        }
        for (let y = h - 1; y >= 0; y--) {
          for (let x = w - 1; x >= 0; x--) {
            const k = y * w + x;
            let v = d[k];
            if (!v) continue;
            if (x < w - 1 && d[k + 1] + 1 < v) v = d[k + 1] + 1;
            if (y < h - 1) {
              if (d[k + w] + 1 < v) v = d[k + w] + 1;
              if (x < w - 1 && d[k + w + 1] + 1 < v) v = d[k + w + 1] + 1;
              if (x > 0 && d[k + w - 1] + 1 < v) v = d[k + w - 1] + 1;
            }
            d[k] = v;
          }
        }
      }
      const out = new Uint8Array(w * h);
      for (let k = 0; k < w * h; k++) out[k] = on[k] ? d0[k] : d1[k];
      return out;
    }
    // the margin of one sample at mask pixel coordinates (u, v), in mask pixels; `floor` for the
    // name's cells (maskAt floors), truncation for image masks (litAt and the soft samples use |0,
    // so pixel 0 spans -1..1 there: the edge distance below is then on the small, safe side)
    function sampleMargin(dt, w, h, u, v, floor) {
      const iu = floor ? Math.floor(u) : u | 0, iv = floor ? Math.floor(v) : v | 0;
      if (iu < 0 || iv < 0 || iu >= w || iv >= h) {
        // outside the data: off; it can only change by reaching the data's edge
        const lo = floor ? 0 : -1;
        const ox = u < lo ? lo - u : u >= w ? u - w : 0, oy = v < lo ? lo - v : v >= h ? v - h : 0;
        return Math.max(ox, oy);
      }
      return dt[iv * w + iu] - 1 + Math.min(edge(u), edge(v));
    }
    function maskDT(m) {
      if (m.cells) return chess(m.cells, m.cols, m.rows);
      if (!m.data) return null;
      const on = new Uint8Array(m.w * m.h);
      for (let k = 0; k < on.length; k++) on[k] = m.data[k] > 127 ? 1 : 0;
      return chess(on, m.w, m.h);
    }
    function maskMargin(m, x, y) {
      if (!m.__dt) {
        // with a pour thread the maps are built there (tens of ms for the deep echo, never on the
        // drawing thread); without one, here, once per masks message
        if (pourer) return 0;
        m.__dt = maskDT(m);
        if (!m.__dt) return 0;
      }
      if (m.cells) return sampleMargin(m.__dt, m.cols, m.rows, x / S.pitch - m.c0, y / S.pitch - m.r0, true) * S.pitch;
      const sc = m.scale;
      const mx = (x - m.x) / sc;
      const my = (y - m.y - S.scrollY * (1 - m.depth)) / sc;
      if (!(Number.isFinite(mx) && Number.isFinite(my))) return 0;
      // the bounds test maskAt does before sampling
      let g = Math.min(Math.abs(mx + 2), Math.abs(m.w + 2 - mx), Math.abs(my + 2), Math.abs(m.h + 2 - my));
      if (mx < -2 || my < -2 || mx >= m.w + 2 || my >= m.h + 2) return g * sc;
      // every sample lies within Rs pixels (by index) of the centre's pixel; when the nearest pixel
      // of the other value is further than that from the centre, every sample reads the centre's
      // value and stays within (centre distance - Rs) of the change: one lookup instead of nine
      const reach = m.soft ? (S.pitch * 0.8) / sc : S.pitch / 3;
      const Rs = Math.ceil(reach) + 1;
      const cu = mx | 0, cv = my | 0;
      if (cu >= 0 && cv >= 0 && cu < m.w && cv < m.h) {
        const Dc = m.__dt[cv * m.w + cu];
        if (Dc > Rs) return Math.max(0, Math.min(g, Dc - Rs - 1)) * sc;
      }
      if (m.soft) {
        const r = (S.pitch * 0.8) / sc;
        for (let dy = -1; dy <= 1; dy++) {
          for (let dx = -1; dx <= 1; dx++) g = Math.min(g, sampleMargin(m.__dt, m.w, m.h, mx + dx * r, my + dy * r, false));
        }
      } else {
        const q = S.pitch / 3;
        for (const [ux, uy] of [[0, 0], [-q, 0], [q, 0], [0, -q], [0, q]]) g = Math.min(g, sampleMargin(m.__dt, m.w, m.h, mx + ux, my + uy, false));
      }
      return Math.max(0, g) * sc;
    }
    function margin(x, y) {
      let g = Infinity;
      for (let k = 0; k < S.masks.length; k++) g = Math.min(g, maskMargin(S.masks[k], x, y));
      // a hair less, so floating-point rounding at the edge can never decide it
      return Math.max(0, g - 1e-6);
    }

    // poison never settles where text sits, so the page stays readable however long it is played
    function underText(x, y) {
      for (const k of S.keep) {
        if (x > k.x && x < k.x + k.w && y > k.y && y < k.y + k.h) return true;
      }
      // the rail is fixed to the viewport, so it is checked in viewport coordinates
      const vy = y - S.scrollY;
      for (const k of S.keepFixed) {
        if (x > k.x && x < k.x + k.w && vy > k.y && vy < k.y + k.h) return true;
      }
      return false;
    }

    function cover(x, y) {
      let t = 0;
      for (let k = 0; k < S.masks.length; k++) {
        const v = maskAt(S.masks[k], x, y);
        if (v > t) t = v;
      }
      return t;
    }

    function resize(m) {
      if (m.pitch !== S.pitch || m.cols !== S.cols) { S.isl = []; S.pal = []; }
      S.cols = m.cols;
      S.rows = m.rows;
      S.pitch = m.pitch;
      if (!S.ctx) return; // the pour thread draws nothing
      for (const c of [S.canvas, S.bloom, S.gapsCanvas]) {
        if (!c) continue;
        c.width = S.cols;
        c.height = S.rows;
      }
      S.img = S.ctx.createImageData(S.cols, S.rows);
      S.gimg = S.ctx.createImageData(S.cols, S.rows);
      S.bimg = S.ctx.createImageData(S.cols, S.rows);
      S.glowCell = new Uint8Array(S.cols * S.rows);
      S.glowCount = 0;
      S.resizeEpoch = (S.resizeEpoch || 0) + 1;
      S.prev = new Float32Array(S.cols * S.rows * 3);
      S.cellOld = new Uint8Array(S.cols * S.rows);
      S.fpal = [];
      S.flood = null;
      S.fluid = createFluid(Math.ceil(S.cols / 2) + 2, Math.ceil(S.rows / 2) + 2);
      S.flood = null;
    }

    /* ---------- fluid: the pointer stirs the panel ---------- */

    function stir(lens) {
      const F = S.fluid;
      const p = S.lensPrev;
      S.lensPrev = lens;
      if (!F || !lens || !p) return;
      const cp = S.pitch * 2;
      const mx = lens.x - p.x;
      const my = lens.y - p.y;
      if (Math.abs(mx) + Math.abs(my) < 1) return;
      const x = lens.x / cp;
      const y = (lens.y + S.scrollY) / cp - S.rowStart / 2;
      fluidSplat(F, x, y, (mx / cp) * 0.35, (my / cp) * 0.35, 3.5);
    }

    /* ---------- flood: the old field drains along least-cost paths from the target ---------- */

    const keyOf = (b) => `${Math.round(b.x)},${Math.round(b.y)},${Math.round(b.w)},${Math.round(b.h)},${S.rowStart},${S.cols}`;

    function startFlood(now, texts) {
      const lk = S.lock;
      if (!lk || !S.old) return;
      // the pointer's heading usually predicted this target already, so the map is ready; if not,
      // the pour thread computes it (the frames keep coming meanwhile) and the flood starts when it
      // answers, a frame or two later, with every cell still showing its old colour until then
      let ready = S.prepared && S.prepared.key === keyOf(lk) ? S.prepared : null;
      if (!ready && pourer) {
        S.pending = { key: keyOf(lk), texts, msg: S.pendingMsg };
        pourer({ type: "pourJob", lock: lk });
        return;
      }
      if (!ready) ready = timed("pour, inline", () => computePour(lk));
      S.prepared = null;
      if (!ready) return;
      if (ready.islands.length) {
        S.pal.push(S.old);
        const id = S.pal.length;
        for (const k of ready.islands) {
          const row = ((k / S.cols) | 0) + ready.rowStart;
          const c = k % S.cols;
          const rr = S.isl[row] || (S.isl[row] = new Uint16Array(S.cols));
          if (!rr[c]) rr[c] = id;
        }
      }
      let rank = ready.rank;
      if (texts && texts.length) {
        // every block of text turns as one unit: the cells under it take the arrival time of its
        // centre, so text and the ground behind it always change together and stay readable
        rank = rank.slice();
        for (const t of texts) {
          const c0 = Math.max(0, Math.floor(t.x / S.pitch)), c1 = Math.min(S.cols - 1, Math.floor((t.x + t.w) / S.pitch));
          const r0 = Math.max(0, Math.floor(t.y / S.pitch) - S.rowStart), r1 = Math.min(S.rows - 1, Math.floor((t.y + t.h) / S.pitch) - S.rowStart);
          if (c1 < c0 || r1 < r0) continue;
          const cc = Math.min(S.cols - 1, Math.max(0, Math.floor((t.x + t.w / 2) / S.pitch)));
          const rc = Math.min(S.rows - 1, Math.max(0, Math.floor((t.y + t.h / 2) / S.pitch) - S.rowStart));
          const v = ready.rank[rc * S.cols + cc];
          for (let r = r0; r <= r1; r++) rank.fill(v, r * S.cols + c0, r * S.cols + c1 + 1);
        }
      }
      S.flood = { dist: rank, max: 1, at: now, ms: 1100, old: S.old, seed: ready.seed };
    }

    /* The pour, in three passes.
       1. Routing: arrival time over the cell grid by Dijkstra (8 neighbours) on uneven ground
          (two octaves of value noise, fresh seed per pour); the name's lit cells are slow ground,
          so the colour routes around the letters.
       2. Enclosure: the latest time each cell is still connected to the panel's edge through cells
          the pour has not reached (a widest-path pass from the border). A cell enclosed before the
          pour reaches it sits in a pocket.
       3. Pockets: small ones (up to POCKET cells, off the name and text) are never reached: they keep
          the old colour for good, the poison. Bigger ones flood inward from their rim the moment
          they close, so nothing is left to turn after the pour ends. */
    const POCKET = 70;
    const POISON = false;

    function heapOps(less, cap) {
      let key = new Float64Array(cap);
      let item = new Int32Array(cap);
      let n = 0;
      return {
        get size() { return n; },
        top: 0,
        topKey: 0,
        push(k, d) {
          if (n === key.length) {
            const nk = new Float64Array(n * 2); nk.set(key); key = nk;
            const ni = new Int32Array(n * 2); ni.set(item); item = ni;
          }
          let i = n++;
          while (i > 0) {
            const p = (i - 1) >> 1;
            if (!less(d, key[p])) break;
            key[i] = key[p]; item[i] = item[p];
            i = p;
          }
          key[i] = d; item[i] = k;
        },
        pop() {
          this.top = item[0];
          this.topKey = key[0];
          n--;
          if (n > 0) {
            const d = key[n], k = item[n];
            let i = 0;
            for (;;) {
              const l = i * 2 + 1, r = l + 1;
              let m = i, md = d;
              if (l < n && less(key[l], md)) { m = l; md = key[l]; }
              if (r < n && less(key[r], md)) { m = r; md = key[r]; }
              if (m === i) break;
              key[i] = key[m]; item[i] = item[m];
              i = m;
            }
            key[i] = d; item[i] = k;
          }
        },
      };
    }

    // a margin around the name, where the destination caption is printed
    function nearName(x, y) {
      const m = S.masks.find((q) => q.cells);
      if (!m) return false;
      const x0 = m.c0 * S.pitch - 24, x1 = (m.c0 + m.cols) * S.pitch + 24;
      const y0 = m.r0 * S.pitch - 24, y1 = (m.r0 + m.rows) * S.pitch + 56;
      return x > x0 && x < x1 && y > y0 && y < y1;
    }

    function computePour(lk) {
      const { cols, rows, pitch } = S;
      const n = cols * rows;
      const name = S.masks.find((m) => m.cells);
      const slow = new Uint8Array(n);
      if (name) {
        for (let r = 0; r < rows; r++) {
          const cy = r + S.rowStart - name.r0;
          if (cy < 0 || cy >= name.rows) continue;
          for (let c = 0; c < cols; c++) {
            const cx = c - name.c0;
            if (cx >= 0 && cx < name.cols && name.cells[cy * name.cols + cx]) slow[r * cols + c] = 1;
          }
        }
      }
      const fl0 = Math.random() * 100; // a different pour every time

      // 1. routing: Dijkstra with a bucket queue (Dial's algorithm). Costs are quantised to 1/32
      //    of a cell, so every edge weight is a small integer and the queue is a ring of buckets:
      //    linear time, no heap, no per-push allocation.
      const Q = 32;
      const cs = new Uint16Array(n); // straight step cost into each cell
      const cd = new Uint16Array(n); // diagonal step cost into each cell
      let maxW = 1;
      for (let r = 0; r < rows; r++) {
        const row = r + S.rowStart;
        for (let c = 0; c < cols; c++) {
          const g = vnoise(c * 0.1 + fl0, row * 0.1) * 0.85 + vnoise(c * 0.25, row * 0.25 + fl0) * 0.15;
          const k = r * cols + c;
          const f = (0.35 + 2.2 * g * g) * (slow[k] ? 3 : 1);
          cs[k] = Math.max(1, Math.round(f * Q));
          cd[k] = Math.max(1, Math.round(f * Q * 1.41421356));
          if (cd[k] > maxW) maxW = cd[k];
        }
      }
      const INF = 0x7fffffff;
      const Ti = new Int32Array(n).fill(INF);
      const B = maxW + 1;
      const head = new Int32Array(B).fill(-1);
      let cap = n * 4;
      let entNode = new Int32Array(cap), entNext = new Int32Array(cap);
      let used = 0, queued = 0;
      const push = (k, d) => {
        if (used === cap) {
          cap *= 2;
          const a = new Int32Array(cap); a.set(entNode); entNode = a;
          const b = new Int32Array(cap); b.set(entNext); entNext = b;
        }
        const b = d % B;
        entNode[used] = k;
        entNext[used] = head[b];
        head[b] = used++;
        queued++;
      };
      const c0 = Math.max(0, Math.floor(lk.x / pitch)), c1 = Math.min(cols - 1, Math.floor((lk.x + lk.w) / pitch));
      const r0 = Math.max(0, Math.floor(lk.y / pitch) - S.rowStart), r1 = Math.min(rows - 1, Math.floor((lk.y + lk.h) / pitch) - S.rowStart);
      for (let r = r0; r <= r1; r++) {
        for (let c = c0; c <= c1; c++) {
          Ti[r * cols + c] = 0;
          push(r * cols + c, 0);
        }
      }
      if (!queued) return null;
      for (let d = 0; queued > 0; d++) {
        const b = d % B;
        let e = head[b];
        head[b] = -1;
        while (e !== -1) {
          const k = entNode[e];
          const next = entNext[e];
          queued--;
          if (Ti[k] === d) {
            const c = k % cols;
            const r = (k - c) / cols;
            const up = r > 0, dn = r < rows - 1, lf = c > 0, rt = c < cols - 1;
            let kk, nd;
            if (lf) { kk = k - 1; nd = d + cs[kk]; if (nd < Ti[kk]) { Ti[kk] = nd; push(kk, nd); } }
            if (rt) { kk = k + 1; nd = d + cs[kk]; if (nd < Ti[kk]) { Ti[kk] = nd; push(kk, nd); } }
            if (up) {
              kk = k - cols; nd = d + cs[kk]; if (nd < Ti[kk]) { Ti[kk] = nd; push(kk, nd); }
              if (lf) { kk = k - cols - 1; nd = d + cd[kk]; if (nd < Ti[kk]) { Ti[kk] = nd; push(kk, nd); } }
              if (rt) { kk = k - cols + 1; nd = d + cd[kk]; if (nd < Ti[kk]) { Ti[kk] = nd; push(kk, nd); } }
            }
            if (dn) {
              kk = k + cols; nd = d + cs[kk]; if (nd < Ti[kk]) { Ti[kk] = nd; push(kk, nd); }
              if (lf) { kk = k + cols - 1; nd = d + cd[kk]; if (nd < Ti[kk]) { Ti[kk] = nd; push(kk, nd); } }
              if (rt) { kk = k + cols + 1; nd = d + cd[kk]; if (nd < Ti[kk]) { Ti[kk] = nd; push(kk, nd); } }
            }
          }
          e = next;
        }
      }
      let maxT = 0;
      const T = new Float32Array(n);
      for (let k = 0; k < n; k++) { T[k] = Ti[k] / Q; if (Ti[k] > maxT) maxT = Ti[k]; }

      // 2. enclosure: widest path to the border (4 neighbours, so diagonal gaps count as closed),
      //    also with a bucket queue, popped from the highest bucket down
      const Ei = new Int32Array(n).fill(-1);
      const bh = new Int32Array(maxT + 1).fill(-1);
      used = 0;
      const push2 = (k, v) => {
        if (used === cap) {
          cap *= 2;
          const a = new Int32Array(cap); a.set(entNode); entNode = a;
          const b = new Int32Array(cap); b.set(entNext); entNext = b;
        }
        entNode[used] = k;
        entNext[used] = bh[v];
        bh[v] = used++;
      };
      for (let k = 0; k < n; k++) {
        const c = k % cols;
        const r = (k - c) / cols;
        if (c === 0 || r === 0 || c === cols - 1 || r === rows - 1) {
          Ei[k] = Ti[k];
          push2(k, Ti[k]);
        }
      }
      for (let v = maxT; v >= 0; v--) {
        let e = bh[v];
        bh[v] = -1;
        while (e !== -1) {
          const k = entNode[e];
          const next = entNext[e];
          if (Ei[k] === v) {
            const c = k % cols;
            const r = (k - c) / cols;
            const nbs = [c > 0 ? k - 1 : -1, c < cols - 1 ? k + 1 : -1, r > 0 ? k - cols : -1, r < rows - 1 ? k + cols : -1];
            for (let q = 0; q < 4; q++) {
              const kk = nbs[q];
              if (kk < 0) continue;
              const cand = v < Ti[kk] ? v : Ti[kk];
              if (cand > Ei[kk]) {
                Ei[kk] = cand;
                push2(kk, cand);
              }
            }
          }
          e = next;
          if (e === -1 && bh[v] !== -1) { e = bh[v]; bh[v] = -1; }
        }
      }
      const E = new Float32Array(n);
      for (let k = 0; k < n; k++) E[k] = Ei[k] / Q;
      const nb4 = [[1, 0], [-1, 0], [0, 1], [0, -1]];

      // 3. pockets
      const enclosed = new Uint8Array(n);
      for (let k = 0; k < n; k++) if (E[k] < T[k] - 0.5) enclosed[k] = 1;
      const comp = new Int32Array(n).fill(-1);
      const pos = new Int32Array(n).fill(-1);
      const island = new Uint8Array(n);
      const islands = [];
      const out = new Float32Array(T);
      for (let s0 = 0; s0 < n; s0++) {
        if (!enclosed[s0] || comp[s0] >= 0) continue;
        const cells = [s0];
        comp[s0] = s0;
        for (let q = 0; q < cells.length; q++) {
          const k = cells[q];
          const c = k % cols;
          const r = (k / cols) | 0;
          for (const [ox, oy] of nb4) {
            const cc = c + ox, rr = r + oy;
            if (cc < 0 || rr < 0 || cc >= cols || rr >= rows) continue;
            const kk = rr * cols + cc;
            if (enclosed[kk] && comp[kk] < 0) {
              comp[kk] = s0;
              cells.push(kk);
            }
          }
        }
        // poison is off (user, 2026-10-12): every pocket floods in from its rim
        if (POISON && cells.length >= 3 && cells.length <= POCKET && hash(s0, fl0 * 1000) < 0.3) {
          for (const k of cells) {
            const x = (k % cols) * pitch + pitch / 2;
            const y = (((k / cols) | 0) + S.rowStart) * pitch + pitch / 2;
            if (!slow[k] && !underText(x, y) && !nearName(x, y)) {
              island[k] = 1;
              islands.push(k);
            }
          }
        }
        // whatever is not poison floods inward from the rim as soon as the pocket closes
        const layer = new Int32Array(cells.length).fill(-1);
        const idx = { get: (k) => { const v = pos[k]; return v >= 0 && comp[k] === s0 ? v : undefined; } };
        cells.forEach((k, i) => { pos[k] = i; });
        const queue = [];
        cells.forEach((k, i) => {
          if (island[k]) return;
          const c = k % cols;
          const r = (k / cols) | 0;
          for (const [ox, oy] of nb4) {
            const cc = c + ox, rr = r + oy;
            if (cc < 0 || rr < 0 || cc >= cols || rr >= rows) continue;
            const kk = rr * cols + cc;
            if (!enclosed[kk] || island[kk]) {
              layer[i] = 0;
              queue.push(i);
              break;
            }
          }
        });
        for (let q = 0; q < queue.length; q++) {
          const i = queue[q];
          const k = cells[i];
          const c = k % cols;
          const r = (k / cols) | 0;
          for (const [ox, oy] of nb4) {
            const cc = c + ox, rr = r + oy;
            if (cc < 0 || rr < 0 || cc >= cols || rr >= rows) continue;
            const kk = rr * cols + cc;
            const j = idx.get(kk);
            if (j === undefined || layer[j] >= 0 || island[kk]) continue;
            layer[j] = layer[i] + 1;
            queue.push(j);
          }
        }
        cells.forEach((k, i) => {
          if (island[k]) return;
          out[k] = Math.min(T[k], E[k] + Math.max(0, layer[i]) * 0.9);
        });
      }

      // time the pour by area, not distance: the front covers an even share of the panel every
      // frame; poison cells are never reached
      // exact fill order: each cell's arrival time and index packed into one double, sorted
      // natively (typed-array sort, a few ms); ties keep a stable order instead of a raster sweep
      let m = 0;
      for (let k = 0; k < n; k++) if (!island[k]) m++;
      const packed = new Float64Array(m);
      let j = 0;
      for (let k = 0; k < n; k++) {
        if (island[k]) continue;
        const t = Number.isFinite(out[k]) ? out[k] : 1e6;
        packed[j++] = Math.round(t * 1024) * n + k;
      }
      packed.sort();
      const rank = new Float32Array(n).fill(2);
      for (let i = 0; i < m; i++) rank[packed[i] % n] = i / m;
      return { key: keyOf(lk), rank, seed: fl0, islands, rowStart: S.rowStart };
    }

    /* Move a row-major grid up or down by dr rows. Rows that come into view are filled with
       `fill`, or with a copy of the nearest edge row when fill is -1 (a pour's arrival times). */
    function shiftRows(a, w, h, dr, fill) {
      if (!dr) return;
      if (Math.abs(dr) >= h) {
        if (fill === -1) return;
        a.fill(fill);
        return;
      }
      if (dr > 0) {
        a.copyWithin(0, dr * w, h * w);
        for (let r = h - dr; r < h; r++) {
          if (fill === -1) a.copyWithin(r * w, (h - dr - 1) * w, (h - dr) * w);
          else a.fill(fill, r * w, (r + 1) * w);
        }
      } else {
        const k = -dr;
        a.copyWithin(k * w, 0, (h - k) * w);
        for (let r = 0; r < k; r++) {
          if (fill === -1) a.copyWithin(r * w, k * w, (k + 1) * w);
          else a.fill(fill, r * w, (r + 1) * w);
        }
      }
    }

    function render(now) {
      if (!S.img) return;
      const { cols, rows, pitch, field, ink } = S;
      // the frame shows rows from wantStart; the page moves the canvas there once it is committed
      if (S.wantStart !== S.rowStart) {
        // the panel re-centred on the reader: carry everything in flight across by the same
        // number of rows, so a pour, the trails and the fluid continue instead of snapping
        const dr = S.wantStart - S.rowStart;
        S.rowStart = S.wantStart;
        shiftRows(S.prev, cols * 3, rows, dr, 0);
        if (S.flood) {
          // rows that scroll into view continue the pour outward from the edge row, with the same
          // uneven ground, instead of copying the edge (which would draw vertical stripes)
          const fd = S.flood.dist;
          shiftRows(fd, cols, rows, dr, 0);
          const n = Math.min(Math.abs(dr), rows);
          if (n < rows) {
            // the edge row, smoothed across 13 columns so no single column leads
            const er = dr > 0 ? rows - n - 1 : n;
            const edge = new Float32Array(cols);
            for (let c = 0; c < cols; c++) {
              let sum = 0, k = 0;
              for (let q = Math.max(0, c - 6); q <= Math.min(cols - 1, c + 6); q++) { sum += Math.min(1, fd[er * cols + q]); k++; }
              edge[c] = sum / k;
            }
            for (let k = 0; k < n; k++) {
              const r = dr > 0 ? rows - n + k : n - 1 - k;
              const away = k + 1;
              const row = r + S.rowStart;
              for (let c = 0; c < cols; c++) {
                const g = vnoise(c * 0.12 + S.flood.seed, row * 0.12);
                fd[r * cols + c] = Math.min(1.5, edge[c] + away * 0.006 + (g - 0.5) * 0.08);
              }
            }
          }
        }
        shiftRows(S.cellOld, cols, rows, dr, -1);
        if (S.prepared) S.prepared = null;
        if (S.fluid) {
          const F = S.fluid;
          const fr = Math.round(dr / 2);
          for (const a of [F.u, F.v, F.dx, F.dy, F.u0, F.v0, F.dx0, F.dy0]) shiftRows(a, F.w, F.h, fr, 0);
        }
      }
      if (S.kRow !== S.rowStart || !S.kGrain || S.kGrain.length !== cols * rows) {
        S.kGrain = new Float32Array(cols * rows);
        S.kLv = new Float32Array(cols * rows);
        for (let r = 0, i = 0; r < rows; r++) {
          const row = r + S.rowStart;
          for (let c = 0; c < cols; c++, i++) {
            S.kGrain[i] = hash(c, row);
            S.kLv[i] = 0.88 + 0.12 * hash(row, c);
          }
        }
        S.kRow = S.rowStart;
        S.kCovKey = null;
      }
      /* Which rows this frame draws: the ones on screen, half a screen above and below (so a scroll
         never reveals an undrawn row), and a rotating eighth of the rest, so nothing off screen is more
         than eight frames old. Everything a cell shows is a function of time, so a row drawn late is
         exactly what it would have been. */
      const vr0 = Math.floor(S.scrollY / pitch) - S.rowStart;
      const vrn = Math.ceil((S.vh || 900) / pitch);
      const on0 = Math.max(0, vr0 - (vrn >> 1)), on1 = Math.min(rows, vr0 + vrn + (vrn >> 1) + 1);
      const sweep = Math.max(1, Math.ceil(rows / 8));
      S.sweepAt = ((S.sweepAt || 0) + sweep) % rows;
      const sw0 = S.sweepAt, sw1 = S.sweepAt + sweep;
      const rowOn = (r) => (r >= on0 && r < on1) || (r >= sw0 && r < sw1) || (r + rows >= sw0 && r + rows < sw1);
      // coverage at rest depends on the masks, the rows shown and (for the deep echo) the scroll; each
      // row is recomputed only when it is drawn and its key has changed
      const covKey = `${S.rowStart}|${S.scrollY}|${S.masksRev}`;
      if (!S.kCov || S.kCov.length !== cols * rows) {
        S.kCov = new Float32Array(cols * rows);
        S.kCov64 = new Float64Array(cols * rows);
        S.kSafe = new Float64Array(cols * rows);
        S.rowMinSafe = new Float64Array(rows);
        S.rowDiff32 = new Int32Array(rows);
        S.kSafeRow = new Array(rows).fill(null);
        S.kCovRow = new Array(rows).fill(null);
      }
      const covNew = S.covNew && S.covNew.length === rows ? S.covNew : (S.covNew = new Uint8Array(rows));
      covNew.fill(0);
      const tbk = S.debug ? (S.tb = { cov: 0, safe: 0, disp: 0, cells: 0, full: 0, why: [0, 0, 0, 0, 0, 0], gs: '' }) : null;
      const tc0 = tbk ? performance.now() : 0;
      for (let r = 0; r < rows; r++) {
        if (S.kCovRow[r] === covKey || !rowOn(r)) continue;
        const y = (r + S.rowStart) * pitch + pitch / 2;
        let diff = 0;
        for (let c = 0, i = r * cols; c < cols; c++, i++) {
          const v = cover(c * pitch + pitch / 2, y);
          S.kCov[i] = v;
          S.kCov64[i] = v;
          if (S.kCov[i] !== v) diff++;
        }
        S.rowDiff32[r] = diff;
        S.kCovRow[r] = covKey;
        covNew[r] = 1;
      }
      if (tbk) tbk.cov = performance.now() - tc0;
      const d = S.img.data;
      const gd = S.gimg.data;
      const lens = S.lens;
      const R = S.lensR;
      const F = S.fluid && S.fluid.active ? S.fluid : null;
      const cp = pitch * 2;
      const fl = S.flood;
      const front = fl ? Math.min(1, (now - fl.at) / fl.ms) : 0;
      // the wake is a band that travels with the front and shrinks to nothing as the pour ends,
      // so when the last cell turns, nothing is left to change
      const WAKE = 0.035;
      const wakeLevel = fl ? 0.7 * Math.min(1, (1 - front) / 0.12) : 0;
      // afterglow fades by 0.075 per 60 Hz frame, whatever the display's rate: per millisecond here
      const decay = 0.075 * Math.min(6, S.frameDt / FLUID_DT);
      const fa = S.fluidAlpha;
      const lk = S.lock;
      const fr = field[0], fg = field[1], fb = field[2];
      const dr = ink[0] - fr, dg = ink[1] - fg, db = ink[2] - fb;

      /* Only what can have changed is computed. A cell's colour is a function of the field and
         palettes, the shape coverage under it, the lock box, the lens, the fluid's displacement, the
         pour's front and its own afterglow. A row is recomputed in full when anything global changed
         since it was last drawn; otherwise only its cells that the lock box, the lens, the fluid
         (moving them past their margin), the pour's front band or a fading afterglow touch now or
         touched then. The rest keep their pixels, which are exactly what recomputing them would
         give: tools/render_equiv.mjs replays recorded sessions through this and through the full
         computation and compares every frame byte for byte. */
      const n = cols * rows;
      if (!S.rowG || S.rowG.length !== rows || !S.fadeCell || S.fadeCell.length !== n) {
        S.rowG = new Array(rows).fill(null);
        S.rowFront = new Float64Array(rows);
        S.rowLensX = new Float64Array(rows); S.rowLensY = new Float64Array(rows); S.rowLensOn = new Uint8Array(rows);
        S.rowLock = new Array(rows).fill(null);
        S.rowLockBox = new Array(rows).fill(null);
        S.rowFade = new Int32Array(rows);
        S.rowUsed = new Int32Array(rows);
        S.rowFOn = new Uint8Array(rows);
        S.rowFl = new Array(rows).fill(null);
        S.rowReset = new Uint8Array(rows);
        S.fadeCell = new Uint8Array(n);
        S.usedCell = new Uint8Array(n);
      }
      /* What makes a row redraw in full: a resize, a shift of the panel's rows, a plain cut (every
         cell turns at once) or the palette list resetting. A pour starting is not one: a cell it
         has not reached keeps showing its old field, which is the field it was drawn in, and a
         settled afterglow gives the same value from a reset as before it; so only the cells the
         front reaches, and the ones that were still fading, change. Likewise when a pour ends or is
         interrupted: only the cells its front had not yet passed when the row was last drawn. */
      const gsig = `${S.rowStart}|${cols}x${rows}|${pitch}|${S.pal.length}|${S.isl.length}|${S.cutEpoch || 0}|${S.resizeEpoch || 0}`;
      const lsig = lk ? `${lk.x},${lk.y},${lk.w},${lk.h}` : "";
      const lensX = lens ? lens.x : 0, lensY = lens ? lens.y + S.scrollY : 0; // the lens in page coordinates
      // the fluid's displacement per cell, once per fluid step instead of every display frame: the
      // two states each frame blends between, and the largest movement either allows
      const dKey = F ? `${F.steps || 0}|${S.rowStart}` : null;
      if (F && S.fRowKey !== dKey) {
        if (!S.fRowMax || S.fRowMax.length !== F.h) S.fRowMax = new Float64Array(F.h);
        if (!S.fMax || S.fMax.length !== F.w * F.h) S.fMax = new Float64Array(F.w * F.h);
        for (let j = 0; j < F.h; j++) {
          let m = 0;
          for (let k = j * F.w, e = k + F.w; k < e; k++) {
            const a = Math.abs(F.dx[k]), b = Math.abs(F.dy[k]), c = Math.abs(F.pdx[k]), q = Math.abs(F.pdy[k]);
            let g = a > b ? a : b;
            if (c > g) g = c;
            if (q > g) g = q;
            S.fMax[k] = g;
            if (g > m) m = g;
          }
          S.fRowMax[j] = m;
        }
        S.fRowKey = dKey;
      }
      /* A cell's displacement blends four corners of the fluid grid (bilerp), so it can be no larger
         than the largest of them: fMax holds that per grid point, once per fluid step, and a cell's
         bound is four lookups (indexed exactly as bilerp indexes). The exact displacement, four
         interpolations, is computed only for the cells that are drawn. */
      const cellBound = (docX, y0) => {
        let fx = docX / cp;
        if (fx < 0) fx = 0; else if (fx > F.w - 1.001) fx = F.w - 1.001;
        const k = y0 * F.w + (fx | 0);
        const fm = S.fMax;
        let g = fm[k];
        if (fm[k + 1] > g) g = fm[k + 1];
        if (fm[k + F.w] > g) g = fm[k + F.w];
        if (fm[k + F.w + 1] > g) g = fm[k + F.w + 1];
        return g;
      };
      // the bound for a row of cells: the two fluid rows its samples read (clamped as bilerp clamps)
      const fluidBound = (docY) => {
        let fy = docY / cp - S.rowStart / 2;
        if (fy < 0) fy = 0; else if (fy > F.h - 1.001) fy = F.h - 1.001;
        const y0 = fy | 0;
        const a = S.fRowMax[y0], b = S.fRowMax[y0 + 1];
        return a > b ? a : b;
      };
      // the pour's arrival times per row, smallest and largest, so a row the front is not crossing
      // is passed over at once
      if (fl && (S.flRowsFor !== fl || S.flRowsStart !== S.rowStart || !S.rowDMin || S.rowDMin.length !== rows)) {
        if (!S.rowDMin || S.rowDMin.length !== rows) { S.rowDMin = new Float64Array(rows); S.rowDMaxF = new Float64Array(rows); }
        for (let r = 0; r < rows; r++) {
          let lo = Infinity, hi = -Infinity;
          for (let k = r * cols, e = k + cols; k < e; k++) { const v = fl.dist[k]; if (v < lo) lo = v; if (v > hi) hi = v; }
          S.rowDMin[r] = lo; S.rowDMaxF[r] = hi;
        }
        S.flRowsFor = fl; S.flRowsStart = S.rowStart;
      }
      // the margins (how far the fluid may move each cell before it can look different): only
      // while the fluid moves, recomputed when the cover or the distance maps change, at most about
      // a millisecond per frame, rows on screen first
      const sk = `${covKey}|${S.safeRev || 0}`;
      // rows on screen first, then the rest of the rows drawn this frame
      const mOrder = [];
      for (let r = Math.max(0, vr0); r < Math.min(rows, vr0 + vrn); r++) mOrder.push(r);
      for (let r = 0; r < rows; r++) if (rowOn(r) && !(r >= vr0 && r < vr0 + vrn)) mOrder.push(r);
      if (F) {
        const ts0 = performance.now();
        marginRows(mOrder, sk, ts0 + MARGIN_MS);
        if (tbk) tbk.safe = performance.now() - ts0;
      }
      // and whatever is left, in idle moments, so the first stir finds them ready
      S.mJob = { order: mOrder, sk };
      if (!S.mTimer) S.mTimer = setTimeout(marginIdle, 0);
      const inBox = (b, x, y) => b !== null && x > b.x && x < b.x + b.w && y > b.y && y < b.y + b.h;
      let i = 0;
      let dirty0 = rows, dirty1 = -1;
      let band0 = rows, band1 = -1;
      for (let r = 0; r < rows; r++) {
        if (!rowOn(r)) { i += cols; continue; }
        if (r < band0) band0 = r;
        band1 = r;
        const row = r + S.rowStart;
        const docY = row * pitch + pitch / 2;
        const vy = docY - S.scrollY;
        const full = S.rowG[r] !== gsig || covNew[r] === 1;
        if (tbk && full) { tbk.full++; if (S.rowG[r] !== gsig) tbk.gs = `${S.rowG[r]} -> ${gsig}`; }
        const lockOld = S.rowLockBox[r];
        const lensOnOld = S.rowLensOn[r], lensXOld = S.rowLensX[r], lensYOld = S.rowLensY[r];
        const frontOld = S.rowFront[r];
        const flOld = S.rowFl[r];
        // a different pour than when this row was last drawn (one started, ended or was interrupted)
        const flSwap = flOld !== fl;
        const resetRow = S.rowReset[r] === 1;
        S.rowReset[r] = 0;
        const safeOk = F !== null && S.kSafeRow[r] === sk;
        const fOn = F ? 1 : 0;
        const chk32 = S.rowFOn[r] !== fOn && S.rowDiff32[r] > 0;
        let chkLock = false, chkLens = false, chkFluid = false, chkFlood = false;
        if (!full) {
          if (S.rowLock[r] !== lsig) {
            chkLock = (lk !== null && docY > lk.y && docY < lk.y + lk.h) || (lockOld !== null && docY > lockOld.y && docY < lockOld.y + lockOld.h);
          }
          if (lens && Math.abs(docY - lensY) < R + pitch) chkLens = true;
          if (lensOnOld && Math.abs(docY - lensYOld) < R + pitch) chkLens = true;
          if (S.rowUsed[r] > 0) chkFluid = true;
          // the fluid can only change cells it moves past their margin
          if (F && (!safeOk || !(fluidBound(docY) < S.rowMinSafe[r]))) chkFluid = true;
          if (fl && !flSwap && S.rowDMaxF[r] > frontOld - WAKE && S.rowDMin[r] <= front) chkFlood = true;
          if (!chkLock && !chkLens && !chkFluid && !chkFlood && !chk32 && !flSwap && S.rowFade[r] === 0) {
            // nothing touches this row: its pixels stand
            S.rowFront[r] = front;
            S.rowFl[r] = fl;
            S.rowFOn[r] = fOn;
            S.rowLock[r] = lsig; S.rowLockBox[r] = lk ? { x: lk.x, y: lk.y, w: lk.w, h: lk.h } : null;
            S.rowLensOn[r] = lens ? 1 : 0; S.rowLensX[r] = lensX; S.rowLensY[r] = lensY;
            i += cols;
            continue;
          }
        }
        // the fluid grid row this row's samples read from (clamped as bilerp clamps)
        let fy0 = 0;
        if (F) {
          let fy = docY / cp - S.rowStart / 2;
          if (fy < 0) fy = 0; else if (fy > F.h - 1.001) fy = F.h - 1.001;
          fy0 = fy | 0;
        }
        let rowChanged = false;
        const R1 = (R + 1) * (R + 1);
        for (let c = 0; c < cols; c++, i++) {
          const docX = c * pitch + pitch / 2;
          if (!full) {
            // is anything that feeds this cell different from when it was last drawn?
            let need = S.fadeCell[i] === 1;
            if (tbk && need) tbk.why[0]++;
            if (!need && chkLock) { need = inBox(lk, docX, docY) || inBox(lockOld, docX, docY); if (tbk && need) tbk.why[1]++; }
            if (!need && chkLens) {
              const ex = docX - lensX, ey = docY - lensY, ox = docX - lensXOld, oy = docY - lensYOld;
              need = (lens !== null && ex * ex + ey * ey < R1) || (lensOnOld === 1 && ox * ox + oy * oy < R1);
              if (tbk && need) tbk.why[2]++;
            }
            if (!need && chkFluid) { need = S.usedCell[i] === 1 || (F !== null && (!safeOk || !(cellBound(docX, fy0) < S.kSafe[i]))); if (tbk && need) tbk.why[3]++; }
            if (!need && chk32) { need = S.kCov[i] !== S.kCov64[i]; if (tbk && need) tbk.why[5]++; }
            if (!need && chkFlood) { const dc = fl.dist[i]; need = dc > frontOld - WAKE && dc <= front; if (tbk && need) tbk.why[4]++; }
            if (!need && flSwap) {
              // the old pour's cells it had not finished, and the new pour's cells it has reached
              need = (flOld !== null && flOld.dist.length === n && flOld.dist[i] > frontOld - WAKE) || (fl !== null && fl.dist[i] <= front);
              if (tbk && need) tbk.why[4]++;
            }
            if (!need) continue;
          }
          rowChanged = true;
          if (tbk) tbk.cells++;
          // where this cell samples the image from: its own place, or wherever the flow carried it
          let px = docX, py = docY;
          if (F) {
            const fx = docX / cp, fy = docY / cp - S.rowStart / 2;
            const ax = bilerp(F.pdx, F.w, F.h, fx, fy), ay = bilerp(F.pdy, F.w, F.h, fx, fy);
            px -= ax + (bilerp(F.dx, F.w, F.h, fx, fy) - ax) * fa;
            py -= ay + (bilerp(F.dy, F.w, F.h, fx, fy) - ay) * fa;
          }
          // which field this cell shows: the one it showed before, until the pour reaches it
          let old = null;
          let wake = 0;
          const ir = S.isl[row];
          const pid = ir ? ir[c] : 0;
          if (pid) old = S.pal[pid - 1]; // poison (off): this cell keeps the colour of the pour that enclosed it
          else if (fl && fl.dist[i] <= front) {
            const dc = fl.dist[i];
            if (front - dc < WAKE) wake = wakeLevel * (1 - (front - dc) / WAKE);
          } else if (S.cellOld[i]) old = S.fpal[S.cellOld[i] - 1];
          const base = old ? old.base : S.base;
          const amp = old ? old.amp : S.amp;
          const grain = S.kGrain[i];
          let bg = base + (grain - 0.5) * 2 * amp;
          if (lk && docX > lk.x && docX < lk.x + lk.w && docY > lk.y && docY < lk.y + lk.h) bg += 0.08;
          let tr, tg, tb;
          let dist = 1e9;
          if (lens) {
            // the exact distance (hypot, as always) only where the cell can be inside the lens; a
            // squared test with a pixel to spare rules out the rest (hypot is slow in V8)
            const lx = docX - lens.x, ly = vy - lens.y;
            if (lx * lx + ly * ly < (R + 1) * (R + 1)) dist = Math.hypot(lx, ly);
          }
          let usedCover = 0;
          if (dist < R) {
            // the glass: cells near the centre sample from closer in (magnified), and the colour
            // channels separate along the radius, strongest halfway out
            const f = 1 - dist / R;
            const mag = 1 - 0.5 * f * f;
            const sx = lens.x + (px - lens.x) * mag;
            const sy = lens.y + (py - S.scrollY - lens.y) * mag + S.scrollY;
            const ux = dist > 0.01 ? (docX - lens.x) / dist : 0;
            const uy = dist > 0.01 ? (vy - lens.y) / dist : 0;
            const ch = f * (1 - f) * 4 * pitch * 1.4;
            tr = cover(sx + ux * ch, sy + uy * ch);
            tg = cover(sx, sy);
            tb = cover(sx - ux * ch, sy - uy * ch);
            bg += 0.05 * f;
          } else if (F) {
            // moved by the flow: within its margin it shows exactly what it shows at rest
            if (safeOk && cellBound(docX, fy0) < S.kSafe[i]) tr = tg = tb = S.kCov64[i];
            else { tr = tg = tb = cover(px, py); usedCover = 1; }
          } else {
            // at rest a cell samples its own place: what the name and echo cover there is cached
            tr = tg = tb = S.kCov[i];
          }
          S.usedCell[i] = usedCover;
          // lit cells vary a little too, like LEDs from different batches
          const lv = S.kLv[i];
          tr *= lv; tg *= lv; tb *= lv;
          let vr = tr > bg ? tr : bg;
          let vg = tg > bg ? tg : bg;
          let vb = tb > bg ? tb : bg;
          // afterglow: a lit cell fades over a few frames instead of switching off at once
          const j = i * 3;
          const pr = (resetRow ? 0 : S.prev[j]) - decay, pg = (resetRow ? 0 : S.prev[j + 1]) - decay, pb = (resetRow ? 0 : S.prev[j + 2]) - decay;
          S.fadeCell[i] = pr > vr || pg > vg || pb > vb ? 1 : 0;
          if (pr > vr) vr = pr;
          if (pg > vg) vg = pg;
          if (pb > vb) vb = pb;
          S.prev[j] = vr;
          S.prev[j + 1] = vg;
          S.prev[j + 2] = vb;
          // the wake is drawn on top, never stored in the afterglow
          if (wake > vr) vr = wake;
          if (wake > vg) vg = wake;
          if (wake > vb) vb = wake;
          const o = i * 4;
          if (old) {
            const of = old.field, oi = old.ink;
            d[o] = of[0] + (oi[0] - of[0]) * vr;
            d[o + 1] = of[1] + (oi[1] - of[1]) * vg;
            d[o + 2] = of[2] + (oi[2] - of[2]) * vb;
          } else {
            d[o] = fr + dr * vr;
            d[o + 1] = fg + dg * vg;
            d[o + 2] = fb + db * vb;
          }
          d[o + 3] = 255;
          // its glow: that of the field it shows (the old one until the pour reaches it), as light
          // under the gap layer, which lets it through only around LEDs whose field glows
          const glw = old ? old.glow || 0 : S.glow;
          const bl = S.bimg.data;
          bl[o] = d[o] * glw; bl[o + 1] = d[o + 1] * glw; bl[o + 2] = d[o + 2] * glw; bl[o + 3] = 255;
          const gOn = glw > 0 ? 1 : 0;
          if (S.glowCell[i] !== gOn) { S.glowCount += gOn - S.glowCell[i]; S.glowCell[i] = gOn; }
          // the gap around the cell belongs to the same field as the cell, so it pours with it
          const gp = old ? old.gap : S.gap;
          if (gp) {
            gd[o] = gp[0]; gd[o + 1] = gp[1]; gd[o + 2] = gp[2]; gd[o + 3] = glw > 0 ? 0 : 255;
          }
        }
        // the row's state as drawn, for the next frame's decision
        let fades = 0, used = 0;
        for (let k = r * cols, e = k + cols; k < e; k++) { fades += S.fadeCell[k]; used += S.usedCell[k]; }
        S.rowFade[r] = fades;
        S.rowUsed[r] = used;
        S.rowFOn[r] = fOn;
        S.rowG[r] = gsig;
        S.rowLock[r] = lsig; S.rowLockBox[r] = lk ? { x: lk.x, y: lk.y, w: lk.w, h: lk.h } : null;
        S.rowLensOn[r] = lens ? 1 : 0; S.rowLensX[r] = lensX; S.rowLensY[r] = lensY;
        S.rowFront[r] = front;
        S.rowFl[r] = fl;
        if (rowChanged) {
          if (r < dirty0) dirty0 = r;
          dirty1 = r;
        }
      }
      // upload only the band of rows drawn this frame (the sweep can wrap; then it is the whole panel)
      const dh = dirty1 - dirty0 + 1;
      if (dh > 0) S.ctx.putImageData(S.img, 0, 0, 0, dirty0, cols, dh);
      // the gap layer only changes while a pour runs or the rows / field change
      // the gap layer only changes while a pour runs, or when the rows, the field or the per-cell
      // history change; it is drawn only once the gap colour is known
      const gapKey = `${S.rowStart}|${S.fpal.length}|${S.gap}|${S.cols}x${S.rows}`;
      if (S.gctx && S.gap && (fl || S.gapKey !== gapKey)) {
        S.gctx.putImageData(S.gimg, 0, 0);
        S.gapKey = fl ? null : gapKey;
      }
      // the glow layer: every row drawn, whatever the field, since LEDs still showing an old
      // field keep that field's glow
      if (S.bctx && band1 >= band0) S.bctx.putImageData(S.bimg, 0, 0, 0, band0, cols, band1 - band0 + 1);
      if (S.motionPort) sampleMotion(now);
      // the page shows the glow layer only while some LED glows
      const glowOn = S.glowCount > 0;
      if (glowOn !== S.glowOn) { S.glowOn = glowOn; notify({ type: "glow", on: glowOn }); }
      notify({ type: "committed", rowStart: S.rowStart });
    }

    // the fluid's margins for a list of rows, until the time runs out; a row's margins hold while
    // its cover and the masks' distance maps are the same (the key `sk`)
    function marginRows(order, sk, tEnd) {
      const { cols, pitch } = S;
      for (const r of order) {
        if (S.kSafeRow[r] === sk || S.kCovRow[r] === null) continue;
        if (performance.now() > tEnd) return false;
        const docY = (r + S.rowStart) * pitch + pitch / 2;
        let ms = Infinity;
        for (let c = 0, k = r * cols; c < cols; c++, k++) {
          const g = margin(c * pitch + pitch / 2, docY);
          S.kSafe[k] = g;
          if (g < ms) ms = g;
        }
        S.rowMinSafe[r] = ms;
        S.kSafeRow[r] = sk;
      }
      return true;
    }
    // margins in idle moments: 2 ms at a time, yielding between, until the rows drawn last are done
    // (a newer frame replaces the job, and a key that has moved on is dropped)
    function marginIdle() {
      S.mTimer = 0;
      const job = S.mJob;
      if (!job || !S.kSafe || !S.kSafeRow || job.sk !== `${S.rowStart}|${S.scrollY}|${S.masksRev}|${S.safeRev || 0}`) return;
      if (!marginRows(job.order, job.sk, performance.now() + 2)) S.mTimer = setTimeout(marginIdle, 0);
      else S.mJob = null;
    }
    const RENDER_BUDGET = 0.5; // of one core
    const MARGIN_MS = 1; // per frame, for the fluid's margins
    function tick(now) {
      timed("frame", () => tick0(now));
    }

    /* What the visitor's eyes are offered: how much the wall changed on screen, block by block.
       This thread drew every cell, so the change is exact, not estimated from pixels. One cell in
       nine (every third row and column) is compared with its last drawn brightness; a block is
       MOTION_B x MOTION_B cells. The changes add up between posts and go to the gaze worker as a
       rate (brightness change per second) about 20 times a second. Cells are anchored to the
       document, so scrolling by itself is not change, as for eyes that ride along with the page. */
    const MOTION_B = 6, MOTION_MS = 50;
    function sampleMotion(now) {
      const cols = S.cols, rows = S.rows, pitch = S.pitch, d = S.img.data;
      const key = `${cols}x${rows}|${S.rowStart}|${pitch}`;
      if (S.mKey !== key) {
        S.mKey = key;
        S.mPrev = new Float32Array(cols * rows).fill(-1);
        S.mAcc = null;
        S.mFrom = now;
      }
      const top = Math.max(S.rowStart, Math.floor(S.scrollY / pitch));
      const bot = Math.min(S.rowStart + rows, Math.ceil((S.scrollY + (S.vh || 900)) / pitch));
      const by0 = Math.floor(top / MOTION_B), by1 = Math.ceil(bot / MOTION_B);
      const nbx = Math.ceil(cols / MOTION_B), nby = Math.max(0, by1 - by0);
      if (!S.mAcc || S.mBy0 !== by0 || S.mAcc.length !== nbx * nby) {
        S.mAcc = new Float32Array(nbx * nby);
        S.mN = new Uint16Array(nbx * nby);
        S.mBy0 = by0;
        S.mFrom = now;
      }
      const acc = S.mAcc, cnt = S.mN, prev = S.mPrev;
      S.mFrames = (S.mFrames || 0) + 1;
      // the sampled rows are the document rows 1, 4, 7, ... that are on screen
      for (let row = top + ((1 - (top % 3)) + 3) % 3; row < bot; row += 3) {
        const r = row - S.rowStart, bRow = (Math.floor(row / MOTION_B) - by0) * nbx;
        if (r < 0 || r >= rows) continue;
        for (let c = 1, i = r * cols + 1; c < cols; c += 3, i += 3) {
          const o = i * 4;
          const y = 0.2126 * d[o] + 0.7152 * d[o + 1] + 0.0722 * d[o + 2];
          const b = bRow + ((c / MOTION_B) | 0);
          if (prev[i] >= 0) acc[b] += Math.abs(y - prev[i]) / 255;
          prev[i] = y;
          if (cnt[b] < 65535) cnt[b]++;
        }
      }
      if (now - S.mFrom < MOTION_MS) return;
      const secs = (now - S.mFrom) / 1000;
      // per block: mean change per sampled cell per second, over the interval since the last post
      const frames = S.mFrames;
      const e = new Float32Array(nbx * nby);
      for (let b = 0; b < e.length; b++) e[b] = cnt[b] ? (acc[b] / (cnt[b] / frames)) / secs : 0;
      S.motionPort.postMessage({ type: "motion", t: now, dt: secs, pitch, B: MOTION_B, by0, nbx, nby, e }, [e.buffer]);
      acc.fill(0); cnt.fill(0);
      S.mFrom = now;
      S.mFrames = 0;
    }
    function tick0(now) {
      S.queued = false;
      // with debug on: a frame that came more than two 60 Hz frames after it was asked for is a stall
      if (S.debug) {
        const late = performance.now() - S.queuedAt;
        if (late > 34) notify({ type: "slow", what: "late frame", ms: Math.round(late), at: Math.round(S.queuedAt) });
      }
      if (!S.visible || !S.img) return;
      /* A CPU budget: the wall never takes more than half of one core. It measures what its frames
         cost and, when drawing every display frame would exceed that (a 540 Hz screen, a slow CPU),
         draws every other frame or fewer. Every pixel is a function of time, so a skipped display
         frame only lowers the frame rate; nothing is ever shown late or wrong, and the page's own
         threads always keep the other half and more. */
      const minGap = S.renderEma ? S.renderEma / RENDER_BUDGET : 0;
      if (S.lastTick && now - S.lastTick < minGap - 0.5) { queue(); return; }
      // real time since the last drawn frame (a fresh start counts as one 60 Hz frame)
      S.frameDt = S.lastTick && now - S.lastTick < 250 ? now - S.lastTick : FLUID_DT;
      S.lastTick = now;
      S.fluidAlpha = S.fluid && S.fluid.active ? fluidAdvance(S.fluid, S.pitch * 2, S.frameDt) : 0;
      if (S.flood && now - S.flood.at >= S.flood.ms) {
        S.flood = null;
        S.cellOld.fill(0);
        S.fpal = [];
      }
      const t0 = performance.now();
      render(now);
      const ms = performance.now() - t0;
      S.renderEma = S.renderEma ? S.renderEma * 0.9 + ms * 0.1 : ms;
      if (S.debug && ms > 8 && S.tb) {
        const t = S.tb;
        notify({ type: "slow", what: `frame: cover ${t.cov.toFixed(1)} margins ${t.safe.toFixed(1)} offsets ${t.disp.toFixed(1)} ms, ${t.full} full rows, ${t.cells} cells; fade/lock/lens/fluid/flood/f32 ${t.why.join("/")}; ${t.gs}`, ms: Math.round(ms * 10) / 10, at: Math.round(t0) });
      }
      // keep drawing only while something moves: the fluid, a pour, the lens, or fading trails
      const busy = (S.fluid && S.fluid.active) || S.flood || now - S.lastChange < 450;
      if (busy) queue();
    }

    function queue() {
      if (S.queued) return;
      S.queued = true;
      S.queuedAt = performance.now();
      schedule(tick);
    }

    // with debug on, anything in the worker that takes more than 8 ms is reported by name
    function timed(what, fn) {
      if (!S.debug) return fn();
      const t0 = performance.now();
      const r = fn();
      const ms = performance.now() - t0;
      if (ms > 8) notify({ type: "slow", what, ms: Math.round(ms * 10) / 10, at: Math.round(t0) });
      return r;
    }
    function handle(m) {
      // with ?debug&rec every message is recorded with its time, for tools/render_equiv.mjs
      if (S.rec && m.type !== "dumpRec" && m.type !== "pourResult" && m.type !== "maskDT" && m.type !== "motionPort") S.rec.push({ t: performance.now(), m });
      return timed("message " + m.type, () => handle0(m));
    }

    // tell the page when the pour reaches each block of text, so its colour turns then
    function reportArrivals(m) {
      if (m.texts) {
        const fl = S.flood;
        const list = m.texts.map((t) => {
          if (!fl) return 0;
          const c = Math.min(S.cols - 1, Math.max(0, Math.floor((t.x + t.w / 2) / S.pitch)));
          const r = Math.floor((t.y + t.h / 2) / S.pitch) - S.rowStart;
          if (r < 0 || r >= S.rows) return fl.ms;
          return Math.min(1, fl.dist[r * S.cols + c]) * fl.ms;
        });
        // and when it reaches the probe point (where the pour leaves the page for the tab icon)
        let probe = -1;
        if (fl && m.probe) {
          const c = Math.min(S.cols - 1, Math.max(0, Math.floor(m.probe.x / S.pitch)));
          const r = Math.floor(m.probe.y / S.pitch) - S.rowStart;
          probe = r < 0 || r >= S.rows ? fl.ms : Math.min(1, fl.dist[r * S.cols + c]) * fl.ms;
        }
        notify({ type: "arrivals", seq: m.seq, list, probe });
      }
    }
    function handle0(m) {
      const now = performance.now();
      switch (m.type) {
        case "init":
          S.debug = !!m.debug;
          S.rec = m.rec ? [] : null;
          S.canvas = m.canvas;
          S.gapsCanvas = m.gaps || null;
          // transparent until its first frame, so the page background shows through, never black
          S.gctx = S.gapsCanvas ? S.gapsCanvas.getContext("2d") : null;
          S.bloom = m.bloom || null;
          S.ctx = S.canvas.getContext("2d", { alpha: false });
          S.bctx = S.bloom ? S.bloom.getContext("2d", { alpha: false }) : null;
          break;
        case "resize":
          resize(m);
          break;
        case "motionPort":
          S.motionPort = m.port;
          break;
        case "maskDT":
          // the distance maps for the current masks, from the pour thread
          if (m.rev === S.masksRev) {
            m.dts.forEach((dt, k) => { if (dt && S.masks[k]) S.masks[k].__dt = dt; });
            S.safeRev = (S.safeRev || 0) + 1;
          }
          return; // nothing to draw because of it
        case "dumpRec":
          notify({ type: "rec", log: S.rec || [] });
          break;
        case "field": {
          S.old = { field: S.field, ink: S.ink, base: S.base, amp: S.amp, gap: S.gap, glow: S.glow };
          // every cell now showing the current field keeps showing it until the next pour
          // reaches it; cells an unfinished pour had not reached yet keep what they showed
          if (S.cellOld) {
            if (S.fpal.length >= 250) { S.fpal = []; S.cellOld.fill(0); S.cutEpoch = (S.cutEpoch || 0) + 1; }
            S.fpal.push(S.old);
            const id = S.fpal.length;
            const fl = S.flood;
            const front = fl ? Math.min(1, (now - fl.at) / fl.ms) : 0;
            for (let i = 0; i < S.cellOld.length; i++) {
              if (!S.cellOld[i] || (fl && fl.dist[i] <= front)) S.cellOld[i] = id;
            }
          }
          S.flood = null;
          S.field = m.field;
          S.ink = m.ink;
          S.gap = m.gap;
          S.base = m.base;
          S.amp = m.amp;
          S.glow = m.glow;
          /* The afterglow resets with the field: until a row is next drawn, its cells' afterglow
             counts as zero. Rather than zeroing every cell (which would force redrawing them all,
             since a skipped cell must keep its stored afterglow), each row is marked: a cell computed
             while its row is marked starts from zero, exactly as after a reset; drawing the row clears
             the mark, and a cell skipped then already holds its unchanged value, which is what the
             reset and a redraw would have left. */
          if (S.prev) {
            if (S.rowReset && S.rowReset.length * S.cols * 3 === S.prev.length) S.rowReset.fill(1);
            else S.prev.fill(0);
          }
          S.prevEpoch = (S.prevEpoch || 0) + 1;
          S.pending = null;
          S.pendingMsg = m;
          if (m.cut && !S.reduce) startFlood(now, m.texts);
          if (S.pending) break; // the pour thread is computing it: arrivals are reported when it starts
          if (!S.flood && S.cellOld) { S.cellOld.fill(0); S.fpal = []; S.cutEpoch = (S.cutEpoch || 0) + 1; } // a plain cut
          reportArrivals(m);
          break;
        }
        case "pourResult": {
          // the pour thread's answer: a pending flood starts now; a prediction is kept for later
          const r = m.result;
          if (!r) break;
          if (S.pending && S.pending.key === r.key) {
            const p = S.pending;
            S.pending = null;
            S.prepared = r;
            startFlood(performance.now(), p.texts);
            if (!S.flood && S.cellOld) { S.cellOld.fill(0); S.fpal = []; S.cutEpoch = (S.cutEpoch || 0) + 1; }
            if (p.msg) reportArrivals(p.msg);
            queue();
          } else if (S.wantKey === r.key) {
            S.prepared = r;
          }
          break;
        }
        case "pourJob": {
          // in the pour thread: compute and send back, the arrays transferred, not copied
          S.lock = m.lock;
          const res = computePour(m.lock);
          notify({ type: "pourResult", result: res }, res ? [res.rank.buffer] : []);
          break;
        }
        case "scroll":
          S.scrollY = m.scrollY;
          if (m.vw) { S.vw = m.vw; S.vh = m.vh; }
          S.wantStart = m.rowStart;
          break;
        case "lens":
          if (!S.reduce) stir(m.lens);
          S.lens = m.lens;
          break;
        case "lock":
          S.lock = m.lock;

          break;
        case "masks":
          S.masks = m.masks;
          S.masksRev = (S.masksRev || 0) + 1;
          if (!S.ctx) {
            // the pour thread: build the masks' distance maps for the drawing thread
            const dts = S.masks.map(maskDT);
            notify({ type: "maskDT", rev: S.masksRev, dts }, dts.filter(Boolean).map((a) => a.buffer));
          }
          if (m.keep) S.keep = m.keep;
          if (m.keepFixed) S.keepFixed = m.keepFixed;
          break;
        case "prepare":
          // precompute the pour for the target the pointer is heading to; only the latest request
          // is kept, and it runs after the next frame so it never delays drawing
          S.wantPrep = m.box;
          if (!S.prepTimer) {
            S.prepTimer = setTimeout(() => {
              S.prepTimer = 0;
              const box = S.wantPrep;
              S.wantPrep = null;
              if (box && !S.reduce && S.img && (!S.prepared || S.prepared.key !== keyOf(box))) {
                S.wantKey = keyOf(box);
                if (pourer) pourer({ type: "pourJob", lock: box });
                else S.prepared = timed("prepare pour", () => computePour(box));
              }
            }, 30);
          }
          return;
        case "reduce":
          S.reduce = m.reduce;
          break;
        case "visible":
          S.visible = m.visible;
          break;
      }
      S.lastChange = now;
      queue();
    }

    return { handle };
  }

  scope.createWall = createWall;
  scope.wallLitAt = litAt;
})(self);
