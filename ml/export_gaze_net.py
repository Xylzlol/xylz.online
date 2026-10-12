"""Trained gaze model (runs/NAME.pt from gaze_mdn.py) -> site/gaze-net.bin for site/gaze-net.js:
8-bit weights with one float scale per output row (symmetric, max-abs), float biases.
  python export_gaze_net.py NAME [--abs-dropped] [--view-dropped] [--no-layout] [--out PATH]"""
import os, struct, sys
import numpy as np
import torch

ML = os.path.dirname(os.path.abspath(__file__))
name = sys.argv[1]
flags = (1 if "--abs-dropped" in sys.argv else 0) | (2 if "--view-dropped" in sys.argv else 0) | (4 if "--no-layout" in sys.argv else 0)
out = sys.argv[sys.argv.index("--out") + 1] if "--out" in sys.argv else os.path.join(ML, "..", "site", "gaze-net.bin")
sd = torch.load(os.path.join(ML, "runs", f"{name}.pt"), map_location="cpu")
lin = sorted({k.split(".")[0] for k in sd if k.endswith(".weight")}, key=int)
K = sd[f"{lin[-1]}.weight"].shape[0] // 5
buf = bytearray(b"GZN1") + struct.pack("<III", len(lin), K, flags)
err = 0.0
for l in lin:
    W = sd[f"{l}.weight"].numpy().astype(np.float32); b = sd[f"{l}.bias"].numpy().astype(np.float32)
    scale = np.abs(W).max(1) / 127.0; scale[scale == 0] = 1e-8
    q = np.clip(np.round(W / scale[:, None]), -127, 127).astype(np.int8)
    err = max(err, float(np.abs(q * scale[:, None] - W).max()))
    buf += struct.pack("<II", W.shape[1], W.shape[0]) + scale.astype("<f4").tobytes() + b.astype("<f4").tobytes() + q.tobytes()
open(out, "wb").write(bytes(buf))
print(f"{out}: {len(buf)} bytes, {len(lin)} layers, K={K}, flags={flags}, max weight error {err:.5f}")
