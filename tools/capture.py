import base64, json, pathlib, subprocess, sys, tempfile, time, urllib.request
import websocket

out = pathlib.Path(sys.argv[1])
out.mkdir(parents=True, exist_ok=True)
base = "http://localhost:8765/"
chrome = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
profile = pathlib.Path(tempfile.mkdtemp(prefix="xylz-cap-"))
proc = subprocess.Popen([chrome, "--headless=new", "--disable-gpu", "--no-first-run", "--hide-scrollbars",
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

    def call(m, p=None):
        global n
        n += 1
        i = n
        ws.send(json.dumps({"id": i, "method": m, "params": p or {}}))
        while True:
            msg = json.loads(ws.recv())
            if msg.get("id") == i:
                if "error" in msg:
                    raise RuntimeError(msg["error"])
                return msg.get("result", {})

    def js(e):
        r = call("Runtime.evaluate", {"expression": e, "returnByValue": True, "awaitPromise": True})
        return r["result"].get("value")

    call("Page.enable")
    call("Runtime.enable")
    report = {}

    stub = None

    def shot(name, w, h, hash_="", full=False, mobile=False, reduced=False):
        global stub
        # full-page stitches hold one field: scroll-driven relocking is stubbed only in the capture browser
        if full and stub is None:
            stub = call("Page.addScriptToEvaluateOnNewDocument", {"source": "window.IntersectionObserver = class { observe(){} disconnect(){} };"})["identifier"]
        if not full and stub is not None:
            call("Page.removeScriptToEvaluateOnNewDocument", {"identifier": stub})
            stub = None
        call("Emulation.setDeviceMetricsOverride", {"width": w, "height": h, "deviceScaleFactor": 1, "mobile": mobile})
        # a phone is a touch device: coarse pointer, no hover
        call("Emulation.setTouchEmulationEnabled", {"enabled": bool(mobile), "maxTouchPoints": 5 if mobile else 1})
        call("Emulation.setEmulatedMedia", {"features": [{"name": "prefers-reduced-motion", "value": "reduce" if reduced else "no-preference"}]})
        call("Page.navigate", {"url": "about:blank"})
        time.sleep(0.2)
        call("Page.navigate", {"url": base + hash_})
        time.sleep(1.6)
        info = js("""(() => ({field: document.documentElement.dataset.field, coarse: matchMedia('(pointer: coarse)').matches, gaze: !!document.querySelector('.gaze-cloud'),
            say: document.querySelector('.lock-say').textContent,
            scrollW: document.documentElement.scrollWidth, innerW: innerWidth,
            height: document.documentElement.scrollHeight,
            dots: document.documentElement.classList.contains('dots-on'),
            lockTransition: getComputedStyle(document.querySelector('.lock')).transitionDuration}))()""")
        report[name] = info
        if full:
            H = info["height"]
            # stitch viewport-height slices so svh-based layout is not stretched
            from PIL import Image
            canvas = Image.new("RGB", (w, H))
            y = 0
            while y < H:
                js(f"scrollTo(0,{y})")
                time.sleep(0.35)
                actual = js("scrollY")
                data = call("Page.captureScreenshot", {"format": "png"})["data"]
                tmp = out / "_slice.png"
                tmp.write_bytes(base64.b64decode(data))
                im = Image.open(tmp).convert("RGB")
                canvas.paste(im, (0, actual))
                if actual + h >= H:
                    break
                y = actual + h
            canvas.save(out / f"{name}.png")
            (out / "_slice.png").unlink(missing_ok=True)
        else:
            data = call("Page.captureScreenshot", {"format": "png"})["data"]
            (out / f"{name}.png").write_bytes(base64.b64decode(data))

    shot("desktop", 1440, 900, full=True)
    shot("mobile", 390, 844, full=True, mobile=True)
    shot("desktop-github", 1440, 900, "#github")
    shot("desktop-x", 1440, 900, "#x")
    shot("desktop-report", 1440, 900, "#r92963")
    shot("desktop-artist", 1440, 900, "#artist")
    shot("desktop-ens", 1440, 900, "#ens")
    shot("laptop", 1366, 768)
    shot("zoom-720x450", 720, 450)
    shot("reduced-motion", 1440, 900, reduced=True)
    print(json.dumps(report, indent=1))
finally:
    proc.terminate()
