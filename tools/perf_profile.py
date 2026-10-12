"""Baseline performance profile: load weight, main-thread time per scenario, hottest functions."""
import shutil, json, math, pathlib, subprocess, sys, tempfile, time, urllib.request
from collections import Counter
import websocket

URL = "http://localhost:8765/"
chrome = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
prof = pathlib.Path(tempfile.mkdtemp(prefix="xylz-perf-"))
p = subprocess.Popen([chrome, "--headless=new", "--remote-allow-origins=*", "--remote-debugging-port=0", f"--user-data-dir={prof}", "about:blank"],
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=subprocess.CREATE_NO_WINDOW)
try:
    pf = prof / "DevToolsActivePort"
    for _ in range(100):
        if pf.exists() and pf.read_text().strip():
            break
        time.sleep(0.1)
    port = pf.read_text().splitlines()[0]
    t = next(x for x in json.load(urllib.request.urlopen(f"http://127.0.0.1:{port}/json")) if x["type"] == "page")
    ws = websocket.create_connection(t["webSocketDebuggerUrl"], timeout=60)
    n = [0]
    events = []

    def call(m, prm=None):
        n[0] += 1
        i = n[0]
        ws.send(json.dumps({"id": i, "method": m, "params": prm or {}}))
        while True:
            r = json.loads(ws.recv())
            if r.get("id") == i:
                return r.get("result", {})
            events.append(r)

    def metrics():
        return {m["name"]: m["value"] for m in call("Performance.getMetrics")["metrics"]}

    def ev(e):
        return call("Runtime.evaluate", {"expression": e, "returnByValue": True, "awaitPromise": True})["result"].get("value")

    call("Page.enable"); call("Runtime.enable"); call("Network.enable"); call("Performance.enable"); call("Profiler.enable")
    call("Network.setCacheDisabled", {"cacheDisabled": True})
    call("Emulation.setDeviceMetricsOverride", {"width": 1440, "height": 900, "deviceScaleFactor": 1, "mobile": False})
    call("Emulation.setEmulatedMedia", {"features": [{"name": "prefers-reduced-motion", "value": "no-preference"}]})
    events.clear()
    t0 = time.time()
    call("Page.navigate", {"url": URL})
    time.sleep(6)
    for _ in range(50):
        try:
            ws.settimeout(0.05)
            events.append(json.loads(ws.recv()))
        except Exception:
            break
    ws.settimeout(60)
    resp = {}
    size = Counter()
    for e in events:
        if e.get("method") == "Network.responseReceived":
            resp[e["params"]["requestId"]] = e["params"]["response"]["url"].split("/")[-1].split("?")[0]
        if e.get("method") == "Network.loadingFinished":
            size[resp.get(e["params"]["requestId"], "?")] += e["params"]["encodedDataLength"]
    print("LOAD bytes by file (uncompressed local server):")
    for k, v in size.most_common(20):
        print(f"  {k:40s} {v/1e6:7.2f} MB")
    print("  total", round(sum(size.values()) / 1e6, 2), "MB")
    paint = ev("JSON.stringify(performance.getEntriesByType('paint').map(p=>[p.name,Math.round(p.startTime)]))")
    print("paint", paint, "| saliency", ev("document.documentElement.dataset.saliency"))

    def scenario(name, fn, secs):
        m0 = metrics()
        call("Profiler.start")
        fn(secs)
        prof_ = call("Profiler.stop")["profile"]
        m1 = metrics()
        d = {k: m1[k] - m0.get(k, 0) for k in ("ScriptDuration", "TaskDuration", "LayoutDuration", "RecalcStyleDuration")}
        # hottest self-time functions
        nodes = {nd["id"]: nd for nd in prof_["nodes"]}
        dt = Counter()
        samples, deltas = prof_.get("samples", []), prof_.get("timeDeltas", [])
        for sid, dlt in zip(samples, deltas):
            cf = nodes[sid]["callFrame"]
            key = f'{cf["functionName"] or "(anon)"} {cf["url"].split("/")[-1].split("?")[0]}:{cf["lineNumber"]+1}'
            dt[key] += dlt / 1000
        busy = {k: v for k, v in dt.items() if not k.startswith("(idle)") and not k.startswith("(program)")}
        print(f"\n== {name} ({secs}s): script {d['ScriptDuration']*1000:.0f}ms, task {d['TaskDuration']*1000:.0f}ms, layout {d['LayoutDuration']*1000:.0f}ms, style {d['RecalcStyleDuration']*1000:.0f}ms"
              f"  -> main thread busy {d['TaskDuration']/secs*100:.0f}%")
        for k, v in sorted(busy.items(), key=lambda x: -x[1])[:8]:
            print(f"   {v:7.1f} ms  {k}")

    def idle(s):
        time.sleep(s)

    def circle(s):
        t1 = time.time(); k = 0
        while time.time() - t1 < s:
            a = k * 0.09
            call("Input.dispatchMouseEvent", {"type": "mouseMoved", "x": 700 + 520 * math.cos(a), "y": 640 + 200 * math.sin(a)})
            k += 1
            time.sleep(0.008)

    def name_lens(s):
        t1 = time.time(); k = 0
        while time.time() - t1 < s:
            call("Input.dispatchMouseEvent", {"type": "mouseMoved", "x": 300 + (k * 7) % 700, "y": 250 + 60 * math.sin(k * 0.1)})
            k += 1
            time.sleep(0.008)

    def scroll(s):
        t1 = time.time()
        while time.time() - t1 < s:
            call("Input.dispatchMouseEvent", {"type": "mouseWheel", "x": 700, "y": 450, "deltaX": 0, "deltaY": 60})
            time.sleep(0.03)
        ev("scrollTo(0,0)")

    scenario("idle", idle, 4)
    scenario("circling over destinations", circle, 4)
    scenario("lens over the name", name_lens, 4)
    scenario("scrolling", scroll, 3)
    print("\nheap MB", round(metrics()["JSHeapUsedSize"] / 1e6, 1), "| nodes", metrics()["Nodes"])
finally:
    p.terminate()
    try:
        p.wait(timeout=15)
    except Exception:
        pass
    shutil.rmtree(prof, ignore_errors=True)  # never leave the profile in %TEMP%