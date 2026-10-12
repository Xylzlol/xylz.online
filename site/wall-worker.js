/* The LED wall off the main thread: the page posts state, this worker draws and reports
   which rows each committed frame shows, so the page can move the canvas to match. */
importScripts("wall.js?v=20261013m3");

const schedule = typeof requestAnimationFrame === "function"
  ? (fn) => requestAnimationFrame(fn)
  : (fn) => setTimeout(() => fn(performance.now()), 16);

const wall = createWall(schedule, (m) => postMessage(m));
onmessage = (e) => wall.handle(e.data);
