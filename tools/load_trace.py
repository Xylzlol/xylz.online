"""First load, measured: a full Chrome performance trace from navigation to 6 s, with the pointer
moving over the page from 1.0 s like an arriving visitor. Reports, per thread (main page, each worker):
every task over 16 ms with what ran in it (function, file, line), plus first paint and first contentful
paint, and how long the main thread was blocked in total.
Usage: load_trace.py [--throttle 4]  (CPU throttling, to stand in for a slower laptop)"""
import shutil, json, pathlib, subprocess, sys, tempfile, threading, time, urllib.request, collections
import websocket

chrome = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
throttle = float(sys.argv[sys.argv.index("--throttle") + 1]) if "--throttle" in sys.argv else 1
profile = pathlib.Path(tempfile.mkdtemp(prefix="xylz-trace-"))
proc = subprocess.Popen([chrome, "--headless=new", "--hide-scrollbars", "--no-first-run", "--remote-allow-origins=*",
                         "--remote-debugging-port=0", f"--user-data-dir={profile}", "about:blank"],
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=subprocess.CREATE_NO_WINDOW)
events = []
try:
    pf = profile / "DevToolsActivePort"
    for _ in range(100):
        if pf.exists() and pf.read_text().strip():
            break
        time.sleep(0.1)
    port = pf.read_text().splitlines()[0]
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
    call("Emulation.setDeviceMetricsOverride", {"width": 1440, "height": 900, "deviceScaleFactor": 1, "mobile": False})
    if throttle > 1:
        call("Emulation.setCPUThrottlingRate", {"rate": throttle})
    call("Tracing.start", {"traceConfig": {"includedCategories": ["devtools.timeline", "v8.execute", "blink.user_timing", "loading",
                                                                   "disabled-by-default-devtools.timeline", "toplevel", "v8"]},
                           "transferMode": "ReportEvents"})
    t0 = time.time()
    call("Page.navigate", {"url": "http://localhost:8765/"})
    time.sleep(1.0)
    for k in range(120):  # the visitor's pointer drifts across the name and down to the links
        call("Input.dispatchMouseEvent", {"type": "mouseMoved", "x": 200 + k * 7, "y": 300 + k * 3.5, "pointerType": "mouse"})
        time.sleep(0.03)
    while time.time() - t0 < 6:
        time.sleep(0.05)
    call("Tracing.end")
    done.wait(60)
finally:
    proc.terminate()
    try:
        proc.wait(timeout=15)
    except Exception:
        pass
    shutil.rmtree(profile, ignore_errors=True)  # never leave the profile in %TEMP%
# threads by name
names = {}
for e in events:
    if e.get("ph") == "M" and e.get("name") == "thread_name":
        names[(e["pid"], e["tid"])] = e["args"]["name"]
nav = min((e["ts"] for e in events if e.get("name") in ("navigationStart", "NavigationBodyLoader::StartLoadingBody", "ResourceSendRequest")), default=0)
fp = [e["ts"] for e in events if e.get("name") in ("firstPaint",)]
fcp = [e["ts"] for e in events if e.get("name") in ("firstContentfulPaint",)]
print(f"CPU throttle x{throttle}")
if fp: print(f"first paint {(min(fp) - nav) / 1000:.0f} ms", end="  ")
if fcp: print(f"first contentful paint {(min(fcp) - nav) / 1000:.0f} ms")
tasks = [e for e in events if e.get("name") in ("RunTask", "ThreadControllerImpl::RunTask") and e.get("ph") == "X" and e.get("dur", 0) > 16000]
by_thread = collections.defaultdict(list)
for t in tasks:
    by_thread[names.get((t["pid"], t["tid"]), str(t["tid"]))].append(t)
for th, ts in sorted(by_thread.items(), key=lambda kv: -sum(t["dur"] for t in kv[1])):
    if not any(k in th for k in ("Main", "Worker", "Dedicated")):
        continue
    print(f"\n{th}: {len(ts)} tasks over 16 ms, total {sum(t['dur'] for t in ts) / 1000:.0f} ms")
    for t in sorted(ts, key=lambda t: -t["dur"])[:8]:
        inner = [e for e in events if e.get("pid") == t["pid"] and e.get("tid") == t["tid"] and e.get("ph") == "X"
                 and t["ts"] <= e["ts"] <= t["ts"] + t["dur"] and e.get("name") in ("FunctionCall", "EvaluateScript", "v8.compile", "Layout",
                 "UpdateLayoutTree", "Paint", "TimerFire", "FireAnimationFrame", "EventDispatch", "ParseHTML", "v8.parseOnBackground", "V8.GC_SCAVENGER", "MajorGC", "MinorGC", "wasm.CompileLazy", "v8.wasm.compileLazy")]
        top = sorted(inner, key=lambda e: -e.get("dur", 0))[:3]
        desc = []
        for e in top:
            a = e.get("args", {}).get("data", {}) or {}
            where = a.get("functionName") or a.get("url", "").split("/")[-1] or a.get("type", "")
            line = a.get("lineNumber")
            desc.append(f"{e['name']} {where}{':' + str(line) if line else ''} {e.get('dur', 0) / 1000:.0f}ms")
        print(f"  at {(t['ts'] - nav) / 1000:6.0f} ms: {t['dur'] / 1000:5.0f} ms  " + " | ".join(desc))
