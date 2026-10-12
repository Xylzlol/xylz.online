"""AdSERP -> replay sessions for the gaze certificate (data/adserp/sessions.jsonl).
Per session: viewport, the mouse/scroll/press event stream and the true gaze, all in page CSS px on
the session's own clock (ms from start). Gaze is mapped from eye-tracker pixels with the fit found by
adserp_align.py on mouse presses: gaze_px = 0.903 * css_px - (14.8, 11.4); the page ran at 90% zoom.
Run with python -I from the ml folder."""
import csv, glob, json, os, re

D = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "adserp")
K, OX, OY = 0.903, 14.8, 11.4
F = lambda v: float(v)
out = open(os.path.join(D, "sessions.jsonl"), "w", encoding="utf-8")
n = 0
for f in sorted(glob.glob(os.path.join(D, "mouse", "mouse-movement-data", "*.csv"))):
    key = os.path.basename(f)
    gp = os.path.join(D, "pupil", "pupil-data", key)
    if not os.path.exists(gp):
        continue
    meta = open(os.path.join(D, "meta", "trial-metadata", key.replace(".csv", ".xml")), encoding="utf-8").read()
    wm = re.search(r"<window>(\d+)x(\d+)</window>", meta)
    w, h = (int(wm.group(1)), int(wm.group(2))) if wm else (1422, 1137)
    ms = list(csv.reader(open(f, encoding="utf-8")))[1:]
    gz = list(csv.reader(open(gp, encoding="utf-8")))[1:]
    if not ms or not gz:
        continue
    t0 = int(F(ms[0][0]))
    ev, sy, sx = [], 0.0, 0.0
    scroll = []  # (t, scrollY) for mapping gaze into page coordinates
    for r in ms:
        t, x, y, e = int(F(r[0])) - t0, F(r[1]), F(r[2]), r[3]
        if e == "scroll":
            sx, sy = x, y
            scroll.append((t, sy))
            ev.append([t, "s", round(x, 1), round(y, 1)])
        elif e == "mousemove":
            ev.append([t, "m", round(x, 1), round(y, 1)])
        elif e == "mousedown":
            ev.append([t, "c", round(x, 1), round(y, 1)])
    gaze, k, cur = [], 0, 0.0
    for r in gz:
        t = int(F(r[0])) - t0
        while k < len(scroll) and scroll[k][0] <= t:
            cur = scroll[k][1]; k += 1
        gx, gy = F(r[1]), F(r[2])
        if gx <= 0 or gy <= 0:
            continue  # tracker lost the eye
        gaze.append([t, round((gx + OX) / K, 1), round((gy + OY) / K + cur, 1)])
    if len(gaze) < 50 or len(ev) < 10:
        continue
    out.write(json.dumps({"key": key[:-4], "p": key.split("-")[0], "view": [w, h], "events": ev, "gaze": gaze}) + "\n")
    n += 1
out.close()
print("sessions", n)
