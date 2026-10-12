// The gaze certificate: replays recorded sessions (adserp_prep.py) through a gaze model, by default
// the site's own gaze.js unchanged, on a simulated clock, and scores the estimate against where the
// person really looked.
//   node gaze_cert.mjs [path/to/gaze.js] [--participants p004,p005] [--json out.json] [--seed 1]
// Every 100 ms of every session (after its first second, while the tracker has the eye): error =
// distance from the estimate to the true gaze, in page CSS px. Reported per session, then as the
// median over sessions, with two predictors to beat (the cursor, the viewport centre) and the
// calibration of the printed 50% radius (it should contain the true gaze half the time).
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import vm from "node:vm";
import { fileURLToPath } from "node:url";
import { Worker, isMainThread, parentPort, workerData } from "node:worker_threads";

const med = (a) => { const s = [...a].sort((x, y) => x - y); return s.length ? s[Math.floor(s.length / 2)] : NaN; };
function mulberry(a) { return () => { a |= 0; a = (a + 0x6D2B79F5) | 0; let t = Math.imul(a ^ (a >>> 15), 1 | a); t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t; return ((t ^ (t >>> 14)) >>> 0) / 4294967296; }; }

function runSession(s, src, seed, idx, net, layoutDir) {
  const clock = { t: 0 };
  const sandbox = { self: {}, performance: { now: () => clock.t }, Math: Object.create(Math) };
  sandbox.Math.random = mulberry(seed * 7919 + idx);
  vm.createContext(sandbox);
  vm.runInContext(src, sandbox);
  if (net) sandbox.self.createGaze.setNet(sandbox.self.createGaze.parse(net.buffer.slice(net.byteOffset, net.byteOffset + net.byteLength)));
  const g = sandbox.self.createGaze(600);
  const [w, h] = s.view;
  let sx = 0, sy = 0, mx = w / 2, my = h / 2;
  let textLines = [];
  if (layoutDir) {
    const lp = path.join(layoutDir, s.key + ".json");
    if (!fs.existsSync(lp)) return null;
    textLines = JSON.parse(fs.readFileSync(lp, "utf8")).lines.map(([x, y, w2, h2]) => ({ x, y, w: w2, h: h2 }));
  }
  g.layout({ aois: [], lines: [], textLines, view: { x: 0, y: 0, w, h } });
  const errs = [], cursor = [], centre = [], inside = [];
  let ei = 0, gi = 0;
  const end = s.gaze[s.gaze.length - 1][0];
  for (let t = 0; t <= end; t += 100) {
    for (let tt = t - 100 + 16; tt <= t; tt += 16) {
      while (ei < s.events.length && s.events[ei][0] <= tt) {
        const [et, k, x, y] = s.events[ei++];
        clock.t = et;
        if (k === "s") { sx = x; sy = y; g.view({ x: sx, y: sy, w, h }); }
        else if (k === "m") { mx = x; my = y; g.move(x, y); }
        else if (k === "c") { mx = x; my = y; g.click(x, y); } // viewport coordinates, as main.js sends
      }
      clock.t = Math.max(clock.t, tt);
      g.step(tt);
    }
    clock.t = t;
    while (gi + 1 < s.gaze.length && s.gaze[gi + 1][0] <= t) gi++;
    const [gt, tx, ty] = s.gaze[gi];
    if (Math.abs(gt - t) > 40 || t < 1000) continue;
    const e = g.estimate();
    const d = Math.hypot(e.x - tx, e.y - ty);
    errs.push(d);
    inside.push(d <= e.r50 ? 1 : 0);
    cursor.push(Math.hypot(mx + sx - tx, my + sy - ty));
    centre.push(Math.hypot(w / 2 + sx - tx, h / 2 + sy - ty));
  }
  if (errs.length < 20) return null;
  return { key: s.key, p: s.p, n: errs.length, err: med(errs), cursor: med(cursor), centre: med(centre),
    within100: errs.filter((d) => d <= 100).length / errs.length, inside: inside.reduce((a, b) => a + b, 0) / inside.length };
}

if (!isMainThread) {
  const { lines, src, seed, offset, net, layoutDir } = workerData;
  const out = lines.map((l, i) => runSession(JSON.parse(l), src, seed, offset + i, net, layoutDir)).filter(Boolean);
  parentPort.postMessage(out);
} else {
  const args = process.argv.slice(2);
  const here = path.dirname(fileURLToPath(import.meta.url));
  const gazePath = args[0] && !args[0].startsWith("--") ? args[0] : path.join(here, "..", "site", "gaze.js");
  const opt = (k) => { const i = args.indexOf(k); return i >= 0 ? args[i + 1] : null; };
  const only = opt("--participants") ? new Set(opt("--participants").split(",")) : null;
  const seed = Number(opt("--seed") || 1);
  const src = fs.readFileSync(gazePath, "utf8");
  const net = opt("--net") ? fs.readFileSync(opt("--net")) : null;      // weights for gaze-net.js
  const layoutDir = args.includes("--layout") ? path.join(here, "data", "adserp", "layouts") : null; // the pages' text
  const heldOut = opt("--held-out") ? new Set(opt("--held-out").split(",")) : null;
  let lines = fs.readFileSync(path.join(here, "data", "adserp", "sessions.jsonl"), "utf8").split("\n").filter(Boolean);
  const pOf = (l) => /"p": ?"(p\d+)"/.exec(l.slice(0, 200))[1];
  if (only) lines = lines.filter((l) => only.has(pOf(l)));
  if (heldOut) lines = lines.filter((l) => heldOut.has(pOf(l)));
  const K = Math.max(1, os.cpus().length - 1);
  const per = Math.ceil(lines.length / K);
  const parts = await Promise.all(Array.from({ length: K }, (_, k) => new Promise((res, rej) => {
    const chunk = lines.slice(k * per, (k + 1) * per);
    if (!chunk.length) return res([]);
    const w = new Worker(fileURLToPath(import.meta.url), { workerData: { lines: chunk, src, seed, offset: k * per, net, layoutDir } });
    w.once("message", res); w.once("error", rej);
  })));
  const sessions = parts.flat();
  const pick = (k) => sessions.map((x) => x[k]);
  const res = {
    gaze_js: path.relative(path.join(here, ".."), gazePath).replace(/\\/g, "/"), net: opt("--net"), layout: !!layoutDir, seed, sessions: sessions.length,
    participants: new Set(pick("p")).size,
    median_error_px: med(pick("err")), cursor_median_error_px: med(pick("cursor")), centre_median_error_px: med(pick("centre")),
    within_100px: med(pick("within100")), r50_calibration: med(pick("inside")),
  };
  console.log(JSON.stringify(res, null, 1));
  if (opt("--json")) fs.writeFileSync(opt("--json"), JSON.stringify({ ...res, per_session: sessions }, null, 1));
}
