"""Render every recorded AdSERP page and measure its layout the way the site measures its own:
every line box of text (Range.getClientRects per text node) and every link, in page CSS px, at the
recorded window size. Writes data/adserp/layouts/<page>.json.
The pages are saved Google result pages from the dataset, whose results only show with their own
scripts running. They are loaded from disk in a throwaway headless profile with every network
request blocked, so their scripts run but cannot reach anything.
Usage: python -I adserp_render.py [limit [shard shards]]"""
import shutil, base64, glob, json, os, pathlib, subprocess, sys, tempfile, time, urllib.request
import websocket

ML = os.path.dirname(os.path.abspath(__file__))
D = os.path.join(ML, "data", "adserp")
OUT = os.path.join(D, "layouts"); os.makedirs(OUT, exist_ok=True)
chrome = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
W, H = 1403, 1137  # the recorded content width: the 1422 px window minus its 19 px scrollbar
MEASURE = r"""(() => {
  const lines = [], links = [];
  const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  const range = document.createRange();
  for (let n = walker.nextNode(); n; n = walker.nextNode()) {
    if (!n.data.trim()) continue;
    const el = n.parentElement;
    if (!el) continue;
    const st = getComputedStyle(el);
    if (st.visibility === 'hidden' || st.display === 'none' || +st.opacity === 0) continue;
    range.selectNodeContents(n);
    const fs = parseFloat(st.fontSize) || 14;
    for (const r of range.getClientRects()) {
      if (r.width < 2 || r.height < 2) continue;
      lines.push([Math.round(r.left + scrollX), Math.round(r.top + scrollY), Math.round(r.width), Math.round(r.height), Math.round(fs), +st.fontWeight >= 600 ? 1 : 0]);
    }
  }
  for (const a of document.querySelectorAll('a[href], button, input')) {
    const r = a.getBoundingClientRect();
    if (r.width < 2 || r.height < 2) continue;
    links.push([Math.round(r.left + scrollX), Math.round(r.top + scrollY), Math.round(r.width), Math.round(r.height)]);
  }
  return JSON.stringify({ doc: [document.documentElement.scrollWidth, document.documentElement.scrollHeight], lines, links });
})()"""

pages = sorted(glob.glob(os.path.join(D, "serps", "**", "*.htm*"), recursive=True))
limit = int(sys.argv[1]) if len(sys.argv) > 1 else len(pages)
shard, shards = (int(sys.argv[2]), int(sys.argv[3])) if len(sys.argv) > 3 else (0, 1)
pages = pages[shard::shards]
profile = pathlib.Path(tempfile.mkdtemp(prefix="adserp-render-"))
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
    ws = websocket.create_connection(tgt["webSocketDebuggerUrl"], timeout=60)
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

    call("Page.enable"); call("Runtime.enable"); call("Network.enable")
    # no network: every request outside the local file is blocked
    call("Network.setBlockedURLs", {"urls": ["http://*", "https://*", "ws://*", "wss://*"]})
    call("Emulation.setDeviceMetricsOverride", {"width": W, "height": H, "deviceScaleFactor": 1, "mobile": False})
    done = 0
    for page in pages[:limit]:
        name = os.path.splitext(os.path.basename(page))[0]
        dst = os.path.join(OUT, name + ".json")
        if os.path.exists(dst):
            continue
        call("Page.navigate", {"url": pathlib.Path(page).as_uri()})
        time.sleep(1.2)
        r = call("Runtime.evaluate", {"expression": MEASURE, "returnByValue": True})
        v = r.get("result", {}).get("value")
        if not v:
            continue
        open(dst, "w", encoding="utf-8").write(v)
        done += 1
        if done % 100 == 0:
            print("rendered", done, flush=True)
    print("rendered", done, "of", min(limit, len(pages)))
finally:
    proc.terminate()
    try:
        proc.wait(timeout=15)
    except Exception:
        pass
    shutil.rmtree(profile, ignore_errors=True)  # never leave the profile in %TEMP%