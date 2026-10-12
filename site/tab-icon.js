/* The tab icon: the wall writes the name in the tab. A 16 x 16 LED panel, one LED per pixel of a
   16px tab icon, spelling "xylz" in a hand-set LED face: 4-LED letters (the l one LED) with single
   gaps make exactly 16 columns; x-height 5, the l's ascender and the y's descender above and below.
   Up to 48px each LED is a crisp square (round dots that small only blur); from 64px they are round
   and the unlit ones show faintly, as on the wall. One drawing for the live icon (main.js) and the
   static files (tools/favicon_export.py renders this file in Chrome).

   xylzIcon.draw(ctx, size, palOf, { shift })
     palOf(i)  the palette { field, ink } of LED i (0..255, row-major); a pour passes per-LED palettes
     shift     columns the text is moved right (the scroll-in on arrival), 0 at rest
   xylzIcon.lit  Uint8Array(256), 1 where an LED is lit at rest (the pour routes around these) */
(function () {
  const GLYPHS = {
    x: ["....", "....", "#..#", "#..#", ".##.", "#..#", "#..#", "...."],
    y: ["....", "....", "#..#", "#..#", "#..#", ".###", "...#", "###."],
    l: ["#", "#", "#", "#", "#", "#", "#", "."],
    z: ["....", "....", "####", "...#", ".##.", "#...", "####", "...."],
  };
  const TOP = 4; // the band's first row: rows 4..11 of 16

  function bitmap(shift) {
    const g = new Uint8Array(256);
    let x = shift;
    for (const ch of "xylz") {
      const rows = GLYPHS[ch];
      for (let r = 0; r < rows.length; r++) {
        for (let c = 0; c < rows[r].length; c++) {
          const cc = x + c;
          if (rows[r][c] === "#" && cc >= 0 && cc < 16) g[(TOP + r) * 16 + cc] = 1;
        }
      }
      x += rows[0].length + 1;
    }
    return g;
  }
  const lit = bitmap(0);

  function rgb(css) {
    if (css[0] === "#") {
      let h = css.slice(1);
      if (h.length === 3) h = h.replace(/./g, "$&$&");
      const n = parseInt(h, 16);
      return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
    }
    return css.match(/\d+/g).slice(0, 3).map(Number);
  }
  const mix = (a, b, t) => `rgb(${a.map((v, k) => Math.round(v + (b[k] - v) * t)).join(",")})`;

  function draw(ctx, size, palOf, opt = {}) {
    const s = size, p = s / 16;
    const on = opt.shift ? bitmap(opt.shift) : lit;
    const round = s >= 64;
    ctx.clearRect(0, 0, s, s);
    // the tile: rounded, its ground per LED (so a pour shows on the ground as well as the letters)
    ctx.save();
    const r = s * 0.2;
    ctx.beginPath();
    ctx.moveTo(r, 0);
    ctx.arcTo(s, 0, s, s, r);
    ctx.arcTo(s, s, 0, s, r);
    ctx.arcTo(0, s, 0, 0, r);
    ctx.arcTo(0, 0, s, 0, r);
    ctx.closePath();
    ctx.clip();
    for (let i = 0; i < 256; i++) {
      const pal = palOf(i), row = i >> 4, col = i & 15;
      const x0 = Math.round(col * p), y0 = Math.round(row * p);
      const x1 = Math.round((col + 1) * p), y1 = Math.round((row + 1) * p);
      ctx.fillStyle = pal.field;
      ctx.fillRect(x0, y0, x1 - x0, y1 - y0);
      if (round) {
        const f = rgb(pal.field), k = rgb(pal.ink);
        ctx.fillStyle = on[i] ? pal.ink : mix(f, k, 0.08);
        ctx.beginPath();
        ctx.arc((col + 0.5) * p, (row + 0.5) * p, p * 0.44, 0, Math.PI * 2);
        ctx.fill();
      } else if (on[i]) {
        ctx.fillStyle = pal.ink;
        ctx.fillRect(x0, y0, x1 - x0, y1 - y0);
      }
    }
    ctx.restore();
  }

  window.xylzIcon = { draw, lit };
})();
