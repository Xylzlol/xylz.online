"""Memory of the page, old against new: headless Chrome (real GPU), low priority. Measures private
memory (USS) of every process of that browser, by kind, and the JS heap of the page and each worker
(wall, pour, gaze): after load, after about 45 s of stirring, pours to every field and scrolling,
and after a forced garbage collection.
Usage: mem_test.py URL [--cpus 12,13,14,15]"""
import json, math, pathlib, shutil, subprocess, sys, tempfile, threading, time, urllib.request, collections
import psutil, websocket

url = sys.argv[1]
CSS = sys.argv[sys.argv.index("--css") + 1] if "--css" in sys.argv else ""  # extra CSS, to find what costs
cpus = [int(x) for x in sys.argv[sys.argv.index("--cpus") + 1].split(",")] if "--cpus" in sys.argv else None
chrome = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
profile = pathlib.Path(tempfile.mkdtemp(prefix="xylz-mem-"))
proc = subprocess.Popen([chrome, "--headless=new", "--hide-scrollbars", "--no-first-run", "--remote-allow-origins=*",
                         "--remote-debugging-port=0", f"--user-data-dir={profile}", "about:blank"],
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=subprocess.CREATE_NO_WINDOW)


def procs():
    root = psutil.Process(proc.pid)
    return [root] + root.children(recursive=True)


def lower():
    for p in procs():
        try:
            p.nice(psutil.BELOW_NORMAL_PRIORITY_CLASS)
            if cpus:
                p.cpu_affinity(cpus)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass


workers = {}
try:
    pf = profile / "DevToolsActivePort"
    for _ in range(100):
        try:
            if pf.exists() and pf.read_text().strip():
                break
        except PermissionError:
            pass
        time.sleep(0.1)
    port = pf.read_text().splitlines()[0]
    lower()
    tgt = next(t for t in json.load(urllib.request.urlopen(f"http://127.0.0.1:{port}/json")) if t["type"] == "page")
    ws = websocket.create_connection(tgt["webSocketDebuggerUrl"], timeout=60)
    lock = threading.Lock(); pending = {}; cid = [0]

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

    def memory(label):
        by = collections.defaultdict(int)
        for p in procs():
            try:
                cmd = " ".join(p.cmdline())
                kind = "browser" if p.pid == proc.pid else "gpu" if "--type=gpu-process" in cmd else "renderer" if "--type=renderer" in cmd else "other"
                by[kind] += p.memory_full_info().uss
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
        heaps = {"page": call("Runtime.getHeapUsage").get("usedSize", 0)}
        for s, name in list(workers.items()):
            heaps[name] = call("Runtime.getHeapUsage", session=s).get("usedSize", 0)
        return {"label": label, "total": sum(by.values()), "by": dict(by), "heaps": heaps}

    call("Page.enable"); call("Runtime.enable")
    call("Target.setAutoAttach", {"autoAttach": True, "waitForDebuggerOnStart": False, "flatten": True})
    call("Emulation.setDeviceMetricsOverride", {"width": 1456, "height": 933, "deviceScaleFactor": 1, "mobile": False})
    if CSS:
        call("Page.addScriptToEvaluateOnNewDocument", {"source": "addEventListener('DOMContentLoaded', () => { const s = document.createElement('style'); s.textContent = " + json.dumps(CSS) + "; document.head.append(s); });"})
    call("Page.navigate", {"url": url})
    time.sleep(4); lower()
    mv = lambda x, y: call("Input.dispatchMouseEvent", {"type": "mouseMoved", "x": x, "y": y, "pointerType": "mouse"})
    res = [memory("after load")]
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
    res.append(memory("after activity"))
    call("HeapProfiler.collectGarbage")
    for s in list(workers):
        call("HeapProfiler.collectGarbage", session=s)
    time.sleep(2)
    res.append(memory("after GC"))
    # what Chrome keeps only because it can: under memory pressure it drops caches
    bws = websocket.create_connection(f"ws://127.0.0.1:{port}" + pf.read_text().splitlines()[1], timeout=30)
    bws.send(json.dumps({"id": 1, "method": "Memory.simulatePressureNotification", "params": {"level": "critical"}}))
    call("Memory.simulatePressureNotification", {"level": "critical"})
    for s_ in list(workers):
        call("Memory.simulatePressureNotification", {"level": "critical"}, session=s_)
    time.sleep(3)
    res.append(memory("under pressure"))
finally:
    proc.terminate()
    try:
        proc.wait(timeout=15)
    except Exception:
        pass
    shutil.rmtree(profile, ignore_errors=True)
for m in res:
    print(f"{m['label']:15s} total {m['total'] / 1e6:6.1f} MB  " + "  ".join(f"{k} {v / 1e6:.1f}" for k, v in sorted(m["by"].items()))
          + "  | heaps MB " + "  ".join(f"{k} {v / 1e6:.2f}" for k, v in m["heaps"].items()))
