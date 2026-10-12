"""Phone input, for real: a 390 x 844 touch device (Chromium, mobile emulation, touch events), driven
with synthesized touch gestures. Every scenario logs link activations (clicks on links, which would
navigate), hash changes, field changes and scroll, and prints PASS/FAIL against what a phone visitor
should get. Links are kept from actually navigating so each scenario sees its own result."""
import shutil, json, pathlib, subprocess, sys, tempfile, time, urllib.request
import websocket

chrome = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
URL = "http://localhost:8765/"
profile = pathlib.Path(tempfile.mkdtemp(prefix="xylz-touch-"))
proc = subprocess.Popen([chrome, "--headless=new", "--hide-scrollbars", "--no-first-run", "--remote-allow-origins=*",
                         "--remote-debugging-port=0", f"--user-data-dir={profile}", "about:blank"],
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=subprocess.CREATE_NO_WINDOW)
LOG = r"""
window.__ev = [];
const t0 = performance.now();
const log = (k, v) => window.__ev.push([Math.round(performance.now() - t0), k, v]);
// after the page's own handlers (bubble phase on window): only clicks that would really navigate
addEventListener('click', (e) => {
  const a = e.target.closest('a');
  if (!a || e.defaultPrevented) return;
  log('open', a.getAttribute('href'));
  if (!a.getAttribute('href').startsWith('#')) e.preventDefault();
});
addEventListener('hashchange', () => log('hash', location.hash));
addEventListener('DOMContentLoaded', () => {
  new MutationObserver(() => log('field', document.documentElement.dataset.field))
    .observe(document.documentElement, { attributes: true, attributeFilter: ['data-field'] });
});
"""
results = []
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
        r = call("Runtime.evaluate", {"expression": e, "returnByValue": True, "awaitPromise": True})
        if "exceptionDetails" in r:
            raise RuntimeError(json.dumps(r["exceptionDetails"])[:400])
        return r["result"].get("value")

    call("Page.enable"); call("Runtime.enable")
    call("Emulation.setDeviceMetricsOverride", {"width": 390, "height": 844, "deviceScaleFactor": 3, "mobile": True})
    call("Emulation.setTouchEmulationEnabled", {"enabled": True, "maxTouchPoints": 5})
    call("Emulation.setUserAgentOverride", {"userAgent": "Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0.0.0 Mobile Safari/537.36"})
    call("Emulation.setEmulatedMedia", {"features": [{"name": "prefers-reduced-motion", "value": "no-preference"}]})
    call("Page.addScriptToEvaluateOnNewDocument", {"source": LOG})

    def fresh(scroll=0):
        call("Page.navigate", {"url": "about:blank"}); time.sleep(0.2)
        call("Page.navigate", {"url": URL}); time.sleep(2.2)
        if scroll:
            js(f"window.scrollTo(0, {scroll})"); time.sleep(0.4)
        js("window.__ev.length = 0")

    def rect(sel, i=0):
        return js(f"(() => {{ const r = document.querySelectorAll({json.dumps(sel)})[{i}].getBoundingClientRect(); return [r.left + r.width / 2, r.top + r.height / 2, r.top, r.bottom]; }})()")

    def touch(kind, x, y):
        pts = [] if kind == "touchEnd" else [{"x": x, "y": y, "id": 1}]
        call("Input.dispatchTouchEvent", {"type": kind, "touchPoints": pts})

    def drag(x, y0, y1, ms, steps=None):
        """a finger on the glass from y0 to y1 over ms (a scroll by hand)"""
        steps = steps or max(4, int(ms / 16))
        touch("touchStart", x, y0)
        for k in range(1, steps + 1):
            time.sleep(ms / steps / 1000)
            touch("touchMove", x, y0 + (y1 - y0) * k / steps)
        touch("touchEnd", x, y1)

    def tap(x, y, hold=0.06):
        touch("touchStart", x, y); time.sleep(hold); touch("touchEnd", x, y)

    def fling(x, y, dy):
        call("Input.synthesizeScrollGesture", {"x": x, "y": y, "yDistance": dy, "speed": 2400, "gestureSourceType": "touch", "preventFling": False})

    def check(name, expect_open, expect_field_change, extra=None):
        time.sleep(1.3)
        ev = js("window.__ev")
        opens = [v for _, k, v in ev if k == "open"]
        fields = [v for _, k, v in ev if k == "field"]
        sy = js("scrollY")
        ok = (bool(opens) == expect_open) and (expect_field_change is None or bool(fields) == expect_field_change)
        if extra:
            ok = ok and extra(ev, sy)
        results.append(ok)
        print(("PASS " if ok else "FAIL ") + name, "| opens:", opens, "| field:", fields, "| scrollY:", sy, flush=True)
        return ev

    fresh()
    print("loaded:", js("JSON.stringify({url: location.href, ready: document.readyState, targets: document.querySelectorAll('.targets .target').length, title: document.title})"))
    # 1. a scroll that starts on a top destination (thumb lands on Immunefi, page scrolls)
    fresh(); x, y, _, _ = rect(".targets .target", 0)
    drag(x, y, y - 320, 380)
    check("scroll starting on Immunefi", expect_open=False, expect_field_change=False, extra=lambda ev, sy: sy > 100)

    # 2. a scroll starting on GitHub
    fresh(); x, y, _, _ = rect(".targets .target", 2)
    drag(x, y, y - 320, 380)
    check("scroll starting on GitHub", False, False, lambda ev, sy: sy > 100)

    # 3. a slow, hesitant scroll on X (the finger rests, then moves)
    fresh(); x, y, _, _ = rect(".targets .target", 3)
    touch("touchStart", x, y); time.sleep(0.25)
    for k in range(1, 20):
        time.sleep(0.03); touch("touchMove", x, y - k * 12)
    touch("touchEnd", x, y - 228)
    check("hesitant scroll starting on X", False, False, lambda ev, sy: sy > 50)

    # 4. a fast swipe, then a tap to stop the momentum, landing on a destination
    fresh(); x, y, _, _ = rect(".targets .target", 2)
    drag(195, 780, 380, 120, steps=6); time.sleep(0.05)
    x, y, _, _ = rect(".targets .target", 2)
    tap(x, max(10, min(830, y)))
    check("fast swipe, then a tap to stop it on GitHub", False, None, lambda ev, sy: True)

    # 5. scrolling across the Elsewhere links at the bottom
    fresh(scroll=99999); x, y, _, _ = rect(".close-links .target", 1)
    drag(x, y, y + 300, 380)
    check("scroll across Elsewhere links", False, False)

    # 6. one tap on a destination selects it: the pour, no leaving the page
    fresh(); x, y, _, _ = rect(".targets .target", 2)
    tap(x, y)
    check("one tap on GitHub selects it", False, True)

    # 7. its open control opens it
    x, y, _, _ = rect(".targets .target.current .t-open")
    js("window.__ev.length = 0"); tap(x, y)
    check("tap on GitHub's open control", True, False)

    # 8. the destination selected at load is safe from a stray tap
    fresh(); x, y, _, _ = rect(".targets .target", 0)
    tap(x - 60, y)
    check("stray tap on Immunefi (selected at load)", False, False)

    # 9. Public work: a tap selects, go jumps to the section
    fresh(); x, y, _, _ = rect(".targets .target", 1)
    tap(x - 60, y)
    check("tap on Public work selects it", False, True)
    x, y, _, _ = rect(".targets .target.current .t-open")
    js("window.__ev.length = 0"); tap(x, y)
    check("tap on Public work's go control jumps", True, False, lambda ev, sy: sy > 300)

    # 10. keyboard and assistive activation still open at once (a click with no pointer)
    fresh()
    js("document.querySelectorAll('.targets .target')[3].click()")
    check("activation without a pointer opens X", True, None, lambda ev, sy: True)

    # 11. the open control is a real touch target
    fresh()
    box = js("(() => { const r = document.querySelector('.targets .target.current .t-open').getBoundingClientRect(); return [r.width, r.height]; })()")
    ok = box[0] >= 44 and box[1] >= 44
    results.append(ok); print(("PASS " if ok else "FAIL ") + "open control size", box)

    print("SUMMARY", sum(results), "/", len(results))
finally:
    proc.terminate()
    try:
        proc.wait(timeout=15)
    except Exception:
        pass
    shutil.rmtree(profile, ignore_errors=True)  # never leave the profile in %TEMP%