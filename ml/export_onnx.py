"""Export the fine-tuned UI saliency model to ONNX for the browser, and check it against PyTorch.

Input:  [1, 3, 288, 448] float32, ImageNet-normalised RGB of the current viewport
Output: [1, 1, 72, 112]  float32, a probability map that sums to 1 (where the eyes are likely to be)
"""
import json, sys
from pathlib import Path
import numpy as np
import torch
import torch.nn.functional as F

ROOT = Path(__file__).parent
# load the model package without its training-time __init__ (tensorboardX, cv2 ...)
import types  # noqa: E402
_pkg = types.ModuleType("unisal")
_pkg.__path__ = [str(ROOT / "unisal" / "unisal")]
sys.modules["unisal"] = _pkg
from unisal.model import UNISAL  # noqa: E402

H, W, OH, OW = 288, 448, 72, 112


class Exportable(torch.nn.Module):
    def __init__(self, m):
        super().__init__()
        self.m = m

    def forward(self, x):
        lp = self.m(x[:, None], source="SALICON", static=True)[:, 0]
        p = lp.exp()
        p = F.avg_pool2d(p, 4)  # 288x448 -> 72x112, exactly
        return p / p.sum(dim=(2, 3), keepdim=True)


def main():
    cfg = json.load(open(ROOT / "unisal/training_runs/pretrained_unisal/UNISAL.json"))
    cfg["cnn_cfg"]["pretrained"] = False
    cfg.pop("verbose", None)
    m = UNISAL(**cfg)
    m.load_state_dict(torch.load(ROOT / "ui_unisal_best.pth", map_location="cpu"))
    m.eval()
    net = Exportable(m).eval()
    x = torch.randn(1, 3, H, W)
    out = ROOT / "ui_saliency.onnx"
    torch.onnx.export(net, x, str(out), input_names=["image"], output_names=["saliency"], opset_version=17, dynamo=False)
    import onnxruntime as ort
    sess = ort.InferenceSession(str(out), providers=["CPUExecutionProvider"])
    with torch.no_grad():
        ref = net(x).numpy()
    got = sess.run(None, {"image": x.numpy()})[0]
    print("max abs diff vs PyTorch:", float(np.abs(ref - got).max()), "| sum", float(got.sum()))
    print("onnx size MB:", round(out.stat().st_size / 1e6, 2))


if __name__ == "__main__":
    main()
