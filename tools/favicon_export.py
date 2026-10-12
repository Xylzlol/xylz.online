"""Renders site/tab-icon.js in headless Chrome with the site's own Archivo, for a preview sheet
(favicon-work/sheet.png) and, with --write, the static icon files in site/.
Needs the local server on http://localhost:8765/."""
import shutil, base64, io, json, pathlib, subprocess, sys, tempfile, time, urllib.request
import websocket
from PIL import Image

tools = pathlib.Path(__file__).parent
site = tools.parent / "site"
work = tools / "favicon-work"
work.mkdir(exist_ok=True)
chrome = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
profile = pathlib.Path(tempfile.mkdtemp(prefix="xylz-icon-"))
proc = subprocess.Popen([chrome, "--headless=new", "--no-first-run", "--remote-allow-origins=*", "--remote-debugging-port=0",
                         f"--user-data-dir={profile}", "about:blank"],
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=subprocess.CREATE_NO_WINDOW)
FIELDS = {"white": ("#F7F9FA", "#050506"), "sky": ("#B8DCEB", "#050506"), "black": ("#050506", "#F7F9FA"), "magenta": ("#FF2BD6", "#050506")}
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
            raise RuntimeError(r["exceptionDetails"])
        return r["result"].get("value")

    call("Page.enable"); call("Runtime.enable")
    call("Page.navigate", {"url": "http://localhost:8765/"})
    time.sleep(2.0)
    js("document.fonts.load('900 100px \"Archivo\"')")

    def render(size, field="white", **opt):
        f, i = FIELDS[field]
        url = js(f"""(() => {{ const c = document.createElement('canvas'); c.width = c.height = {size};
            const pal = {{ field: '{f}', ink: '{i}' }};
            xylzIcon.draw(c.getContext('2d'), {size}, () => pal, {json.dumps(opt)});
            return c.toDataURL('image/png'); }})()""")
        return Image.open(io.BytesIO(base64.b64decode(url.split(",", 1)[1]))).convert("RGBA")

    # preview sheet: real sizes on light and dark tab strips, the four fields, the arrival, big
    sheet = Image.new("RGB", (1200, 330), (222, 225, 230))
    from PIL import ImageDraw
    d = ImageDraw.Draw(sheet)
    d.rectangle([0, 165, 1200, 330], fill=(32, 33, 36))
    x = 14
    for s in (16, 20, 24, 32, 48):
        im = render(s); sheet.paste(im, (x, 50), im); sheet.paste(im, (x, 215), im); x += s + 16
    for fld in ("sky", "black", "magenta"):
        im = render(32, fld); sheet.paste(im, (x, 50), im); sheet.paste(im, (x, 215), im); x += 46
    # the scroll-in on arrival: the four frames, then rest
    for sh in (12, 8, 4):
        im = render(32, shift=sh); sheet.paste(im, (x, 50), im)
        im = render(16, shift=sh); sheet.paste(im, (x + 8, 222), im); x += 44
    z = render(16).resize((128, 128), Image.NEAREST); sheet.paste(z, (x, 10), z); x += 140
    z = render(32).resize((128, 128), Image.NEAREST); sheet.paste(z, (x, 10), z); x += 140
    big = render(150); sheet.paste(big, (x, 10), big)
    sheet.save(work / "sheet.png")
    print("sheet written")

    if "--write" in sys.argv:
        i16, i32, i48 = render(16), render(32), render(48)
        i48.save(site / "favicon.ico", sizes=[(16, 16), (32, 32), (48, 48)], append_images=[i16, i32])
        # iOS rounds its own corners: the apple icon is drawn on a square, opaque
        a = render(180)
        bg = Image.new("RGB", a.size, (0xF7, 0xF9, 0xFA)); bg.paste(a, (0, 0), a); bg.save(site / "apple-touch-icon.png")
        render(192).save(site / "icon-192.png")
        render(512).save(site / "icon-512.png")
        # the SVG: the same LEDs as crisp rectangles (runs per row), on the rounded tile
        lit = js("Array.from(xylzIcon.lit)")
        runs = []
        for r in range(16):
            c = 0
            while c < 16:
                if lit[r * 16 + c]:
                    c0 = c
                    while c < 16 and lit[r * 16 + c]:
                        c += 1
                    runs.append(f'<rect x="{c0}" y="{r}" width="{c - c0}" height="1"/>')
                else:
                    c += 1
        svg = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16" shape-rendering="crispEdges">'
               '<rect width="16" height="16" rx="3.2" fill="#F7F9FA" shape-rendering="geometricPrecision"/>'
               f'<g fill="#050506">{"".join(runs)}</g></svg>' + "\n")
        (site / "favicon.svg").write_text(svg, encoding="utf-8")
        print("static icons written, svg", len(svg), "bytes")
finally:
    proc.terminate()
    try:
        proc.wait(timeout=15)
    except Exception:
        pass
    shutil.rmtree(profile, ignore_errors=True)  # never leave the profile in %TEMP%