"""A/B frame timing on the real GPU: rAF intervals and long animation frames while the pointer
circles, for the current build and with parts of the gaze display switched off by injected CSS."""
import json, math, pathlib, subprocess, sys, tempfile, time, urllib.request
import websocket

chrome = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
VARIANTS = {
    "white": ("", ""),
    "white-no-scanpath": ("", ".gaze-fill,.gaze-node,.gaze-path,.gaze-say,.gaze-glow{display:none!important}"),
    "black": ("#github", ""),
    "black-no-scanpath": ("#github", ".gaze-fill,.gaze-node,.gaze-path,.gaze-say,.gaze-glow{display:none!important}"),
}
ROUNDS = int(sys.argv[1]) if len(sys.argv) > 1 else 2

RECORDER = r"""
window.__fr = { d: [], loaf: [] };
(function () {
  let last = 0;
  window.__fr.slow = []; window.__fr.jumps = [];
  function tick(t) { if (last) { window.__fr.d.push(t - last); if (t - last > 10) window.__fr.slow.push([Math.round(last), Math.round(t - last)]); } last = t; requestAnimationFrame(tick); }
  addEventListener("DOMContentLoaded", () => {
    const n = document.querySelector(".gaze-node.now");
    if (n) new MutationObserver(() => window.__fr.jumps.push(Math.round(performance.now()))).observe(n, { attributes: true, attributeFilter: ["style"] });
  });
  requestAnimationFrame(tick);
  try {
    new PerformanceObserver((l) => { for (const e of l.getEntries()) window.__fr.loaf.push(e.duration); })
      .observe({ type: "long-animation-frame", buffered: false });
  } catch (e) {}
})();
"""


def run(v):
    hsh, css = v
    profile = pathlib.Path(tempfile.mkdtemp(prefix="xylz-ab-"))
    proc = subprocess.Popen([chrome, "--headless=new", "--hide-scrollbars", "--no-first-run",
                             "--remote-allow-origins=*", "--remote-debugging-port=0",
                             "--use-angle=d3d11", "--enable-gpu", "--ignore-gpu-blocklist",
                             "--enable-gpu-rasterization", "--window-size=1440,900",
                             f"--user-data-dir={profile}", "about:blank"],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                            creationflags=subprocess.CREATE_NO_WINDOW)
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

        call("Page.enable")
        call("Runtime.enable")
        call("Emulation.setDeviceMetricsOverride", {"width": 1440, "height": 900, "deviceScaleFactor": 1, "mobile": False})
        call("Page.addScriptToEvaluateOnNewDocument", {"source": RECORDER})
        call("Page.navigate", {"url": "http://localhost:8765/" + hsh})
        time.sleep(2.5)
        if css:
            js(f"document.head.insertAdjacentHTML('beforeend', '<style>{css}</style>')")
        gpu = js("""(()=>{const c=document.createElement('canvas').getContext('webgl');if(!c)return 'no webgl';const e=c.getExtension('WEBGL_debug_renderer_info');return e?c.getParameter(e.UNMASKED_RENDERER_WEBGL):'?'})()""")
        js("window.__fr.d.length=0; window.__fr.loaf.length=0; window.__fr.slow.length=0; window.__fr.jumps.length=0")
        t0 = time.time()
        k = 0
        while time.time() - t0 < 6:
            a = k / 40
            x = 720 + 420 * math.cos(a)
            y = 470 + 300 * math.sin(a * 1.3)
            call("Input.dispatchMouseEvent", {"type": "mouseMoved", "x": x, "y": y, "pointerType": "mouse"})
            k += 1
            time.sleep(0.008)
        r = js("JSON.stringify(window.__fr)")
        jumps = js("document.querySelectorAll('.gaze-node.ghost').length")
        return gpu, json.loads(r), jumps
    finally:
        proc.terminate()


def summarise(d, loaf):
    d = sorted(d)
    if not d:
        return {}
    med = d[len(d) // 2]
    over = sum(1 for x in d if x > med * 1.5)
    return {"frames": len(d), "median_ms": round(med, 2), "p95_ms": round(d[int(len(d) * 0.95)], 1),
            "p99_ms": round(d[int(len(d) * 0.99)], 1), "max_ms": round(d[-1], 1),
            "late_frames": over, "loaf_count": len(loaf), "loaf_max_ms": round(max(loaf), 1) if loaf else 0}


results = {}
for rnd in range(ROUNDS):
    for name, css in VARIANTS.items():
        gpu, fr, ghosts = run(css)
        s = summarise(fr["d"], fr["loaf"])
        results.setdefault(name, []).append(s)
        sl = fr["slow"]
        near = sum(1 for t, d in sl if any(0 <= t - j <= 40 or 0 <= j - t <= d for j in fr["jumps"]))
        print(rnd, name, "max", s.get("max_ms"), "late", s.get("late_frames"), "jumps", len(fr["jumps"]), "slow>10ms", len(sl), "of which at a jump", near, "worst", sorted(sl, key=lambda x: -x[1])[:4], flush=True)
