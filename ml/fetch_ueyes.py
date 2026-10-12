# Pull only the members training needs out of the 13 GB remote zip, without tripping the
# server's per-request rate limit: wanted members are grouped into contiguous byte spans (each
# folder is stored together), each span is streamed in ONE range request, and members are sliced
# out locally.
import os, struct, zlib, time
from concurrent.futures import ThreadPoolExecutor
import requests
from remotezip import RemoteZip

URL = "https://zenodo.org/records/8010312/files/UEyes_dataset.zip?download=1"
OUT = "data"
SPAN = "spans"
want = lambda n: (not n.startswith("__MACOSX") and not n.endswith("/") and (
    n.startswith("UEyes_dataset/images/") or n.startswith("UEyes_dataset/saliency_maps/heatmaps_3s/")
    or n.startswith("UEyes_dataset/saliency_maps/fixmaps_3s/") or (n.endswith(".csv") and n.count("/") == 1)))

t0 = time.time()
for attempt in range(6):
    try:
        with RemoteZip(URL) as z:
            infos = sorted([i for i in z.infolist() if want(i.filename)], key=lambda i: i.header_offset)
        break
    except Exception as e:
        print("directory retry", attempt, e, flush=True)
        time.sleep(20 * (attempt + 1))
todo = [i for i in infos if not (os.path.exists(os.path.join(OUT, i.filename)) and os.path.getsize(os.path.join(OUT, i.filename)) == i.file_size)]
print(len(infos), "files,", len(todo), "to fetch,", round(sum(i.compress_size for i in todo) / 1e6), "MB", flush=True)

# group into spans: merge neighbours when the bytes in between are small
spans, cur = [], []
for i in todo:
    end = i.header_offset + 30 + len(i.filename.encode()) + 2048 + i.compress_size
    if cur and i.header_offset - cur[-1][1] > 4_000_000:
        spans.append(cur); cur = []
    cur.append((i, end))
if cur:
    spans.append(cur)
print(len(spans), "spans", flush=True)
os.makedirs(SPAN, exist_ok=True)


def fetch_span(k_span):
    k, span = k_span
    start, stop = span[0][0].header_offset, max(e for _, e in span)
    path = os.path.join(SPAN, f"{k}.bin")
    for attempt in range(8):
        try:
            have = os.path.getsize(path) if os.path.exists(path) else 0
            if have >= stop - start + 1:
                break
            with requests.get(URL, headers={"Range": f"bytes={start + have}-{stop}"}, stream=True, timeout=120) as r:
                if r.status_code == 429:
                    raise RuntimeError("429")
                r.raise_for_status()
                with open(path, "ab") as f:
                    for chunk in r.iter_content(1 << 20):
                        f.write(chunk)
        except Exception as e:
            print("span", k, "retry", attempt, e, flush=True)
            time.sleep(15 * (attempt + 1))
    buf = open(path, "rb").read()
    n_ok = 0
    for info, _ in span:
        o = info.header_offset - start
        n, m = struct.unpack("<HH", buf[o + 26:o + 30])
        data = buf[o + 30 + n + m: o + 30 + n + m + info.compress_size]
        if info.compress_type == 8:
            data = zlib.decompress(data, -15)
        dst = os.path.join(OUT, info.filename)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        with open(dst, "wb") as f:
            f.write(data)
        n_ok += 1
    os.remove(path)
    print("span", k, "done:", n_ok, "files,", round((stop - start) / 1e6), "MB,", round(time.time() - t0), "s", flush=True)


with ThreadPoolExecutor(3) as ex:
    list(ex.map(fetch_span, enumerate(spans)))
print("FETCH_OK", round(time.time() - t0), "s", flush=True)
