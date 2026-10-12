"""Does the name jump while scrolling? Records every composited frame (Chrome screencast, which
reports each frame's scroll offset) during wheel scrolling, finds the top edge of the name's lit
cells in each frame and adds that frame's scroll offset. The sum is the name's position on the
page; it must stay constant. Prints how many frames were off and by how much.
Needs the local server on http://localhost:8765/."""
import base64, io, json, pathlib, subprocess, tempfile, threading, time, urllib.request
import numpy as np
import websocket
from PIL import Image

chrome = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
W, H = 1440, 900
profile = pathlib.Path(tempfile.mkdtemp(prefix="xylz-jump-"))
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
    lock = threading.Lock(); pending = {}; frames = []; rec = {"on": False}; cid = [0]

    def reader():
        while True:
            try:
                msg = json.loads(ws.recv())
            except Exception:
                return
            if msg.get("method") == "Page.screencastFrame":
                p = msg["params"]
                if rec["on"]:
                    frames.append((p["metadata"]["timestamp"], p["metadata"]["scrollOffsetY"], p["data"]))
                ws.send(json.dumps({"id": 10**7 + len(frames), "method": "Page.screencastFrameAck", "params": {"sessionId": p["sessionId"]}}))
            elif "id" in msg and msg["id"] in pending:
                pending[msg["id"]].append(msg)
    threading.Thread(target=reader, daemon=True).start()

    def call(m, p=None):
        with lock:
            cid[0] += 1; i = cid[0]; pending[i] = []
            ws.send(json.dumps({"id": i, "method": m, "params": p or {}}))
        for _ in range(6000):
            if pending[i]:
                r = pending.pop(i)[0]
                if "error" in r:
                    raise RuntimeError(r["error"])
                return r.get("result", {})
            time.sleep(0.005)
        raise TimeoutError(m)

    call("Page.enable"); call("Runtime.enable")
    call("Emulation.setDeviceMetricsOverride", {"width": W, "height": H, "deviceScaleFactor": 1, "mobile": False})
    call("Page.navigate", {"url": "http://localhost:8765/"}); time.sleep(2.5)
    call("Input.dispatchMouseEvent", {"type": "mouseMoved", "x": 1300, "y": 850})
    call("Page.startScreencast", {"format": "png", "everyNthFrame": 1})
    rec["on"] = True
    for burst in range(3):
        for _ in range(14):
            call("Input.dispatchMouseEvent", {"type": "mouseWheel", "x": 1300, "y": 850, "deltaX": 0, "deltaY": 33})
            time.sleep(0.016)
        time.sleep(0.25)
        for _ in range(14):
            call("Input.dispatchMouseEvent", {"type": "mouseWheel", "x": 1300, "y": 850, "deltaX": 0, "deltaY": -33})
            time.sleep(0.016)
        time.sleep(0.25)
    time.sleep(0.4)
    rec["on"] = False
    # each frame's brightness profile down the name's columns (left of the pointer's lens), placed
    # in page coordinates by the frame's own scroll offset, then matched against the first frame:
    # the best-matching extra shift is how far the name sits from where it belongs
    profs = []
    for ts, sy, data in frames:
        im = np.asarray(Image.open(io.BytesIO(base64.b64decode(data))).convert("L"), dtype=np.float32)
        profs.append((ts, int(round(sy)), im[:, 60:700].mean(1)))
    ref_sy, ref = profs[0][1], profs[0][2]
    lo_doc, hi_doc = 90, 560  # the name's rows on the page
    shifts = []
    for ts, sy, pr in profs:
        best, bs = None, 0
        for sh in range(-40, 41):
            a0 = max(lo_doc, sy, ref_sy); a1 = min(hi_doc, sy + H, ref_sy + H)
            ys = np.arange(a0, a1)
            ya = ys - sy + sh; yr = ys - ref_sy
            ok = (ya >= 0) & (ya < H)
            if ok.sum() < 120:
                continue
            x = pr[ya[ok]]; y = ref[yr[ok]]
            c = np.corrcoef(x, y)[0, 1]
            if best is None or c > best:
                best, bs = c, sh
        if best is not None:
            shifts.append((sy, bs))
    off = np.array([abs(b) for _, b in shifts])
    print(f"frames {len(shifts)}  scroll range {min(s for s, _ in shifts)}..{max(s for s, _ in shifts)} px  "
          f"frames where the name is out of place: {int((off > 2).sum())}  worst {off.max()} px")
finally:
    proc.terminate()
