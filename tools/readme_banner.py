"""The GitHub profile banner: the site's LED wordmark as an animated SVG.

The lit cells are the site's own: the name mask the page sends the LED wall (recorded by
wall_record.py), so the letters are cell for cell the ones on xylz.online. The four fields and
their ink/gap colours come from style.css. Every few seconds a pour floods the panel with the next
field from a different point, with an uneven front like the site's; it is a clip shape scaled from
the pour's origin, so it costs the viewer next to nothing. With reduced motion it holds still.
Usage: readme_banner.py rec.json outdir"""
import json, math, random, sys, pathlib

rec, outdir = sys.argv[1], pathlib.Path(sys.argv[2])
outdir.mkdir(parents=True, exist_ok=True)
name = None
for r in json.load(open(rec)):
    if r["m"]["type"] == "masks":
        name = next(m for m in r["m"]["masks"] if "cells" in m)
        break
cells = name["cells"]["d"] if isinstance(name["cells"], dict) else name["cells"]
NC, NR = name["cols"], name["rows"]
P = 10                      # px per cell in the SVG
MX, MY = 8, 6               # margin, in cells
COLS, ROWS = NC + 2 * MX, NR + 2 * MY
W, H = COLS * P, ROWS * P
DOT = P * 0.4
FIELDS = {  # field, ink, gap (style.css)
    "white": ("#F7F9FA", "#050506", "#FFFFFF"),
    "sky": ("#B8DCEB", "#050506", "#C5EBFB"),
    "black": ("#050506", "#F7F9FA", "#000000"),
    "magenta": ("#FF2BD6", "#050506", "#FF2EE5"),
}


def dots(pred):
    # all dots in one path: a zero-length segment per dot, drawn with a round cap
    out = []
    for r in range(ROWS):
        for c in range(COLS):
            if pred(c, r):
                out.append(f"M{c * P + P // 2} {r * P + P // 2}h0")
    return "".join(out)


lit = lambda c, r: MX <= c < MX + NC and MY <= r < MY + NR and cells[(r - MY) * NC + (c - MX)]
LIT = dots(lit)
# unlit cells as a tiled pattern: a 7x5 tile with two shades scattered by a fixed hash, like LEDs
# from different batches (repeats every 7 cells, too irregular inside to read as a grid of tiles)
h = lambda c, r: ((c * 73856093) ^ (r * 19349663)) % 997 / 997
TW, TH = 7, 5


def blob(seed, n=72):
    """An uneven, closed front of radius ~1 around the origin, like the site's noisy pour."""
    rnd = random.Random(seed)
    ph = [rnd.random() * 6.283 for _ in range(4)]
    pts = []
    for k in range(n):
        a = k / n * 2 * math.pi
        rr = 1 + 0.05 * math.sin(3 * a + ph[0]) + 0.035 * math.sin(7 * a + ph[1]) + 0.02 * math.sin(13 * a + ph[2]) + 0.012 * math.sin(23 * a + ph[3])
        pts.append(f"{math.cos(a) * rr:.4f} {math.sin(a) * rr:.4f}")
    return "M" + "L".join(pts) + "Z"


def layer(fname, clip):
    f, ink, gap = FIELDS[fname]
    lo = "".join(f"M{c * P + P // 2} {r * P + P // 2}h0" for r in range(TH) for c in range(TW) if h(c, r) < 0.5)
    hi = "".join(f"M{c * P + P // 2} {r * P + P // 2}h0" for r in range(TH) for c in range(TW) if h(c, r) >= 0.5)
    pat = (f'<pattern id="u{fname}" width="{TW * P}" height="{TH * P}" patternUnits="userSpaceOnUse">'
           f'<path d="{lo}" stroke="{f}"/><path d="{hi}" stroke="{f}" opacity="0.9"/></pattern>')
    g = (f'<g{f" mask={chr(34)}url(#{clip}){chr(34)}" if clip else ""}>'
         f'<rect width="{W}" height="{H}" fill="{gap}"/><rect width="{W}" height="{H}" fill="url(#u{fname})"/>'
         f'<use href="#lit" stroke="{ink}"/></g>')
    return pat, g


