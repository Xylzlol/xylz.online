"""Screenshots on touch devices (mobile emulation with touch), with an optional tap first.
Usage: mobile_shots.py <outdir>"""
import base64, json, pathlib, subprocess, sys, tempfile, time, urllib.request
import websocket

out = pathlib.Path(sys.argv[1]); out.mkdir(parents=True, exist_ok=True)
chrome = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
SCENES = [
    {"name": "phone-390", "w": 390, "h": 844},
    {"name": "phone-390-github", "w": 390, "h": 844, "tap": 2},
    {"name": "phone-320", "w": 320, "h": 640},
    {"name": "phone-landscape", "w": 844, "h": 390},
    {"name": "tablet-700", "w": 700, "h": 1000, "tap": 3},
]
profile = pathlib.Path(tempfile.mkdtemp(prefix="xylz-mob-"))
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
    call("Emulation.setTouchEmulationEnabled", {"enabled": True, "maxTouchPoints": 5})
    call("Page.addScriptToEvaluateOnNewDocument", {"source": "addEventListener('click', e => { const a = e.target.closest('a'); if (a && !a.getAttribute('href').startsWith('#')) e.preventDefault(); });"})
    for sc in SCENES:
        call("Emulation.setDeviceMetricsOverride", {"width": sc["w"], "height": sc["h"], "deviceScaleFactor": 2, "mobile": True})
        call("Page.navigate", {"url": "about:blank"}); time.sleep(0.2)
        call("Page.navigate", {"url": "http://localhost:8765/"}); time.sleep(2.2)
        if "tap" in sc:
            x, y = js(f"(() => {{ const r = document.querySelectorAll('.targets .target')[{sc['tap']}].getBoundingClientRect(); return [r.left + 30, r.top + r.height / 2]; }})()")
            for t in ("touchStart", "touchEnd"):
                call("Input.dispatchTouchEvent", {"type": t, "touchPoints": [] if t == "touchEnd" else [{"x": x, "y": y, "id": 1}]})
                time.sleep(0.05)
            time.sleep(1.8)
        overflow = js("document.documentElement.scrollWidth > innerWidth")
        data = call("Page.captureScreenshot", {"format": "png"})["data"]
        (out / f"{sc['name']}.png").write_bytes(base64.b64decode(data))
        print(sc["name"], "touch-ui:", js("document.documentElement.classList.contains('touch-ui')"), "horizontal overflow:", overflow, "field:", js("document.documentElement.dataset.field"))
finally:
    proc.terminate()
