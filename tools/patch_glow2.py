"""Glow, second form (applied on top of patch_glow.py, to site/wall.js and to the reference):
additive light without a blend mode, and no glow layer at all while nothing glows.

The glow layer now lies under the gap layer and holds, per LED, its light: colour x glow for an LED
showing a field that glows, black for any other. The gap layer above it is opaque around LEDs whose
field does not glow and transparent around those whose field does. Over the black field's black
gaps this is exactly the old glow (0.75 x the blurred LEDs, by linearity of the blur); at a pour's
front, the glow cannot reach the gaps of the light field beside it, which cover it, so nothing smears
grey there. A plus-lighter blend gave the same picture but cost the software compositor about a
fifth of a core. And the worker reports whether any LED glows, so the page hides the layer (and
Chrome skips blurring it) whenever none does.
Usage: patch_glow2.py wall.js [more.js ...]"""
import pathlib, sys

for path in sys.argv[1:]:
    p = pathlib.Path(path)
    s = p.read_text(encoding="utf-8")

    def rep(a, b):
        global s
        assert s.count(a) == 1, (path, a[:80], s.count(a))
        s = s.replace(a, b)

    rep('''          // the glow layer carries each LED's glow in its alpha, so it needs alpha
          S.bctx = S.bloom ? S.bloom.getContext("2d", { alpha: true }) : null;''',
        '''          S.bctx = S.bloom ? S.bloom.getContext("2d", { alpha: false }) : null;''')
    rep('''          // its glow: that of the field it shows (the old one until the pour reaches it)
          const bl = S.bimg.data;
          bl[o] = d[o]; bl[o + 1] = d[o + 1]; bl[o + 2] = d[o + 2];
          bl[o + 3] = Math.round(255 * (old ? old.glow || 0 : S.glow));
''', '''          // its glow: that of the field it shows (the old one until the pour reaches it), as light
          // under the gap layer, which lets it through only around LEDs whose field glows
          const glw = old ? old.glow || 0 : S.glow;
          const bl = S.bimg.data;
          bl[o] = d[o] * glw; bl[o + 1] = d[o + 1] * glw; bl[o + 2] = d[o + 2] * glw; bl[o + 3] = 255;
          const gOn = glw > 0 ? 1 : 0;
          if (S.glowCell[i] !== gOn) { S.glowCount += gOn - S.glowCell[i]; S.glowCell[i] = gOn; }
''')
    rep('''            gd[o] = gp[0]; gd[o + 1] = gp[1]; gd[o + 2] = gp[2]; gd[o + 3] = 255;''',
        '''            gd[o] = gp[0]; gd[o + 1] = gp[1]; gd[o + 2] = gp[2]; gd[o + 3] = glw > 0 ? 0 : 255;''')
    rep('''      S.bimg = S.ctx.createImageData(S.cols, S.rows);''',
        '''      S.bimg = S.ctx.createImageData(S.cols, S.rows);
      S.glowCell = new Uint8Array(S.cols * S.rows);
      S.glowCount = 0;''')
    rep('''      notify({ type: "committed", rowStart: S.rowStart });''',
        '''      // the page shows the glow layer only while some LED glows
      const glowOn = S.glowCount > 0;
      if (glowOn !== S.glowOn) { S.glowOn = glowOn; notify({ type: "glow", on: glowOn }); }
      notify({ type: "committed", rowStart: S.rowStart });''')
    p.write_text(s, encoding="utf-8", newline="\n")
    print("patched", path)
