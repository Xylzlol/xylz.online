"""Smoothness and memory, measured on what reaches the screen, in a real windowed Chrome.

Modes: --sw (hardware acceleration off: --disable-gpu, verified from Chrome's own GPU feature
status) or --gpu (on). The window sits off screen with occlusion/background throttling disabled,
1456x1020 at DPR 1.

Every scenario runs the same scripted input and is bracketed by console.timeStamp markers, so the
Chrome trace and the page clock line up. Per scenario:
- display: every viz DrawAndSwap (what the display compositor actually put on screen). While the
  page is animating (the wall delivering frames, or a scroll in flight), a gap between two draws of
  more than 1.5 vsyncs is a dropped frame; reported: frames drawn, drops, worst gap.
- page: dropped main-frame updates (PipelineReporter STATE_DROPPED for the page's own layer tree),
  long animation frames (> 50 ms) on the main thread.
- wall: the worker's frame gaps while it animates.
- CPU: process CPU time (renderer, GPU/viz, browser) over the scenario, as % of one core.
Memory: private bytes (USS) of every process of this browser, the page's and each worker's JS heap,
after load, after all scenarios, and after 60 s more of continuous activity (a leak check).
Usage: frames_test.py --sw|--gpu [--json out.json]"""
import shutil, json, pathlib, subprocess, sys, tempfile, threading, time, urllib.request, collections, math
import websocket, psutil

chrome = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
SW = "--gpu" not in sys.argv
out_json = sys.argv[sys.argv.index("--json") + 1] if "--json" in sys.argv else None
CSS = sys.argv[sys.argv.index("--css") + 1] if "--css" in sys.argv else ""   # extra CSS, for cost experiments
QUICK = "--quick" in sys.argv
# a slower machine: --cores 4 pins every process of this browser to 4 logical CPUs (one per physical
# core), --throttle N slows the renderer's CPU N times (Chrome's own throttling; checked below on the
# page and in a worker)
CORES = int(sys.argv[sys.argv.index("--cores") + 1]) if "--cores" in sys.argv else 0
THROTTLE = float(sys.argv[sys.argv.index("--throttle") + 1]) if "--throttle" in sys.argv else 1   # load, stir, pours, reading only; no leak check
URL = sys.argv[sys.argv.index("--url") + 1] if "--url" in sys.argv else "http://localhost:8765/?debug"
profile = pathlib.Path(tempfile.mkdtemp(prefix="xylz-frames-"))
flags = [chrome, "--no-first-run", "--no-default-browser-check", "--remote-allow-origins=*", "--remote-debugging-port=0",
         f"--user-data-dir={profile}", "--window-position=-2400,-2400", "--window-size=1456,1020",
         "--disable-backgrounding-occluded-windows", "--disable-renderer-backgrounding", "--disable-background-timer-throttling",
         "--disable-features=CalculateNativeWinOcclusion", "--disable-extensions", "about:blank"]
if SW:
    flags.insert(1, "--disable-gpu")
