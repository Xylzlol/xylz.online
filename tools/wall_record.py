"""Record every message the page sends the LED wall, with its time, during a scripted session that
touches everything the wall draws: load, the pointer stirring the name (fluid, lens), all four pours,
wheel scrolling (also during a pour), reading further down, and a resize. Saved as JSON (typed arrays
kept with their type) for tools/render_equiv.mjs to replay.
Usage: wall_record.py out.json"""
import shutil, json, math, pathlib, subprocess, sys, tempfile, time, urllib.request
import websocket

out = pathlib.Path(sys.argv[1])
chrome = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
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
    ws = websocket.create_connection(tgt["webSocketDebuggerUrl"], timeout=120)
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

    def js(e):
        r = call("Runtime.evaluate", {"expression": e, "returnByValue": True, "awaitPromise": True})
        if "exceptionDetails" in r:
            raise RuntimeError(r["exceptionDetails"])
        return r["result"].get("value")

    def move(x, y):
        call("Input.dispatchMouseEvent", {"type": "mouseMoved", "x": x, "y": y, "pointerType": "mouse"})

    def wheel(x, y, dy):
        call("Input.dispatchMouseEvent", {"type": "mouseWheel", "x": x, "y": y, "deltaX": 0, "deltaY": dy, "pointerType": "mouse"})

    call("Page.enable")
    call("Emulation.setDeviceMetricsOverride", {"width": 1440, "height": 900, "deviceScaleFactor": 1, "mobile": False})
    call("Page.navigate", {"url": "http://localhost:8765/?debug&rec"})
    time.sleep(2.0)
    for k in range(150):  # stir the name
        move(200 + 900 * (0.5 + 0.5 * math.sin(k / 9)), 260 + 160 * math.sin(k / 13)); time.sleep(0.016)
    time.sleep(0.6)
    R = json.loads(js("JSON.stringify([...document.querySelectorAll('.targets .target')].map(e => { const r = e.getBoundingClientRect(); return [r.left + r.width / 2, r.top + r.height / 2]; }))"))
    x, y = 700, 400
    for t in [2, 3, 1, 0]:  # all four pours
        tx, ty = R[t]
        for k in range(1, 31):
            u = 1 - (1 - k / 30) ** 3
            move(x + (tx - x) * u, y + (ty - y) * u); time.sleep(0.016)
        x, y = tx, ty
        time.sleep(1.4)
    for k in range(25):  # wheel down and up
        wheel(700, 500, 100); time.sleep(0.05)
    for k in range(25):
        wheel(700, 500, -100); time.sleep(0.05)
    time.sleep(0.5)
    tx, ty = R[2]  # scroll during a pour
    for k in range(1, 21):
        move(700 + (tx - 700) * k / 20, 400 + (ty - 400) * k / 20); time.sleep(0.016)
    time.sleep(0.15)
    for k in range(15):
        wheel(tx, ty, 120); time.sleep(0.04)
    time.sleep(1.2)
    for k in range(120):  # reading further down
        move(150 + (k % 60) * 12, 300 + (k // 60) * 40); time.sleep(0.016)
    call("Emulation.setDeviceMetricsOverride", {"width": 1200, "height": 900, "deviceScaleFactor": 1, "mobile": False})
    time.sleep(0.8)
    for k in range(60):
        move(300 + k * 8, 300); time.sleep(0.016)
    time.sleep(0.8)
    js("window.__dumpWallRec(), 1")
    time.sleep(0.5)
    log = js("""JSON.stringify(window.__wallRec, (k, v) => ArrayBuffer.isView(v) ? { __ta: v.constructor.name, d: Array.from(v) } : v)""")
finally:
    proc.terminate()
    try:
        proc.wait(timeout=15)
    except Exception:
        pass
    shutil.rmtree(profile, ignore_errors=True)  # never leave the profile in %TEMP%
out.write_text(log)
recs = json.loads(log)
import collections
print(len(recs), "messages over", round((recs[-1]["t"] - recs[0]["t"]) / 1000, 1), "s:", dict(collections.Counter(r["m"]["type"] for r in recs)))
