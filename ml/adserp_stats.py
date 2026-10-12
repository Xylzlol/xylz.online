"""What the pointer actually says about the eyes, measured on AdSERP (all sessions, CSS px):
  - gaze minus cursor at lags: where the eyes are relative to where the hand was L ms earlier/later
  - spread in x and y, and how it grows with the time since the hand last moved
  - the same around presses
These replace the hand-set constants in gaze.js (700 ms lag, sigma 110/60 px, idle growth)."""
import json, os
import numpy as np

D = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "adserp")
rows = []  # (dt_since_move, dx, dy) at lag 0; and lagged distances
lags = [-1500, -1000, -700, -400, -200, 0, 200, 400, 700, 1000]
lagd = {L: [] for L in lags}
with open(os.path.join(D, "sessions.jsonl"), encoding="utf-8") as f:
    for line in f:
        s = json.loads(line)
        ev = [e for e in s["events"] if e[1] in "mc"]
        sc = [e for e in s["events"] if e[1] == "s"]
        if len(ev) < 5:
            continue
        et = np.array([e[0] for e in ev]); ex = np.array([e[2] for e in ev]); ey = np.array([e[3] for e in ev])
        st = np.array([e[0] for e in sc]) if sc else np.array([0]); sy = np.array([e[3] for e in sc]) if sc else np.array([0.0])
        g = np.array(s["gaze"])[::10]  # ~15 Hz is plenty
        for t, gx, gy in g:
            if t < 1000:
                continue
            k = np.searchsorted(st, t, "right") - 1
            scroll = sy[k] if k >= 0 else 0.0
            i = np.searchsorted(et, t, "right") - 1
            if i < 0:
                continue
            rows.append((t - et[i], gx - ex[i], gy - (ey[i] + scroll)))
            for L in lags:
                j = np.searchsorted(et, t - L, "right") - 1
                if j >= 0:
                    lagd[L].append(np.hypot(gx - ex[j], gy - (ey[j] + scroll)))
R = np.array(rows)
print("samples", len(R))
print("median |gaze - cursor(t - L)| by L (negative L = the cursor's FUTURE position):")
for L in lags:
    print(f"  L {L:6d} ms: {np.median(lagd[L]):6.0f} px")
print("spread of gaze - cursor, by time since the hand last moved (median abs dx, dy; share within 100 px):")
for lo, hi in [(0, 100), (100, 300), (300, 700), (700, 1500), (1500, 4000), (4000, 1e9)]:
    m = (R[:, 0] >= lo) & (R[:, 0] < hi)
    if m.sum() < 50:
        continue
    d = np.hypot(R[m, 1], R[m, 2])
    print(f"  still {lo:5.0f}-{hi:7.0f} ms: n {m.sum():7d}  |dx| {np.median(np.abs(R[m,1])):5.0f}  |dy| {np.median(np.abs(R[m,2])):5.0f}  "
          f"mean dx {np.mean(R[m,1]):+6.0f}  mean dy {np.mean(R[m,2]):+6.0f}  within100 {np.mean(d < 100):.2f}")
