/* Where is the visitor looking? An estimate, from no camera at all. Runs in gaze-worker.js.

   A particle filter keeps a few hundred hypotheses of the gaze point, in document coordinates.

   Motion model (what eyes do between observations):
   - Gaze alternates fixations and saccades. Fixation durations follow a gamma distribution,
     mean ~225ms on text and ~280ms elsewhere (reading research: 3-4 saccades a second).
   - On a line of text, the next saccade is mostly a forward step of ~7-9 characters, sometimes a
     short regression, and a return sweep to the next line at the end (E-Z Reader / SWIFT literature).
   - Elsewhere, the next fixation is drawn from the neural saliency map (UNISAL fine-tuned on UEyes
     UI eye-tracking) when it is available, otherwise from the page's layout (big type, headings,
     links, central bias, inhibition of return); fresh onsets capture attention for a moment.

   Observation model (what the pointer tells us):
   - The mouse lags gaze by ~700ms on average (Huang et al., reported in Navalpakkam et al. 2013),
     and in goal-directed pointing the eyes land on the target before the hand gets there, so while
     the pointer is heading for a predicted target, the target is stronger evidence than the cursor.
   - Eye-mouse coupling is tighter vertically than horizontally, so the likelihood is anisotropic.
   - An idle cursor says less and less: people read away from it.
   - A click is strong evidence the eyes are on the cursor.

   The estimate is the densest mode of the cloud (mean shift), not the mean, because the belief is
   often split between two places and the mean would sit where nobody looks. Its stated precision is
   the radius around that mode which holds half of the whole belief, however large that is. */