def banner(order, path):
    POUR = 1.1                   # each pour takes this long to cross
    starts = [2.4 + 4.0 * k for k in range(len(order) - 1)]
    T = starts[-1] + 4.0         # seconds per cycle
    origins = [(0.10, 1.02), (1.02, 0.55), (0.30, -0.02), (0.78, 1.02)]
    p0, g0 = layer(order[0], None)
    # the pour's front, snapped to the cells: the mask is sampled at each cell's centre (a 2 px point
    # per cell) and grown back to the whole cell, so every LED switches whole, as on the wall
    snap = (f'<filter id="snap" filterUnits="userSpaceOnUse" primitiveUnits="userSpaceOnUse" x="0" y="0" width="{W}" height="{H}" color-interpolation-filters="sRGB">'
            f'<feFlood x="{P // 2 - 1}" y="{P // 2 - 1}" width="2" height="2" flood-color="#fff"/>'
            f'<feComposite width="{P}" height="{P}"/><feTile result="grid"/>'
            f'<feComposite in="SourceGraphic" in2="grid" operator="in"/>'
            # no half cells: a sample on the front's anti-aliased edge is either in or out
            f'<feComponentTransfer><feFuncR type="discrete" tableValues="0 1"/><feFuncG type="discrete" tableValues="0 1"/>'
            f'<feFuncB type="discrete" tableValues="0 1"/><feFuncA type="discrete" tableValues="0 1"/></feComponentTransfer>'
            f'<feMorphology operator="dilate" radius="{P / 2 + 0.5:g}"/></filter>')
    defs, css, layers = [p0, snap, f'<path id="lit" d="{LIT}"/>'], [], [g0]
    for k, (fname, st, (ox, oy)) in enumerate(zip(order[1:], starts, origins)):
        x0, y0 = ox * W, oy * H
        R = max(math.hypot(x0 - cx, y0 - cy) for cx in (0, W) for cy in (0, H)) * 1.12
        cid = f"p{k}"
        defs.append(f'<mask id="{cid}" maskUnits="userSpaceOnUse" x="0" y="0" width="{W}" height="{H}"><g filter="url(#snap)">'
                    f'<path class="g{k} f" d="{blob(k * 7 + 3)}" transform="translate({x0:.1f} {y0:.1f})"/></g></mask>')
        a, b = st / T * 100, (st + POUR) / T * 100
        # the front: grows from nothing to past the far corner, eased like the site's ranking
        css.append(f"@keyframes k{k}{{0%,{a:.2f}%{{transform:translate({x0:.1f}px,{y0:.1f}px) scale(0)}}"
                   f"{(a + b) / 2:.2f}%{{transform:translate({x0:.1f}px,{y0:.1f}px) scale({R * 0.62:.1f})}}"
                   f"{b:.2f}%,99.99%{{transform:translate({x0:.1f}px,{y0:.1f}px) scale({R:.1f})}}100%{{transform:translate({x0:.1f}px,{y0:.1f}px) scale(0)}}}}"
                   f".g{k}{{animation:k{k} {T}s linear infinite;transform:translate({x0:.1f}px,{y0:.1f}px) scale(0)}}")
        pk, gk = layer(fname, cid)
        if f'id="u{fname}"' not in "".join(defs):
            defs.append(pk)
        layers.append(gk)
    css.append("@media (prefers-reduced-motion:reduce){[class^=g]{animation:none!important}}")
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" role="img" aria-label="xylz">'
           f'<title>xylz</title><style>path{{stroke-width:{2 * DOT:g}px;stroke-linecap:round;fill:none}}.f{{fill:#fff;stroke:none}}{"".join(css)}</style><defs>{"".join(defs)}</defs>{"".join(layers)}</svg>')
    path.write_text(svg, encoding="utf-8")
    return len(svg)


# the cycle ends on the field it started from, so the loop is seamless
# the site's fields without magenta (the X link's colour), which the user kept off the profile
print("light", banner(["white", "sky", "black", "white"], outdir / "banner-light.svg"), "bytes")
print("dark", banner(["black", "white", "sky", "black"], outdir / "banner-dark.svg"), "bytes")
print(f"{W}x{H}, lit cells {sum(1 for v in cells if v)}")
