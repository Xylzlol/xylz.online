# Store the weights as float16 (half the download); inputs and outputs stay float32. Checked against fp32.
import numpy as np, onnx, onnxruntime as ort
from onnxconverter_common import float16
m = onnx.load("ui_saliency.onnx")
m16 = float16.convert_float_to_float16(m, keep_io_types=True)
onnx.save(m16, "ui_saliency_fp16.onnx")
x = np.random.RandomState(0).randn(1, 3, 288, 448).astype(np.float32)
a = ort.InferenceSession("ui_saliency.onnx").run(None, {"image": x})[0]
b = ort.InferenceSession("ui_saliency_fp16.onnx").run(None, {"image": x})[0]
cc = np.corrcoef(a.ravel(), b.ravel())[0, 1]
import os
print("fp16 vs fp32 correlation:", round(float(cc), 6), "| size MB:", round(os.path.getsize("ui_saliency_fp16.onnx") / 1e6, 2))
