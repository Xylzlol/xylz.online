"""Gloss per LED (applied to site/wall.js and to the reference, so they are compared like for like).

The LEDs' specular gloss used to be one CSS layer whose strength was set per field (0.7 on the black
field, 1 elsewhere), so it switched for the whole page when a pour committed. Now it is two canvases
the wall draws (one pixel per LED, like the others): a rim layer (black) and a highlight layer
(white), each masked in CSS by the original gradient, with each LED's pixel alpha set to the gloss of
the field that LED shows. So the gloss turns with the pour front. They are re-uploaded only where an
LED's gloss changes (during a pour), so at rest they cost the compositor nothing new.
Usage: patch_gloss.py wall.js [more.js ...]"""
import pathlib, sys

for path in sys.argv[1:]:
    p = pathlib.Path(path)
    s = p.read_text(encoding="utf-8")

    def rep(a, b):
        global s
        assert s.count(a) == 1, (path, a[:80], s.count(a))
        s = s.replace(a, b)

    # init: the two gloss canvases
    rep('''          S.bctx = S.bloom ? S.bloom.getContext("2d", { alpha: false }) : null;''',
        '''          S.bctx = S.bloom ? S.bloom.getContext("2d", { alpha: false }) : null;
          S.glossHi = m.glossHi || null;
          S.glossRim = m.glossRim || null;
          S.ghctx = S.glossHi ? S.glossHi.getContext("2d") : null;
          S.grctx = S.glossRim ? S.glossRim.getContext("2d") : null;''')
    # resize: sized like the others, with their images
    rep('''      for (const c of [S.canvas, S.bloom, S.gapsCanvas]) {''',
        '''      for (const c of [S.canvas, S.bloom, S.gapsCanvas, S.glossHi, S.glossRim]) {''')
    rep('''      S.bimg = S.ctx.createImageData(S.cols, S.rows);''',
        '''      S.bimg = S.ctx.createImageData(S.cols, S.rows);
      S.ghimg = S.ctx.createImageData(S.cols, S.rows);
      S.grimg = S.ctx.createImageData(S.cols, S.rows);
      S.gloss0 = S.rows; S.gloss1 = -1; // rows whose gloss changed since the last upload''')
    # palettes remember their gloss; the field message carries it
    rep('''          S.old = { field: S.field, ink: S.ink, base: S.base, amp: S.amp, gap: S.gap, glow: S.glow };''',
        '''          S.old = { field: S.field, ink: S.ink, base: S.base, amp: S.amp, gap: S.gap, glow: S.glow, gloss: S.gloss };''')
    rep('''          S.glow = m.glow;''', '''          S.glow = m.glow;
          S.gloss = m.gloss == null ? 1 : m.gloss;''')
    # per computed LED: its gloss, written only when it changes
    rep('''          const gOn = glw > 0 ? 1 : 0;''', '''          const gOn = glw > 0 ? 1 : 0;
          const gls = Math.round(255 * (old ? (old.gloss == null ? 1 : old.gloss) : (S.gloss == null ? 1 : S.gloss)));
          const gh = S.ghimg.data;
          if (gh[o + 3] !== gls || gh[o] !== 255) {
            gh[o] = 255; gh[o + 1] = 255; gh[o + 2] = 255; gh[o + 3] = gls;
            const gr = S.grimg.data;
            gr[o] = 0; gr[o + 1] = 0; gr[o + 2] = 0; gr[o + 3] = gls;
            const rr = (i / S.cols) | 0;
            if (rr < S.gloss0) S.gloss0 = rr;
            if (rr > S.gloss1) S.gloss1 = rr;
          }''')
    rep('''      // the page shows the glow layer only while some LED glows''',
        '''      // the gloss layers: only the rows where some LED's gloss changed
      if (S.ghctx && S.gloss1 >= S.gloss0) {
        S.ghctx.putImageData(S.ghimg, 0, 0, 0, S.gloss0, cols, S.gloss1 - S.gloss0 + 1);
        S.grctx.putImageData(S.grimg, 0, 0, 0, S.gloss0, cols, S.gloss1 - S.gloss0 + 1);
        S.gloss0 = S.rows; S.gloss1 = -1;
      }
      // the page shows the glow layer only while some LED glows''')
    p.write_text(s, encoding="utf-8", newline="\n")
    print("patched", path)
