"""Script errors anywhere: loads the page with every worker attached, stirs the name, pours to the
black field and away, scrolls, and lists every exception and console error from the page and the
workers (wall, pour, gaze). Usage: errors_check.py [url]"""
import json, math, pathlib, shutil, subprocess, sys, tempfile, threading, time, urllib.request
import websocket
url = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8765/"
chrome = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
profile = pathlib.Path(tempfile.mkdtemp(prefix="xylz-err-"))
proc = subprocess.Popen([chrome, "--headless=new", "--hide-scrollbars", "--no-first-run", "--remote-allow-origins=*", "--remote-debugging-port=0", f"--user-data-dir={profile}", "about:blank"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=subprocess.CREATE_NO_WINDOW)
errors, targets = [], {}
try:
    pf = profile / "DevToolsActivePort"
    for _ in range(100):
        try:
            if pf.exists() and pf.read_text().strip(): break
        except PermissionError: pass
        time.sleep(0.1)
    port = pf.read_text().splitlines()[0]
    tgt = next(t for t in json.load(urllib.request.urlopen(f"http://127.0.0.1:{port}/json")) if t["type"] == "page")
    ws = websocket.create_connection(tgt["webSocketDebuggerUrl"], timeout=60)
    lock = threading.Lock(); pending = {}; cid = [0]
    def send(m, p=None, session=None):
        with lock:
            cid[0] += 1; i = cid[0]; pending[i] = []
            o = {"id": i, "method": m, "params": p or {}}
            if session: o["sessionId"] = session
            ws.send(json.dumps(o)); return i
    def call(m, p=None, session=None):
        i = send(m, p, session)
        for _ in range(4000):
            if pending.get(i): return pending.pop(i)[0].get("result", {})
            time.sleep(0.005)
    def reader():
        while True:
            try: msg = json.loads(ws.recv())
            except Exception: return
            meth = msg.get("method"); sid = msg.get("sessionId", "page")
            if meth == "Target.attachedToTarget":
                s = msg["params"]["sessionId"]; targets[s] = msg["params"]["targetInfo"].get("url", "").split("/")[-1].split("?")[0]
                send("Runtime.enable", session=s)
                # workers inside workers (the pour thread) attach through their parent
                send("Target.setAutoAttach", {"autoAttach": True, "waitForDebuggerOnStart": False, "flatten": True}, session=s)
                send("Runtime.runIfWaitingForDebugger", session=s)
            elif meth == "Runtime.exceptionThrown":
                d = msg["params"]["exceptionDetails"]
                errors.append((targets.get(sid, sid), (d.get("exception") or {}).get("description", d.get("text", ""))[:300]))
            elif meth == "Runtime.consoleAPICalled" and msg["params"]["type"] in ("error", "assert"):
                errors.append((targets.get(sid, sid), " ".join(str(a.get("value", a.get("description", ""))) for a in msg["params"]["args"])[:300]))
            elif meth == "Log.entryAdded" and msg["params"]["entry"]["level"] == "error":
                errors.append(("log", msg["params"]["entry"]["text"][:300]))
            elif "id" in msg and msg["id"] in pending:
                pending[msg["id"]].append(msg)
    threading.Thread(target=reader, daemon=True).start()
    call("Page.enable"); call("Runtime.enable"); call("Log.enable")
    call("Target.setAutoAttach", {"autoAttach": True, "waitForDebuggerOnStart": False, "flatten": True})
    call("Emulation.setDeviceMetricsOverride", {"width": 1440, "height": 900, "deviceScaleFactor": 1, "mobile": False})
    call("Page.navigate", {"url": url}); time.sleep(3)
    mv = lambda x, y: call("Input.dispatchMouseEvent", {"type": "mouseMoved", "x": x, "y": y, "pointerType": "mouse"})
    for k in range(120): mv(200 + 900 * (0.5 + 0.5 * math.sin(k / 9)), 260 + 160 * math.sin(k / 13)); time.sleep(0.016)
    R = json.loads(call("Runtime.evaluate", {"expression": "JSON.stringify([...document.querySelectorAll('.targets .target')].map(e => { const r = e.getBoundingClientRect(); return [r.left + r.width / 2, r.top + r.height / 2]; }))", "returnByValue": True})["result"]["value"])
    x, y = 700, 400
    for t in [2, 3, 0, 2]:
        for k in range(1, 21): mv(x + (R[t][0] - x) * k / 20, y + (R[t][1] - y) * k / 20); time.sleep(0.016)
        x, y = R[t]; time.sleep(1.4)
    for k in range(20):
        call("Input.dispatchMouseEvent", {"type": "mouseWheel", "x": 700, "y": 500, "deltaX": 0, "deltaY": 120, "pointerType": "mouse"}); time.sleep(0.05)
    time.sleep(1.5)
finally:
    proc.terminate(); proc.wait(timeout=15); shutil.rmtree(profile, ignore_errors=True)
print("contexts:", sorted(set(targets.values())))
print("ERRORS:", len(errors))
for e in errors[:20]: print("  ", e)
