(() => {
  // the old way: clip to the rounded tile, fill each LED's ground, then its ink if lit
  function oldDraw(ctx, s, palOf, on) {
    const p = s / 16; ctx.clearRect(0, 0, s, s); ctx.save();
    const r = s * 0.2; ctx.beginPath(); ctx.moveTo(r, 0); ctx.arcTo(s, 0, s, s, r); ctx.arcTo(s, s, 0, s, r); ctx.arcTo(0, s, 0, 0, r); ctx.arcTo(0, 0, s, 0, r); ctx.closePath(); ctx.clip();
    for (let i = 0; i < 256; i++) { const pal = palOf(i), row = i >> 4, col = i & 15;
      const x0 = Math.round(col * p), y0 = Math.round(row * p), x1 = Math.round((col + 1) * p), y1 = Math.round((row + 1) * p);
      ctx.fillStyle = pal.field; ctx.fillRect(x0, y0, x1 - x0, y1 - y0);
      if (on[i]) { ctx.fillStyle = pal.ink; ctx.fillRect(x0, y0, x1 - x0, y1 - y0); } }
    ctx.restore();
  }
  const A = { field: "rgb(247,249,250)", ink: "rgb(5,5,6)" }, B = { field: "rgb(255,43,214)", ink: "rgb(5,5,6)" };
  const palOf = (i) => ((i * 37) % 7 < 3 ? A : B); // a mid-pour mix
  const out = {};
  for (const s of [16, 32, 48]) {
    const a = new OffscreenCanvas(s, s).getContext("2d", { willReadFrequently: true });
    const b = new OffscreenCanvas(s, s).getContext("2d", { willReadFrequently: true });
    oldDraw(a, s, palOf, xylzIcon.lit);
    xylzIcon.draw(b, s, palOf, {});
    const da = a.getImageData(0, 0, s, s).data, db = b.getImageData(0, 0, s, s).data;
    let worst = 0, differ = 0;
    for (let k = 0; k < da.length; k += 4) {
      // compare as displayed (premultiplied), since that is what the tab shows
      for (let c = 0; c < 3; c++) { const e = Math.abs(da[k + c] * da[k + 3] - db[k + c] * db[k + 3]) / 255; worst = Math.max(worst, e); if (e > 1) differ++; }
      const ea = Math.abs(da[k + 3] - db[k + 3]); worst = Math.max(worst, ea); if (ea > 1) differ++;
    }
    const t0 = performance.now(); for (let i = 0; i < 50; i++) oldDraw(a, s, palOf, xylzIcon.lit); const tOld = (performance.now() - t0) / 50;
    const t1 = performance.now(); for (let i = 0; i < 50; i++) xylzIcon.draw(b, s, palOf, {}); const tNew = (performance.now() - t1) / 50;
    out[s] = { worstDifference: Math.round(worst * 10) / 10, channelsOffByMoreThan1: differ, oldMs: +tOld.toFixed(3), newMs: +tNew.toFixed(3) };
  }
  return JSON.stringify(out);
})()
