"""Where the renderer's time goes, in a real windowed Chrome (GPU on unless --sw): traces 4 s of the
pointer stirring the name (or hovering pours with --pours) and lists, per thread, the tasks over 8 ms
and the busiest top-level event names with their total time."""
import shutil, json, pathlib, subprocess, tempfile, threading, time, urllib.request, collections, sys
import websocket

chrome = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
sw = "--sw" in sys.argv
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
    pours = "--pours" in sys.argv
    time.sleep(2)
    print("viewport:", call("Runtime.evaluate", {"expression": "[innerWidth, innerHeight, devicePixelRatio]", "returnByValue": True})["result"]["value"])
    call("Tracing.start", {"traceConfig": {"includedCategories": ["devtools.timeline", "disabled-by-default-devtools.timeline", "toplevel", "v8.execute", "blink", "gpu", "cc", "viz"]},
                           "transferMode": "ReportEvents"})
    if pours:
        R = json.loads(call("Runtime.evaluate", {"expression": "JSON.stringify([...document.querySelectorAll('.targets .target')].map(e => { const r = e.getBoundingClientRect(); return [r.left + r.width / 2, r.top + r.height / 2]; }))", "returnByValue": True})["result"]["value"])
        x, y = 700, 400
        for t in [2, 3]:
            tx, ty = R[t]
            for k in range(1, 31):
                call("Input.dispatchMouseEvent", {"type": "mouseMoved", "x": x + (tx - x) * k / 30, "y": y + (ty - y) * k / 30, "pointerType": "mouse"}); time.sleep(0.016)
            x, y = tx, ty; time.sleep(1.5)
    else:
        import math
        for k in range(220):
            call("Input.dispatchMouseEvent", {"type": "mouseMoved", "x": 200 + 900 * (0.5 + 0.5 * math.sin(k / 9)), "y": 260 + 160 * math.sin(k / 13), "pointerType": "mouse"})
            time.sleep(0.016)
    call("Tracing.end"); done.wait(60)
finally:
    proc.terminate()
    try:
        proc.wait(timeout=15)
    except Exception:
        pass
    shutil.rmtree(profile, ignore_errors=True)
names = {}
for e in events:
    if e.get("ph") == "M" and e.get("name") == "thread_name": names[(e["pid"], e["tid"])] = e["args"]["name"]
tasks = collections.defaultdict(list)
for e in events:
    if e.get("ph") == "X" and e.get("name") in ("ThreadControllerImpl::RunTask", "RunTask") and e.get("dur", 0) > 8000:
        tasks[names.get((e["pid"], e["tid"]), str(e["tid"]))].append(e)
busy = collections.defaultdict(lambda: collections.Counter())
for e in events:
    if e.get("ph") == "X" and e.get("dur"):
        busy[names.get((e["pid"], e["tid"]), str(e["tid"]))][e["name"]] += e["dur"]
for th, ts in sorted(tasks.items(), key=lambda kv: -sum(t["dur"] for t in kv[1])):
    print(f"{th}: {len(ts)} tasks > 8 ms, total {sum(t['dur'] for t in ts) / 1000:.0f} ms, worst {max(t['dur'] for t in ts) / 1000:.0f} ms")
    for t in sorted(ts, key=lambda t: -t["dur"])[:3]:
        inner = [e for e in events if e.get("pid") == t["pid"] and e.get("tid") == t["tid"] and e.get("ph") == "X" and t["ts"] <= e["ts"] < t["ts"] + t["dur"] and e is not t]
        top = collections.Counter()
        for e in inner: top[e["name"]] += e.get("dur", 0)
        print(f"    {t['dur'] / 1000:.0f} ms: " + ", ".join(f"{k} {v / 1000:.0f}" for k, v in top.most_common(6)))
fa = collections.defaultdict(list)
for e in events:
    if e.get("ph") == "X" and e.get("name") == "FireAnimationFrame":
        fa[names.get((e["pid"], e["tid"]), str(e["tid"]))].append(e["dur"] / 1000)
for th, d in fa.items():
    d.sort()
    print(f"FireAnimationFrame on {th}: n {len(d)}  median {d[len(d)//2]:.2f} ms  p90 {d[int(len(d)*.9)]:.2f}  max {d[-1]:.2f}  total {sum(d):.0f} ms")
print("busiest event names per thread (ms, nested times overlap):")
for th, c in busy.items():
    if any(k in th for k in ("Main", "Worker", "Compositor", "VizCompositor", "CrGpuMain", "Raster", "Dedicated")):
        print(f"  {th}: " + ", ".join(f"{k} {v / 1000:.0f}" for k, v in c.most_common(6)))
