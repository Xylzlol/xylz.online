/* The LED wall off the main thread: the page posts state, this worker draws and reports
   which rows each committed frame shows. Pours are computed on a second thread (pour-worker.js), so
   drawing never waits for one; it gets the same grid, mask and scroll state, and answers pour jobs. */
importScripts("wall.js?v=20261013n39");

const schedule = typeof requestAnimationFrame === "function"
  ? (fn) => requestAnimationFrame(fn)
  : (fn) => setTimeout(() => fn(performance.now()), 16);

let pour = null;
try {
  pour = new Worker("pour-worker.js?v=20261013n39");
} catch (e) {
  pour = null; // no nested workers: pours are computed here, as before
}
const wall = createWall(schedule, (m, transfer) => postMessage(m, transfer || []), pour ? (job) => pour.postMessage(job) : null);
if (pour) pour.onmessage = (e) => wall.handle(e.data);
const MIRROR = new Set(["resize", "masks", "scroll", "reduce"]);
onmessage = (e) => {
  const m = e.data;
  if (pour && MIRROR.has(m.type)) pour.postMessage(m);
  wall.handle(m);
};
