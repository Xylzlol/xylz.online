"""Records every tab icon (link rel=icon href) and theme-color change through a real pour, then
writes the frames as a strip, with their times after the pour began."""
import shutil, base64, io, json, pathlib, subprocess, sys, tempfile, time, urllib.request
import websocket
from PIL import Image, ImageDraw

out = pathlib.Path(__file__).parent / "favicon-work"
out.mkdir(exist_ok=True)
chrome = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
profile = pathlib.Path(tempfile.mkdtemp(prefix="xylz-fav-"))
proc = subprocess.Popen([chrome, "--headless=new", "--hide-scrollbars", "--no-first-run", "--remote-allow-origins=*",
                         "--remote-debugging-port=0", "--force-device-scale-factor=2", f"--user-data-dir={profile}", "about:blank"],
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=subprocess.CREATE_NO_WINDOW)
REC = r"""
window.__ic = [];
addEventListener('DOMContentLoaded', () => {
  const rec = () => {
    const l = document.querySelector('link[rel~="icon"]');
    const m = document.querySelector('meta[name="theme-color"]');
    const last = window.__ic[window.__ic.length - 1];
    const v = { t: performance.now(), href: l ? l.href : '', theme: m ? m.content : '' };
    if (!last || last.href !== v.href || last.theme !== v.theme) window.__ic.push(v);
  };
  new MutationObserver(rec).observe(document.head, { subtree: true, childList: true, attributes: true, attributeFilter: ['href', 'content'] });
  rec();
});
"""
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

    call("Page.enable"); call("Runtime.enable"); call("Emulation.setFocusEmulationEnabled", {"enabled": True})
    call("Emulation.setDeviceMetricsOverride", {"width": 1440, "height": 900, "deviceScaleFactor": 2, "mobile": False})
    call("Page.addScriptToEvaluateOnNewDocument", {"source": REC})
    # optional: pretend to be a browser window with a frame (headless has none), from argv
    # layout = strip | vertical | full
    layout = (sys.argv[1] if len(sys.argv) > 1 and not sys.argv[1].isdigit() else "strip")
    frame = {"strip": (0, 87), "vertical": (300, 60), "full": (0, 0)}[layout]
    call("Page.addScriptToEvaluateOnNewDocument", {"source": f"Object.defineProperty(window, 'outerWidth', {{get: () => innerWidth + {frame[0]}}}); Object.defineProperty(window, 'outerHeight', {{get: () => innerHeight + {frame[1]}}}); Object.defineProperty(navigator, 'platform', {{get: () => 'Win32'}});"})
    names = ["immunefi", "public work", "github", "x"]
    rows = []
    for idx in [0, 1, 2, 3]:
        call("Page.navigate", {"url": "about:blank"}); time.sleep(0.2)
        call("Page.navigate", {"url": "http://localhost:8765/"})
        time.sleep(2.5)
        if idx == 0:  # Immunefi is selected at load: choose another first, then come back
            arr0 = [v for v in js("window.__ic") if v["href"].startswith("data:image/png;base64,")]
            rows.append(("arrival", [(round(v["t"]), Image.open(io.BytesIO(base64.b64decode(v["href"].split(",", 1)[1]))).convert("RGB")) for v in arr0]))
            print("arrival frames", len(arr0), [round(v["t"]) for v in arr0])
            js("document.querySelectorAll('.targets .target')[1].focus()"); time.sleep(2.4)
        js("window.__ic.length = 0")
        t0 = js(f"(() => {{ const t = performance.now(); document.querySelectorAll('.targets .target')[{idx}].focus(); return t; }})()")
        time.sleep(2.4)
        ic = js("window.__ic")
        frames = []
        for v in ic:
            if v["href"].startswith("data:image/png;base64,"):
                frames.append((round(v["t"] - t0), Image.open(io.BytesIO(base64.b64decode(v["href"].split(",", 1)[1]))).convert("RGB")))
        print(names[idx], "frames", len(frames), "first at", frames[0][0] if frames else None, "last at", frames[-1][0] if frames else None, flush=True)
        rows.append((names[idx], frames))
    Z = 3
    w = max(f[1].size[0] for _, fr in rows for f in fr) * Z
    cols = max(len(f) for _, f in rows)
    sheet = Image.new("RGB", (110 + (w + 8) * cols, (w + 28) * len(rows) + 8), (60, 62, 66))
    d = ImageDraw.Draw(sheet)
    for ri, (name, frames) in enumerate(rows):
        y = 8 + ri * (w + 28)
        d.text((8, y + w // 2), name, fill=(240, 240, 240))
        for k, (dt, im) in enumerate(frames):
            x = 110 + k * (w + 8)
            sheet.paste(im.resize((w, w), Image.NEAREST), (x, y))
            d.text((x, y + w + 4), f"{dt}", fill=(200, 200, 200))
    sheet.save(out / f"favicon-pour-{layout}.png")
finally:
    proc.terminate()
    try:
        proc.wait(timeout=15)
    except Exception:
        pass
    shutil.rmtree(profile, ignore_errors=True)  # never leave the profile in %TEMP%