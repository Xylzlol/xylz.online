// Pixel-exactness and cost of a wall.js change: replays a recorded message stream (wall_record.py)
// through two versions of wall.js on the same simulated clock, at a given display rate, and compares
// every frame of all three canvases (cells, bloom, gaps) byte for byte. Also times each version's
// frames (the same V8 as Chrome, minus the canvas upload).
//   node render_equiv.mjs old_wall.js new_wall.js rec.json [hz ...]
import fs from "node:fs";
import vm from "node:vm";
import crypto from "node:crypto";

const [, , oldPath, newPath, recPath, ...hzArgs] = process.argv;
const rates = hzArgs.length ? hzArgs.map(Number) : [60, 540];
const revive = (k, v) => (v && v.__ta ? new globalThis[v.__ta](v.d) : v);
const recs = JSON.parse(fs.readFileSync(recPath, "utf8"), revive);

function mulberry(a) { return () => { a |= 0; a = (a + 0x6D2B79F5) | 0; let t = Math.imul(a ^ (a >>> 15), 1 | a); t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t; return ((t ^ (t >>> 14)) >>> 0) / 4294967296; }; }

function fakeCanvas() {
  const c = { _w: 0, _h: 0, fb: new Uint8ClampedArray(0), puts: 0 };
  const alloc = () => { c.fb = new Uint8ClampedArray(c._w * c._h * 4); };
  Object.defineProperty(c, "width", { get: () => c._w, set: (v) => { c._w = v; alloc(); } });
  Object.defineProperty(c, "height", { get: () => c._h, set: (v) => { c._h = v; alloc(); } });
  const ctx = {
    createImageData: (w, h) => ({ width: w, height: h, data: new Uint8ClampedArray(w * h * 4) }),
    putImageData(img, dx, dy, sx = 0, sy = 0, sw = img.width, sh = img.height) {
      c.puts++;
      for (let y = sy; y < sy + sh; y++) {
        const ty = y + dy;
        if (ty < 0 || ty >= c._h) continue;
        for (let x = sx; x < sx + sw; x++) {
          const tx = x + dx;
          if (tx < 0 || tx >= c._w) continue;
          const s = (y * img.width + x) * 4, t = (ty * c._w + tx) * 4;
          c.fb[t] = img.data[s]; c.fb[t + 1] = img.data[s + 1]; c.fb[t + 2] = img.data[s + 2]; c.fb[t + 3] = img.data[s + 3];
        }
      }
    },
    clearRect() {}, fillRect() {}, drawImage() {},
  };
  c.getContext = () => ctx;
  return c;
}

function run(path, hz) {
  const src = fs.readFileSync(path, "utf8");
  const clock = { t: 0 };
  // timers run on the simulated clock too
  const timers = []; let tid = 0;
  const sb = { self: {}, performance: { now: () => clock.t }, console, __rnd: mulberry(12345),
    setTimeout: (fn, ms) => { timers.push({ at: clock.t + (ms || 0), fn, id: ++tid }); return tid; },
    clearTimeout: (id) => { const k = timers.findIndex((x) => x.id === id); if (k >= 0) timers.splice(k, 1); } };
  const fireTimers = (t) => {
    for (;;) {
      let k = -1;
      for (let j = 0; j < timers.length; j++) if (timers[j].at <= t && (k < 0 || timers[j].at < timers[k].at)) k = j;
      if (k < 0) return;
      const x = timers.splice(k, 1)[0]; clock.t = x.at; x.fn();
    }
  };
  vm.createContext(sb);
  // the context's own Math (a plain object in its place would cost V8 its fast paths and distort
  // the timing); only random is replaced, by a seeded generator, so both versions pour alike
  vm.runInContext("Math.random = __rnd;", sb);
  vm.runInContext(src, sb);
  const createWall = sb.createWall || sb.self.createWall;
  let queued = null;
  const wall = createWall((fn) => { queued = fn; }, () => {}, null);
  const cv = { cells: fakeCanvas(), bloom: fakeCanvas(), gaps: fakeCanvas(), glossHi: fakeCanvas() };
  clock.t = recs[0].t - 1;
  wall.handle({ type: "init", canvas: cv.cells, bloom: cv.bloom, gaps: cv.gaps, glossHi: cv.glossHi, debug: false });
  const dt = 1000 / hz;
  const end = recs[recs.length - 1].t + 2500;
  let mi = 0;
  const frames = [];
  let busy = 0;
  for (let t = recs[0].t; t <= end; t += dt) {
    while (mi < recs.length && recs[mi].t <= t) { fireTimers(recs[mi].t); clock.t = recs[mi].t; wall.handle(recs[mi].m); mi++; }
    fireTimers(t);
    if (queued) {
      const q = queued; queued = null; clock.t = t;
      const t0 = process.hrtime.bigint();
      q(t);
      busy += Number(process.hrtime.bigint() - t0) / 1e6;
      const h = crypto.createHash("sha1");
      for (const k of ["cells", "bloom", "gaps", "glossHi"]) h.update(cv[k].fb);
      frames.push({ t, h: h.digest("hex"), snap: process.env.DIAG ? { cells: cv.cells.fb.slice(), bloom: cv.bloom.fb.slice(), gaps: cv.gaps.fb.slice(), glossHi: cv.glossHi.fb.slice(), w: cv.cells._w } : null });
    } else frames.push({ t, h: null });
  }
  return { frames, busy, cv, sb };
}

