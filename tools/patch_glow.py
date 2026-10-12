"""The glow per LED (applied to site/wall.js and to the full-computation reference used by
render_equiv.mjs, so the two keep being compared like for like).

The glow layer used to be a copy of the wall whose strength was one CSS variable for the whole page
(--glow: 0.75 on the black field, 0 elsewhere), so the moment a pour committed, every LED gained or
lost its glow at once, also where the pour had not arrived. Now each LED writes its glow into the
glow layer's alpha: the glow of the field that LED is showing, old or new, so it turns with the
pour front. Usage: patch_glow.py wall.js [more.js ...]"""
import pathlib, sys

for path in sys.argv[1:]:
    p = pathlib.Path(path)
    s = p.read_text(encoding="utf-8")

    def rep(a, b):
        global s
        assert s.count(a) == 1, (path, a[:80], s.count(a))
        s = s.replace(a, b)

    # every palette remembers its glow
    rep('''          S.old = { field: S.field, ink: S.ink, base: S.base, amp: S.amp, gap: S.gap };''',
        '''          S.old = { field: S.field, ink: S.ink, base: S.base, amp: S.amp, gap: S.gap, glow: S.glow };''')
    # the glow layer has alpha now, and its own image
    rep('''          S.bctx = S.bloom ? S.bloom.getContext("2d", { alpha: false }) : null;''',
        '''          // the glow layer carries each LED's glow in its alpha, so it needs alpha
          S.bctx = S.bloom ? S.bloom.getContext("2d", { alpha: true }) : null;''')
    rep('''      S.gimg = S.ctx.createImageData(S.cols, S.rows);''',
        '''      S.gimg = S.ctx.createImageData(S.cols, S.rows);
      S.bimg = S.ctx.createImageData(S.cols, S.rows);''')
    # each computed LED: the same colour, with its own field's glow as alpha
    rep('''          d[o + 3] = 255;
''', '''          d[o + 3] = 255;
          // its glow: that of the field it shows (the old one until the pour reaches it)
          const bl = S.bimg.data;
          bl[o] = d[o]; bl[o + 1] = d[o + 1]; bl[o + 2] = d[o + 2];
          bl[o + 3] = Math.round(255 * (old ? old.glow || 0 : S.glow));
''')
    if "band1 >= band0" in s:
        rep('''      if (S.bctx && S.glow > 0 && band1 >= band0) S.bctx.putImageData(S.img, 0, 0, 0, band0, cols, band1 - band0 + 1);''',
            '''      // the glow layer: every row drawn, whatever the field, since LEDs still showing an old
      // field keep that field's glow
      if (S.bctx && band1 >= band0) S.bctx.putImageData(S.bimg, 0, 0, 0, band0, cols, band1 - band0 + 1);''')
    else:
        rep('''      if (S.bctx && S.glow > 0 && dh > 0) S.bctx.putImageData(S.img, 0, 0, 0, dirty0, cols, dh);''',
            '''      if (S.bctx && dh > 0) S.bctx.putImageData(S.bimg, 0, 0, 0, dirty0, cols, dh);''')
    p.write_text(s, encoding="utf-8", newline="\n")
    print("patched", path)
