"""Headless interaction captures: real mouse moves, then a screenshot."""
import base64, json, pathlib, subprocess, sys, tempfile, time, urllib.request
import websocket

out = pathlib.Path(sys.argv[1])
out.mkdir(parents=True, exist_ok=True)
chrome = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
profile = pathlib.Path(tempfile.mkdtemp(prefix="xylz-int-"))
proc = subprocess.Popen([chrome, "--headless=new", "--hide-scrollbars", "--no-first-run",
                         "--remote-allow-origins=*", "--remote-debugging-port=0",
                         f"--user-data-dir={profile}", "about:blank"],
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                        creationflags=subprocess.CREATE_NO_WINDOW)
try:
    pf = profile / "DevToolsActivePort"
    for _ in range(100):
        if pf.exists() and pf.read_text().strip():
            break
        time.sleep(0.1)
    port = pf.read_text().splitlines()[0]
    tgt = next(t for t in json.load(urllib.request.urlopen(f"http://127.0.0.1:{port}/json")) if t["type"] == "page")
    ws = websocket.create_connection(tgt["webSocketDebuggerUrl"], timeout=30)
    n = 0
    EXC = []

    def call(m, p=None):
        global n
        n += 1
        i = n
        ws.send(json.dumps({"id": i, "method": m, "params": p or {}}))
        while True:
            msg = json.loads(ws.recv())
            if msg.get("method") == "Runtime.exceptionThrown":
                EXC.append(msg["params"]["exceptionDetails"].get("exception", {}).get("description", "")[:300])
            if msg.get("id") == i:
                if "error" in msg:
                    raise RuntimeError(msg["error"])
                return msg.get("result", {})

    def js(e):
        return call("Runtime.evaluate", {"expression": e, "returnByValue": True, "awaitPromise": True})["result"].get("value")

    def move(x, y):
        call("Input.dispatchMouseEvent", {"type": "mouseMoved", "x": x, "y": y, "pointerType": "mouse"})

    def shot(name):
        data = call("Page.captureScreenshot", {"format": "png"})["data"]
        (out / f"{name}.png").write_bytes(base64.b64decode(data))

    call("Page.enable")
    call("Runtime.enable")
    logs = []
    call("Emulation.setDeviceMetricsOverride", {"width": 1440, "height": 900, "deviceScaleFactor": 1, "mobile": False})
    call("Emulation.setEmulatedMedia", {"features": [{"name": "prefers-reduced-motion", "value": "no-preference"}]})
    for scene in json.loads(sys.argv[2]):
        call("Page.navigate", {"url": "about:blank"})
        time.sleep(0.2)
        call("Page.navigate", {"url": "http://localhost:8765/" + scene.get("hash", "")})
        time.sleep(1.6)
        if scene.get("pre"):
            js(scene["pre"])
            call("Page.navigate", {"url": "http://localhost:8765/" + scene.get("hash", "")})
            time.sleep(1.6)
        if scene.get("vw"):
            call("Emulation.setDeviceMetricsOverride", {"width": scene["vw"], "height": scene["vh"], "deviceScaleFactor": 1, "mobile": scene["vw"] < 700})
            call("Page.navigate", {"url": "http://localhost:8765/" + scene.get("hash", "")})
            time.sleep(1.6)
        if scene.get("scrollTo") is not None:
            js(f"window.scrollTo(0, {scene['scrollTo']})")
            time.sleep(0.5)
        for (x, y) in scene.get("path", []):
            move(x, y)
            time.sleep(0.03)
        for dy in scene.get("wheel", []):
            call("Input.dispatchMouseEvent", {"type": "mouseWheel", "x": 700, "y": 450, "deltaX": 0, "deltaY": dy})
            time.sleep(0.016)
        if scene.get("burst"):
            t0 = time.time()
            k = 0
            wheel_at = scene.get("wheel_at")
            while time.time() - t0 < scene["burst"]:
                if wheel_at is not None and time.time() - t0 > wheel_at:
                    for _ in range(6):
                        call("Input.dispatchMouseEvent", {"type": "mouseWheel", "x": 700, "y": 450, "deltaX": 0, "deltaY": 90})
                    wheel_at = None
                shot(f'{scene["name"]}-{k:02d}-{int((time.time()-t0)*1000):04d}')
                k += 1
        time.sleep(scene.get("settle", 0.25))
        shot(scene["name"])
        if scene.get("vw"):
            call("Emulation.setDeviceMetricsOverride", {"width": 1440, "height": 900, "deviceScaleFactor": 1, "mobile": False})
        logs.append({scene["name"]: js(scene.get("js", "document.documentElement.dataset.field"))})
    print(json.dumps(logs))
    print('EXCEPTIONS', EXC)
finally:
    proc.terminate()