// PROFILE_ONLY=path: run just that version once (for node --cpu-prof), no comparison
if (process.env.PROFILE_ONLY) {
  const r = run(process.env.PROFILE_ONLY, rates[0]);
  console.log(`render time ${r.busy.toFixed(0)} ms over ${r.frames.filter((f) => f.h).length} frames`);
  if (r.sb && r.sb.self.__st) console.log(JSON.stringify(r.sb.self.__st));
  process.exit(0);
}
let allSame = true;
for (const hz of rates) {
  const a = run(oldPath, hz), b = run(newPath, hz);
  let drawnA = 0, drawnB = 0, diff = 0, first = null;
  for (let i = 0; i < Math.max(a.frames.length, b.frames.length); i++) {
    const fa = a.frames[i], fb = b.frames[i];
    if (fa && fa.h) drawnA++;
    if (fb && fb.h) drawnB++;
  }
  // compare the picture at every display frame: the latest drawn state of each version
  let la = null, lb = null;
  for (let i = 0; i < a.frames.length; i++) {
    if (a.frames[i].h) la = a.frames[i].h;
    if (b.frames[i] && b.frames[i].h) lb = b.frames[i].h;
    if (la !== lb) {
      diff++;
      if (first === null) {
        first = Math.round(a.frames[i].t - recs[0].t);
        // which canvas, how many pixels, where
        const fa = [...a.frames.slice(0, i + 1)].reverse().find((f) => f.snap), fb = [...b.frames.slice(0, i + 1)].reverse().find((f) => f.snap);
        if (fa && fb) {
          for (const k of ["cells", "bloom", "gaps", "glossHi"]) {
            const A = fa.snap[k], B = fb.snap[k], w = fa.snap.w;
            let nd = 0, x0 = 1e9, y0 = 1e9, x1 = -1, y1 = -1, ex = null;
            for (let q = 0; q < A.length; q += 4) {
              if (A[q] !== B[q] || A[q + 1] !== B[q + 1] || A[q + 2] !== B[q + 2] || A[q + 3] !== B[q + 3]) {
                nd++; const px = (q / 4) % w, py = Math.floor(q / 4 / w);
                x0 = Math.min(x0, px); x1 = Math.max(x1, px); y0 = Math.min(y0, py); y1 = Math.max(y1, py);
                if (!ex) ex = `(${px},${py}) old ${[...A.slice(q, q + 4)]} new ${[...B.slice(q, q + 4)]}`;
              }
            }
            if (nd) console.log(`  first difference at +${first} ms: ${k}: ${nd} pixels in x ${x0}..${x1}, y ${y0}..${y1}; e.g. ${ex}`);
          }
        }
      }
    }
  }
  if (diff) allSame = false;
  console.log(`${hz} Hz: frames ${a.frames.length}, drawn old ${drawnA} new ${drawnB}; frames whose picture differs: ${diff}${first !== null ? ` (first at +${first} ms)` : ""}; render time old ${a.busy.toFixed(0)} ms, new ${b.busy.toFixed(0)} ms (${(a.busy / b.busy).toFixed(2)}x)`);
}
console.log(allSame ? "IDENTICAL: every displayed frame matches byte for byte" : "DIFFERENT");
process.exit(allSame ? 0 : 1);
