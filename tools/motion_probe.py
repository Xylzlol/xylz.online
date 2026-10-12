"""The wall's change map, as the gaze worker receives it: loads the page with ?debug, records the
maps for a few seconds while the pointer rests, then hovers a link so a pour runs, and prints per
map the total change, where the strongest block is, and how far the change has spread from the
pour's start. Usage: motion_probe.py"""
import shutil, json, pathlib, subprocess, tempfile, time, urllib.request, math
import websocket

chrome = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
profile = pathlib.Path(tempfile.mkdtemp(prefix="xylz-motion-"))
proc = subprocess.Popen([chrome, "--headless=new", "--hide-scrollbars", "--no-first-run", "--remote-allow-origins=*",
                         "--remote-debugging-port=0", f"--user-data-dir={profile}", "about:blank"],
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=subprocess.CREATE_NO_WINDOW)
try:
    pf = profile / "DevToolsActivePort"
    for _ in range(100):
        if pf.exists() and pf.read_text().strip():
            break
        time.sleep(0.1)
    port = pf.read_text().splitlines()[0]
    tgt = next(t for t in json.load(urllib.request.urlopen(f"http://127.0.0.1:{port}/json")) if t["type"] == "page")
    ws = websocket.create_connection(tgt["webSocketDebuggerUrl"], timeout=120)
    n = [0]

    def call(m, p=None):
        n[0] += 1; i = n[0]
        ws.send(json.dumps({"id": i, "method": m, "params": p or {}}))
        while True:
            msg = json.loads(ws.recv())
            if msg.get("id") == i:
                if "error" in msg:
                    raise RuntimeError(msg["error"])
                return msg.get("result", {})

    def ev(expr):
        r = call("Runtime.evaluate", {"expression": expr, "returnByValue": True, "awaitPromise": True})
        if "exceptionDetails" in r:
            raise RuntimeError(r["exceptionDetails"])
        return r["result"].get("value")

    def mouse(x, y):
        call("Input.dispatchMouseEvent", {"type": "mouseMoved", "x": x, "y": y, "pointerType": "mouse"})

    call("Page.enable"); call("Runtime.enable")
    call("Emulation.setDeviceMetricsOverride", {"width": 1440, "height": 900, "deviceScaleFactor": 1, "mobile": False})
    call("Page.navigate", {"url": ("http://localhost:8765/?debug&dyn" if "--dyn" in __import__("sys").argv else "http://localhost:8765/?debug")})
    time.sleep(2.5)
    mouse(700, 600); time.sleep(0.3)
    ev("window.__gazeWorker.postMessage({type:'motionLog', on:true}), 1")
    t0 = ev("performance.now()")
    time.sleep(1.5)
    box = ev("(() => { const r = document.querySelector('.target[data-key=github]').getBoundingClientRect(); return {x: r.left + r.width/2, y: r.top + r.height/2}; })()")
    # glide onto the link and rest there, so the pour commits
    for k in range(12):
        mouse(700 + (box["x"] - 700) * (k + 1) / 12, 600 + (box["y"] - 600) * (k + 1) / 12); time.sleep(0.016)
    tpour = ev("performance.now()")
    f0 = ev("document.documentElement.dataset.field")
    hov = ev(f"(() => {{ const e = document.elementFromPoint({box['x']}, {box['y']}); return e ? e.outerHTML.slice(0, 80) : null; }})()")
    time.sleep(2.5)
    ev("window.__gazeWorker.postMessage({type:'motionLog', on:false}), 1")
    time.sleep(0.3)
    log = ev("window.__motionLog")
    shows = ev("window.__gazeShows || []")
    print("field", f0, "->", ev("document.documentElement.dataset.field"), "| under pointer:", hov)
    name = ev("(() => { const r = document.querySelector('.name').getBoundingClientRect(); return {x0: r.left, y0: r.top + scrollY, x1: r.right, y1: r.bottom + scrollY}; })()")
    sy = ev("scrollY")
finally:
    proc.terminate()
    try:
        proc.wait(timeout=15)
    except Exception:
        pass
    shutil.rmtree(profile, ignore_errors=True)  # never leave the profile in %TEMP%

print(f"maps {len(log)}; pour hovered at +{(tpour - t0):.0f} ms at ({box['x']:.0f},{box['y'] + sy:.0f}); name {name}")
for m in log:
    cell = m["B"] * m["pitch"]
    e = m["e"]; tot = sum(e)
    if not e:
        continue
    k = max(range(len(e)), key=lambda i: e[i])
    bx, by = k % m["nbx"], k // m["nbx"] + m["by0"]
    cx, cy = (bx + 0.5) * cell, (by + 0.5) * cell
    in_name = sum(v for i, v in enumerate(e)
                  if name["x0"] <= ((i % m["nbx"]) + 0.5) * cell <= name["x1"]
                  and name["y0"] <= ((i // m["nbx"] + m["by0"]) + 0.5) * cell <= name["y1"])
    # radius of the changed region around the hovered link: the farthest block with > 20% of the max
    far = max((math.hypot(((i % m["nbx"]) + 0.5) * cell - box["x"], ((i // m["nbx"] + m["by0"]) + 0.5) * cell - box["y"] - sy)
               for i, v in enumerate(e) if v > 0.2 * e[k]), default=0)
    print(f"  +{m['t'] - t0:6.0f} ms  total {tot:7.2f}  name share {in_name / tot if tot else 0:4.2f}  max {e[k]:5.2f} at ({cx:.0f},{cy:.0f})  spread {far:5.0f} px")

print("estimate jumps (time from hover, position, distance from the hovered link):")
for j in shows:
    if j["t"] < tpour - 600:
        continue
    print(f"  +{j['t'] - tpour:6.0f} ms  ({j['x']:.0f},{j['y']:.0f})  r50 {j['r50']:.0f}  from link {math.hypot(j['x'] - box['x'], j['y'] - box['y'] - sy):.0f} px")
