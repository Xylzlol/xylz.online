"""Where a page's memory sits, by Chrome's own accounting: the same activity as mem_test.py (load,
~45 s of stirring, pours to every field and scrolling, GC, memory pressure), then a detailed
memory-infra dump, summed per process type and top-level allocator (malloc, partition_alloc, v8,
gpu, cc, skia, canvas, ...). Usage: mem_dump.py URL [--cpus 12,13,14,15]"""
import json, math, pathlib, shutil, subprocess, sys, tempfile, threading, time, urllib.request, collections
import psutil, websocket

url = sys.argv[1]
cpus = [int(x) for x in sys.argv[sys.argv.index("--cpus") + 1].split(",")] if "--cpus" in sys.argv else None
chrome = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
profile = pathlib.Path(tempfile.mkdtemp(prefix="xylz-dump-"))
proc = subprocess.Popen([chrome, "--headless=new", "--hide-scrollbars", "--no-first-run", "--remote-allow-origins=*",
                         "--remote-debugging-port=0", f"--user-data-dir={profile}", "about:blank"],
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=subprocess.CREATE_NO_WINDOW)
events, workers = [], {}
try:
    pf = profile / "DevToolsActivePort"
    for _ in range(100):
        try:
            if pf.exists() and pf.read_text().strip():
                break
        except PermissionError:
            pass
        time.sleep(0.1)
    port, bpath = pf.read_text().splitlines()[:2]
    for p in [psutil.Process(proc.pid)] + psutil.Process(proc.pid).children(recursive=True):
        try:
            p.nice(psutil.BELOW_NORMAL_PRIORITY_CLASS)
            if cpus:
                p.cpu_affinity(cpus)
        except Exception:
            pass
    tgt = next(t for t in json.load(urllib.request.urlopen(f"http://127.0.0.1:{port}/json")) if t["type"] == "page")
    ws = websocket.create_connection(tgt["webSocketDebuggerUrl"], timeout=60)
    bws = websocket.create_connection(f"ws://127.0.0.1:{port}{bpath}", timeout=120)
    lock = threading.Lock(); pending = {}; cid = [0]; done = threading.Event()

    def send(m, p=None, session=None):
        with lock:
            cid[0] += 1; i = cid[0]; pending[i] = []
            o = {"id": i, "method": m, "params": p or {}}
            if session:
                o["sessionId"] = session
            ws.send(json.dumps(o))
            return i

    def call(m, p=None, session=None, timeout=30):
        i = send(m, p, session)
        t0 = time.time()
        while time.time() - t0 < timeout:
            if pending.get(i):
                return pending.pop(i)[0].get("result", {})
            time.sleep(0.005)
        return {}

    def reader():
        while True:
            try:
                msg = json.loads(ws.recv())
            except Exception:
                return
            if msg.get("method") == "Target.attachedToTarget":
                s = msg["params"]["sessionId"]
                workers[s] = msg["params"]["targetInfo"].get("url", "").split("/")[-1].split("?")[0]
                send("Target.setAutoAttach", {"autoAttach": True, "waitForDebuggerOnStart": False, "flatten": True}, session=s)
            elif "id" in msg and msg["id"] in pending:
                pending[msg["id"]].append(msg)
    threading.Thread(target=reader, daemon=True).start()

    # the browser-wide trace (all processes) goes over the browser connection
    bn = [0]
    def bcall(m, p=None, timeout=60):
        bn[0] += 1; i = bn[0]
        bws.send(json.dumps({"id": i, "method": m, "params": p or {}}))
        t0 = time.time()
        while time.time() - t0 < timeout:
            r = json.loads(bws.recv())
            if r.get("method") == "Tracing.dataCollected":
                events.extend(r["params"]["value"])
            elif r.get("method") == "Tracing.tracingComplete":
                done.set()
            elif r.get("id") == i:
                return r.get("result", {})
        return {}

    call("Page.enable"); call("Runtime.enable")
    call("Target.setAutoAttach", {"autoAttach": True, "waitForDebuggerOnStart": False, "flatten": True})
    call("Emulation.setDeviceMetricsOverride", {"width": 1456, "height": 933, "deviceScaleFactor": 1, "mobile": False})
    call("Page.navigate", {"url": url}); time.sleep(4)
    mv = lambda x, y: call("Input.dispatchMouseEvent", {"type": "mouseMoved", "x": x, "y": y, "pointerType": "mouse"})
    R = json.loads(call("Runtime.evaluate", {"expression": "JSON.stringify([...document.querySelectorAll('.targets .target')].map(e => { const r = e.getBoundingClientRect(); return [r.left + r.width / 2, r.top + r.height / 2]; }))", "returnByValue": True})["result"]["value"])
    x, y = 700, 400
    for rnd in range(2):
        for k in range(150):
            mv(200 + 900 * (0.5 + 0.5 * math.sin(k / 9)), 260 + 160 * math.sin(k / 13)); time.sleep(0.016)
        for t in [2, 3, 1, 0]:
            for k in range(1, 21):
                mv(x + (R[t][0] - x) * k / 20, y + (R[t][1] - y) * k / 20); time.sleep(0.016)
            x, y = R[t]; time.sleep(1.4)
        for d in (120, -120):
            for k in range(20):
                call("Input.dispatchMouseEvent", {"type": "mouseWheel", "x": 700, "y": 500, "deltaX": 0, "deltaY": d, "pointerType": "mouse"}); time.sleep(0.05)
        time.sleep(1)
    call("HeapProfiler.collectGarbage")
    for s in list(workers):
        call("HeapProfiler.collectGarbage", session=s)
    bcall("Memory.simulatePressureNotification", {"level": "critical"})
    time.sleep(3)
    bcall("Tracing.start", {"traceConfig": {"includedCategories": ["disabled-by-default-memory-infra"], "excludedCategories": ["*"],
                                            "memoryDumpConfig": {"triggers": []}}, "transferMode": "ReportEvents"})
    time.sleep(0.5)
    bcall("Tracing.requestMemoryDump", {"levelOfDetail": "detailed"})
    time.sleep(1)
    bcall("Tracing.end")
    t0 = time.time()
    while not done.is_set() and time.time() - t0 < 60:
        r = json.loads(bws.recv())
        if r.get("method") == "Tracing.dataCollected":
            events.extend(r["params"]["value"])
        elif r.get("method") == "Tracing.tracingComplete":
            done.set()
finally:
    proc.terminate()
    try:
        proc.wait(timeout=15)
    except Exception:
        pass
    shutil.rmtree(profile, ignore_errors=True)

names = {}
for e in events:
    if e.get("ph") == "M" and e.get("name") == "process_name":
        names[e["pid"]] = e["args"]["name"]
by = collections.defaultdict(lambda: collections.Counter())
for e in events:
    if e.get("ph") != "v":
        continue
    alloc = (((e.get("args") or {}).get("dumps") or {}).get("allocators") or {})
    pname = names.get(e["pid"], str(e["pid"]))
    for path, node in alloc.items():
        if "/" in path:
            continue  # top-level allocators only
        size = ((node.get("attrs") or {}).get("size") or {}).get("value")
        if size:
            by[pname][path] += int(size, 16)
for pname, c in sorted(by.items()):
    print(f"{pname}: " + ", ".join(f"{k} {v / 1e6:.1f}" for k, v in c.most_common(9)))
