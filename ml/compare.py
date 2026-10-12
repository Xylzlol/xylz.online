"""Paired comparison of two runs on the same held-out pages: the mean difference per metric and a
95% bootstrap interval (10,000 resamples of pages). A run beats the baseline only if the interval
excludes zero in its favour.  python compare.py baseline NAME"""
import json, sys
from pathlib import Path
import numpy as np

R = Path(__file__).parent / "runs"
a = json.load(open(R / f"{sys.argv[1]}.json")); b = json.load(open(R / f"{sys.argv[2]}.json"))
assert a["names"] == b["names"], "the two runs were scored on different pages"
rng = np.random.default_rng(0)
for sub in ("all", "web"):
    idx = np.array([i for i, c in enumerate(a["cats"]) if sub == "all" or c == sub])
    print(f"{sub} ({len(idx)} pages)")
    for m, better in (("cc", 1), ("nss", 1), ("kld", -1)):
        x = np.array([a["per"][i][m] for i in idx]); y = np.array([b["per"][i][m] for i in idx])
        d = y - x
        boot = np.array([d[rng.integers(0, len(d), len(d))].mean() for _ in range(10000)])
        lo, hi = np.percentile(boot, [2.5, 97.5])
        wins = int(((d * better) > 0).sum())
        verdict = "better" if (lo * better > 0 and hi * better > 0) else ("worse" if (lo * better < 0 and hi * better < 0) else "no clear difference")
        print(f"  {m:4s} {x.mean():.4f} -> {y.mean():.4f}  diff {d.mean():+.4f}  95% CI [{lo:+.4f}, {hi:+.4f}]  better on {wins}/{len(d)} pages  {verdict}")
