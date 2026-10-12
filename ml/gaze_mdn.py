"""A learned pointer-to-gaze model for the site's live estimate, trained on AdSERP.

Every 100 ms (the certificate's grid): features from the pointer stream so far -> a mixture of K
Gaussians over where the eyes are, relative to the cursor. People are split, not samples: 10 held out
for test, 5 for model selection, the rest for training, so the score is for someone never seen.

  python -I gaze_mdn.py build        # features -> data/adserp/mdn.npz
  python -I gaze_mdn.py train NAME   # train, report test metrics in the certificate's terms
"""
import json, math, os, sys, time
import numpy as np

ML = os.path.dirname(os.path.abspath(__file__))
D = os.path.join(ML, "data", "adserp")
LAGS = [100, 200, 400, 700, 1000, 1500, 2000]
NF = 2 + 2 * len(LAGS) + 1 + 3 + 3 + 1


LOCAL_C, LOCAL_R, CELL = 9, 7, 80   # text around the cursor: 9 x 7 cells of 80 px, cursor in the middle
VIEW_C, VIEW_R = 8, 6                 # text over the whole viewport, coarse
NL = LOCAL_C * LOCAL_R + VIEW_C * VIEW_R


class TextGrid:
    """text line boxes in page px -> a coverage raster at 20 px, for fast box sums"""
    def __init__(self, lines, doc_w, doc_h, res=20):
        self.res = res
        self.w, self.h = doc_w // res + 2, doc_h // res + 2
        g = np.zeros((self.h, self.w), np.float32)
        for x, y, w, h, *_ in lines:
            x0, y0 = max(0, x // res), max(0, y // res)
            x1, y1 = min(self.w, (x + w) // res + 1), min(self.h, (y + h) // res + 1)
            g[y0:y1, x0:x1] = 1.0
        self.sat = np.pad(g, ((1, 0), (1, 0))).cumsum(0).cumsum(1)

    def cover(self, x0, y0, x1, y1):
        r = self.res
        a, b = int(np.clip(x0 // r, 0, self.w)), int(np.clip(y0 // r, 0, self.h))
        c, d = int(np.clip(x1 // r, 0, self.w)), int(np.clip(y1 // r, 0, self.h))
        if c <= a or d <= b:
            return 0.0
        S = self.sat
        return float(S[d, c] - S[b, c] - S[d, a] + S[b, a]) / ((c - a) * (d - b))


def layout_features(tg, px, py, sx, sy, w, h):
    f = []
    for j in range(LOCAL_R):
        for i in range(LOCAL_C):
            x0 = px + (i - LOCAL_C / 2) * CELL; y0 = py + (j - LOCAL_R / 2) * CELL
            f.append(tg.cover(x0, y0, x0 + CELL, y0 + CELL) if tg else 0.0)
    for j in range(VIEW_R):
        for i in range(VIEW_C):
            x0 = sx + i * w / VIEW_C; y0 = sy + j * h / VIEW_R
            f.append(tg.cover(x0, y0, x0 + w / VIEW_C, y0 + h / VIEW_R) if tg else 0.0)
    return f


def features(s, tg=None, with_layout=False):
    """yields (t, feature vector, target dx, dy, cursor page x, y) every 100 ms"""
    w, h = s["view"]
    ev = s["events"]
    gaze = s["gaze"]
    hist = []  # (t, x, y) cursor history, viewport px
    sx = sy = 0.0
    scrolls = [(0, 0.0)]
    last_move, last_click, click = -1e9, -1e9, (0.0, 0.0)
    ei = gi = 0
    end = gaze[-1][0]
    for t in range(0, end + 1, 100):
        while ei < len(ev) and ev[ei][0] <= t:
            et, k, x, y = ev[ei]; ei += 1
            if k == "s":
                sx, sy = x, y; scrolls.append((et, y))
            else:
                hist.append((et, x, y)); last_move = et
                if k == "c":
                    last_click, click = et, (x, y)
        while gi + 1 < len(gaze) and gaze[gi + 1][0] <= t:
            gi += 1
        gt, gx, gy = gaze[gi]
        if abs(gt - t) > 40 or t < 1000 or not hist:
            continue
        cx, cy = hist[-1][1], hist[-1][2]
        f = [cx / w, cy / h]
        j = len(hist) - 1
        for L in LAGS:  # where the cursor was L ms ago, relative to now
            while j > 0 and hist[j][0] > t - L:
                j -= 1
            f += [(hist[j][1] - cx) / w, (hist[j][2] - cy) / h]
        f.append(math.log1p(max(0, t - last_move)) / 8)
        dc = t - last_click
        f += [math.log1p(min(dc, 60000)) / 11, (click[0] - cx) / w if dc < 3000 else 0.0, (click[1] - cy) / h if dc < 3000 else 0.0]
        k2 = len(scrolls) - 1
        while k2 > 0 and scrolls[k2][0] > t - 500:
            k2 -= 1
        f += [sy / 3000, (sy - scrolls[k2][1]) / 500, math.log1p(min(t - scrolls[-1][0], 60000)) / 11]
        f.append(math.log1p(t) / 11)
        if with_layout:
            f += layout_features(tg, cx + sx, cy + sy, sx, sy, w, h)
        yield t, f, (gx - (cx + sx)) / 1000, (gy - (cy + sy)) / 1000, cx + sx, cy + sy


def build(with_layout=False):
    X, Y, S, P = [], [], [], []
    sid = 0
    missing = 0
    with open(os.path.join(D, "sessions.jsonl"), encoding="utf-8") as fh:
        for line in fh:
            s = json.loads(line)
            tg = None
            if with_layout:
                lp = os.path.join(D, "layouts", s["key"] + ".json")
                if not os.path.exists(lp):
                    missing += 1; sid += 1
                    continue
                lay = json.load(open(lp, encoding="utf-8"))
                tg = TextGrid(lay["lines"], lay["doc"][0], lay["doc"][1])
            for t, f, dx, dy, px, py in features(s, tg, with_layout):
                X.append(f); Y.append((dx, dy)); S.append(sid); P.append(int(s["p"][1:]))
            sid += 1
    X = np.array(X, np.float32); Y = np.array(Y, np.float32)
    name = "mdn_layout.npz" if with_layout else "mdn.npz"
    np.savez_compressed(os.path.join(D, name), X=X, Y=Y, S=np.array(S, np.int32), P=np.array(P, np.int16))
    if with_layout:
        print("sessions without a layout:", missing)
    print("samples", len(X), "features", X.shape[1], "sessions", sid, "people", len(set(P)))


def split(P):
    people = sorted(set(P.tolist()))
    rng = np.random.RandomState(7)
    rng.shuffle(people)
    return set(people[:10]), set(people[10:15])


def train(name, K=6, hidden=128, epochs=40, data="mdn.npz", drop=()):
    import torch, torch.nn as nn
    torch.manual_seed(0)
    z = np.load(os.path.join(D, data))
    X, Y, S, P = z["X"], z["Y"], z["S"], z["P"]
    if drop:  # feature groups left out, to see what the score depends on
        groups = {"abs": [0, 1], "view": list(range(24 + LOCAL_C * LOCAL_R, 24 + NL))}
        cols = [c for g in drop for c in groups[g] if c < X.shape[1]]
        X = np.delete(X, cols, axis=1)
    test_p, val_p = split(P)
    te = np.isin(P, list(test_p)); va = np.isin(P, list(val_p)); tr = ~(te | va)
    Xt, Yt = torch.tensor(X[tr]), torch.tensor(Y[tr])
    net = nn.Sequential(nn.Linear(X.shape[1], hidden), nn.GELU(), nn.Linear(hidden, hidden), nn.GELU(),
                        nn.Linear(hidden, hidden), nn.GELU(), nn.Linear(hidden, K * 5))

    def mix(o):
        o = o.view(-1, K, 5)
        logpi = torch.log_softmax(o[..., 0], -1)
        mu = o[..., 1:3]
        logs = o[..., 3:5].clamp(-5, 2)
        return logpi, mu, logs

    def nll(o, y):
        logpi, mu, logs = mix(o)
        d = (y[:, None, :] - mu) / logs.exp()
        lp = -0.5 * (d * d).sum(-1) - logs.sum(-1) - math.log(2 * math.pi)
        return -torch.logsumexp(logpi + lp, -1).mean()

    opt = torch.optim.AdamW(net.parameters(), lr=2e-3, weight_decay=1e-4)
    sched = torch.optim.lr_scheduler.CosineAnnealingLR(opt, epochs)
    Xv, Yv = torch.tensor(X[va]), torch.tensor(Y[va])
    best, state = 1e9, None
    t0 = time.time()
    for ep in range(epochs):
        net.train()
        perm = torch.randperm(len(Xt))
        for i in range(0, len(perm), 4096):
            idx = perm[i:i + 4096]
            loss = nll(net(Xt[idx]), Yt[idx])
            opt.zero_grad(); loss.backward(); opt.step()
        sched.step()
        net.eval()
        with torch.no_grad():
            v = nll(net(Xv), Yv).item()
        if v < best:
            best, state = v, {k: t.clone() for k, t in net.state_dict().items()}
        print(f"{name} epoch {ep:2d} val nll {v:.4f}  {time.time() - t0:.0f}s", flush=True)
    net.load_state_dict(state)
    torch.save(state, os.path.join(ML, "runs", f"{name}.pt"))

    # test, in the certificate's terms: per session the median distance from the estimate to the true
    # gaze and how often the stated 50% radius holds it; then the median over sessions
    Xe, Ye, Se = torch.tensor(X[te]), Y[te], S[te]
    with torch.no_grad():
        logpi, mu, logs = mix(net(Xe))
    pi = logpi.exp().numpy(); mu = mu.numpy(); sg = logs.exp().numpy()
    # the estimate: the highest-density point, searched from each component mean
    n = len(Xe)
    rng = np.random.default_rng(0)
    def dens(px, py):
        d = ((px[:, None] - mu[:, :, 0]) / sg[:, :, 0]) ** 2 + ((py[:, None] - mu[:, :, 1]) / sg[:, :, 1]) ** 2
        return (pi / (2 * math.pi * sg[:, :, 0] * sg[:, :, 1]) * np.exp(-0.5 * d)).sum(1)
    best_d = np.full(n, -1.0); est = np.zeros((n, 2))
    for k in range(K):
        dk = dens(mu[:, k, 0], mu[:, k, 1])
        better = dk > best_d
        best_d[better] = dk[better]; est[better] = mu[better, k]
    err = np.hypot(est[:, 0] - Ye[:, 0], est[:, 1] - Ye[:, 1]) * 1000
    # r50 by sampling the mixture
    M = 256
    comp = np.array([rng.choice(K, M, p=p / p.sum()) for p in pi])
    rows = np.arange(n)[:, None]
    smp = mu[rows, comp] + sg[rows, comp] * rng.standard_normal((n, M, 2))
    r = np.hypot(smp[..., 0] - est[:, None, 0], smp[..., 1] - est[:, None, 1])
    r50 = np.median(r, 1)
    inside = (err / 1000) <= r50
    cursor = np.hypot(Ye[:, 0], Ye[:, 1]) * 1000
    med = lambda a: float(np.median(a))
    per = {}
    for i, s in enumerate(Se):
        per.setdefault(int(s), []).append(i)
    sess = [v for v in per.values() if len(v) >= 20]
    res = {"name": name, "test_people": len(test_p), "test_sessions": len(sess),
           "median_error_px": med([med(err[v]) for v in sess]), "cursor_median_error_px": med([med(cursor[v]) for v in sess]),
           "within_100px": med([float(np.mean(err[v] <= 100)) for v in sess]), "r50_calibration": med([float(np.mean(inside[v])) for v in sess]),
           "params": int(sum(p.numel() for p in net.parameters()))}
    json.dump(res, open(os.path.join(ML, "runs", f"{name}.json"), "w"), indent=1)
    print(json.dumps(res, indent=1))


if __name__ == "__main__":
    os.makedirs(os.path.join(ML, "runs"), exist_ok=True)
    if sys.argv[1] == "build":
        build()
    elif sys.argv[1] == "build_layout":
        build(with_layout=True)
    else:
        train(sys.argv[2], **(json.loads(sys.argv[3]) if len(sys.argv) > 3 else {}))
