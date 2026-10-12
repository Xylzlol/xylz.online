"""CPU profile of each dedicated worker (and the page) while the pointer stirs the name in a real
windowed Chrome (GPU on unless --sw); self time by function. Was: where the renderer's time goes, in a real windowed Chrome (GPU on unless --sw): traces 4 s of the
pointer stirring the name (or hovering pours with --pours) and lists, per thread, the tasks over 8 ms
and the busiest top-level event names with their total time."""
import shutil, json, pathlib, subprocess, tempfile, threading, time, urllib.request, collections, sys
import websocket

chrome = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
sw = "--sw" in sys.argv
headless = "--headless" in sys.argv
URL = sys.argv[sys.argv.index("--url") + 1] if "--url" in sys.argv else "http://localhost:8765/"
profile = pathlib.Path(tempfile.mkdtemp(prefix="xylz-tprobe-"))
flags = [chrome, "--no-first-run", "--no-default-browser-check", "--remote-allow-origins=*", "--remote-debugging-port=0",
         f"--user-data-dir={profile}", "--window-position=-2400,-2400", "--window-size=1456,1020",
         "--disable-backgrounding-occluded-windows", "--disable-renderer-backgrounding", "--disable-background-timer-throttling",
         "--disable-features=CalculateNativeWinOcclusion", "about:blank"]
if sw:
    flags.insert(1, "--disable-gpu")
if headless:
    flags = [f for f in flags if not f.startswith("--window-")]
    flags.insert(1, "--headless=new")
proc = subprocess.Popen(flags, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
import psutil
CPUS = [int(x) for x in sys.argv[sys.argv.index("--cpus") + 1].split(",")] if "--cpus" in sys.argv else None
def pin():
    if not CPUS: return
    root = psutil.Process(proc.pid)
    for q in [root] + root.children(recursive=True):
        try:
            q.cpu_affinity(CPUS); q.nice(psutil.BELOW_NORMAL_PRIORITY_CLASS)
        except Exception:
            pass
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
    lock = threading.Lock(); pending = {}; cid = [0]; done = threading.Event(); attached = {}

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
            elif msg.get("method") == "Target.attachedToTarget":
                attached[msg["params"]["sessionId"]] = msg["params"]["targetInfo"].get("url", "").split("/")[-1].split("?")[0]
            elif "id" in msg and msg["id"] in pending:
                pending[msg["id"]].append(msg)
    threading.Thread(target=reader, daemon=True).start()

    def call(m, p=None, session=None):
        with lock:
            cid[0] += 1; i = cid[0]; pending[i] = []
            o = {"id": i, "method": m, "params": p or {}}
            if session: o["sessionId"] = session
            ws.send(json.dumps(o))
        for _ in range(12000):
            if pending[i]:
                r = pending.pop(i)[0]
                if "error" in r:
                    raise RuntimeError(r["error"])
                return r.get("result", {})
            time.sleep(0.005)
        raise TimeoutError(m)

    workers = {}
    def reader2():
        pass
    call("Page.enable")
    call("Target.setAutoAttach", {"autoAttach": True, "waitForDebuggerOnStart": False, "flatten": True})
    if headless:
        call("Emulation.setDeviceMetricsOverride", {"width": 1456, "height": 933, "deviceScaleFactor": 1, "mobile": False})
    call("Page.navigate", {"url": URL})
    time.sleep(2.5)
    pin()
    sess = [s for s in list(attached)]
    for sid in sess:
        call("Profiler.enable", session=sid); call("Profiler.setSamplingInterval", {"interval": 200}, session=sid); call("Profiler.start", session=sid)
    call("Profiler.enable"); call("Profiler.start")
    import math
    for k in range(220):
        call("Input.dispatchMouseEvent", {"type": "mouseMoved", "x": 200 + 900 * (0.5 + 0.5 * math.sin(k / 9)), "y": 260 + 160 * math.sin(k / 13), "pointerType": "mouse"})
        time.sleep(0.016)
    profs = {"page": call("Profiler.stop")["profile"]}
    for sid in sess:
        profs[attached[sid]] = call("Profiler.stop", session=sid)["profile"]
finally:
    proc.terminate()
    try:
        proc.wait(timeout=15)
    except Exception:
        pass
    shutil.rmtree(profile, ignore_errors=True)
for name, prof in profs.items():
    nodes = {nd["id"]: nd for nd in prof["nodes"]}
    dt = collections.Counter()
    for sid_, d in zip(prof["samples"], prof["timeDeltas"]):
        dt[sid_] += d
    selfc = collections.Counter()
    for nid, us in dt.items():
        cf = nodes[nid]["callFrame"]
        selfc[f"{cf['functionName'] or '(anon)'} {cf['url'].split('/')[-1].split('?')[0]}:{cf['lineNumber'] + 1}"] += us
    tot = sum(v for k, v in selfc.items() if not k.startswith("(idle)"))
    print(f"== {name}: busy {tot / 1000:.0f} ms of {(prof['endTime'] - prof['startTime']) / 1000:.0f} ms")
    if "--lines" in sys.argv and "wall" in name:
        src = urllib.request.urlopen(URL.split("?")[0].rstrip("/") + "/wall.js").read().decode("utf-8").splitlines()
        lines = collections.Counter()
        for nd in prof["nodes"]:
            if nd["callFrame"]["functionName"] in ("render", "tick0", "cover", "maskAt"):
                tot = sum(t["ticks"] for t in nd.get("positionTicks", [])) or 1
                for t in nd.get("positionTicks", []):
                    lines[t["line"]] += dt[nd["id"]] * t["ticks"] / tot
        for ln, us in lines.most_common(18):
            print(f"      {us / 1000:7.1f} ms  {ln}: {src[ln - 1].strip()[:100]}")
    for k, v in selfc.most_common(14):
        if not k.startswith("(idle)"):
            print(f"   {v / 1000:7.1f}  {k}")
