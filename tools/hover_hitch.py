"""Smoothness while selecting: the pointer glides to each of the four destinations and settles (which
commits a pour), with the page freshly loaded (the neural model loading in the background). Records
long animation frames on the main thread and the gaps between the wall worker's delivered frames.
A hitch is any main-thread frame over 32 ms or any wall gap over 34 ms while the wall is animating.
Usage: hover_hitch.py [rounds]"""
import shutil, json, math, pathlib, subprocess, sys, tempfile, time, urllib.request
import websocket

chrome = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
ROUNDS = int(sys.argv[1]) if len(sys.argv) > 1 else 2
LOAF = """window.__loaf = []; try { new PerformanceObserver((l) => { for (const e of l.getEntries())
  window.__loaf.push({ t: Math.round(e.startTime), d: Math.round(e.duration), block: Math.round(e.blockingDuration),
  scripts: (e.scripts || []).map((s) => `${s.sourceFunctionName || s.invoker} [${s.invokerType}] @${(s.sourceURL || '').split('/').pop()} char ${s.sourceCharPosition} run ${Math.round(s.duration)}ms forcedLayout ${Math.round(s.forcedStyleAndLayoutDuration)}ms`), render: Math.round(e.renderStart ? e.startTime + e.duration - e.renderStart : 0), styleLayout: Math.round(e.styleAndLayoutStart ? e.startTime + e.duration - e.styleAndLayoutStart : 0) }); })
  .observe({ type: 'long-animation-frame', buffered: true }); } catch (e) {}"""
for rnd in range(ROUNDS):
    profile = pathlib.Path(tempfile.mkdtemp(prefix="xylz-hitch-"))
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
            n[0] += 1; i = n[0]
            ws.send(json.dumps({"id": i, "method": m, "params": p or {}}))
            while True:
                msg = json.loads(ws.recv())
                if msg.get("id") == i:
                    if "error" in msg:
                        raise RuntimeError(msg["error"])
                    return msg.get("result", {})

        def js(e):
            return call("Runtime.evaluate", {"expression": e, "returnByValue": True, "awaitPromise": True})["result"].get("value")

        def move(x, y):
            call("Input.dispatchMouseEvent", {"type": "mouseMoved", "x": x, "y": y, "pointerType": "mouse"})

        call("Page.enable"); call("Runtime.enable")
        call("Emulation.setDeviceMetricsOverride", {"width": 1440, "height": 900, "deviceScaleFactor": 1, "mobile": False})
        call("Page.addScriptToEvaluateOnNewDocument", {"source": LOAF})
        call("Page.navigate", {"url": "http://localhost:8765/?debug"})
        time.sleep(1.0)  # early: the model is still loading during the first selections
        R = json.loads(js("JSON.stringify([...document.querySelectorAll('.targets .target')].map(e => { const r = e.getBoundingClientRect(); return [r.left + r.width / 2, r.top + r.height / 2]; }))"))
        x, y = 700, 400
        move(x, y)
        t_start = js("performance.now()")
        for target in [2, 3, 1, 0, 2, 3]:
            tx, ty = R[target]
            for k in range(1, 31):  # an aimed movement: fast, then slowing into the target
                u = 1 - (1 - k / 30) ** 3
                move(x + (tx - x) * u, y + (ty - y) * u); time.sleep(0.016)
            x, y = tx, ty
            time.sleep(1.4)  # settle: the pour runs
        t_end = js("performance.now()")
        frames = js("window.__wallFrames || []")
        slow = js("window.__wallSlow || []")
        loaf = js("window.__loaf")
        gaps = [b - a for a, b in zip(frames, frames[1:]) if a >= t_start]
        big_gaps = sorted([round(g) for g in gaps if g > 34], reverse=True)
        long_frames = [l for l in loaf if l["t"] >= t_start and l["d"] > 32]
        print(f"round {rnd}: wall frames {len(gaps)}, worst gap {round(max(gaps)) if gaps else None} ms, gaps over 34 ms: {big_gaps[:8]}")
        print("         slow worker work (>8 ms):", [(w["what"], w["ms"]) for w in slow if w["at"] >= t_start - 200])
        print(f"         main-thread frames over 32 ms: {len(long_frames)}" + "".join(f"\n           {l['d']} ms (blocking {l['block']}): {l['scripts'][:4]}" for l in sorted(long_frames, key=lambda l: -l['d'])[:6]))
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=15)
        except Exception:
            pass
        shutil.rmtree(profile, ignore_errors=True)  # never leave the profile in %TEMP%