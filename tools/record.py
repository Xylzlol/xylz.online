"""Records README media from the running site with Chrome's screencast (every composited frame):
  pour.webp     selecting GitHub: the black field pours out from the destination around the letters
  scanpath.webp the gaze scanpath following a mouse path on the black field
Needs the local server on http://localhost:8765/. Usage: record.py <outdir>"""
import base64, io, json, math, pathlib, subprocess, sys, tempfile, threading, time, urllib.request
import websocket
from PIL import Image

out = pathlib.Path(sys.argv[1]); out.mkdir(parents=True, exist_ok=True)
chrome = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
W, H = 1440, 900
profile = pathlib.Path(tempfile.mkdtemp(prefix="xylz-rec-"))
proc = subprocess.Popen([chrome, "--headless=new", "--hide-scrollbars", "--no-first-run", "--remote-allow-origins=*",
                         "--remote-debugging-port=0", f"--user-data-dir={profile}", "about:blank"],
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=subprocess.CREATE_NO_WINDOW)
try:
    pf = profile / "DevToolsActivePort"
    for _ in range(100):
        if pf.exists() and pf.read_text().strip():
            break
        time.sleep(0.1)
    port = pf.read_text().splitlines()[0]
    tgt = next(t for t in json.load(urllib.request.urlopen(f"http://127.0.0.1:{port}/json")) if t["type"] == "page")
    ws = websocket.create_connection(tgt["webSocketDebuggerUrl"], timeout=60)
    lock = threading.Lock()
    pending, frames, rec = {}, [], {"on": False}
    n = [0]

    def reader():
        while True:
            try:
                msg = json.loads(ws.recv())
            except Exception:
                return
            if msg.get("method") == "Page.screencastFrame":
                p = msg["params"]
                if rec["on"]:
                    frames.append((p["metadata"]["timestamp"], p["data"]))
                n[0] += 1
                ws.send(json.dumps({"id": 900000 + n[0], "method": "Page.screencastFrameAck", "params": {"sessionId": p["sessionId"]}}))
            elif "id" in msg and msg["id"] in pending:
                pending[msg["id"]].append(msg)

    threading.Thread(target=reader, daemon=True).start()
    cid = [0]

    def call(m, p=None):
        with lock:
            cid[0] += 1
            i = cid[0]
            pending[i] = []
            ws.send(json.dumps({"id": i, "method": m, "params": p or {}}))
        for _ in range(6000):
            if pending[i]:
                r = pending.pop(i)[0]
                if "error" in r:
                    raise RuntimeError(r["error"])
                return r.get("result", {})
            time.sleep(0.005)
        raise TimeoutError(m)

    def js(e):
        return call("Runtime.evaluate", {"expression": e, "returnByValue": True, "awaitPromise": True})["result"].get("value")

    def move(x, y):
        call("Input.dispatchMouseEvent", {"type": "mouseMoved", "x": x, "y": y, "pointerType": "mouse"})

    call("Page.enable"); call("Runtime.enable")
    call("Emulation.setDeviceMetricsOverride", {"width": W, "height": H, "deviceScaleFactor": 1, "mobile": False})
    call("Emulation.setFocusEmulationEnabled", {"enabled": True})
    # README media show the site itself, not the demonlist note (it stays on the live page)
    call("Page.addScriptToEvaluateOnNewDocument", {"source": "addEventListener('DOMContentLoaded', () => document.head.insertAdjacentHTML('beforeend', '<style>.list-note{display:none!important}</style>'));"})
    call("Page.startScreencast", {"format": "jpeg", "quality": 88, "maxWidth": 900, "maxHeight": 563, "everyNthFrame": 1})

    def take(name, scene, seconds, crop, width, fps=30, hold_last=1.2):
        frames.clear()
        call("Page.navigate", {"url": "about:blank"}); time.sleep(0.2)
        call("Page.navigate", {"url": "http://localhost:8765/"}); time.sleep(2.4)
        rec["on"] = True
        t0 = time.time()
        scene()
        while time.time() - t0 < seconds:
            time.sleep(0.02)
        rec["on"] = False
        time.sleep(0.2)
        got = sorted(f for f in frames if f[0] >= t0 - 0.05)
        if not got:
            print(name, "no frames"); return
        # resample to a steady fps
        ts0 = got[0][0]
        out_frames, k = [], 0
        t = 0.0
        while t <= got[-1][0] - ts0:
            while k + 1 < len(got) and got[k + 1][0] - ts0 <= t:
                k += 1
            out_frames.append(got[k][1])
            t += 1 / fps
        ims = []
        for data in out_frames:
            im = Image.open(io.BytesIO(base64.b64decode(data))).convert("RGB")
            k = im.width / W
            im = im.crop(tuple(round(v * k) for v in crop))
            h = round(im.height * width / im.width)
            ims.append(im.resize((width, h), Image.LANCZOS))
        dur = [round(1000 / fps)] * len(ims)
        dur[-1] = int(hold_last * 1000)
        # animated WebP: the LED texture defeats GIF's palette and LZW; lossy WebP keeps it small
        ims[0].save(out / name, save_all=True, append_images=ims[1:], duration=dur, loop=0, quality=72, method=6)
        print(name, len(got), "screencast frames ->", len(ims), "gif frames,", round((out / name).stat().st_size / 1e6, 2), "MB")

    # the pour: rest on the page, then select GitHub (keyboard focus commits at once)
    def pour():
        move(700, 300); time.sleep(0.6)
        js("document.querySelectorAll('.targets .target')[2].focus()")
    take("pour.webp", pour, 2.4, (0, 0, W, H), 900, fps=25)

    # the pour onto magenta from X, a second colour
    def pour_x():
        js("document.querySelectorAll('.targets .target')[2].focus()"); time.sleep(1.8)
        move(700, 300); time.sleep(0.5)
        js("document.querySelectorAll('.targets .target')[3].focus()")
    take("pour-x.webp", pour_x, 4.6, (0, 0, W, H), 900, fps=25)

    # the scanpath: a mouse path with pauses through the open field under the name, where the
    # fixation boxes show against the black
    def scan():
        js("document.querySelectorAll('.targets .target')[2].focus()"); time.sleep(1.6)
        stops = [(260, 640), (520, 600), (760, 660), (980, 610), (700, 700), (420, 690)]
        x0, y0 = 120, 620
        for x1, y1 in stops:
            for k in range(1, 16):
                move(x0 + (x1 - x0) * k / 15, y0 + (y1 - y0) * k / 15); time.sleep(0.02)
            x0, y0 = x1, y1
            for _ in range(10):  # rest here, with the slight tremor of a hand
                move(x0 + math.sin(time.time() * 7) * 2, y0 + math.cos(time.time() * 5) * 2); time.sleep(0.06)
    take("scanpath.webp", scan, 9.0, (0, 330, W, H), 900, fps=15)
finally:
    proc.terminate()
