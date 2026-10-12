"""Which frame events does this Chrome emit? Loads the page in a real (windowed, off-screen) Chrome
with hardware acceleration off, traces 4 s with the pointer moving, and counts event names that
look frame-related, plus the GPU feature status. A probe for frames_test.py."""
import shutil, json, pathlib, subprocess, tempfile, threading, time, urllib.request, collections, sys
import websocket

chrome = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
sw = "--gpu" not in sys.argv
profile = pathlib.Path(tempfile.mkdtemp(prefix="xylz-tprobe-"))
flags = [chrome, "--no-first-run", "--no-default-browser-check", "--remote-allow-origins=*", "--remote-debugging-port=0",
         f"--user-data-dir={profile}", "--window-position=-2400,-2400", "--window-size=1456,1020",
         "--disable-backgrounding-occluded-windows", "--disable-renderer-backgrounding", "--disable-background-timer-throttling",
         "--disable-features=CalculateNativeWinOcclusion", "about:blank"]
if sw:
    flags.insert(1, "--disable-gpu")
proc = subprocess.Popen(flags, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
events = []
try:
    pf = profile / "DevToolsActivePort"
    for _ in range(150):
        if pf.exists() and pf.read_text().strip():
            break
        time.sleep(0.1)
    port, bpath = pf.read_text().splitlines()[:2]
    bws = websocket.create_connection(f"ws://127.0.0.1:{port}{bpath}", timeout=60)
    bws.send(json.dumps({"id": 1, "method": "SystemInfo.getInfo"}))
    while True:
        m = json.loads(bws.recv())
        if m.get("id") == 1:
            break
    print("featureStatus:", flush=True); print( {k: v for k, v in m["result"]["gpu"]["featureStatus"].items() if k in ("gpu_compositing", "2d_canvas", "rasterization", "webgl", "video_decode")})
    tgt = next(t for t in json.load(urllib.request.urlopen(f"http://127.0.0.1:{port}/json")) if t["type"] == "page")
    ws = websocket.create_connection(tgt["webSocketDebuggerUrl"], timeout=120)
    lock = threading.Lock(); pending = {}; cid = [0]; done = threading.Event()

    def reader():
        while True:
            try:
                msg = json.loads(ws.recv())
            except Exception:
                return
            if msg.get("method") == "Tracing.dataCollected":
                events.extend(msg["params"]["value"])
            elif msg.get("method") == "Tracing.tracingComplete":
                done.set()
            elif "id" in msg and msg["id"] in pending:
                pending[msg["id"]].append(msg)
    threading.Thread(target=reader, daemon=True).start()

    def call(m, p=None):
        with lock:
            cid[0] += 1; i = cid[0]; pending[i] = []
            ws.send(json.dumps({"id": i, "method": m, "params": p or {}}))
        for _ in range(12000):
            if pending[i]:
                r = pending.pop(i)[0]
                if "error" in r:
                    raise RuntimeError(r["error"])
                return r.get("result", {})
            time.sleep(0.005)
        raise TimeoutError(m)

    call("Page.enable")
    call("Page.navigate", {"url": "http://localhost:8765/"})
    time.sleep(2)
    print("viewport:", call("Runtime.evaluate", {"expression": "[innerWidth, innerHeight, devicePixelRatio]", "returnByValue": True})["result"]["value"])
    call("Tracing.start", {"traceConfig": {"includedCategories": ["benchmark", "cc", "viz", "graphics.pipeline", "devtools.timeline",
                                                                   "disabled-by-default-devtools.timeline.frame", "disabled-by-default-devtools.timeline"]},
                           "transferMode": "ReportEvents"})
    for k in range(200):
        call("Input.dispatchMouseEvent", {"type": "mouseMoved", "x": 200 + (k % 100) * 9, "y": 300 + (k % 50) * 4, "pointerType": "mouse"})
        time.sleep(0.016)
    call("Tracing.end"); done.wait(60)
finally:
    proc.terminate()
    try:
        proc.wait(timeout=15)
    except Exception:
        pass
    shutil.rmtree(profile, ignore_errors=True)
c = collections.Counter(e.get("name") for e in events if any(k in (e.get("name") or "") for k in ("Frame", "Pipeline", "Draw", "Present", "Swap")))
for k, v in c.most_common(40):
    print(f"{v:6d}  {k}")
pr = [e for e in events if e.get("name") == "PipelineReporter" and e.get("ph") in ("b", "B")]
st = collections.Counter((((e.get("args") or {}).get("frame_reporter") or {}).get("layer_tree_host_id"), ((e.get("args") or {}).get("frame_reporter") or {}).get("state")) for e in pr)
print("PipelineReporter (lth, state):", st)
names = {}
for e in events:
    if e.get("ph") == "M" and e.get("name") == "thread_name": names[(e["pid"], e["tid"])] = e["args"]["name"]
for nm in ("Graphics.Pipeline.DrawAndSwap", "DirectRenderer::DrawRenderPass", "DroppedFrame"):
    ev = [e for e in events if e.get("name") == nm]
    print(nm, collections.Counter(names.get((e["pid"], e["tid"]), "?") + "/" + e.get("ph", "") for e in ev))
d = sorted(e["ts"] for e in events if e.get("name") == "Graphics.Pipeline.DrawAndSwap" and e.get("ph") in ("b", "B"))
iv = [round((b - a) / 1000, 1) for a, b in zip(d, d[1:])]
print("draw intervals (ms): n", len(iv), "sorted tail", sorted(iv)[-12:])
