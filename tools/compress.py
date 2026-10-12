"""Writes the pre-compressed copies the server can send as-is (brotli_static / gzip_static):
a .br and a .gz beside every text asset and the large binaries. Run after any change to site/."""
import gzip, pathlib
import brotli

site = pathlib.Path(__file__).parent.parent / "site"
EXT = {".html", ".js", ".mjs", ".css", ".svg", ".webmanifest", ".wasm", ".onnx", ".txt"}
total = [0, 0, 0]
for f in sorted(site.rglob("*")):
    if f.suffix not in EXT or not f.is_file():
        continue
    raw = f.read_bytes()
    br = brotli.compress(raw, quality=11)
    gz = gzip.compress(raw, 9)
    f.with_name(f.name + ".br").write_bytes(br)
    f.with_name(f.name + ".gz").write_bytes(gz)
    total[0] += len(raw); total[1] += len(br); total[2] += len(gz)
    print(f"{f.relative_to(site).as_posix():42s} {len(raw)/1e3:9.1f} kB  br {len(br)/1e3:8.1f}  gz {len(gz)/1e3:8.1f}")
print(f"{'total':42s} {total[0]/1e6:8.2f} MB  br {total[1]/1e6:7.2f}  gz {total[2]/1e6:7.2f}")
