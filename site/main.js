(() => {
  const root = document.documentElement;
  root.classList.add("js");

  const reduceMotion = matchMedia("(prefers-reduced-motion: reduce)");

  const narrow = matchMedia("(max-width: 860px)");
  const targets = [...document.querySelectorAll("[data-lock]")];
  const tracker = document.querySelector(".tracker");
  const lockBox = tracker.querySelector(".lock");
  const lockSay = tracker.querySelector(".lock-say");
  const reticle = tracker.querySelector(".reticle");
  const wire = tracker.querySelector(".wire");
  const SVG = "http://www.w3.org/2000/svg";
  const themeMeta = document.querySelector('meta[name="theme-color"]');

  /* ---------- the tab icon: the wall writes the name in the tab ----------
     tab-icon.js draws a 16 x 16 LED panel spelling "xylz" (one LED per pixel of the 16px icon).
     Here it is kept live, in the current field, at the tab's real device size. Chrome repaints a
     tab icon only about four times a second (once a second in a background tab), so everything
     here moves in 250ms steps: on arrival the name scrolls in from the right in four steps, and a
     pour reaches the icon last: when the wall reports that the new colour has got to where it
     leaves the page for the tab (see tabRoute), it pours on through the LEDs over a second,
     entering at the pour's angle and routing around the lit LEDs the way the wall routes around
     the letters; the address bar colour (theme-color) changes at that moment too. Without script,
     the static favicon files stand in. */
  const tab = (() => {
    const icon = window.xylzIcon;
    const size = Math.min(64, Math.max(16, Math.round(16 * (window.devicePixelRatio || 1))));
    // drawn on a CPU-backed canvas and encoded asynchronously: reading a GPU canvas back with
    // toDataURL stalled the main thread for ~60 ms on the first call
    const cv = typeof OffscreenCanvas === "function" ? new OffscreenCanvas(size, size) : document.createElement("canvas");
    cv.width = cv.height = size;
    const cx = cv.getContext("2d", { willReadFrequently: true });
    let encodeSeq = 0;
    const STEP = 250;
    let link = null;

    /* Arrival order for a pour travelling in direction (dx, dy) (unit, y down): it enters through
       the edges that face it, as a straight front at that angle (each entry LED starts at its own
       distance along the direction), then spreads by cheapest path with a lit LED costing 2.6
       times an unlit one. Timed by rank, as the wall's pour is. */
    function arrival(dx, dy) {
      const N = 16, n = N * N;
      const lit = icon ? icon.lit : new Uint8Array(n);
      const d = new Float64Array(n).fill(1e9), done = new Uint8Array(n);
      const h = (N - 1) / 2;
      for (let r = 0; r < N; r++) {
        for (let c = 0; c < N; c++) {
          const entry = (dy < -0.15 && r === N - 1) || (dy > 0.15 && r === 0) || (dx < -0.15 && c === N - 1) || (dx > 0.15 && c === 0);
          if (entry) d[r * N + c] = (c - h) * dx + (r - h) * dy + (lit[r * N + c] ? 1.6 : 0);
        }
      }
      for (let it = 0; it < n; it++) {
        let k = -1;
        for (let i = 0; i < n; i++) if (!done[i] && (k < 0 || d[i] < d[k])) k = i;
        done[k] = 1;
        const r = (k / N) | 0, c = k % N;
        for (let dr = -1; dr <= 1; dr++) {
          for (let dc = -1; dc <= 1; dc++) {
            const rr = r + dr, cc = c + dc;
            if ((!dr && !dc) || rr < 0 || rr >= N || cc < 0 || cc >= N) continue;
            const w = (dr && dc ? Math.SQRT2 : 1) * (lit[rr * N + cc] ? 2.6 : 1);
            if (d[k] + w < d[rr * N + cc]) d[rr * N + cc] = d[k] + w;
          }
        }
      }
      const out = new Float64Array(n);
      [...d.keys()].sort((a, b) => d[a] - d[b]).forEach((i, m) => { out[i] = m / (n - 1); });
      return out;
    }

    const rgb = (v) => {
      let x = v.trim().replace("#", "");
      if (x.length === 3) x = x.replace(/./g, "$&$&");
      const n = parseInt(x, 16);
      return `rgb(${(n >> 16) & 255},${(n >> 8) & 255},${n & 255})`;
    };
    function palette() {
      const cs = getComputedStyle(root);
      return { field: rgb(cs.getPropertyValue("--field")), ink: rgb(cs.getPropertyValue("--ink")), meta: cs.getPropertyValue("--field").trim() };
    }
    function draw(palOf, shift = 0) {
      if (!icon) return;
      icon.draw(cx, size, palOf, { shift });
      if (!link) {
        document.querySelectorAll('link[rel~="icon"]').forEach((l) => l.remove());
        link = document.createElement("link");
        link.rel = "icon";
        link.type = "image/png";
        document.head.append(link);
      }
      if (!cv.convertToBlob) { link.href = cv.toDataURL("image/png"); return; }
      // a data: URL, as every browser accepts for an icon, made off the main thread; only the newest
      // drawing is applied if several are in flight
      const seq = ++encodeSeq;
      cv.convertToBlob({ type: "image/png" }).then((blob) => {
        const fr = new FileReader();
        fr.onload = () => { if (seq === encodeSeq) link.href = fr.result; };
        fr.readAsDataURL(blob);
      });
    }

    let job = null;
    const stop = () => {
      if (!job) return;
      clearTimeout(job.wait);
      clearInterval(job.tick);
      job = null;
    };
    function set(pal) {
      stop();
      draw(() => pal);
      themeMeta.content = pal.meta;
    }
    // on arrival the name scrolls in from the right, a quarter of the way per step
    function arrive(pal) {
      themeMeta.content = pal.meta;
      if (reduceMotion.matches || document.hidden) return set(pal);
      stop();
      const j = (job = { shifts: [12, 8, 4, 0], k: 0 });
      draw(() => pal, 12);
      j.tick = setInterval(() => {
        if (job !== j) return;
        j.k++;
        draw(() => pal, j.shifts[j.k]);
        if (j.k >= j.shifts.length - 1) { clearInterval(j.tick); job = null; }
      }, STEP);
    }
    // a pour has started on the page: hold the icon until the wall says the colour reached the edge
    function pour(from, to, dir) {
      stop();
      job = { from, to, at: arrival(dir.x, dir.y), started: false };
      job.wait = setTimeout(() => reached(0), 1600); // if the wall never says, finish anyway
    }
    function reached(ms) {
      if (!job || job.started || !job.at) return;
      const j = job;
      j.started = true;
      clearTimeout(j.wait);
      j.wait = setTimeout(() => {
        if (job !== j) return;
        themeMeta.content = j.to.meta;
        let k = 0;
        const frame = () => {
          k++;
          const u = Math.min(1, k / 4); // four steps of 250ms
          draw((i) => (j.at[i] <= u ? j.to : j.from));
          if (u >= 1) { clearInterval(j.tick); if (job === j) job = null; }
        };
        frame();
        j.tick = setInterval(frame, STEP);
      }, ms);
    }
    return { palette, set, arrive, pour, reached };
  })();

  let current = null;
  const lockListeners = [];
  let started = false; // no lock-on for the default lock at load
  let settleUntil = Infinity;
  if ("scrollRestoration" in history) history.scrollRestoration = "manual";

  /* ---------- field: one colour owns the page, cut hard, under three cuts a second ---------- */

  const CUT_GAP = 340;
  let lastCut = 0;
  let pendingField = null;
  let cutTimer = 0;

  function applyField(name) {
    if (root.dataset.field === name) return;
    const before = tab.palette();
    // pin every block of text to its current colour before the field changes under it
    const texts = wallCtl && !reduceMotion.matches ? wallCtl.pinText() : null;
    root.dataset.field = name;
    lastCut = performance.now();
    // with a pour, the tab icon and the address bar change when it reaches them; otherwise now
    const route = texts ? tabRoute() : null;
    if (texts) tab.pour(before, tab.palette(), route.dir);
    else tab.set(tab.palette());
    // only the four destinations at the top pour; every other field change is a plain cut
    if (wallCtl) wallCtl.field(true, texts, route && route.probe);
    else dots.paint();
  }

  /* Where the tab probably is. No web API says where a page's tab sits, how many tabs are open
     or which one this is. What a page can measure is the browser's frame around it: the total
     chrome (outer minus inner size) and, from any pointer event (screenX - clientX against
     window.screenX), which sides it is on. Thick chrome on the left or right means vertical tabs
     on that side; thick chrome on top means a tab strip above; almost none means fullscreen or an
     installed app, with no tab in sight. The tab's place along the strip cannot be known, so it is
     taken as equally likely anywhere on it: the expected point is the middle of the strip (after
     the room macOS keeps on the left for its window buttons, or Windows on the right for its
     caption buttons), or the upper part of a vertical tab list. */
  const chrome = { left: null, top: null };
  addEventListener("pointermove", (e) => {
    if (e.pointerType !== "mouse" || chrome.left !== null) return;
    chrome.left = Math.max(0, e.screenX - e.clientX - screenX);
    chrome.top = Math.max(0, e.screenY - e.clientY - screenY);
  }, { passive: true });
  addEventListener("resize", () => { chrome.left = chrome.top = null; });
  function tabPoint() {
    const sideTotal = Math.max(0, outerWidth - innerWidth);
    const topTotal = Math.max(0, outerHeight - innerHeight);
    const left = chrome.left !== null ? chrome.left : 0;
    const top = chrome.top !== null ? chrome.top : topTotal;
    const right = Math.max(0, sideTotal - left);
    if (sideTotal > 120) {
      // vertical tabs: on the measured side (the left, until a pointer has said otherwise)
      const onRight = chrome.left !== null && right > left;
      return { x: onRight ? innerWidth + right / 2 : -Math.max(left, sideTotal) / 2, y: outerHeight * 0.28 - top };
    }
    if (top < 40) return null; // no tab in sight
    const mac = /mac/i.test((navigator.userAgentData && navigator.userAgentData.platform) || navigator.platform || "");
    const reserveL = mac ? 80 : 8, reserveR = mac ? 40 : 150;
    return { x: (reserveL + outerWidth - reserveR) / 2 - left, y: -top / 2 };
  }

  /* The pour's way out to the tab: the line from the chosen destination to where the tab probably
     is. It leaves the page where that line crosses the viewport's edge (the wall reports when the
     colour gets there), and the icon pours at that line's angle. */
  function tabRoute() {
    const el = selectedTop;
    const r = el ? el.getBoundingClientRect() : { left: innerWidth / 2, top: innerHeight, width: 0, height: 0 };
    const sx = r.left + r.width / 2, sy = r.top + r.height / 2;
    const t = tabPoint() || { x: sx, y: -1 }; // no tab: straight up
    let dx = t.x - sx, dy = t.y - sy;
    const n = Math.hypot(dx, dy) || 1;
    dx /= n;
    dy /= n;
    // first crossing of the viewport's edge along that line, in viewport px
    let k = Infinity;
    if (dy < 0) k = Math.min(k, -sy / dy);
    if (dx < 0) k = Math.min(k, -sx / dx);
    if (dx > 0) k = Math.min(k, (innerWidth - sx) / dx);
    if (!isFinite(k)) k = 0;
    const ex = Math.min(innerWidth - 2, Math.max(2, sx + dx * k));
    const ey = Math.min(innerHeight - 2, Math.max(2, sy + dy * k));
    return { dir: { x: dx, y: dy }, probe: { x: ex + scrollX, y: ey + scrollY } };
  }

  function requestField(name) {
    pendingField = name;
    const wait = lastCut + CUT_GAP - performance.now();
    if (wait <= 0) {
      applyField(name);
      return;
    }
    clearTimeout(cutTimer);
    cutTimer = setTimeout(() => applyField(pendingField), wait);
  }

  /* ---------- geometry ---------- */

  /* Boxes on ruled targets sit on the target's own hairline and end on the next one: one line, never two. */
  function boxFor(el) {
    const r = el.getBoundingClientRect();
    const ruled = el.matches(".targets .target, .report");
    const px = 8;
    const py = ruled ? 0 : 8;
    return {
      x: Math.round(r.left + scrollX - px),
      y: Math.round(r.top + scrollY - py),
      w: Math.round(r.width + px * 2),
      h: Math.round(r.height + py * 2) + (ruled ? 1 : 0),
    };
  }

  function corners(b) {
    return [
      { x: b.x, y: b.y }, { x: b.x + b.w, y: b.y },
      { x: b.x, y: b.y + b.h }, { x: b.x + b.w, y: b.y + b.h },
    ];
  }

  /* Corner-to-corner link between two boxes, the way a tracker joins its points.
     Side by side: top corners facing each other, so the line stays above the text. */
  function link(a, b) {
    if (b.x >= a.x + a.w) return [{ x: a.x + a.w, y: a.y }, { x: b.x, y: b.y }];
    if (a.x >= b.x + b.w) return [{ x: a.x, y: a.y }, { x: b.x + b.w, y: b.y }];
    let best = null;
    let bd = Infinity;
    for (const p of corners(a)) {
      for (const q of corners(b)) {
        const d = (p.x - q.x) ** 2 + (p.y - q.y) ** 2;
        if (d < bd) { bd = d; best = [p, q]; }
      }
    }
    return best;
  }

  /* The wire runs from a tracked point on the section's subject to the lock, through open space only. */
  function anchorFor(el, box) {
    const section = el.closest("section");
    if (section && section.classList.contains("stage")) {
      if (narrow.matches) return null;
      let best = null;
      for (const end of [{ x: box.x, y: box.y }, { x: box.x + box.w, y: box.y }]) {
        const a = dots.anchor(end.x, end.y);
        if (!a) continue;
        const d = Math.hypot(a.x - end.x, a.y - end.y);
        if (!best || d < best.d) best = { ...a, end, d };
      }
      return best;
    }
    const h = section && section.querySelector("[data-anchor]");
    if (!h) return null;
    const r = h.getBoundingClientRect();
    const right = r.right + scrollX + 16;
    // clear of the heading: a diagonal from its end; under it: a drop in the margin
    if (box.x >= right) return { x: Math.round(right), y: Math.round(r.top + scrollY + r.height * 0.55), kind: "end", end: { x: box.x, y: box.y } };
    return { x: box.x, y: Math.round(r.bottom + scrollY + 12), kind: "drop", end: { x: box.x, y: box.y } };
  }

  /* ---------- drawing the near plane ---------- */

  function node(p, size, cls) {
    const g = document.createElementNS(SVG, "g");
    if (cls) g.setAttribute("class", cls);
    const o = document.createElementNS(SVG, "rect");
    o.setAttribute("class", "node-o");
    o.setAttribute("x", p.x - size / 2 + 0.5);
    o.setAttribute("y", p.y - size / 2 + 0.5);
    o.setAttribute("width", size);
    o.setAttribute("height", size);
    const i = document.createElementNS(SVG, "rect");
    i.setAttribute("class", "node-i");
    i.setAttribute("x", p.x - 3);
    i.setAttribute("y", p.y - 3);
    i.setAttribute("width", 7);
    i.setAttribute("height", 7);
    g.append(o, i);
    wire.append(g);
  }

  function segment(p, q, { cls = "" } = {}) {
    // a related link shorter than this reads as two touching squares, not a connection: draw nothing
    if (cls === "rel" && Math.hypot(q.x - p.x, q.y - p.y) < 48) return;
    const l = document.createElementNS(SVG, "line");
    l.setAttribute("x1", p.x); l.setAttribute("y1", p.y);
    l.setAttribute("x2", q.x); l.setAttribute("y2", q.y);
    if (cls) l.setAttribute("class", cls);
    wire.appendChild(l);
    node(p, 15, cls);
    node(q, 15, cls);
  }

  const ghosts = [];
  function ghost(i) {
    if (!ghosts[i]) {
      const g = document.createElement("div");
      g.className = "ghost";
      g.innerHTML = "<i></i><i></i><i></i><i></i>";
      tracker.appendChild(g);
      ghosts[i] = g;
    }
    return ghosts[i];
  }

  function placeSay(a, box) {
    lockSay.style.transform = "";
    if (!a) {
      // no wire: print inside the lock's top-right corner, in the target's empty side
      lockSay.style.left = `${box.x + box.w - 12}px`;
      lockSay.style.top = `${box.y + 12}px`;
      lockSay.style.transform = "translateX(-100%)";
      return;
    }
    // the caption sits on the side of the tracked point the wire does not leave from
    if (a.kind === "end") {
      lockSay.style.left = `${a.x + 14}px`;
      lockSay.style.top = `${a.y - 24}px`;
    } else if (a.kind === "drop") {
      lockSay.style.left = `${a.x + 14}px`;
      lockSay.style.top = `${a.y + 4}px`;
    } else {
      const goesRight = a.end.x > a.x + 4;
      const w = lockSay.offsetWidth;
      const left = goesRight ? a.x - 14 - w : a.x + 14;
      // printed in open field: below the lowest lit cell it would otherwise sit on, clear of its bleed
      const clear = dots.litBottom(left - 8, left + w + 8) + 16;
      lockSay.style.top = `${Math.max(a.y + 14, clear)}px`;
      lockSay.style.left = `${left}px`;
    }
  }

  /* The caption must be readable: if its spot overlaps any block of text or the name (it can at
     high zoom), it moves into the lock box's own top-right corner. */
  const SAY_OBSTACLES = ".caption, .list-note, .targets li, h2, .result, .report, .close-links li, .source, .rail";
  function keepSayClear(box) {
    const r = lockSay.getBoundingClientRect();
    const me = { x: r.left - 4, y: r.top - 4, w: r.width + 8, h: r.height + 8 };
    const hit = (o) => me.x < o.right && me.x + me.w > o.left && me.y < o.bottom && me.y + me.h > o.top;
    let blocked = [...document.querySelectorAll(SAY_OBSTACLES)].some((el) => !el.contains(current) && !current.contains(el) && hit(el.getBoundingClientRect()));
    // the name counts as an obstacle only where its cells are really lit, not its bounding box
    if (!blocked) {
      const lb = dots.litBottom(me.x + scrollX, me.x + me.w + scrollX);
      if (Number.isFinite(lb) && me.y + scrollY < lb + 6) {
        const nb = dots.bounds && dots.bounds();
        blocked = !!nb && me.y + scrollY > nb.y; // inside the name's rows and above its lowest lit cell there
      }
    }
    if (!blocked) return;
    lockSay.style.left = `${box.x + box.w - 12}px`;
    lockSay.style.top = `${box.y + 12}px`;
    lockSay.style.transform = "translateX(-100%)";
  }

  function place() {
    if (!current) return;
    const box = boxFor(current);
    lockBox.style.transform = `translate(${box.x}px, ${box.y}px)`;
    lockBox.style.width = `${box.w}px`;
    lockBox.style.height = `${box.h}px`;
    if (wallCtl) wallCtl.lock(box);

    wire.replaceChildren();
    const a = anchorFor(current, box);
    if (a) segment(a, a.end);
    placeSay(a, box);
    keepSayClear(box);

    // the network: related items in the same section get tick-only boxes, joined to the lock
    const section = current.closest("section");
    const rel = (current.dataset.rel || "").split(" ").filter(Boolean)
      .map((k) => targets.find((t) => t.dataset.key === k))
      .filter((t) => t && t.closest("section") === section);
    ghosts.forEach((g, i) => { g.style.display = i < rel.length ? "" : "none"; });
    rel.forEach((t, i) => {
      const b = boxFor(t);
      const g = ghost(i);
      g.style.transform = `translate(${b.x}px, ${b.y}px)`;
      g.style.width = `${b.w}px`;
      g.style.height = `${b.h}px`;
      const [p, q] = link(box, b);
      segment(p, q, { cls: "rel" });
    });
  }

  /* Where the lock just was stays behind as an afterimage that sinks back. */
  function afterimage() {
    if (!current || reduceMotion.matches) return;
    const box = boxFor(current);
    const el = document.createElement("div");
    el.className = "after";
    el.innerHTML = "<i></i><i></i><i></i><i></i>";
    el.style.transform = `translate(${box.x}px, ${box.y}px)`;
    el.style.width = `${box.w}px`;
    el.style.height = `${box.h}px`;
    tracker.insertBefore(el, lockBox);
    el.addEventListener("animationend", () => el.remove());
    const all = tracker.querySelectorAll(".after");
    if (all.length > 4) all[0].remove();
  }

  function lock(el, { hash = false, field = true } = {}) {
    if (!el) return;
    const changed = el !== current;
    if (current && changed) current.classList.remove("current");
    el.classList.add("current");
    if (changed) afterimage();
    current = el;
    lockSay.textContent = el.dataset.say || "";
    root.classList.add("locked");
    place();
    if (gaze && changed) gaze.onset(boxFor(el));
    if (changed) lockListeners.forEach((fn) => fn());
    // only the four destinations at the top change the field (and pour); every other lock keeps
    // the colour it finds, so scrolling or hovering lower down never snaps the wall. A pointer
    // passing over a destination only previews it (field: false); see commit() below.
    if (field && el.matches(".targets .target")) commit(el);
    if (hash && el.dataset.key) history.replaceState(null, "", `#${el.dataset.key}`);
  }

  /* ---------- input ---------- */

  /* ---------- hover previews, intent commits ----------
     The field (and its pour) changes only when the visitor means it. Passing the pointer over one
     of the four destinations moves the tracker there at once, as a preview; the colour follows only
     when the pointer settles on it, the way an aimed movement ends: it stops (no movement for 60ms),
     or slows below 0.12px/ms for 40ms (the final corrective phase of a pointing movement), or stays
     on it for 400ms while moving slowly (under 0.25px/ms; a steady drift across is not staying). A click, a key or focus commits at once. A hover that only happened because
     the page scrolled under a still pointer commits nothing until the pointer itself moves on the
     target (4px or more); turning the wheel while a preview waits means scrolling, not choosing, so it
     waits for the pointer to move again. Leaving before a commit puts the tracker back where it was. */
  let selectedTop = null; // the top destination whose colour the field shows
  function commit(el) {
    cancelPreview();
    clearTimeout(revertTimer);
    revertHome = null;
    selectedTop = el;
    requestField(el.dataset.field || "white");
  }
  const STOP_MS = 60, SLOW = 0.12, SLOW_MS = 40, DWELL_MS = 400, DWELL_SLOW = 0.25;
  let preview = null; // { el, home, since, slowSince, live, timer }
  let revertTimer = 0;
  let revertHome = null; // where the tracker goes back to while the pointer crosses between destinations
  let lastPtr = null; // the pointer's last real position (pointermove), viewport px
  function cancelPreview() {
    if (!preview) return;
    clearTimeout(preview.timer);
    preview = null;
  }
  function previewTick() {
    // the pointer has not moved for STOP_MS while on the target: it stopped there
    if (preview && preview.live) commit(preview.el);
  }
  function previewMove(speed, now) {
    if (!preview) return;
    if (!preview.live) {
      if (!lastPtr || Math.hypot(lastPtr.x - preview.entry.x, lastPtr.y - preview.entry.y) < 4) return;
      preview.live = true;
      preview.since = now;
      preview.slowSince = 0;
    }
    clearTimeout(preview.timer);
    if (now - preview.since >= DWELL_MS && speed < DWELL_SLOW) return commit(preview.el);
    if (speed < SLOW) {
      if (!preview.slowSince) preview.slowSince = now;
      if (now - preview.slowSince >= SLOW_MS) return commit(preview.el);
    } else preview.slowSince = 0;
    preview.timer = setTimeout(previewTick, STOP_MS);
  }

  addEventListener("wheel", () => {
    if (!preview) return;
    clearTimeout(preview.timer);
    preview.live = false;
    preview.entry = lastPtr || preview.entry;
  }, { passive: true });

  // the last kind of pointer used; touch switches the page to its touch controls (.touch-ui)
  let lastPointer = matchMedia("(hover: none) and (pointer: coarse)").matches ? "touch" : "mouse";
  if (lastPointer === "touch") root.classList.add("touch-ui");
  addEventListener("pointerdown", (e) => {
    lastPointer = e.pointerType;
    root.classList.toggle("touch-ui", e.pointerType === "touch");
  }, { capture: true, passive: true });
  addEventListener("pointermove", (e) => {
    if (e.pointerType === "mouse" && lastPointer !== "mouse") {
      lastPointer = "mouse";
      root.classList.remove("touch-ui");
    }
  }, { passive: true });

  let overTarget = false;
  for (const el of targets) {
    const top = el.matches(".targets .target");
    el.addEventListener("pointerenter", (e) => {
      if (e.pointerType === "touch") return;
      overTarget = true;
      clearLead();
      clearTimeout(revertTimer);
      if (!top) { lock(el); return; }
      if (el === selectedTop && root.dataset.field === (el.dataset.field || "white")) { cancelPreview(); revertHome = null; lock(el, { field: false }); return; }
      const home = preview ? preview.home : revertHome || current;
      revertHome = null;
      cancelPreview();
      // entered by the page scrolling under a still pointer, not by the pointer moving
      const still = !lastPtr || Math.hypot(e.clientX - lastPtr.x, e.clientY - lastPtr.y) < 1;
      preview = { el, home, since: performance.now(), slowSince: 0, live: !still, timer: 0, entry: { x: e.clientX, y: e.clientY } };
      lock(el, { field: false });
      if (preview.live) preview.timer = setTimeout(previewTick, STOP_MS);
    });
    el.addEventListener("pointerleave", () => {
      overTarget = false;
      if (!preview || preview.el !== el) return;
      const home = preview.home;
      cancelPreview();
      // back to what was selected, unless the pointer goes straight on to another destination
      revertHome = home;
      revertTimer = setTimeout(() => {
        revertHome = null;
        if (home && home !== current) lock(home, { field: false });
      }, 120);
    });
    el.addEventListener("pointerdown", (e) => {
      // a press commits at once for mouse and pen; a finger going down is usually a scroll starting
      if (!top || e.pointerType === "touch") return;
      clearTimeout(revertTimer);
      lock(el, { field: false });
      commit(el);
    });
    if (top) {
      el.addEventListener("click", (e) => {
        // touch: a tap selects; only the selected one's control opens it. Clicks with no pointer
        // (Enter, assistive technology: detail 0) and mouse clicks open as links always do.
        if (lastPointer !== "touch" || e.detail === 0 || e.target.closest(".t-open")) return;
        e.preventDefault();
        lock(el);
      });
    }
    el.addEventListener("focus", () => lock(el, { hash: true }));
  }

  /* Keyboard: arrows move the lock (selection); Enter follows the link (activation). */
  document.addEventListener("keydown", (e) => {
    if (e.altKey || e.ctrlKey || e.metaKey) return;
    const keys = ["ArrowDown", "ArrowRight", "ArrowUp", "ArrowLeft", "Home", "End"];
    if (!keys.includes(e.key)) return;
    const active = document.activeElement;
    const i = targets.indexOf(active);
    if (i === -1 && active !== document.body) return;
    e.preventDefault();
    let next;
    if (e.key === "Home") next = 0;
    else if (e.key === "End") next = targets.length - 1;
    else {
      const dir = e.key === "ArrowDown" || e.key === "ArrowRight" ? 1 : -1;
      const from = i === -1 ? targets.indexOf(current) : i;
      next = (from + dir + targets.length) % targets.length;
    }
    targets[next].focus();
  });

  /* The pointer is tracked as well: a reticle that jumps to it in discrete 50ms steps,
     like tracking data sampled at 20 per second, never easing. */
  const STEP = 50;
  let ptr = null;
  let lastStep = 0;
  let raf = 0;

  function frame(now) {
    raf = 0;
    if (!ptr) return;
    if (now - lastStep < STEP) {
      raf = requestAnimationFrame(frame);
      return;
    }
    lastStep = now;
    const x = Math.round((ptr.x - 13) / 2) * 2;
    const y = Math.round((ptr.y - 13) / 2) * 2;
    reticle.style.transform = `translate(${x}px, ${y}px)`;
    reticle.classList.toggle("on", !overTarget);
  }

  /* ---------- intent: read where the pointer is heading ----------
     Velocity is smoothed over the last few moves and projected forward as a ray; the destination
     the ray enters first (within reach) is the predicted target. Prediction never selects: it only
     leads the tracker there and has the wall compute that target's pour before the pointer lands. */
  const leadLine = tracker.querySelector(".lead line");
  const leadBox = tracker.querySelector(".lead-box");
  let vel = { x: 0, y: 0 };
  let lastMove = null;
  let predicted = null;
  let leadStill = 0;
  let prepTimer = 0;
  // destination rects in viewport px, refreshed on scroll and resize instead of read per move
  let rects = null;
  const dropRects = () => { rects = null; };
  addEventListener("scroll", dropRects, { passive: true });
  addEventListener("resize", dropRects);

  function rayHit(px, py, dx, dy, r, reach) {
    // slab test of the ray against the rect, returns the entry distance or Infinity
    let t0 = 0;
    let t1 = reach;
    for (const [p, d, lo, hi] of [[px, dx, r.left, r.right], [py, dy, r.top, r.bottom]]) {
      if (Math.abs(d) < 1e-6) { if (p < lo || p > hi) return Infinity; continue; }
      let a = (lo - p) / d;
      let b = (hi - p) / d;
      if (a > b) [a, b] = [b, a];
      t0 = Math.max(t0, a);
      t1 = Math.min(t1, b);
      if (t0 > t1) return Infinity;
    }
    return t0;
  }

  let intentNow = null;
  function clearLead() {
    if (intentNow && gaze) gaze.intent(null);
    intentNow = null;
    predicted = null;
    root.classList.remove("leading");
  }

  function readIntent(e) {
    const now = performance.now();
    if (lastMove) {
      const dt = Math.max(1, now - lastMove.t);
      const k = Math.min(1, dt / 50);
      vel.x += ((e.clientX - lastMove.x) / dt - vel.x) * k;
      vel.y += ((e.clientY - lastMove.y) / dt - vel.y) * k;
    }
    lastMove = { x: e.clientX, y: e.clientY, t: now };
    previewMove(Math.hypot(vel.x, vel.y), now);
    clearTimeout(leadStill);
    leadStill = setTimeout(clearLead, 140); // the pointer stopped: no heading, no lead

    const speed = Math.hypot(vel.x, vel.y);
    if (speed < 0.35) { clearLead(); return; }
    intentNow = null;
    const dx = vel.x / speed;
    const dy = vel.y / speed;
    const reach = Math.min(900, 240 + speed * 260);
    let best = null;
    let bt = Infinity;
    if (!rects) rects = targets.map((t) => t.getBoundingClientRect());
    for (let ti = 0; ti < targets.length; ti++) {
      const t = targets[ti];
      if (t === current || t.contains(e.target)) continue;
      const r = rects[ti];
      if (r.bottom < 0 || r.top > innerHeight) continue;
      const pad = 14;
      const box = { left: r.left - pad, right: r.right + pad, top: r.top - pad, bottom: r.bottom + pad };
      // a narrow cone: the heading and two rays 7 degrees either side
      for (const a of [0, 0.122, -0.122]) {
        const cx = dx * Math.cos(a) - dy * Math.sin(a);
        const cy = dx * Math.sin(a) + dy * Math.cos(a);
        const hit = rayHit(e.clientX, e.clientY, cx, cy, box, reach);
        if (hit < bt) { bt = hit; best = t; }
      }
    }
    if (!best) { clearLead(); return; }
    const b = boxFor(best);
    intentNow = { box: { x: b.x - scrollX, y: b.y - scrollY, w: b.w, h: b.h }, speed };
    if (gaze) gaze.intent(intentNow);
    leadBox.style.transform = `translate(${b.x}px, ${b.y}px)`;
    leadBox.style.width = `${b.w}px`;
    leadBox.style.height = `${b.h}px`;
    const px = e.clientX + scrollX;
    const py = e.clientY + scrollY;
    const ex = Math.min(Math.max(px, b.x), b.x + b.w);
    const ey = Math.min(Math.max(py, b.y), b.y + b.h);
    leadLine.setAttribute("x1", Math.round(px));
    leadLine.setAttribute("y1", Math.round(py));
    leadLine.setAttribute("x2", Math.round(ex));
    leadLine.setAttribute("y2", Math.round(ey));
    root.classList.add("leading");
    if (best !== predicted) {
      predicted = best;
      // prepare only once the heading has held on one target for a moment: circling the pointer
      // changes the guess constantly, and each pour takes the worker several milliseconds
      clearTimeout(prepTimer);
      prepTimer = setTimeout(() => { if (predicted === best && wallCtl) wallCtl.prepare(b); }, 120);
    }
  }

  addEventListener("pointermove", (e) => {
    if (e.pointerType === "touch") return;
    root.classList.add("pointer-in");
    ptr = { x: e.clientX + scrollX, y: e.clientY + scrollY };
    lastPtr = { x: e.clientX, y: e.clientY };
    if (!raf) raf = requestAnimationFrame(frame);
    readIntent(e);
    if (gaze) gaze.move(e.clientX, e.clientY);
    if (wallCtl) wallCtl.lens({ x: e.clientX, y: e.clientY });
  }, { passive: true });
  root.addEventListener("pointerleave", () => {
    root.classList.remove("pointer-in");
    if (wallCtl) wallCtl.lens(null);
  });

  /* ---------- scroll: the dot screen sits deeper, the rail says where you are ---------- */

  const rail = [...document.querySelectorAll(".rail a")];
  let wallScrollQueued = false;
  function onScroll() {
    // the CSS dot screen only shows without the wall; setting its offset on the root restyles the
    // whole page, so with the wall on it is left alone
    if (!wallCtl) {
      const py = reduceMotion.matches ? 0 : -((scrollY * 0.33) % 10);
      root.style.setProperty("--py", `${py.toFixed(1)}px`);
    }
    // the wall hears about scrolling once per frame, not once per event
    if (wallCtl && !wallScrollQueued) {
      wallScrollQueued = true;
      requestAnimationFrame(() => { wallScrollQueued = false; wallCtl.scroll(); });
    }
  }
  addEventListener("scroll", onScroll, { passive: true });
  // first call in the first frame: reading scrollY while the script runs forced a layout early
  requestAnimationFrame(onScroll);

  /* When the locked item leaves view, the tracker picks up the section you are reading. */
  const sections = [...document.querySelectorAll("main > section")];
  const seen = new Map();
  const io = new IntersectionObserver(
    (entries) => {
      for (const en of entries) seen.set(en.target, en.intersectionRatio);
      let best = null;
      let bestRatio = 0;
      for (const [s, ratio] of seen) {
        if (ratio > bestRatio) { best = s; bestRatio = ratio; }
      }
      if (best) {
        for (const a of rail) a.classList.toggle("here", a.dataset.rail === (best.id === "top" ? "stage" : best.id));
      }
      if (performance.now() < settleUntil) return;
      const r = current && current.getBoundingClientRect();
      const inView = r && r.bottom > 0 && r.top < innerHeight;
      if (inView) return;
      if (lastPointer === "touch") return;
      if (best && bestRatio > 0.35) {
        const pick = best.id === "top" && selectedTop ? selectedTop : best.querySelector("[data-lock]");
        lock(pick, { field: false });
      }
    },
    { threshold: [0, 0.2, 0.35, 0.6, 1] }
  );
  sections.forEach((s) => io.observe(s));

  /* ---------- the name: a lit dot panel ---------- */

  const dots = (() => {
    const h1 = document.querySelector(".name");
    const canvas = h1.querySelector(".name-dots");
    const glow = h1.querySelector(".name-bloom");
    const ctx = canvas.getContext("2d");
    const gctx = glow.getContext("2d");
    let lit = [];
    let unlit = [];
    let alpha = null;
    let grid = null;
    let W = 0;
    let H = 0;
    let gap = 8;
    let dpr = 1;
    let ready = false;
    let pointer = null;
    let raf = 0;

    function build() {
      const w = Math.round(h1.getBoundingClientRect().width);
      if (!w) return;
      const probe = document.createElement("canvas").getContext("2d");
      probe.font = "900 200px Archivo";
      const size = (200 * w) / probe.measureText("xylz").width;
      probe.font = `900 ${size}px Archivo`;
      const mm = probe.measureText("xylz");
      const asc = Math.ceil(mm.actualBoundingBoxAscent);
      const desc = Math.ceil(mm.actualBoundingBoxDescent);
      W = w;
      H = asc + desc;
      gap = Math.max(5, Math.min(12, Math.round(W / 92)));

      const mask = document.createElement("canvas");
      mask.width = W;
      mask.height = H;
      // CPU-backed, so reading its pixels does not stall on a GPU read-back
      const mc = mask.getContext("2d", { willReadFrequently: true });
      mc.font = `900 ${size}px Archivo`;
      mc.fillText("xylz", -mm.actualBoundingBoxLeft, asc);
      const data = mc.getImageData(0, 0, W, H).data;
      alpha = new Uint8Array(W * H);
      for (let k = 0; k < W * H; k++) alpha[k] = data[k * 4 + 3];

      lit = [];
      unlit = [];
      const half = gap / 2;
      const s = [[0, 0], [-gap / 3, 0], [gap / 3, 0], [0, -gap / 3], [0, gap / 3]];
      for (let y = half; y < H; y += gap) {
        for (let x = half; x < W; x += gap) {
          let a = 0;
          for (const [dx, dy] of s) {
            const sx = Math.min(W - 1, Math.max(0, Math.round(x + dx)));
            const sy = Math.min(H - 1, Math.max(0, Math.round(y + dy)));
            a += data[(sy * W + sx) * 4 + 3];
          }
          a /= s.length * 255;
          // an LED cell is on or off: no half-lit edge dots
          if (a >= 0.5) lit.push({ x, y, r: gap * 0.42, k: 0 });
          else unlit.push({ x, y, k: 0 });
        }
      }

      dpr = Math.min(2, devicePixelRatio || 1);
      for (const c of [canvas, glow]) {
        c.width = Math.round(W * dpr);
        c.height = Math.round(H * dpr);
        c.style.width = `${W}px`;
        c.style.height = `${H}px`;
      }
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      ready = true;
      root.classList.add("dots-on");
      if (wallPitch) wallCells();
      else paint();
    }

    /* With the wall on, the name's lit cells are the wall's cells: the same grid, page-aligned,
       so every tracked point lands on a cell that is really lit. */
    function wallCells() {
      const r = canvas.getBoundingClientRect();
      const ox = r.left + scrollX;
      const oy = r.top + scrollY;
      const p = wallPitch;
      const c0 = Math.floor(ox / p);
      const r0 = Math.floor(oy / p);
      const cols = Math.ceil((ox + W) / p) - c0;
      const rows = Math.ceil((oy + H) / p) - r0;
      const cells = new Uint8Array(cols * rows);
      const m = { w: W, h: H, data: alpha };
      for (let r = 0; r < rows; r++) {
        for (let c = 0; c < cols; c++) {
          const x = (c0 + c) * p + p / 2 - ox;
          const y = (r0 + r) * p + p / 2 - oy;
          if (window.wallLitAt(m, x, y, p / 3)) cells[r * cols + c] = 1;
        }
      }
      // a lit cell with no lit neighbour is an edge artefact, not part of the letter
      const on = (c, r) => c >= 0 && r >= 0 && c < cols && r < rows && cells[r * cols + c] === 1;
      const drop = [];
      for (let r = 0; r < rows; r++) {
        for (let c = 0; c < cols; c++) {
          if (on(c, r) && !on(c - 1, r) && !on(c + 1, r) && !on(c, r - 1) && !on(c, r + 1)) drop.push(r * cols + c);
        }
      }
      for (const k of drop) cells[k] = 0;
      grid = { c0, r0, cols, rows, cells };
      lit = [];
      unlit = [];
      for (let r = 0; r < rows; r++) {
        for (let c = 0; c < cols; c++) {
          if (cells[r * cols + c]) lit.push({ x: (c0 + c) * p + p / 2 - ox, y: (r0 + r) * p + p / 2 - oy, r: 0, k: 0 });
        }
      }
    }

    function litBottom(x0, x1) {
      const r = canvas.getBoundingClientRect();
      const ox = r.left + scrollX;
      const oy = r.top + scrollY;
      let b = -Infinity;
      for (const p of lit) {
        const x = ox + p.x;
        if (x >= x0 && x <= x1 && oy + p.y > b) b = oy + p.y;
      }
      return b;
    }

    // the name's lit cells as one rectangle, in document px (for keeping labels off it)
    function bounds() {
      if (!grid) return null;
      const p = wallPitch || 8;
      return { x: grid.c0 * p, y: grid.r0 * p, w: grid.cols * p, h: grid.rows * p };
    }

    function mask() {
      const r = canvas.getBoundingClientRect();
      return { x: r.left + scrollX, y: r.top + scrollY, w: W, h: H, data: alpha, grid };
    }

    function paint() {
      if (!ready) return;
      const ink = getComputedStyle(root).getPropertyValue("--ink").trim();
      ctx.clearRect(0, 0, W, H);
      ctx.fillStyle = ink;
      // the unlit panel: every cell is there, faint; the pointer lights the ones near it
      for (const p of unlit) {
        ctx.globalAlpha = 0.09 + p.k * 0.4;
        ctx.beginPath();
        ctx.arc(p.x, p.y, gap * (0.14 + p.k * 0.12), 0, Math.PI * 2);
        ctx.fill();
      }
      ctx.globalAlpha = 1;
      ctx.beginPath();
      for (const p of lit) {
        const r = p.r * (1 + p.k * 0.22);
        ctx.moveTo(p.x + r, p.y);
        ctx.arc(p.x, p.y, r, 0, Math.PI * 2);
      }
      ctx.fill();
      // the bleed behind the lit dots is the same image, blurred by CSS
      gctx.setTransform(1, 0, 0, 1, 0, 0);
      gctx.clearRect(0, 0, glow.width, glow.height);
      gctx.drawImage(canvas, 0, 0);
    }

    /* The pointer is a light on the panel: dots near it grow and glow; they settle back. */
    let lastStep = 0;
    function step(now) {
      raf = 0;
      const R = gap * 10;
      let moving = false;
      // eases a quarter of the way per 60 Hz frame, whatever the display's rate
      const dt = lastStep && now - lastStep < 250 ? now - lastStep : 1000 / 60;
      lastStep = now;
      const ease = 1 - Math.pow(0.75, dt / (1000 / 60));
      const update = (p) => {
        let t = 0;
        if (pointer) {
          const d = Math.hypot(p.x - pointer.x, p.y - pointer.y);
          if (d < R) t = (1 - d / R) ** 2;
        }
        p.k += (t - p.k) * ease;
        if (Math.abs(t - p.k) > 0.01) moving = true;
      };
      lit.forEach(update);
      unlit.forEach(update);
      paint();
      if (moving) raf = requestAnimationFrame(step);
    }

    addEventListener("pointermove", (e) => {
      if (wallPitch || !ready || reduceMotion.matches || e.pointerType === "touch") return;
      const r = canvas.getBoundingClientRect();
      const x = e.clientX - r.left;
      const y = e.clientY - r.top;
      const near = x > -gap * 10 && x < W + gap * 10 && y > -gap * 10 && y < H + gap * 10;
      if (!near && !pointer) return;
      pointer = near ? { x, y } : null;
      if (!raf) raf = requestAnimationFrame(step);
    }, { passive: true });

    const caption = document.querySelector(".caption");

    // does the segment p-q pass through rectangle b (Liang-Barsky clip)?
    function crosses(p, q, b) {
      let t0 = 0;
      let t1 = 1;
      const dx = q.x - p.x;
      const dy = q.y - p.y;
      const tests = [[-dx, p.x - b.l], [dx, b.r - p.x], [-dy, p.y - b.t], [dy, b.b - p.y]];
      for (const [pp, qq] of tests) {
        if (pp === 0) { if (qq < 0) return false; continue; }
        const t = qq / pp;
        if (pp < 0) { if (t > t1) return false; if (t > t0) t0 = t; }
        else { if (t < t0) return false; if (t < t1) t1 = t; }
      }
      return true;
    }

    function anchor(bx, by) {
      // the tracked point is a real lit dot of the name: the nearest one whose wire to the lock
      // passes clear of the caption, kept a gutter away from its text
      if (!ready || !lit.length) return null;
      const r = canvas.getBoundingClientRect();
      const ox = r.left + scrollX;
      const oy = r.top + scrollY;
      const c = caption.getBoundingClientRect();
      const keep = 14;
      const cap = { l: c.left + scrollX - keep, r: c.right + scrollX + keep, t: c.top + scrollY - keep, b: c.bottom + scrollY + keep };
      const end = { x: bx, y: by };
      // nearest lit cell whose wire clears the caption: one pass keeps the best candidate, no sort
      let best = null, bd = Infinity;
      for (let i = 0; i < lit.length; i++) {
        const p = lit[i];
        const d = (ox + p.x - bx) ** 2 + (oy + p.y - by) ** 2;
        if (d >= bd) continue;
        const s = { x: ox + p.x, y: oy + p.y };
        if (crosses(s, end, cap)) continue;
        bd = d;
        best = s;
      }
      return best ? { x: Math.round(best.x), y: Math.round(best.y), kind: "name" } : null;
    }

    return { build, paint, anchor, mask, litBottom, bounds };
  })();

  /* ---------- the LED wall ---------- */

  var wallPitch = 0; // hoisted: scroll and field handlers run before the wall is set up
  const FIELD_LIGHT = {
    // glow: how strongly lit LEDs bleed light into the gaps; gloss: the strength of each LED's
    // specular highlight and rim (both per LED in the wall, so they turn with the pour)
    white: { base: 0.055, amp: 0.02, glow: 0, gloss: 1 },
    black: { base: 0.08, amp: 0.025, glow: 0.75, gloss: 0.7 },
    sky: { base: 0.07, amp: 0.02, glow: 0, gloss: 1 },
    magenta: { base: 0.07, amp: 0.02, glow: 0, gloss: 1 },
  };

  var wallCtl = (() => {
    const host = document.createElement("div");
    host.className = "wall";
    host.setAttribute("aria-hidden", "true");
    const bloom = document.createElement("canvas");
    bloom.className = "wall-bloom";
    const cells = document.createElement("canvas");
    cells.className = "wall-cells";
    const gaps = document.createElement("canvas");
    gaps.className = "wall-gaps";
    // each LED is a small domed lens: a darker rim (the same on every field) and a highlight, whose
    // strength depends on the field: a plain layer while every LED has the same, and one pixel per
    // LED, masked into shape in CSS, while a pour mixes them
    const rim = document.createElement("div");
    rim.className = "wall-rim";
    const glossHi = document.createElement("canvas");
    glossHi.className = "wall-gloss-hi";
    const gloss = document.createElement("div");
    gloss.className = "wall-gloss";
    // the glow lies under the gaps, which let it through only around LEDs whose field glows
    host.append(bloom, gaps, cells, rim, glossHi, gloss);

    let post = null;
    let givePort = null; // hands the wall a port to the gaze worker, for its change map
    try {
      if (window.Worker && cells.transferControlToOffscreen) {
        const worker = new Worker("wall-worker.js?v=20261013n35");
        worker.onmessage = (e) => committed(e.data);
        const oc = cells.transferControlToOffscreen();
        const ob = bloom.transferControlToOffscreen();
        const og = gaps.transferControlToOffscreen();
        const oh = glossHi.transferControlToOffscreen();
        worker.postMessage({ type: "init", canvas: oc, bloom: ob, gaps: og, glossHi: oh, debug: location.search.includes("debug"), rec: /[?&]rec(?:[=&]|$)/.test(location.search) }, [oc, ob, og, oh]);
        post = (m) => worker.postMessage(m);
        givePort = (port) => worker.postMessage({ type: "motionPort", port }, [port]);
      } else if (window.createWall) {
        const w = window.createWall((fn) => requestAnimationFrame(fn), (m) => committed(m));
        w.handle({ type: "init", canvas: cells, bloom, gaps, glossHi });
        post = (m) => w.handle(m);
      }
    } catch (err) {
      post = null;
    }
    if (!post) return null;
    if (location.search.includes("debug")) window.__dumpWallRec = () => post({ type: "dumpRec" });
    document.body.prepend(host);
    root.classList.add("wall-on");

    const hex = (s) => {
      const v = s.trim().replace("#", "");
      return [0, 2, 4].map((k) => parseInt(v.slice(k, k + 2), 16));
    };

    /* The canvas covers the whole document, one pixel per cell, and scrolls with it: the name never
       swims and the canvas never has to move. (Moving it meant the worker's frame and the page's
       style change could land in different compositor frames, and the name jumped for one frame.)
       Only a document taller than FULL_ROWS falls back to a window of the document that re-centres
       when the reader nears its edge. */
    const FULL_ROWS = 1400;
    let half = 0;
    let want = 0;
    let shown = null;
    let full = false;

    // with ?debug, the time each wall frame was delivered, for the smoothness checks in tools/
    const frameLog = location.search.includes("debug") ? (window.__wallFrames = []) : null;
    function committed(m) {
      if (frameLog && m.type === "committed") frameLog.push(performance.now());
      if (frameLog && m.type === "slow") (window.__wallSlow = window.__wallSlow || []).push(m);
      if (m.type === "arrivals") { arrived(m); return; }
      if (m.type === "rec") { window.__wallRec = m.log; return; }
      if (m.type === "glow") { host.classList.toggle("glow-on", m.on); return; }
      if (m.type === "gloss") {
        // the strength only changes while the per-LED layers are showing, never under the eye
        if (!m.mixed) host.style.setProperty("--gloss", m.k);
        host.classList.toggle("gloss-mixed", m.mixed);
        return;
      }
      if (m.type !== "committed" || m.rowStart === shown) return;
      shown = m.rowStart;
      host.style.setProperty("--top", `${shown * wallPitch}px`);
    }

    function size() {
      wallPitch = Math.max(6, Math.min(9, Math.round(innerWidth / 170)));
      const vrows = Math.ceil(innerHeight / wallPitch);
      const docRows = Math.ceil(Math.max(document.documentElement.scrollHeight, innerHeight) / wallPitch) + 1;
      full = docRows <= FULL_ROWS;
      half = Math.ceil(vrows / 2) + 1;
      const cols = Math.ceil(innerWidth / wallPitch) + 1;
      const rows = full ? docRows : vrows + half * 2;
      host.style.setProperty("--pitch", `${wallPitch}px`);
      for (const c of [cells, bloom, gaps, glossHi]) {
        c.style.width = `${cols * wallPitch}px`;
        c.style.height = `${rows * wallPitch}px`;
      }
      shown = null;
      want = full ? 0 : Math.floor(scrollY / wallPitch) - half;
      post({ type: "resize", cols, rows, pitch: wallPitch });
      scroll();
    }

    function scroll() {
      const row = Math.floor(scrollY / wallPitch);
      if (!full && (row - want < half / 2 || row - want > half * 1.5)) want = row - half;
      post({ type: "scroll", scrollY, rowStart: want, vw: innerWidth, vh: innerHeight });
    }

    /* Text keeps the colour it had until the pour reaches it. Before the field changes, every
       block of text is pinned to the colour it shows; the worker reports when the pour arrives at
       each block's centre, and the pin comes off then. */
    const TEXT = ".caption, .list-note, .targets li, h2, .result, .report, .close-links li, .source, .rail a";
    let pins = [];
    let seq = 0;
    function pinText() {
      const cs = getComputedStyle(root);
      const ink = cs.getPropertyValue("--ink").trim();
      const soft = cs.getPropertyValue("--soft").trim();
      const els = [...document.querySelectorAll(TEXT)];
      pins.forEach((p) => clearTimeout(p.timer));
      pins = els.map((el) => {
        const was = pins.find((p) => p.el === el);
        // an element still pinned from an unfinished pour keeps that colour
        const keepInk = was && el.style.color ? el.style.color : ink;
        const keepSoft = was && el.style.getPropertyValue("--soft") ? el.style.getPropertyValue("--soft") : soft;
        el.style.color = keepInk;
        el.style.setProperty("--ink", keepInk);
        el.style.setProperty("--soft", keepSoft);
        return { el, timer: 0 };
      });
      return els.map((el) => {
        const r = el.getBoundingClientRect();
        return { x: r.left + scrollX, y: r.top + scrollY, w: r.width, h: r.height };
      });
    }
    function unpin(p) {
      p.el.style.removeProperty("color");
      p.el.style.removeProperty("--ink");
      p.el.style.removeProperty("--soft");
    }
    function arrived(m) {
      if (m.seq !== seq) return;
      if (m.probe >= 0) tab.reached(m.probe);
      pins.forEach((p, i) => {
        const ms = m.list[i] || 0;
        if (ms <= 0) unpin(p);
        else p.timer = setTimeout(() => unpin(p), ms);
      });
    }

    function field(cut, texts, probe = null) {
      const cs = getComputedStyle(root);
      const light = FIELD_LIGHT[root.dataset.field] || FIELD_LIGHT.white;
      seq++;
      // probe: where the pour leaves the page for the tab (see tabRoute)
      post({ type: "field", field: hex(cs.getPropertyValue("--field")), ink: hex(cs.getPropertyValue("--ink")), gap: hex(cs.getPropertyValue("--gap")), ...light, cut, texts, probe, seq });
    }

    function masks() {
      const m = dots.mask();
      if (!m.data) return;
      // the name itself, and a giant echo of it far behind, drifting at a third of the scroll speed
      // where text sits, in document px, so the residue keeps off it
      const keep = [...document.querySelectorAll(".caption, .targets li, h2, .result, .report, .close-links li, .source")].map((el) => {
        const r = el.getBoundingClientRect();
        return { x: r.left + scrollX - 10, y: r.top + scrollY - 10, w: r.width + 20, h: r.height + 20 };
      });
      const keepFixed = [...document.querySelectorAll(".rail")].map((el) => {
        const r = el.getBoundingClientRect();
        return { x: r.left - 10, y: r.top - 10, w: r.width + 20, h: r.height + 20 };
      });
      post({
        type: "masks",
        keep,
        keepFixed,
        masks: [
          { ...m.grid, t: 1 },
          // it peeks in at the bottom of the first screen, then rises behind Public work and Elsewhere;
          // soft-edged cells, so it reads as further back than the crisp name
          { x: m.x - innerWidth * 0.1, y: innerHeight * 0.92, w: m.w, h: m.h, data: m.data, scale: 2.4, depth: reduceMotion.matches ? 1 : 0.35, t: 0.2, soft: true },
        ],
      });
    }

    // the lens and its trail move only with the visitor's own hand (direct manipulation), so they
    // stay on whatever the motion setting; only motion that plays by itself is switched off
    const lens = (p) => post({ type: "lens", lens: p });
    const lock = (b) => post({ type: "lock", lock: b });
    const prepare = (b) => post({ type: "prepare", box: b });

    reduceMotion.addEventListener("change", () => {
      post({ type: "reduce", reduce: reduceMotion.matches });
      masks();
    });
    post({ type: "reduce", reduce: reduceMotion.matches });
    document.addEventListener("visibilitychange", () => post({ type: "visible", visible: !document.hidden }));

    return { size, scroll, field, masks, lens, lock, prepare, pinText, givePort };
  })();

  /* ---------- gaze: where the visitor is probably looking (gaze-worker.js + gaze.js) ----------
     The filter, its picture and the decision of when the tracker jumps all run in a worker. The page
     sends what only the page knows (layout, scroll, pointer, intent) and places two small elements
     when the worker says the estimate has jumped. Fine pointers only: on touch there is no evidence
     from the visitor, so no estimate is shown. */

  var gaze = null; // hoisted: the pointer handlers above refer to it
  if (window.Worker && "OffscreenCanvas" in window && matchMedia("(pointer: fine)").matches && !reduceMotion.matches) {
    const cloud = document.createElement("canvas");
    cloud.className = "gaze-cloud";
    cloud.setAttribute("aria-hidden", "true");
    document.body.prepend(cloud);
    cloud.width = innerWidth;
    cloud.height = innerHeight;
    const gw = new Worker("gaze-worker.js?v=20261013n35");
    const oc = cloud.transferControlToOffscreen();
    const inkNow = () => getComputedStyle(root).getPropertyValue("--ink").trim();
    gw.postMessage({ type: "init", canvas: oc, N: 600, pitch: 8, ink: inkNow(), dyn: /[?&]dyn(?:[=&]|$)/.test(location.search) }, [oc]);
    // the wall tells the gaze worker directly what moves on screen; the page never touches it (only
    // with ?dyn until the moving-content layer passes its certificate: off, the wall measures nothing)
    if (wallCtl && wallCtl.givePort && /[?&]dyn(?:[=&]|$)/.test(location.search)) {
      const ch = new MessageChannel();
      wallCtl.givePort(ch.port1);
      gw.postMessage({ type: "motionPort", port: ch.port2 }, [ch.port2]);
    }
    reduceMotion.addEventListener("change", () => {
      gw.postMessage({ type: "reduce", reduce: reduceMotion.matches });
    });

    // what the reading model and the label placement need: text blocks and their real line boxes
    const AOI = [
      [".name", 3.2, "shape"], [".caption", 1.4, "text"], [".t-name", 1.6, "text"], [".t-note", 0.7, "text"],
      ["h2", 2.2, "shape"], [".result-lead, .tally, .r-meta", 0.9, "text"], [".r-title", 1.3, "text"],
      [".close-links a, .source a", 1, "text"], [".list-note", 1.2, "text"], [".lock-say", 0.8, "text"],
    ];
    let textRects = [];
    let textLines = [];
    function layout() {
      const aois = [], lines = [];
      const view = { x: scrollX, y: scrollY, w: innerWidth, h: innerHeight };
      textRects = [];
      textLines = [];
      const range = document.createRange();
      for (const [sel, weight, kind] of AOI) {
        for (const el of document.querySelectorAll(sel)) {
          const r = el.getBoundingClientRect();
          if (r.width < 2 || r.height < 2) continue;
          const a = { x: r.left + scrollX, y: r.top + scrollY, w: r.width, h: r.height, weight, kind, lines: [] };
          if (sel !== ".lock-say" && sel !== ".name") textRects.push({ x: a.x, y: a.y, w: a.w, h: a.h });
          if (r.bottom < 0 || r.top > innerHeight) continue;
          if (kind === "text" || sel === "h2") {
            range.selectNodeContents(el);
            const fs = parseFloat(getComputedStyle(el).fontSize) || 16;
            for (const lr of range.getClientRects()) {
              if (lr.width < 4) continue;
              textLines.push({ x: lr.left + scrollX - 2, y: lr.top + scrollY - 2, w: lr.width + 4, h: lr.height + 4 });
              if (kind !== "text") continue;
              a.lines.push(lines.length);
              lines.push({ x: lr.left + scrollX, y: lr.top + scrollY + lr.height / 2, w: lr.width, ch: fs * 0.55, aoi: aois.length });
            }
          }
          aois.push(a);
        }
      }
      const nb = dots.bounds && dots.bounds();
      if (nb) textRects.push(nb);
      gw.postMessage({ type: "layout", aois, lines, textLines, view });
      // what the labels must clear changes only with the layout, so it is measured here, not per jump
      obsCache = obstacles();
      segCache = wireSegs();
    }

    // pointer and scroll are sent at most once per frame
    let pendingMove = null, pendingView = false, flushQueued = false;
    const flush = () => {
      flushQueued = false;
      if (pendingMove) { gw.postMessage({ type: "move", x: pendingMove.x, y: pendingMove.y }); pendingMove = null; }
      if (pendingView) { gw.postMessage({ type: "view", view: { x: scrollX, y: scrollY, w: innerWidth, h: innerHeight } }); pendingView = false; }
    };
    const queue = () => { if (!flushQueued) { flushQueued = true; requestAnimationFrame(flush); } };
    let layoutTimer = 0;
    addEventListener("scroll", () => {
      pendingView = true;
      queue();
      clearTimeout(layoutTimer);
      layoutTimer = setTimeout(layout, 140);
    }, { passive: true });
    addEventListener("resize", () => {
      gw.postMessage({ type: "size", w: innerWidth, h: innerHeight, pitch: wallPitch || 8 });
      clearTimeout(layoutTimer);
      layoutTimer = setTimeout(layout, 140);
    });
    addEventListener("pointerdown", (e) => gw.postMessage({ type: "click", x: e.clientX, y: e.clientY }), { passive: true });
    new MutationObserver(() => gw.postMessage({ type: "ink", ink: inkNow() })).observe(root, { attributes: true, attributeFilter: ["data-field"] });

    /* The scanpath. Each fixation the worker reports becomes a node, drawn the way the references
       track points: a hairline box (the 50% radius), a solid square whose size is how long the
       estimate has held there, and the node's real page position. Earlier fixations stay behind as
       ghosts that sink back with age, joined in order by the saccades between them. */
    const hit = (a, b) => a.x < b.x + b.w && a.x + a.w > b.x && a.y < b.y + b.h && a.y + a.h > b.y;
    const GHOSTS = 6;
    const AGE = [1, 0.7, 0.52, 0.38, 0.27, 0.18, 0.1];
    const path = tracker.querySelector(".gaze-path");
    const now = tracker.querySelector(".gaze-node.now");
    const nowFill = tracker.querySelector(".gaze-fill.now");
    const glow = tracker.querySelector(".gaze-glow");
    const gSay = tracker.querySelector(".gaze-say");
    const gXY = gSay.querySelector(".xy");
    const gPr = gSay.querySelector(".pr");
    let nodes = []; // oldest first: { x, y, el, say, sayRect, s, fill }
    let cur = null; // { x, y, size, r50, fill }
    let nowRect = null;
    let obsCache = null, segCache = null;
    let dwell = null;

    function obstacles() {
      const obs = textRects.slice();
      // never in the band directly above a heading, where a small label would read as its kicker
      for (const el of document.querySelectorAll("h2, .t-name, .r-title")) {
        const hr = el.getBoundingClientRect();
        obs.push({ x: hr.left + scrollX - 8, y: hr.top + scrollY - 48, w: hr.width + 16, h: 48 });
      }
      const lb = lockBox.getBoundingClientRect();
      obs.push({ x: lb.left + scrollX, y: lb.top + scrollY, w: lb.width, h: lb.height });
      const ls = lockSay.getBoundingClientRect();
      obs.push({ x: ls.left + scrollX - 4, y: ls.top + scrollY - 4, w: ls.width + 8, h: ls.height + 8 });
      // the rail is fixed to the screen, so it is wherever the screen is now
      for (const el of document.querySelectorAll(".rail a")) {
        const rr = el.getBoundingClientRect();
        if (rr.width) obs.push({ x: rr.left + scrollX, y: rr.top + scrollY, w: rr.width, h: rr.height });
      }
      return obs;
    }
    // every connector line counts too: no wire may run through a label
    const crossesSeg = (r, [x1, y1, x2, y2]) => {
      let t0 = 0, t1 = 1;
      const dx = x2 - x1, dy = y2 - y1;
      for (const [pp, qq] of [[-dx, x1 - r.x], [dx, r.x + r.w - x1], [-dy, y1 - r.y], [dy, r.y + r.h - y1]]) {
        if (pp === 0) { if (qq < 0) return false; continue; }
        const t = qq / pp;
        if (pp < 0) { if (t > t1) return false; if (t > t0) t0 = t; } else { if (t < t0) return false; if (t < t1) t1 = t; }
      }
      return true;
    };
    const wireSegs = () => [...wire.querySelectorAll("line")].map((l) => [+l.getAttribute("x1"), +l.getAttribute("y1"), +l.getAttribute("x2"), +l.getAttribute("y2")]);

    /* A label goes where it can be read: beside the node's square first, as the references print
       it, then around the box. Each spot must clear text, the name, the lock, its caption, every
       wire and every other label by 12px. If none is clear, the label is not shown. */
    function spotFor(x, y, s, fill, w, h, obs, segs, taken) {
      const bx = x - s / 2, by = y - s / 2;
      const spots = [
        [x + fill / 2 + 6, y - h / 2], [x + fill / 2 + 6, y + fill / 2 - h],
        [bx + s + 8, by - 4], [bx + s + 8, by + s - h + 4], [bx - w - 8, by - 4], [bx - w - 8, by + s - h + 4],
        [bx, by - h - 8], [bx, by + s + 8],
      ];
      const vx0 = scrollX, vx1 = scrollX + innerWidth;
      for (const [sx, sy] of spots) {
        const r = { x: sx - 12, y: sy - 12, w: w + 24, h: h + 24 };
        if (sx < vx0 + 4 || sx + w > vx1 - 4) continue;
        if (obs.some((o) => hit(r, o)) || taken.some((o) => hit(r, o)) || segs.some((sg) => crossesSeg(r, sg))) continue;
        // and within reach of the node it describes
        if (Math.hypot(sx + w / 2 - x, sy + h / 2 - y) > s / 2 + w / 2 + 40) continue;
        return { x: sx, y: sy, w, h };
      }
      return null;
    }

    function drawPath() {
      const pts = cur ? nodes.concat([cur]) : nodes.slice();
      const k = pts.length;
      let html = "";
      for (let i = 1; i < k; i++) {
        const a = pts[i - 1], b = pts[i];
        // a saccade is as bright as the older of its two fixations
        const op = AGE[Math.min(AGE.length - 1, k - i)];
        html += `<line x1="${Math.round(a.x)}" y1="${Math.round(a.y)}" x2="${Math.round(b.x)}" y2="${Math.round(b.y)}" opacity="${op}"></line>`;
      }
      path.innerHTML = html;
    }

    /* Every element of the scanpath is made once and reused: a jump only moves, resizes and fades
       them. Creating and removing a blended square per jump made Chrome rebuild its compositing
       layers and drop frames. */
    const slots = [];
    for (let i = 0; i < GHOSTS; i++) {
      const el = document.createElement("div");
      el.className = "gaze-node ghost";
      const fe = document.createElement("b");
      fe.className = "gaze-fill ghost";
      const say = document.createElement("span");
      say.className = "gaze-say ghost-say";
      for (const e of [el, fe, say]) { e.style.visibility = "hidden"; tracker.insertBefore(e, now); }
      slots.push({ el, fe, say });
    }
    const echo = gSay.cloneNode(true);
    echo.className = "gaze-say echo";
    echo.style.opacity = "0";
    tracker.insertBefore(echo, gSay.nextSibling);
    const echoXY = echo.querySelector(".xy"), echoPr = echo.querySelector(".pr");

    // the fixation that just ended becomes a ghost: frozen where it was, its square at the size
    // its dwell reached
    function leaveGhost() {
      if (!cur) return;
      const slot = nodes.length < GHOSTS ? slots.find((sl) => !nodes.some((n) => n.slot === sl)) : nodes.shift().slot;
      const { el, fe, say } = slot;
      el.style.width = el.style.height = `${cur.size}px`;
      el.style.transform = now.style.transform;
      el.style.borderColor = now.style.borderColor;
      el.style.visibility = "";
      fe.style.setProperty("--f", `${cur.fill}px`);
      fe.style.transform = nowFill.style.transform;
      fe.style.scale = getComputedStyle(nowFill).scale;
      fe.style.visibility = "";
      say.style.visibility = "hidden";
      if (nowRect) say.textContent = gXY.textContent;
      nodes.push({ x: cur.x, y: cur.y, slot, el, fe, say: nowRect ? say : null, sayRect: null, s: cur.size, fill: cur.fill });
    }

    function show(m) {
      leaveGhost();
      // the box is the fixation marker, as in any scanpath: it widens with the uncertainty but only
      // gently, so it stays a mark; the exact 50% radius is printed beside it
      const s = Math.round(Math.min(96, Math.max(36, 28 + m.r50 * 0.25)));
      const fill = Math.round(Math.min(34, s * 0.55));
      cur = { x: m.x, y: m.y, size: s, r50: m.r50, fill };
      // brightness is certainty: a tight box is near full ink, a wide one sinks toward the field
      now.style.borderColor = `color-mix(in oklab, var(--ink) ${Math.round(86 - 36 * (s - 36) / 60)}%, transparent)`;
      now.style.width = now.style.height = `${s}px`;
      now.style.transform = `translate(${Math.round(m.x - s / 2)}px, ${Math.round(m.y - s / 2)}px)`;
      nowFill.style.setProperty("--f", `${fill}px`);
      nowFill.style.transform = `translate(${Math.round(m.x - fill / 2)}px, ${Math.round(m.y - fill / 2)}px)`;
      glow.style.transform = `translate(${Math.round(m.x)}px, ${Math.round(m.y)}px)`;
      // the square starts small and grows in steps for as long as the fixation holds
      if (dwell) dwell.cancel();
      dwell = nowFill.animate([{ scale: 0.35 }, { scale: 1 }], { duration: 360, easing: "steps(4, end)", fill: "forwards" });

      // real numbers only: where the estimate is on the page, and how sure it is
      gXY.textContent = `x:${Math.round(m.x)} y:${Math.round(m.y)}`;
      gPr.textContent = `gaze, 50% within ${Math.round(m.r50)}px`;
      const obs = obsCache || (obsCache = obstacles());
      // the scanpath's own saccades count as wires too
      const segs = (segCache || (segCache = wireSegs())).slice();
      const pts = nodes.concat([cur]);
      for (let i = 1; i < pts.length; i++) segs.push([pts[i - 1].x, pts[i - 1].y, pts[i].x, pts[i].y]);
      const w = gSay.offsetWidth, h = gSay.offsetHeight || 28;
      nowRect = spotFor(m.x, m.y, s, fill, w, h, obs, segs, []);
      if (nowRect) {
        gSay.style.transform = `translate(${Math.round(nowRect.x)}px, ${Math.round(nowRect.y)}px)`;
        gSay.style.visibility = "";
        // the readout is printed twice for a moment, the copy offset and fading, as the trackers
        // in the references double their readouts when they jump
        echoXY.textContent = gXY.textContent;
        echoPr.textContent = gPr.textContent;
        echo.style.transform = gSay.style.transform;
        echo.animate([{ opacity: 0.45 }, { opacity: 0 }], { duration: 180, easing: "steps(2, end)", fill: "forwards" });
        gw.postMessage({ type: "label", rect: { x: nowRect.x - 6, y: nowRect.y - 6, w: nowRect.w + 12, h: nowRect.h + 12 } });
      } else {
        gSay.style.visibility = "hidden";
        gw.postMessage({ type: "label", rect: null });
      }

      // ghosts: older is fainter; each keeps its own coordinates only where they can be read
      const taken = nowRect ? [nowRect] : [];
      for (let i = nodes.length - 1; i >= 0; i--) {
        const n = nodes[i];
        const op = AGE[nodes.length - i];
        // a ghost's box and square sink together, never a square left without its box
        n.el.style.opacity = n.fe.style.opacity = Math.sqrt(op).toFixed(2);
        if (!n.say) continue;
        if (n.sayRect === null) {
          const sw = n.say.offsetWidth, sh = n.say.offsetHeight || 14;
          n.sayRect = spotFor(n.x, n.y, n.s, n.fill, sw, sh, obs, segs, taken) || false;
          if (n.sayRect) n.say.style.transform = `translate(${Math.round(n.sayRect.x)}px, ${Math.round(n.sayRect.y)}px)`;
        }
        const clear = n.sayRect && !taken.some((o) => hit(n.sayRect, o));
        n.say.style.visibility = clear ? "" : "hidden";
        n.say.style.opacity = op;
        if (clear) taken.push(n.sayRect);
      }
      drawPath();
      root.classList.add("gazing");
    }

    // a new layout makes the old positions meaningless: the path starts over
    function clearPath() {
      for (const sl of slots) sl.el.style.visibility = sl.fe.style.visibility = sl.say.style.visibility = "hidden";
      nodes = [];
      drawPath();
    }
    addEventListener("resize", clearPath);

    if (location.search.includes("debug")) window.__gazeWorker = gw; // tools/ read the change maps through it
    gw.onmessage = (e) => {
      if (e.data && e.data.type === "motionLog") { window.__motionLog = e.data.log; return; }
      if (window.__gazeWorker && e.data && e.data.type === "show") (window.__gazeShows = window.__gazeShows || []).push({ t: performance.now(), x: e.data.x, y: e.data.y, r50: e.data.r50 });
      const m = e.data;
      if (m.type === "show") show(m);
      // the worker says which model it runs: the learned one needs no saliency network, so the
      // network (and its 14 MB runtime, whose compile competes with the first seconds' frames) only
      // loads for the particle filter
      else if (m.type === "model" && !m.net) startNeuralWhenIdle();
    };

    gaze = {
      start: layout,
      onset: (box) => gw.postMessage({ type: "onset", box }),
      move: (x, y) => { pendingMove = { x, y }; queue(); },
      intent: (i) => gw.postMessage({ type: "intent", intent: i }),
      saliency: (m) => gw.postMessage({ type: "saliency", map: m.map, w: m.w, h: m.h, view: m.view }, [m.map.buffer]),
      relayout: () => { clearTimeout(layoutTimer); layoutTimer = setTimeout(layout, 60); },
    };
    lockListeners.push(gaze.relayout);

    /* The neural prior. Loaded only on desktop-class devices with data saving off, after the page
       is up and idle: the ONNX Runtime wasm (14 MB, about 2.4 MB with brotli) and the model
       (3.5 MB, 3.1 MB with brotli). Without it, the layout weights in gaze.js stand in. */
    function startNeuralWhenIdle() {
      const saveData = navigator.connection && navigator.connection.saveData;
      if ((navigator.hardwareConcurrency || 2) < 4 || saveData) return;
      const idle = window.requestIdleCallback || ((fn) => setTimeout(fn, 1500));
      idle(() => startNeural(), { timeout: 4000 });
    }

    function startNeural() {
      let worker;
      try {
        worker = new Worker("saliency-worker.js?v=20261013n35", { type: "module" });
      } catch (err) {
        return;
      }
      let ready = false;
      let timer = 0;
      const SW = 448, SH = 288;
      const pic = new OffscreenCanvas(SW, SH);
      const pc = pic.getContext("2d");
      const debug = location.search.includes("debug");
      worker.onmessage = (e) => {
        const m = e.data;
        if (m.type === "ready") { ready = true; shoot(); }
        else if (m.type === "map") {
          if (reduceMotion.matches) return;
          if (debug) window.__sal = { map: Array.from(m.map), w: m.w, h: m.h, pic: m.pic ? Array.from(m.pic) : null };
          root.dataset.saliency = `${Math.round(m.ms)}ms`;
          gaze.saliency(m);
        }
      };
      worker.postMessage({ type: "init", url: new URL("models/ui_saliency.onnx", location.href).href, debug });

      // a picture of what the visitor sees right now, as the network was trained on screenshots;
      // it travels to the worker as an ImageBitmap (no pixel readback on this thread)
      function shoot() {
        if (!ready || document.hidden || reduceMotion.matches) return;
        const cs = getComputedStyle(root);
        const sx = SW / innerWidth, sy = SH / innerHeight;
        const ox = scrollX, oy = scrollY;
        pc.setTransform(1, 0, 0, 1, 0, 0);
        pc.fillStyle = cs.getPropertyValue("--field").trim();
        pc.fillRect(0, 0, SW, SH);
        const ink = cs.getPropertyValue("--ink").trim();
        pc.setTransform(sx, 0, 0, sy, -ox * sx, -oy * sy);
        const m = dots.mask();
        const p = wallPitch || 8;
        if (m.grid) {
          pc.fillStyle = ink;
          pc.beginPath();
          const gd = m.grid;
          for (let r = 0; r < gd.rows; r++) {
            for (let c = 0; c < gd.cols; c++) {
              if (!gd.cells[r * gd.cols + c]) continue;
              const x = (gd.c0 + c + 0.5) * p, y = (gd.r0 + r + 0.5) * p;
              pc.moveTo(x + p * 0.42, y);
              pc.arc(x, y, p * 0.42, 0, Math.PI * 2);
            }
          }
          pc.fill();
        }
        pc.strokeStyle = ink;
        pc.lineWidth = 1;
        for (const el of document.querySelectorAll(".targets .target, .report")) {
          const r = el.getBoundingClientRect();
          pc.beginPath();
          pc.moveTo(r.left + ox, r.top + oy);
          pc.lineTo(r.right + ox, r.top + oy);
          pc.stroke();
        }
        if (current) {
          const b = boxFor(current);
          pc.strokeRect(b.x, b.y, b.w, b.h);
        }
        const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
        const range = document.createRange();
        const widths = [[50, "ultra-condensed"], [62.5, "extra-condensed"], [75, "condensed"], [87.5, "semi-condensed"], [100, "normal"], [112.5, "semi-expanded"], [125, "expanded"]];
        for (let n = walker.nextNode(); n; n = walker.nextNode()) {
          const el = n.parentElement;
          // everything a visitor can read, except the hidden h1 text (the wall draws the name),
          // the skip link and the gaze tracker's own label
          if (!el || !n.data.trim() || el.closest(".name, .skip, .gaze-say, script, style")) continue;
          const st = getComputedStyle(el);
          if (st.visibility === "hidden" || st.opacity === "0") continue;
          const fs = parseFloat(st.fontSize);
          pc.font = `${st.fontWeight} ${fs}px Archivo`;
          const pct = parseFloat(st.fontStretch) || 100;
          pc.fontStretch = widths.reduce((a, b) => (Math.abs(b[0] - pct) < Math.abs(a[0] - pct) ? b : a))[1];
          pc.letterSpacing = st.letterSpacing === "normal" ? "0px" : st.letterSpacing;
          pc.fillStyle = st.color;
          pc.textBaseline = "alphabetic";
          const re = /\S+/g;
          let mt;
          while ((mt = re.exec(n.data))) {
            range.setStart(n, mt.index);
            range.setEnd(n, mt.index + mt[0].length);
            const r = range.getBoundingClientRect();
            if (r.bottom < 0 || r.top > innerHeight || r.width === 0) continue;
            pc.fillText(mt[0], r.left + ox, r.top + oy + r.height * 0.78);
          }
        }
        const bitmap = pic.transferToImageBitmap();
        worker.postMessage({ type: "frame", bitmap, view: { x: ox, y: oy, w: innerWidth, h: innerHeight } }, [bitmap]);
      }
      const soon = () => { clearTimeout(timer); timer = setTimeout(shoot, 160); };
      addEventListener("scroll", soon, { passive: true });
      addEventListener("resize", soon);
      new MutationObserver(soon).observe(root, { attributes: true, attributeFilter: ["data-field"] });
      lockListeners.push(soon);
    }
  }

  /* ---------- start ---------- */

  function fragmentKey() {
    try { return decodeURIComponent(location.hash.slice(1)); }
    catch { return ""; }
  }

  function initialTarget() {
    const key = fragmentKey();
    return targets.find((t) => t.dataset.key === key) || targets[0];
  }

  function start() {
    builtFor = bodySize();
    tab.arrive(tab.palette());
    if (wallCtl) {
      wallCtl.size();
      wallCtl.field(false);
    }
    dots.build();
    if (wallCtl) wallCtl.masks();
    if (gaze) gaze.start();
    const first = initialTarget();
    current = null;
    lock(first);
    if (first.closest(".stage") === null) first.scrollIntoView({ block: "center" });
    settleUntil = performance.now() + 700;
    started = true;
    requestAnimationFrame(() => requestAnimationFrame(place));
  }

  addEventListener("hashchange", () => {
    const key = fragmentKey();
    const t = targets.find((el) => el.dataset.key === key);
    if (t) {
      t.scrollIntoView({ block: "center" });
      lock(t);
    }
  });

  let resizeTimer = 0;
  // the observer reports the body's size once when it starts; rebuilding then repeated the startup's
  // own work, so only a real change of size rebuilds
  let builtFor = null;
  const bodySize = () => `${document.body.clientWidth}x${document.body.scrollHeight}|${innerWidth}x${innerHeight}`;
  new ResizeObserver(() => {
    clearTimeout(resizeTimer);
    resizeTimer = setTimeout(() => {
      const now = bodySize();
      if (now === builtFor) return;
      builtFor = now;
      if (wallCtl) wallCtl.size();
      dots.build();
      if (wallCtl) wallCtl.masks();
      place();
    }, 80);
  }).observe(document.body);

  document.fonts.load('900 100px "Archivo"').then(start, start);
})();
