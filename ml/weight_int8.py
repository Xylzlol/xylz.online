"""Weight-only int8 storage: every large float initializer becomes int8 + a per-output-channel scale,
followed by DequantizeLinear. ONNX Runtime folds the DequantizeLinear into plain float weights when
the session is created, so inference runs at fp32 speed while the file is ~4x smaller.
Checked on the held-out UEyes test split like the other variants."""
import numpy as np, onnx
from onnx import helper, numpy_helper, TensorProto

m = onnx.load("ui_saliency.onnx")
g = m.graph
inits = {i.name: i for i in g.initializer}
used_as_weight = {}
for node in g.node:
    if node.op_type in ("Conv", "ConvTranspose", "Gemm", "MatMul") and len(node.input) > 1:
        used_as_weight[node.input[1]] = node.op_type

new_inits, new_nodes, saved = [], [], 0
for name, op in used_as_weight.items():
    if name not in inits:
        continue
    w = numpy_helper.to_array(inits[name]).astype(np.float32)
    if w.size < 1024:
        continue
    axis = 0 if op in ("Conv", "Gemm") else (1 if op == "ConvTranspose" else w.ndim - 1)
    red = tuple(i for i in range(w.ndim) if i != axis)
    scale = np.abs(w).max(axis=red) / 127.0
    scale[scale == 0] = 1e-8
    shape = [1] * w.ndim
    shape[axis] = -1
    q = np.clip(np.round(w / scale.reshape(shape)), -127, 127).astype(np.int8)
    g.initializer.remove(inits[name])
    qn, sn, zn = name + "_q", name + "_scale", name + "_zp"
    new_inits += [numpy_helper.from_array(q, qn), numpy_helper.from_array(scale.astype(np.float32), sn),
                  numpy_helper.from_array(np.zeros_like(scale, dtype=np.int8), zn)]
    new_nodes.append(helper.make_node("DequantizeLinear", [qn, sn, zn], [name], axis=axis, name=name + "_dq"))
    saved += w.nbytes - q.nbytes
g.initializer.extend(new_inits)
for n_ in reversed(new_nodes):
    g.node.insert(0, n_)
onnx.checker.check_model(m)
onnx.save(m, "ui_saliency_w8.onnx")
print("saved", round(saved / 1e6, 2), "MB")
