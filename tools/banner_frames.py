"""Frames of the animated profile banner at chosen times (its CSS animations paused and set exactly),
stacked into one PNG for review. Usage: banner_frames.py banner.svg out.png t1 t2 ..."""
import base64, io, json, pathlib, shutil, subprocess, sys, tempfile, time, urllib.request
import websocket
from PIL import Image

svg, out, times = pathlib.Path(sys.argv[1]).resolve(), sys.argv[2], [float(t) for t in sys.argv[3:]]
chrome = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
profile = pathlib.Path(tempfile.mkdtemp(prefix="xylz-banner-"))
proc = subprocess.Popen([chrome, "--headless=new", "--hide-scrollbars", "--no-first-run", "--remote-allow-origins=*",
                         "--remote-debugging-port=0", f"--user-data-dir={profile}", "about:blank"],
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=subprocess.CREATE_NO_WINDOW)
shots = []
try:
    pf = profile / "DevToolsActivePort"
    for _ in range(100):
        if pf.exists() and pf.read_text().strip():
            break
        time.sleep(0.1)
    port = pf.read_text().splitlines()[0]
    tgt = next(t for t in json.load(urllib.request.urlopen(f"http://127.0.0.1:{port}/json")) if t["type"] == "page")
    ws = websocket.create_connection(tgt["webSocketDebuggerUrl"], timeout=60)
    n = [0]

    def call(m, p=None):
        n[0] += 1; i = n[0]
        ws.send(json.dumps({"id": i, "method": m, "params": p or {}}))
        while True:
            msg = json.loads(ws.recv())
            if msg.get("id") == i:
                if "error" in msg:
                    raise RuntimeError(msg["error"])
                return msg.get("result", {})

    call("Page.enable")
    call("Emulation.setDeviceMetricsOverride", {"width": 750, "height": 365, "deviceScaleFactor": 1, "mobile": False})
    # as an image in a page, the way GitHub shows it
    html = f'<body style="margin:0"><img src="{svg.as_uri()}" style="width:750px;display:block"></body>'
    call("Page.navigate", {"url": "data:text/html;base64," + base64.b64encode(html.encode()).decode()})
    time.sleep(1.5)
    for t in times:
        # an <img> SVG's animations are not scriptable from the page: load the SVG itself instead
        pass
    call("Page.navigate", {"url": svg.as_uri()})
    time.sleep(1.0)
    call("Emulation.setDeviceMetricsOverride", {"width": 1500, "height": 730, "deviceScaleFactor": float(__import__("os").environ.get("DPR", "0.5")), "mobile": False})
    for t in times:
        call("Runtime.evaluate", {"expression": f"document.getAnimations().forEach(a => {{ a.pause(); a.currentTime = {t * 1000}; }}), 1"})
        time.sleep(0.15)
        shots.append((t, Image.open(io.BytesIO(base64.b64decode(call("Page.captureScreenshot", {"format": "png"})["data"]))).convert("RGB")))
finally:
    proc.terminate()
    try:
        proc.wait(timeout=15)
    except Exception:
        pass
    shutil.rmtree(profile, ignore_errors=True)
w, h = shots[0][1].size
sheet = Image.new("RGB", (w * 2 + 10, (h + 10) * ((len(shots) + 1) // 2)), "#888")
for k, (t, im) in enumerate(shots):
    sheet.paste(im, ((k % 2) * (w + 10), (k // 2) * (h + 10)))
sheet.save(out)
print(out, sheet.size)