(() => {
  function gamma3(mean) {
    let s = 0;
    for (let i = 0; i < 3; i++) s -= Math.log(1 - Math.random());
    return (s / 3) * mean;
  }
  const gauss = () => {
    const u = 1 - Math.random();
    const v = Math.random();
    return Math.sqrt(-2 * Math.log(u)) * Math.cos(2 * Math.PI * v);
  };

  self.createGaze = function createGaze(N) {
    const P = {
      x: new Float32Array(N), y: new Float32Array(N), w: new Float32Array(N).fill(1 / N),
      left: new Float32Array(N), line: new Int16Array(N).fill(-1),
    };
    let aois = [];
    let lines = [];
    let view = { x: 0, y: 0, w: 1440, h: 900 };
    const ior = new Map();
    let sal = null;
    let onset = null;
    let started = false;
    let last = performance.now();
    const ev = { x: 0, y: 0, lastMove: -1e9, click: null, intent: null };

    function setLayout(l) {
      aois = l.aois;
      lines = l.lines;
      view = l.view;
      ior.clear();
      for (const a of aois) {
        const cx = a.x + a.w / 2 - view.x - view.w / 2;
        const cy = a.y + a.h / 2 - view.y - view.h / 2;
        a.base = a.weight * Math.sqrt(Math.min(a.w * a.h, 400000) / 4000) * Math.exp(-(cx * cx) / (2 * (0.35 * view.w) ** 2) - (cy * cy) / (2 * (0.4 * view.h) ** 2));
      }
      if (!started) seed();
    }

    function setSaliency(map, w, h, v) {
      const cdf = new Float32Array(map.length);
      let acc = 0;
      for (let i = 0; i < map.length; i++) { acc += map[i]; cdf[i] = acc; }
      sal = { cdf, map, w, h, view: v, total: acc };
    }
    function salAt(x, y) {
      if (!sal) return 1;
      const v = sal.view;
      const cx = Math.floor(((x - v.x) / v.w) * sal.w);
      const cy = Math.floor(((y - v.y) / v.h) * sal.h);
      if (cx < 0 || cy < 0 || cx >= sal.w || cy >= sal.h) return 0.2;
      return sal.map[cy * sal.w + cx] * sal.w * sal.h;
    }
    function sampleSal() {
      const r = Math.random() * sal.total;
      let lo = 0, hi = sal.cdf.length - 1;
      while (lo < hi) {
        const mid = (lo + hi) >> 1;
        if (sal.cdf[mid] < r) lo = mid + 1; else hi = mid;
      }
      const v = sal.view;
      const cx = lo % sal.w, cy = (lo / sal.w) | 0;
      return { x: v.x + ((cx + Math.random()) / sal.w) * v.w, y: v.y + ((cy + Math.random()) / sal.h) * v.h };
    }
    function lineAt(x, y) {
      for (let i = 0; i < lines.length; i++) {
        const l = lines[i];
        if (x >= l.x - 4 && x <= l.x + l.w && Math.abs(y - l.y) < l.ch * 1.6) return i;
      }
      return -1;
    }
    function landIn(a) {
      if (a.lines.length) {
        const li = a.lines[Math.min(a.lines.length - 1, Math.floor(Math.random() * Math.min(2, a.lines.length)))];
        const l = lines[li];
        return { x: l.x + Math.min(l.w, l.ch * (3 + Math.random() * 5)), y: l.y, line: li };
      }
      return { x: a.x + a.w * (0.5 + 0.22 * gauss()), y: a.y + a.h * (0.5 + 0.2 * gauss()), line: -1 };
    }
    function sampleAoi(now) {
      let total = 0;
      const ws = aois.map((a, i) => {
        const t = ior.get(i);
        const w = a.base * (t ? 1 - 0.75 * Math.exp(-(now - t) / 1800) : 1);
        total += w;
        return w;
      });
      let r = Math.random() * total;
      for (let i = 0; i < ws.length; i++) {
        r -= ws[i];
        if (r <= 0) return i;
      }
      return ws.length - 1;
    }

    function likelihood(px, py, now) {
      const idle = Math.min(1.6, (now - ev.lastMove) / 1000);
      let tx = ev.x, ty = ev.y, sx = 110 + idle * 260, sy = 60 + idle * 170, floor = 0.12 + idle * 0.45;
      const intent = ev.intent;
      if (intent && now - ev.lastMove < 150) {
        const b = intent.box;
        const cx = b.x + b.w / 2, cy = b.y + b.h / 2;
        const dt = Math.hypot(cx - tx, cy - ty);
        const k = Math.min(1, intent.speed / 1.4);
        tx += (cx - tx) * k;
        ty += (cy - ty) * k;
        sx = Math.max(sx, b.w / 2 + dt * 0.15);
        sy = Math.max(sy, b.h / 2 + 30);
      }
      if (ev.click && now - ev.click.t < 300) {
        tx = ev.click.x; ty = ev.click.y; sx = 40; sy = 40; floor = 0.02;
      }
      const dx = px - tx, dy = py - ty;
      return floor + (1 - floor) * Math.exp(-(dx * dx) / (2 * sx * sx) - (dy * dy) / (2 * sy * sy));
    }

    function seed() {
      for (let i = 0; i < N; i++) {
        const a = aois.length ? aois[sampleAoi(0)] : { x: view.x + view.w / 2, y: view.y + view.h / 3, w: 1, h: 1, lines: [] };
        const p = landIn(a);
        P.x[i] = p.x; P.y[i] = p.y; P.line[i] = p.line; P.left[i] = gamma3(240) * Math.random();
        P.w[i] = 1 / N;
      }
      started = true;
    }

    function saccade(i, now) {
      const li = P.line[i];
      if (li >= 0 && lines[li] && Math.random() < 0.72) {
        const l = lines[li];
        if (Math.random() < 0.12) P.x[i] -= l.ch * (2 + Math.random() * 4);
        else P.x[i] += l.ch * (7 + 2 * gauss());
        if (P.x[i] > l.x + l.w) {
          const a = aois[l.aoi];
          const k = a ? a.lines.indexOf(li) : -1;
          if (k >= 0 && k + 1 < a.lines.length) {
            const nl = lines[a.lines[k + 1]];
            P.x[i] = nl.x + nl.ch * (2 + Math.random() * 3);
            P.y[i] = nl.y;
            P.line[i] = a.lines[k + 1];
            return;
          }
          P.line[i] = -1;
        } else {
          P.x[i] = Math.max(l.x, P.x[i]);
          P.y[i] = l.y + gauss() * 2;
          return;
        }
      }
      const r = Math.random();
      if (onset && now - onset.at < 600 && r < 0.35) {
        P.x[i] = onset.x + onset.w * (0.3 + 0.4 * Math.random());
        P.y[i] = onset.y + onset.h * (0.3 + 0.4 * Math.random());
        P.line[i] = -1;
        return;
      }
      if (sal && r < 0.8) {
        const p = sampleSal();
        P.x[i] = p.x; P.y[i] = p.y; P.line[i] = lineAt(p.x, p.y);
        return;
      }
      if (r < 0.72 && aois.length) {
        const k = sampleAoi(now);
        const p = landIn(aois[k]);
        ior.set(k, now);
        P.x[i] = p.x; P.y[i] = p.y; P.line[i] = p.line;
        return;
      }
      P.x[i] += gauss() * 40;
      P.y[i] += gauss() * 30;
      P.line[i] = -1;
    }

    function step(now) {
      if (!started) return;
      const dt = Math.min(100, now - last);
      last = now;
      const vx0 = view.x, vy0 = view.y, vx1 = vx0 + view.w, vy1 = vy0 + view.h;
      const tempered = dt / 100;
      const pointer = ev.lastMove > -1e8;
      let sum = 0;
      for (let i = 0; i < N; i++) {
        P.left[i] -= dt;
        if (P.left[i] <= 0 || P.x[i] < vx0 || P.x[i] > vx1 || P.y[i] < vy0 || P.y[i] > vy1) {
          saccade(i, now);
          P.left[i] = gamma3(P.line[i] >= 0 ? 225 : 280);
        }
        if (pointer) P.w[i] *= Math.pow(likelihood(P.x[i] - vx0, P.y[i] - vy0, now), tempered);
        if (sal) P.w[i] *= Math.pow(salAt(P.x[i], P.y[i]) + 0.05, 0.25 * tempered);
        sum += P.w[i];
      }
      if (!(sum > 0)) { P.w.fill(1 / N); sum = 1; }
      let ess = 0;
      for (let i = 0; i < N; i++) { P.w[i] /= sum; ess += P.w[i] * P.w[i]; }
      if (1 / ess < N / 2) resample();
    }

    const nx = new Float32Array(N), ny = new Float32Array(N), nl = new Int16Array(N), nleft = new Float32Array(N);
    function resample() {
      let c = P.w[0], j = 0;
      const u0 = Math.random() / N;
      for (let i = 0; i < N; i++) {
        const u = u0 + i / N;
        while (u > c && j < N - 1) c += P.w[++j];
        nx[i] = P.x[j] + gauss() * 4;
        ny[i] = P.y[j] + gauss() * 3;
        nl[i] = P.line[j];
        nleft[i] = P.left[j];
      }
      P.x.set(nx); P.y.set(ny); P.line.set(nl); P.left.set(nleft);
      P.w.fill(1 / N);
    }

    const order = new Uint32Array(N);
    const dist = new Float32Array(N);
    function estimate() {
      let best = 0;
      for (let i = 1; i < N; i++) if (P.w[i] > P.w[best]) best = i;
      let mx = P.x[best], my = P.y[best];
      const h = 70;
      for (let it = 0; it < 6; it++) {
        let sx = 0, sy = 0, sw = 0;
        for (let i = 0; i < N; i++) {
          const dx = P.x[i] - mx, dy = P.y[i] - my;
          const k = P.w[i] * Math.exp(-(dx * dx + dy * dy) / (2 * h * h));
          sx += k * P.x[i]; sy += k * P.y[i]; sw += k;
        }
        if (sw > 0) { mx = sx / sw; my = sy / sw; }
      }
      // the radius that holds half of the whole belief: the weighted median distance from the mode
      for (let i = 0; i < N; i++) { order[i] = i; dist[i] = Math.hypot(P.x[i] - mx, P.y[i] - my); }
      order.sort((a, b) => dist[a] - dist[b]);
      let acc = 0, r50 = dist[order[N - 1]];
      for (let i = 0; i < N; i++) {
        acc += P.w[order[i]];
        if (acc >= 0.5) { r50 = dist[order[i]]; break; }
      }
      return { x: mx, y: my, r50 };
    }

    return {
      N, P, step, estimate,
      layout: setLayout,
      view(v) { view = v; },
      saliency: setSaliency,
      onset(box) { onset = { ...box, at: performance.now() }; },
      move(x, y) { ev.x = x; ev.y = y; ev.lastMove = performance.now(); },
      click(x, y) { ev.click = { x, y, t: performance.now() }; },
      intent(i) { ev.intent = i; },
      lines: () => lines,
    };
  };
})();
