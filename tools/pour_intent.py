"""Does the field (pour) change only when meant? Real mouse input over CDP at controlled speeds;
every change of data-field is logged by a MutationObserver. Prints PASS/FAIL per scenario."""
import json, math, pathlib, subprocess, tempfile, time, urllib.request
import websocket

chrome = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
profile = pathlib.Path(tempfile.mkdtemp(prefix="xylz-pi-"))
proc = subprocess.Popen([chrome, "--headless=new", "--hide-scrollbars", "--no-first-run",
                         "--remote-allow-origins=*", "--remote-debugging-port=0",
                         f"--user-data-dir={profile}", "about:blank"],
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                        creationflags=subprocess.CREATE_NO_WINDOW)
LOG = """window.__fl = []; addEventListener('DOMContentLoaded', () => new MutationObserver(() =>
  window.__fl.push(document.documentElement.dataset.field)).observe(document.documentElement, {attributes: true, attributeFilter: ['data-field']}));"""
try:
    pf = profile / "DevToolsActivePort"
    for _ in range(100):
        if pf.exists() and pf.read_text().strip():
            break
        time.sleep(0.1)
    port = pf.read_text().splitlines()[0]
    tgt = next(t for t in json.load(urllib.request.urlopen(f"http://127.0.0.1:{port}/json")) if t["type"] == "page")
    ws = websocket.create_connection(tgt["webSocketDebuggerUrl"], timeout=60)
    n = [0]

    def call(m, p=None):
        n[0] += 1
        i = n[0]
        ws.send(json.dumps({"id": i, "method": m, "params": p or {}}))
        while True:
            msg = json.loads(ws.recv())
            if msg.get("id") == i:
                if "error" in msg:
                    raise RuntimeError(msg["error"])
                return msg.get("result", {})

    def js(e):
        return call("Runtime.evaluate", {"expression": e, "returnByValue": True, "awaitPromise": True})["result"].get("value")

    pos = [0, 0]

    def move(x, y):
        pos[0], pos[1] = x, y
        call("Input.dispatchMouseEvent", {"type": "mouseMoved", "x": x, "y": y, "pointerType": "mouse"})

    def glide(x1, y1, speed, ease=False, step_ms=8):
        """move from the current position to (x1, y1) at speed px/ms; ease = decelerate into the end"""
        x0, y0 = pos
        d = math.hypot(x1 - x0, y1 - y0)
        T = d / speed * (1.6 if ease else 1.0)
        steps = max(1, int(T / step_ms))
        for k in range(1, steps + 1):
            u = k / steps
            if ease:
                u = 1 - (1 - u) ** 3  # fast start, slow landing
            move(x0 + (x1 - x0) * u, y0 + (y1 - y0) * u)
            time.sleep(step_ms / 1000)

    def wheel(dy, times):
        for _ in range(times):
            call("Input.dispatchMouseEvent", {"type": "mouseWheel", "x": pos[0], "y": pos[1], "deltaX": 0, "deltaY": dy})
            time.sleep(0.03)

    def click(x, y):
        for t in ("mousePressed", "mouseReleased"):
            call("Input.dispatchMouseEvent", {"type": t, "x": x, "y": y, "button": "left", "clickCount": 1})

    call("Page.enable")
    call("Runtime.enable")
    call("Emulation.setDeviceMetricsOverride", {"width": 1440, "height": 900, "deviceScaleFactor": 1, "mobile": False})
    call("Page.addScriptToEvaluateOnNewDocument", {"source": LOG})
    # keep links from navigating away when clicked
    call("Page.addScriptToEvaluateOnNewDocument", {"source": "addEventListener('click', e => { if (e.target.closest('a')) e.preventDefault(); }, true);"})

    def fresh(hash_=""):
        call("Page.navigate", {"url": "about:blank"})
        time.sleep(0.2)
        call("Page.navigate", {"url": "http://localhost:8765/" + hash_})
        time.sleep(2.0)
        move(700, 300)
        time.sleep(0.4)
        js("window.__fl.length = 0")

    def rects():
        return js("""JSON.stringify([...document.querySelectorAll('.targets .target')].map(e => { const r = e.getBoundingClientRect(); return [r.left, r.top, r.right, r.bottom, e.dataset.field]; }))""")

    results = []

    def check(name, expect):
        time.sleep(0.6)
        fl = js("window.__fl")
        field = js("document.documentElement.dataset.field")
        ok = (fl == expect) if isinstance(expect, list) else expect(fl, field)
        results.append((name, ok, fl, field))
        print(("PASS " if ok else "FAIL ") + name, "changes:", fl, "field:", field, flush=True)

    fresh()
    R = json.loads(rects())
    rowy = (R[0][1] + R[0][3]) / 2
    print("targets", R)

    # 1. fast horizontal sweep across all four destinations
    move(20, rowy); time.sleep(0.2); js("window.__fl.length = 0")
    glide(1400, rowy, 1.6)
    move(1400, rowy + 200)
    check("fast sweep across the row (1.6 px/ms)", [])

    # 2. moderate sweep
    fresh(); move(20, rowy); time.sleep(0.2); js("window.__fl.length = 0")
    glide(1400, rowy, 0.8)
    move(1400, rowy + 200)
    check("moderate sweep across the row (0.8 px/ms)", [])

    # 3. heading down the page through a destination
    fresh(); move(520, 200); time.sleep(0.2); js("window.__fl.length = 0")
    glide(520, 890, 1.0)
    check("passing down through Public work (1.0 px/ms)", [])

    # 4. diagonal pass on the way to the rail
    fresh(); move(200, 650); time.sleep(0.2); js("window.__fl.length = 0")
    glide(1380, 880, 1.2)
    check("diagonal pass across GitHub and X", [])

    # 5. page scrolled under a still pointer, then back
    fresh(); move(800, 500); time.sleep(0.3); js("window.__fl.length = 0")
    wheel(100, 6); time.sleep(0.6); wheel(-100, 6); time.sleep(0.6); wheel(100, 3); time.sleep(0.6)
    check("scrolling under a still pointer", [])

    # 6. aimed: decelerate onto GitHub and stop
    fresh(); move(200, 300); time.sleep(0.2); js("window.__fl.length = 0")
    gx, gy = (R[2][0] + R[2][2]) / 2, rowy
    glide(gx, gy, 1.2, ease=True)
    check("aimed at GitHub, slows and stops", ["black"])

    # 7. aimed then scroll down and back up: the choice stays
    fresh(); move(200, 300); time.sleep(0.2)
    xx = (R[3][0] + R[3][2]) / 2
    glide(xx, rowy, 1.2, ease=True); time.sleep(0.5); js("window.__fl.length = 0")
    move(1000, 300); time.sleep(0.2)
    wheel(120, 12); time.sleep(0.8); wheel(-120, 14); time.sleep(1.0)
    check("chose X, scrolled away and back: stays magenta", lambda fl, f: f == "magenta" and fl == [])

    # 8. pointer parked on a destination, then wheel: scrolling is not choosing
    fresh()
    px = (R[1][0] + R[1][2]) / 2
    move(px, 200); time.sleep(0.2); js("window.__fl.length = 0")
    glide(px, rowy, 2.0)  # fast arrival, then the wheel at once
    wheel(100, 4)
    time.sleep(0.6)
    check("arrive on Public work and scroll at once", [])

    # 9. slow reading-speed drift across the row
    fresh(); move(20, rowy); time.sleep(0.2); js("window.__fl.length = 0")
    glide(1400, rowy, 0.35)
    move(1400, rowy + 200)
    check("slow drift across the row (0.35 px/ms)", [])

    # 10. click commits immediately
    fresh(); move(200, 300); time.sleep(0.2); js("window.__fl.length = 0")
    glide(gx, gy, 3.0)
    click(gx, gy)
    check("click on GitHub mid-motion", lambda fl, f: f == "black")

    # 11. hover lingering while moving slowly inside
    fresh(); move((R[1][0] + R[1][2]) / 2 - 60, rowy - 140); time.sleep(0.2); js("window.__fl.length = 0")
    glide((R[1][0] + R[1][2]) / 2 - 60, rowy, 1.0)
    glide((R[1][0] + R[1][2]) / 2 + 60, rowy, 0.2)
    check("lingering, moving slowly inside Public work", ["sky"])

    # 12. keyboard: focus selects at once
    fresh()
    js("document.querySelectorAll('.targets .target')[3].focus()")
    check("keyboard focus on X", lambda fl, f: f == "magenta")

    # 13. after an accidental sweep the tracker goes back to the chosen destination
    fresh(); move(20, rowy); time.sleep(0.2); js("window.__fl.length = 0")
    glide(1400, rowy, 1.2)
    move(1400, rowy + 200); time.sleep(0.5)
    say = js("document.querySelector('.lock-say').textContent")
    results.append(("tracker back on Immunefi after sweep", "immunefi" in say, [], say))
    print(("PASS " if "immunefi" in say else "FAIL ") + "tracker back on the chosen destination after a sweep:", say, flush=True)

    print("SUMMARY", sum(1 for r in results if r[1]), "/", len(results))
finally:
    proc.terminate()
