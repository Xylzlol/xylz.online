import json, math, pathlib, subprocess, sys, tempfile, time, urllib.request
import websocket
chrome = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
prof = pathlib.Path(tempfile.mkdtemp())
p = subprocess.Popen([chrome, "--headless=new", "--remote-allow-origins=*", "--remote-debugging-port=0", f"--user-data-dir={prof}", "about:blank"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=subprocess.CREATE_NO_WINDOW)
try:
    pf = prof / "DevToolsActivePort"
    for _ in range(100):
        if pf.exists() and pf.read_text().strip(): break
        time.sleep(0.1)
    port = pf.read_text().splitlines()[0]
    t = next(x for x in json.load(urllib.request.urlopen(f"http://127.0.0.1:{port}/json")) if x["type"] == "page")
    ws = websocket.create_connection(t["webSocketDebuggerUrl"], timeout=30)
    n = [0]
    def call(m, prm=None):
        n[0] += 1; i = n[0]
        ws.send(json.dumps({"id": i, "method": m, "params": prm or {}}))
        while True:
            r = json.loads(ws.recv())
            if r.get("id") == i: return r.get("result", {})
    call("Page.enable"); call("Runtime.enable")
    call("Emulation.setDeviceMetricsOverride", {"width": 1440, "height": 900, "deviceScaleFactor": 1, "mobile": False})
    call("Emulation.setEmulatedMedia", {"features": [{"name": "prefers-reduced-motion", "value": "no-preference"}]})
    call("Page.addScriptToEvaluateOnNewDocument", {"source": """
      window.__commits = 0; window.__long = [];
      const W = window.Worker;
      window.Worker = class extends W { constructor(...a){ super(...a); this.addEventListener('message', e => { if (e.data && e.data.type === 'committed') window.__commits++; }); } };
      new PerformanceObserver(l => l.getEntries().forEach(e => window.__long.push(Math.round(e.duration)))).observe({type:'longtask', buffered:true});
    """})
    call("Page.navigate", {"url": "http://localhost:8765/"})
    time.sleep(2)
    ev = lambda e: call("Runtime.evaluate", {"expression": e, "returnByValue": True})["result"].get("value")
    ev("window.__commits=0; window.__long=[]")
    t0 = time.time(); k = 0
    while time.time() - t0 < 4:
        a = k * 0.09
        x = 700 + 520 * math.cos(a); y = 640 + 200 * math.sin(a)
        call("Input.dispatchMouseEvent", {"type": "mouseMoved", "x": x, "y": y})
        k += 1
        time.sleep(0.008)
    dur = time.time() - t0
    print(json.dumps({"moves": k, "seconds": round(dur, 2), "wall_frames_per_s": round(ev("window.__commits") / dur, 1), "long_tasks_ms": ev("window.__long")}))
finally:
    p.terminate()
