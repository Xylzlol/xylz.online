"""Quantise the UI saliency model to int8 (static, calibrated on UEyes training screenshots) and
measure every variant on the held-out UEyes test split with the training metrics, so the smaller
file only ships if it keeps the quality. Also times each variant on the CPU."""
import csv, time
from pathlib import Path
import numpy as np
import onnxruntime as ort
from PIL import Image
from onnxruntime.quantization import CalibrationDataReader, QuantFormat, QuantType, quantize_static
from onnxruntime.quantization.shape_inference import quant_pre_process

D = Path("data/UEyes_dataset")
H, W = 288, 448
MEAN = np.array([0.485, 0.456, 0.406], np.float32).reshape(3, 1, 1)
STD = np.array([0.229, 0.224, 0.225], np.float32).reshape(3, 1, 1)
rows = list(csv.DictReader(open(D / "image_types.csv", encoding="utf-8-sig"), delimiter=";"))
keep = [r for r in rows if r["Category"] in ("web", "desktop")]
train = [r for r in keep if r["Train/Test"] == "Train"]
test = [r for r in keep if r["Train/Test"] == "Test"]


def img(name):
    x = np.asarray(Image.open(D / "images" / name).convert("RGB").resize((W, H), Image.BICUBIC), np.float32) / 255
    return ((x.transpose(2, 0, 1) - MEAN) / STD)[None].astype(np.float32)


def target(name):
    s = np.asarray(Image.open(D / "saliency_maps/heatmaps_3s" / name).convert("L").resize((112, 72), Image.BILINEAR), np.float64)
    s = s / max(s.sum(), 1e-9)
    f = np.asarray(Image.open(D / "saliency_maps/fixmaps_3s" / name).convert("L"), np.uint8) > 0
    # fixations at 112x72 by max-pooling the binary map
    fh, fw = f.shape
    ys = (np.arange(fh) * 72 // fh)
    xs = (np.arange(fw) * 112 // fw)
    fx = np.zeros((72, 112), bool)
    yy, xx = np.nonzero(f)
    fx[ys[yy], xs[xx]] = True
    return s, fx


def metrics(p, s, fx):
    p = p.astype(np.float64).reshape(72, 112)
    p = p / p.sum()
    eps = 1e-12
    kld = float((s * np.log(eps + s / (p + eps))).sum())
    cc = float(np.corrcoef(p.ravel(), s.ravel())[0, 1])
    z = (p - p.mean()) / (p.std() + eps)
    nss = float(z[fx].mean()) if fx.any() else float("nan")
    return kld, cc, nss


class Calib(CalibrationDataReader):
    def __init__(self, items):
        self.it = iter([{"image": img(r["Image Name"])} for r in items])

    def get_next(self):
        return next(self.it, None)


rng = np.random.RandomState(1)
calib = [train[i] for i in rng.choice(len(train), 120, replace=False)]
quant_pre_process("ui_saliency.onnx", "ui_saliency_pre.onnx", skip_symbolic_shape=True)
quantize_static("ui_saliency_pre.onnx", "ui_saliency_int8.onnx", Calib(calib), quant_format=QuantFormat.QDQ,
                per_channel=True, activation_type=QuantType.QUInt8, weight_type=QuantType.QInt8)

variants = {"fp32": "ui_saliency.onnx", "fp16": "ui_saliency_fp16.onnx", "int8": "ui_saliency_int8.onnx"}
so = ort.SessionOptions()
so.intra_op_num_threads = 1  # like the browser worker without cross-origin isolation
tests = [(img(r["Image Name"]), *target(r["Image Name"]), r["Category"]) for r in test]
for name, path in variants.items():
    sess = ort.InferenceSession(path, so, providers=["CPUExecutionProvider"])
    out = []
    t0 = time.time()
    for x, s, fx, cat in tests:
        p = sess.run(None, {"image": x})[0]
        out.append((*metrics(p, s, fx), cat))
    ms = (time.time() - t0) / len(tests) * 1000
    web = [o for o in out if o[3] == "web"]
    mean = lambda arr, i: np.nanmean([a[i] for a in arr])
    print(f"{name:5s} {Path(path).stat().st_size/1e6:5.2f} MB  {ms:6.0f} ms/img  |  web: KLD {mean(web,0):.3f} CC {mean(web,1):.3f} NSS {mean(web,2):.3f}"
          f"  |  web+desktop: KLD {mean(out,0):.3f} CC {mean(out,1):.3f} NSS {mean(out,2):.3f}")
