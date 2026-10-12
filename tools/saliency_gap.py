"""Audit of the saliency input. The page cannot screenshot itself, so it re-draws the viewport (field,
the name's lit cells, rules, the lock, every word) and sends that sketch to the network. How much does
the sketch change the network's answer compared with a real screenshot of the same view?
For several views (fields, scroll positions): capture the real screenshot and the page's own sketch
(?debug exposes the picture the worker read), run the shipped ONNX model on both, compare.
Also: a bootstrap confidence interval for the shipped model's held-out webpage CC."""
import base64, io, json, pathlib, subprocess, sys, tempfile, time, urllib.request
import numpy as np
import onnxruntime as ort
import websocket
from PIL import Image

tools = pathlib.Path(__file__).parent
site = tools.parent / "site"
out = tools.parent / ".impeccable" / "review" / "saliency"
out.mkdir(parents=True, exist_ok=True)
W, H = 448, 288
MEAN = np.array([0.485, 0.456, 0.406], np.float32)[:, None, None]
STD = np.array([0.229, 0.224, 0.225], np.float32)[:, None, None]
sess = ort.InferenceSession(str(site / "models" / "ui_saliency.onnx"), providers=["CPUExecutionProvider"])


def run(rgb):  # rgb: H x W x 3 uint8
    x = (rgb.astype(np.float32).transpose(2, 0, 1) / 255 - MEAN) / STD
    m = sess.run(None, {"image": x[None]})[0].reshape(72, 112).astype(np.float64)
    return m / m.sum()


def cc(a, b):
    a = (a - a.mean()) / a.std(); b = (b - b.mean()) / b.std()
    return float((a * b).mean())


def kld(p, q, eps=1e-7):  # KL(p || q), p the reference
    return float((p * np.log(eps + p / (q + eps))).sum())


chrome = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
profile = pathlib.Path(tempfile.mkdtemp(prefix="xylz-sal-"))
proc = subprocess.Popen([chrome, "--headless=new", "--hide-scrollbars", "--no-first-run", "--remote-allow-origins=*",
                         "--remote-debugging-port=0", f"--user-data-dir={profile}", "about:blank"],
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=subprocess.CREATE_NO_WINDOW)
VIEWS = [("white top", "", 0), ("sky top", "#work", 0), ("black top", "#github", 0), ("magenta top", "#x", 0),
         ("white public work", "", 950), ("white elsewhere", "", 99999)]
rows = []
try:
    pf = profile / "DevToolsActivePort"
    for _ in range(100):
        if pf.exists() and pf.read_text().strip():
            break
        time.sleep(0.1)
    port = pf.read_text().splitlines()[0]
    tgt = next(t for t in json.load(urllib.request.urlopen(f"http://127.0.0.1:{port}/json")) if t["type"] == "page")
    ws = websocket.create_connection(tgt["webSocketDebuggerUrl"], timeout=120)
    n = [0]

    def call(m, p=None):
        n[0] += 1
        i = n[0]
        ws.send(json.dumps({"id": i, "method": m, "params": p or {}}))
        while True:
            msg = json.loads(ws.recv())
            if msg.get("id") == i:
                if "error" in msg:
                    raise RuntimeError(msg["error"])
                return msg.get("result", {})

    def js(e):
        return call("Runtime.evaluate", {"expression": e, "returnByValue": True, "awaitPromise": True})["result"].get("value")

    call("Page.enable"); call("Runtime.enable")
    call("Emulation.setDeviceMetricsOverride", {"width": 1440, "height": 900, "deviceScaleFactor": 1, "mobile": False})
    for name, hsh, sy in VIEWS:
        call("Page.navigate", {"url": "about:blank"}); time.sleep(0.2)
        call("Page.navigate", {"url": "http://localhost:8765/?debug" + hsh}); time.sleep(2.5)
        if sy:
            js(f"window.scrollTo(0, {sy})"); time.sleep(0.4)
        # the page re-shoots after scroll (160ms) and the network answers in ~150ms; wait for a map
        # whose view matches this scroll position
        js("window.__sal = null")
        call("Input.dispatchMouseEvent", {"type": "mouseMoved", "x": 700, "y": 450})
        js("window.dispatchEvent(new Event('scroll'))")
        sketch = None
        for _ in range(60):
            time.sleep(0.25)
            s = js("window.__sal && window.__sal.pic ? JSON.stringify({pic: window.__sal.pic.length}) : null")
            if s:
                sketch = js("window.__sal.pic")
                break
        if sketch is None:
            print(name, "no sketch from the page (model not loaded?)"); continue
        sk = np.array(sketch, np.uint8).reshape(H, W, 4)[:, :, :3]
        # the real view, without the tracker overlay and the gaze display (they are not page content)
        js("document.querySelector('.tracker').style.visibility='hidden'; document.querySelectorAll('.gaze-cloud').forEach(e => e.style.visibility='hidden')")
        time.sleep(0.15)
        shot = call("Page.captureScreenshot", {"format": "png"})["data"]
        js("document.querySelector('.tracker').style.visibility=''")
        real = np.asarray(Image.open(io.BytesIO(base64.b64decode(shot))).convert("RGB").resize((W, H), Image.BICUBIC))
        mr, ms = run(real), run(sk)
        rows.append((name, cc(mr, ms), kld(mr, ms)))
        tag = name.replace(" ", "-")
        Image.fromarray(real).save(out / f"{tag}-real.png"); Image.fromarray(sk).save(out / f"{tag}-sketch.png")
        for lab, m in (("real", mr), ("sketch", ms)):
            Image.fromarray((255 * m / m.max()).astype(np.uint8)).resize((W, H), Image.BILINEAR).save(out / f"{tag}-map-{lab}.png")
        print(f"{name:20s} CC(real map, sketch map) = {rows[-1][1]:.3f}   KL(real || sketch) = {rows[-1][2]:.3f}", flush=True)
finally:
    proc.terminate()
if rows:
    print("mean CC", round(float(np.mean([r[1] for r in rows])), 3), " mean KL", round(float(np.mean([r[2] for r in rows])), 3))
