"""AdSERP: find how gaze (eye-tracker pixels) relates to mouse coordinates (page or viewport pixels),
and the eye-hand lag, from all sessions. Robust least squares per axis, for several hypotheses about
scroll and several lags; reports slope, offset and median residual for each.
Run with python -I from the ml folder."""
import bisect, csv, glob, os
import numpy as np

D = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "adserp")
I = lambda v: int(float(v))


def session(key):
    ms = list(csv.reader(open(os.path.join(D, "mouse", "mouse-movement-data", key), encoding="utf-8")))[1:]
    gz = list(csv.reader(open(os.path.join(D, "pupil", "pupil-data", key), encoding="utf-8")))[1:]
    return ms, gz


def pairs(lag):
    """(mouse page x, page y, scrollY, gaze x, gaze y) for mouse moves, gaze taken lag ms earlier"""
    out = []
    keys = sorted(os.path.basename(f) for f in glob.glob(os.path.join(D, "mouse", "mouse-movement-data", "*.csv")))
    for key in keys[::3]:
        try:
            ms, gz = session(key)
        except FileNotFoundError:
            continue
        gt = [I(r[0]) for r in gz]
        sy = 0
        for r in ms:
            t, x, y, e = I(r[0]), I(r[1]), I(r[2]), r[3]
            if e == "scroll":
                sy = y
                continue
            if e != "mousemove":
                continue
            i = bisect.bisect_right(gt, t - lag) - 1
            if i < 0 or abs(gt[i] - (t - lag)) > 30:
                continue
            gx, gy = I(gz[i][1]), I(gz[i][2])
            if gx <= 0 or gy <= 0:
                continue
            out.append((x, y, sy, gx, gy))
    return np.array(out, float)


def robust(a, b):
    m = np.ones(len(a), bool)
    for _ in range(10):
        A = np.c_[a[m], np.ones(m.sum())]
        k = np.linalg.lstsq(A, b[m], rcond=None)[0]
        r = np.abs(k[0] * a + k[1] - b)
        m = r < np.percentile(r, 50)
    return k, np.median(r)


for lag in (0, 300, 700):
    P = pairs(lag)
    print(f"lag {lag} ms: {len(P)} pairs")
    for name, my in (("y as logged", P[:, 1]), ("y minus scroll", P[:, 1] - P[:, 2]), ("y plus scroll", P[:, 1] + P[:, 2])):
        kx, rx = robust(P[:, 0], P[:, 3])
        ky, ry = robust(my, P[:, 4])
        print(f"  {name:15s} gx = {kx[0]:.3f} mx {kx[1]:+.0f} (med {rx:.0f})   gy = {ky[0]:.3f} my {ky[1]:+.0f} (med {ry:.0f})")
    print("  corr x", np.corrcoef(P[:, 0], P[:, 3])[0, 1].round(3), " corr y (minus scroll)", np.corrcoef(P[:, 1] - P[:, 2], P[:, 4])[0, 1].round(3))
