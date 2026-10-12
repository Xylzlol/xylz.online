/* What moves on screen, folded into the gaze estimate.

   The wall worker drew every cell, so it sends the exact change of the screen, block by block, about
   20 times a second (sampleMotion in wall.js). Video gaze models have to guess motion from pixels;
   here it is given. This layer turns it into two extra parts of the gaze mixture:

   - capture: a sudden change on a quiet screen (a pour starting) pulls the eyes to where it started,
     after a saccade latency, and holds them there while the change spreads. The eyes do not chase
     the front: an expanding edge at thousands of px/s is far past what smooth pursuit can follow
     (about 30 deg/s for a small target), so they jump once and watch (abrupt and motion onsets
     capture attention: Yantis & Jonides 1984, Abrams & Christ 2003; after a global change viewing
     turns ambient for about a second: Pannasch & Velichkovsky 2009; dynamic features predict the
     saccades right after a cut best: Carmi & Itti 2006).
   - watching: sustained, local motion (the swirl in the name) draws a small, steady share of the
     eyes to where it moves. A change covering much of the screen is global, not a target, and
     draws none.

   Every number below is a parameter of the certificate (ml/gaze_dyn_cert.mjs), fitted on eye
   tracking recorded on moving content and scored on people it never saw. */
(() => {
  const DEFAULTS = {
    onsetTotal: 40,     // change total (summed block rates) that counts as a sudden change...
    quietRatio: 0.25,   // ...when the recent level was below this fraction of it
    latency: 200,       // ms from the change to the capture saccade (logistic ramp centre)
    latencyW: 45,       // ms, ramp width
    capMax: 0.55,       // share of the eyes captured by a screen-wide onset
    capArea: 0.08,      // onset area (share of the screen's blocks) at which capture reaches half
    hold: 900,          // ms the capture holds after landing (exponential)
    capSigma: 70,       // px, spread of the captured gaze around the onset origin
    watchMax: 0.3,      // share of the eyes that sustained local motion can hold
    watchHalf: 25,      // sustained change total at which watching reaches half of watchMax
    watchTau: 350,      // ms, smoothing of the sustained map
    globalArea: 0.25,   // a change over more than this share of the screen is global: no watching
    watchK: 6,          // blocks used as watching components
    watchSigma: 2.5,    // block widths, spread of each watching component
    persistTau: 700,    // ms: how long a block must keep changing to count as moving (a front
                        // passes a block once; the swirl keeps changing it)
    cursorGuard: 120,   // px: change this close to the cursor is the cursor's own wake, not a target
  };

  self.createGazeDyn = function createGazeDyn(params) {
    const P = Object.assign({}, DEFAULTS, params || {});
    let ema = null, per = null, emaT = 0, level = 0, last = null;
    let onset = null; // { t, x, y, area }

    function motion(m, cursor) {
      const n = m.e.length, cell = m.B * m.pitch;
      let tot = 0, active = 0, sx = 0, sy = 0;
      for (let i = 0; i < n; i++) {
        const v = m.e[i];
        if (!v) continue;
        const x = ((i % m.nbx) + 0.5) * cell, y = (((i / m.nbx) | 0) + m.by0 + 0.5) * cell;
        if (cursor && Math.hypot(x - cursor[0], y - cursor[1]) < P.cursorGuard) continue;
        tot += v; sx += v * x; sy += v * y;
        if (v > 0.5) active++;
      }
      const area = active / Math.max(1, n);
      // a sudden change on a quiet screen
      if (tot > P.onsetTotal && level < P.onsetTotal * P.quietRatio && (!onset || m.t - onset.t > 400)) {
        onset = { t: m.t, x: sx / tot, y: sy / tot, area };
      } else if (onset && m.t - onset.t < 150) {
        onset.area = Math.max(onset.area, area); // the onset's size, over its first frames
      }
      const a = 1 - Math.exp(-(m.dt * 1000) / 300);
      level += (tot - level) * a;
      // the sustained map, smoothed; a global change does not feed it
      if (!ema || ema.length !== n || !last || last.by0 !== m.by0 || last.nbx !== m.nbx) { ema = new Float32Array(n); per = new Float32Array(n); }
      const b = 1 - Math.exp(-(m.dt * 1000) / P.watchTau);
      const c = 1 - Math.exp(-(m.dt * 1000) / P.persistTau);
      // while a sudden change holds the eyes, nothing else is watched
      const global = area > P.globalArea || (onset && m.t - onset.t < P.latency + 2 * P.hold);
      for (let i = 0; i < n; i++) {
        ema[i] += ((global ? 0 : m.e[i]) - ema[i]) * b;
        per[i] += ((!global && m.e[i] > 0.3 ? 1 : 0) - per[i]) * c;
      }
      emaT = m.t;
      last = m;
    }

    // extra mixture components, in page coordinates, with their total weight
    function parts(now, cursor) {
      const out = [];
      if (onset) {
        const dt = now - onset.t;
        const ramp = 1 / (1 + Math.exp(-(dt - P.latency) / P.latencyW));
        const hold = dt > P.latency ? Math.exp(-(dt - P.latency) / P.hold) : 1;
        const size = onset.area / (onset.area + P.capArea);
        const w = P.capMax * size * ramp * hold;
        if (w > 0.005) out.push({ w, x: onset.x, y: onset.y, s: P.capSigma });
        if (dt > P.latency + 5 * P.hold) onset = null;
      }
      if (ema && last && now - emaT < 400) {
        const cell = last.B * last.pitch;
        let tot = 0;
        const idx = [];
        const str = new Float32Array(ema.length);
        for (let i = 0; i < ema.length; i++) str[i] = ema[i] * per[i] * per[i];
        for (let i = 0; i < ema.length; i++) {
          if (str[i] < 0.05) continue;
          const x = ((i % last.nbx) + 0.5) * cell, y = (((i / last.nbx) | 0) + last.by0 + 0.5) * cell;
          if (cursor && Math.hypot(x - cursor[0], y - cursor[1]) < P.cursorGuard) continue;
          tot += str[i];
          idx.push(i);
        }
        if (tot > 0) {
          idx.sort((p, q) => str[q] - str[p]);
          const top = idx.slice(0, P.watchK);
          let topSum = 0;
          for (const i of top) topSum += str[i];
          const W = P.watchMax * tot / (tot + P.watchHalf);
          for (const i of top) {
            out.push({
              w: (W * str[i]) / topSum,
              x: ((i % last.nbx) + 0.5) * cell,
              y: (((i / last.nbx) | 0) + last.by0 + 0.5) * cell,
              s: P.watchSigma * cell,
            });
          }
        }
      }
      return out;
    }

    /* The net's mixture (relative to the cursor at `at`) with the moving parts added: the net keeps
       whatever share they leave. Returns a mixture in the same form. */
    function apply(mix, at, now) {
      const extra = parts(now, at);
      if (!extra.length) return mix;
      let W = 0;
      for (const p of extra) W += p.w;
      W = Math.min(0.9, W);
      const K = mix.K + extra.length;
      const pi = new Float32Array(K), mx = new Float32Array(K), my = new Float32Array(K), sx = new Float32Array(K), sy = new Float32Array(K);
      for (let k = 0; k < mix.K; k++) {
        pi[k] = mix.pi[k] * (1 - W); mx[k] = mix.mx[k]; my[k] = mix.my[k]; sx[k] = mix.sx[k]; sy[k] = mix.sy[k];
      }
      const scale = W / extra.reduce((s, p) => s + p.w, 0);
      extra.forEach((p, j) => {
        const k = mix.K + j;
        pi[k] = p.w * scale; mx[k] = p.x - at[0]; my[k] = p.y - at[1]; sx[k] = p.s; sy[k] = p.s;
      });
      return { pi, mx, my, sx, sy, K };
    }

    return { motion, parts, apply, params: P };
  };
  self.createGazeDyn.DEFAULTS = DEFAULTS;
})();
