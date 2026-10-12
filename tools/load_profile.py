"""Where the page's own startup time goes: a sampling CPU profile of the main thread from navigation
to 1.5 s, summed by function (self time and total time), for main.js and wall.js only."""
import shutil, json, pathlib, subprocess, tempfile, time, urllib.request, collections
import websocket

chrome = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
profile = pathlib.Path(tempfile.mkdtemp(prefix="xylz-prof-"))
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

    call("Page.enable"); call("Profiler.enable")
    call("Emulation.setDeviceMetricsOverride", {"width": 1440, "height": 900, "deviceScaleFactor": 1, "mobile": False})
    call("Profiler.setSamplingInterval", {"interval": 100})
    call("Profiler.start")
    call("Page.navigate", {"url": "http://localhost:8765/"})
    time.sleep(1.5)
    prof = call("Profiler.stop")["profile"]
finally:
    proc.terminate()
    try:
        proc.wait(timeout=15)
    except Exception:
        pass
    shutil.rmtree(profile, ignore_errors=True)  # never leave the profile in %TEMP%
nodes = {nd["id"]: nd for nd in prof["nodes"]}
dt = collections.Counter()
for sid, d in zip(prof["samples"], prof["timeDeltas"]):
    dt[sid] += d
self_t = collections.Counter(); total = collections.Counter()
parent = {}
for nd in prof["nodes"]:
    for c in nd.get("children", []):
        parent[c] = nd["id"]
def label(nd):
    cf = nd["callFrame"]
    return f"{cf['functionName'] or '(anon)'} {cf['url'].split('/')[-1].split('?')[0]}:{cf['lineNumber'] + 1}"
for nid, us in dt.items():
    nd = nodes[nid]
    self_t[label(nd)] += us
    seen = set(); cur = nid
    while cur is not None:
        lb = label(nodes[cur])
        if lb not in seen:
            total[lb] += us; seen.add(lb)
        cur = parent.get(cur)
own = lambda k: any(f in k for f in ("main.js", "wall.js", "tab-icon.js"))
print("self time (ms), page code:")
for k, v in [kv for kv in self_t.most_common() if own(kv[0])][:15]:
    print(f"  {v / 1000:6.1f}  {k}")
print("total time (ms), page code:")
for k, v in [kv for kv in total.most_common() if own(kv[0])][:18]:
    print(f"  {v / 1000:6.1f}  {k}")
print("native/browser self time (ms):")
for k, v in [kv for kv in self_t.most_common() if not own(kv[0])][:8]:
    print(f"  {v / 1000:6.1f}  {k}")