proc = subprocess.Popen(flags, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
CPUS = list(range(0, 2 * CORES, 2)) if CORES else None


def pin():
    if not CPUS:
        return
    try:
        root = psutil.Process(proc.pid)
        for p in [root] + root.children(recursive=True):
            try:
                p.cpu_affinity(CPUS)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
    except psutil.NoSuchProcess:
        pass


pin()
events = []
bufmax = [0.0]
LOAF = """window.__loaf = []; try { new PerformanceObserver((l) => { for (const e of l.getEntries())
  window.__loaf.push({ t: e.startTime, d: e.duration, scripts: (e.scripts || []).map((s) => (s.sourceFunctionName || s.invoker) + ' @' + (s.sourceURL || '').split('/').pop() + ' ' + Math.round(s.duration) + 'ms') }); })
  .observe({ type: 'long-animation-frame', buffered: true }); } catch (e) {}"""


def tree():
    root = psutil.Process(proc.pid)
    ps = [root] + root.children(recursive=True)
    out = {}
    for p in ps:
        try:
            cmd = " ".join(p.cmdline())
            kind = "browser" if p.pid == proc.pid else ("gpu" if "--type=gpu-process" in cmd else
                   "renderer" if "--type=renderer" in cmd else "utility" if "--type=utility" in cmd else "other")
            mi = p.memory_full_info()
            ct = p.cpu_times()
            out[p.pid] = {"kind": kind, "uss": mi.uss, "cpu": ct.user + ct.system, "cmd": cmd[-120:]}
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    return out


try:
    pf = profile / "DevToolsActivePort"
    for _ in range(150):
        if pf.exists() and pf.read_text().strip():
            break
        time.sleep(0.1)
    port, bpath = pf.read_text().splitlines()[:2]
    bws = websocket.create_connection(f"ws://127.0.0.1:{port}{bpath}", timeout=60)
    bn = [0]

    def bcall(m, p=None):
        bn[0] += 1; i = bn[0]
        bws.send(json.dumps({"id": i, "method": m, "params": p or {}}))
        while True:
            r = json.loads(bws.recv())
            if r.get("id") == i:
                if "error" in r:
                    raise RuntimeError(r["error"])
                return r.get("result", {})

    fs = bcall("SystemInfo.getInfo")["gpu"]["featureStatus"]
    status = {k: fs.get(k) for k in ("gpu_compositing", "2d_canvas", "rasterization")}
    if SW:
        assert status["gpu_compositing"].startswith("disabled") and "software" in status["2d_canvas"], status
    tgt = next(t for t in json.load(urllib.request.urlopen(f"http://127.0.0.1:{port}/json")) if t["type"] == "page")
    ws = websocket.create_connection(tgt["webSocketDebuggerUrl"], timeout=120)
    lock = threading.Lock(); pending = {}; cid = [0]; done = threading.Event(); workers = {}

    def reader():
        while True:
            try:
                msg = json.loads(ws.recv())
            except Exception:
                return
            if msg.get("method") == "Tracing.bufferUsage":
                bufmax[0] = max(bufmax[0], msg["params"].get("percentFull", 0) or 0)
            elif msg.get("method") == "Tracing.dataCollected":
                events.extend(msg["params"]["value"])
            elif msg.get("method") == "Tracing.tracingComplete":
                done.set()
            elif msg.get("method") == "Target.attachedToTarget":
                ti = msg["params"]["targetInfo"]
                workers[msg["params"]["sessionId"]] = ti.get("url", "").split("/")[-1].split("?")[0]
            elif "id" in msg and msg["id"] in pending:
                pending[msg["id"]].append(msg)
    threading.Thread(target=reader, daemon=True).start()

    def call(m, p=None, session=None):
        with lock:
            cid[0] += 1; i = cid[0]; pending[i] = []
            o = {"id": i, "method": m, "params": p or {}}
            if session:
                o["sessionId"] = session
            ws.send(json.dumps(o))
        for _ in range(12000):
            if pending[i]:
                r = pending.pop(i)[0]
                if "error" in r:
                    raise RuntimeError(r["error"])
                return r.get("result", {})
            time.sleep(0.005)
        raise TimeoutError(m)

    def js(e):
        return call("Runtime.evaluate", {"expression": e, "returnByValue": True, "awaitPromise": True})["result"].get("value")

    def move(x, y):
        call("Input.dispatchMouseEvent", {"type": "mouseMoved", "x": x, "y": y, "pointerType": "mouse"})

    def wheel(x, y, dy):
        call("Input.dispatchMouseEvent", {"type": "mouseWheel", "x": x, "y": y, "deltaX": 0, "deltaY": dy, "pointerType": "mouse"})

    def heaps():
        h = {"page": call("Runtime.getHeapUsage")["usedSize"]}
        for sid, name in list(workers.items()):
            try:
                h[name] = call("Runtime.getHeapUsage", session=sid)["usedSize"]
            except Exception:
                pass
        return h

    def memory(label):
        t = tree()
        by = collections.defaultdict(int)
        for v in t.values():
            by[v["kind"]] += v["uss"]
        return {"label": label, "uss_mb": {k: round(v / 1e6, 1) for k, v in by.items()}, "total_mb": round(sum(by.values()) / 1e6, 1),
                "js_heap_mb": {k: round(v / 1e6, 2) for k, v in heaps().items()}}

    pin()
    call("Page.enable"); call("Runtime.enable")
    if THROTTLE > 1:
        call("Emulation.setCPUThrottlingRate", {"rate": THROTTLE})
    call("Target.setAutoAttach", {"autoAttach": True, "waitForDebuggerOnStart": False, "flatten": True})
    call("Page.addScriptToEvaluateOnNewDocument", {"source": LOAF})
    if CSS:
        call("Page.addScriptToEvaluateOnNewDocument", {"source": "addEventListener('DOMContentLoaded', () => { const s = document.createElement('style'); s.textContent = " + json.dumps(CSS) + "; document.head.append(s); });"})
    mem = []
    # only what the metrics read (a 540 Hz display at full categories overflows the trace buffer and
    # silently drops the later scenarios); the buffer's fill is reported so an overflow cannot hide
    call("Tracing.start", {"traceConfig": {"includedCategories": ["graphics.pipeline", "devtools.timeline", "benchmark", "viz"],
                                           "excludedCategories": ["*"], "recordMode": "recordAsMuchAsPossible"},
                           "transferMode": "ReportEvents", "bufferUsageReportingInterval": 500})
    scen = []
    cpu0 = {}

    def begin(name):
        js(f"console.timeStamp('S:{name}'), 1")
        cpu0[name] = tree()
        scen.append({"name": name, "t0": js("performance.now()")})

    def end():
        s = scen[-1]
        s["t1"] = js("performance.now()")
        js(f"console.timeStamp('E:{s['name']}'), 1")
        t1 = tree()
        dt = (s["t1"] - s["t0"]) / 1000
        by = collections.defaultdict(float)
        for pid, v in t1.items():
            if pid in cpu0[s["name"]]:
                by[v["kind"]] += v["cpu"] - cpu0[s["name"]][pid]["cpu"]
        s["cpu_pct"] = {k: round(100 * v / dt) for k, v in by.items()}

    # 1. first load: navigate, pointer resting; then idle
    begin("load")
    call("Page.navigate", {"url": URL})
    time.sleep(3.0)
    end()
    vp = js("[innerWidth, innerHeight, devicePixelRatio, document.documentElement.scrollHeight]")
    pin()
    # does the throttle reach workers? the same busy loop on the page and in a fresh worker
    bench = "(() => { const t = performance.now(); let x = 0; for (let i = 0; i < 3e7; i++) x += Math.sqrt(i); return performance.now() - t; })()"
    slow = {"page_ms": round(js(bench)), "worker_ms": round(js("new Promise(r => { const w = new Worker(URL.createObjectURL(new Blob(['postMessage(' + " + json.dumps(bench) + " + ')']))); w.onmessage = (e) => { r(e.data); w.terminate(); }; })"))}
    mem.append(memory("after load"))
    begin("idle")
    time.sleep(2.5)
    end()
    # 2. stirring the name: the pointer sweeps across the letters
    begin("stir name")
    for k in range(180):
        move(200 + 900 * (0.5 + 0.5 * math.sin(k / 9)), 260 + 160 * math.sin(k / 13)); time.sleep(0.016)
    time.sleep(0.8)
    end()
    R = json.loads(js("JSON.stringify([...document.querySelectorAll('.targets .target')].map(e => { const r = e.getBoundingClientRect(); return [r.left + r.width / 2, r.top + r.height / 2]; }))"))
    # 3. pours: glide to each destination and settle
    begin("pours")
    x, y = 700, 400
    for target in [2, 3, 1, 0]:
        tx, ty = R[target]
        for k in range(1, 31):
            u = 1 - (1 - k / 30) ** 3
            move(x + (tx - x) * u, y + (ty - y) * u); time.sleep(0.016)
        x, y = tx, ty
        time.sleep(1.5)
    end()
    if not QUICK:
        # 4. scrolling with the wheel, down the whole page and back, pointer resting on text
        begin("wheel scroll")
        for k in range(40):
            wheel(700, 500, 100); time.sleep(0.05)
        for k in range(40):
            wheel(700, 500, -100); time.sleep(0.05)
        time.sleep(0.8)
        end()
        # 5. scrolling while a pour runs
        js("scrollTo(0, 0), 1"); time.sleep(0.5)
        begin("scroll during pour")
        tx, ty = R[2]
        for k in range(1, 21):
            move(700 + (tx - 700) * k / 20, 400 + (ty - 400) * k / 20); time.sleep(0.016)
        time.sleep(0.15)
        for k in range(20):
            wheel(tx, ty, 120); time.sleep(0.04)
        time.sleep(1.2)
        end()
    # 6. reading: the pointer drifts slowly along lines of text further down (gaze jumps)
    begin("reading")
    js("scrollTo(0, 900), 1"); time.sleep(0.3)
    for k in range(240):
        move(150 + (k % 60) * 12, 300 + (k // 60) * 40); time.sleep(0.016)
    time.sleep(0.5)
    end()
    if not QUICK:
        # 7. smooth programmatic scroll to the end and back (anchor-like)
        begin("smooth scroll")
        js("scrollTo({top: document.documentElement.scrollHeight, behavior: 'smooth'}), 1"); time.sleep(1.6)
        js("scrollTo({top: 0, behavior: 'smooth'}), 1"); time.sleep(1.6)
        end()
        # 8. resize while animating
        begin("resize")
        win = bcall("Browser.getWindowForTarget", {"targetId": tgt["id"]})["windowId"]
        for w in (1300, 1100, 1456):
            move(400, 300); bcall("Browser.setWindowBounds", {"windowId": win, "bounds": {"width": w, "height": 1020}}); time.sleep(0.7)
        end()
        # 9. minimise and restore
        begin("restore")
        bcall("Browser.setWindowBounds", {"windowId": win, "bounds": {"windowState": "minimized"}}); time.sleep(1.0)
        bcall("Browser.setWindowBounds", {"windowId": win, "bounds": {"windowState": "normal"}}); time.sleep(0.2)
        move(500, 300); move(600, 320); time.sleep(1.5)
        end()
    mem.append(memory("after scenarios"))
    frames = js("window.__wallFrames || []")
    loaf = js("window.__loaf || []")
    call("Tracing.end"); done.wait(120)
    if not QUICK:
        # 10. leak check: 60 s more of stirring and pours, untraced
        for r in range(4):
            for target in [2, 3, 1, 0]:
                tx, ty = R[target]
                for k in range(1, 31):
                    move(700 + (tx - 700) * k / 30, 400 + (ty - 400) * k / 30); time.sleep(0.016)
                time.sleep(1.2)
            for k in range(120):
                move(200 + 900 * (0.5 + 0.5 * math.sin(k / 9)), 260 + 160 * math.sin(k / 13)); time.sleep(0.016)
        js("new Promise(r => setTimeout(r, 1500))")
        mem.append(memory("after 60 s more"))
        call("HeapProfiler.collectGarbage")
        for sid in list(workers):
            try:
                call("HeapProfiler.collectGarbage", session=sid)
            except Exception:
                pass
        time.sleep(1)
        mem.append(memory("after GC"))
    canv = js("""[...document.querySelectorAll('canvas')].map(c => ({cls: c.className, css: [Math.round(c.getBoundingClientRect().width), Math.round(c.getBoundingClientRect().height)], px: c.width ? [c.width, c.height] : 'transferred'}))""")
finally:
    proc.terminate()
    try:
        proc.wait(timeout=15)
    except Exception:
        pass
    shutil.rmtree(profile, ignore_errors=True)  # never leave the profile in %TEMP%

# ---- align the trace with the page clock ----
marks = {}
for e in events:
    if e.get("name") == "TimeStamp":
        msg = ((e.get("args") or {}).get("data") or {}).get("message", "")
        if msg[:2] in ("S:", "E:"):
            marks[msg] = e["ts"]
draws = sorted(e["ts"] for e in events if e.get("name") == "Graphics.Pipeline.DrawAndSwap" and e.get("ph") in ("b", "B"))
vsync_iv = sorted(b - a for a, b in zip(draws, draws[1:]))
# the display's frame interval, from the BeginFrameArgs viz sends (falls back to the draws' 10th percentile)
ivals = []
def _walk(o):
    if isinstance(o, dict):
        for k, v in o.items():
            if k in ("interval_delta_in_us", "interval_us") and isinstance(v, (int, float)) and v > 0:
                ivals.append(v)
            else:
                _walk(v)
for e in events:
    if "BeginFrame" in (e.get("name") or "") and e.get("args"):
        _walk(e["args"])
vsync = sorted(ivals)[len(ivals) // 2] if ivals else (vsync_iv[len(vsync_iv) // 10] if vsync_iv else 16667)
page_lth = collections.Counter(((e.get("args") or {}).get("frame_reporter") or {}).get("layer_tree_host_id")
                               for e in events if e.get("name") == "PipelineReporter").most_common(1)[0][0]
print(f"trace buffer peak {bufmax[0] * 100:.0f}% full{'  (OVERFLOW: later events lost)' if bufmax[0] >= 0.99 else ''}")
print(f"mode: {'hardware acceleration OFF' if SW else 'GPU'}  feature status {status}  viewport {vp}  vsync ~{vsync / 1000:.1f} ms  cores {CPUS or 'all'}  throttle x{THROTTLE}  busy-loop page/worker {slow}")
print(f"{'scenario':20s} {'drawn':>6s} {'fps':>5s} {'>25ms':>6s} {'worst':>7s} {'pageDrop':>8s} {'wallGap':>8s} {'LoAF>50':>8s}  cpu% (renderer/gpu/browser)")
rows = []
for s in scen:
    a, b = marks.get("S:" + s["name"]), marks.get("E:" + s["name"])
    if a is None or b is None:
        continue
    off = a - s["t0"] * 1000  # trace us = page ms * 1000 + off
    wf = [f for f in frames if s["t0"] <= f <= s["t1"]]
    # animating: within 120 ms of a wall frame, or a scroll scenario
    active = lambda ts: any(abs((ts - off) / 1000 - f) < 120 for f in wf) or "scroll" in s["name"]
    d = [t for t in draws if a <= t <= b]
    gaps = [(q - p) for p, q in zip(d, d[1:]) if active(p) and active(q)]
    drops = sum(1 for g in gaps if g > 25000)  # a gap a viewer sees as a hitch at any refresh rate
    act_s = sum(gaps) / 1e6
    fps = round(len(gaps) / act_s) if act_s > 0 else 0
    worst = max(gaps) / 1000 if gaps else 0
    pdrop = sum(1 for e in events if e.get("name") == "PipelineReporter" and e.get("ph") in ("b", "B") and a <= e["ts"] <= b
                and ((e.get("args") or {}).get("frame_reporter") or {}).get("layer_tree_host_id") == page_lth
                and ((e.get("args") or {}).get("frame_reporter") or {}).get("state") == "STATE_DROPPED")
    wgaps = [q - p for p, q in zip(wf, wf[1:]) if q - p < 400]
    lo = [l for l in loaf if s["t0"] <= l["t"] <= s["t1"] and l["d"] > 50]
    row = {"scenario": s["name"], "drawn": len(d), "fps": fps, "gaps_over_25ms": drops, "worst_ms": round(worst, 1), "page_dropped": pdrop,
           "wall_worst_gap_ms": round(max(wgaps), 1) if wgaps else None, "loaf_over_50": [(round(l["d"]), l["scripts"][:3]) for l in lo], "cpu_pct": s["cpu_pct"]}
    rows.append(row)
    c = s["cpu_pct"]
    print(f"{s['name']:20s} {len(d):6d} {fps:5d} {drops:6d} {worst:7.1f} {pdrop:8d} {str(row['wall_worst_gap_ms']):>8s} {len(lo):8d}  {c.get('renderer', 0)}/{c.get('gpu', 0)}/{c.get('browser', 0)}")
    for l in lo[:3]:
        print(f"{'':22s}LoAF {round(l['d'])} ms: {l['scripts'][:3]}")
print("\nmemory (private MB by process kind; JS heap MB by context):")
for m in mem:
    print(f"  {m['label']:18s} total {m['total_mb']:7.1f}  {m['uss_mb']}  heaps {m['js_heap_mb']}")
print("canvases:", canv)
if out_json:
    pathlib.Path(out_json).write_text(json.dumps({"sw": SW, "status": status, "vsync_ms": vsync / 1000, "rows": rows, "memory": mem, "canvases": canv}, indent=1))
