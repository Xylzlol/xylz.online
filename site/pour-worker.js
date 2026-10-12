/* Pours, computed off the drawing thread. A canvas-less instance of the same wall code holds the
   grid, the name's mask and the scroll position (mirrored from wall-worker.js) and answers
   "pourJob" messages with the arrival order of every cell. */
importScripts("wall.js?v=20261013n35");
const wall = createWall(() => {}, (m, transfer) => postMessage(m, transfer || []));
onmessage = (e) => wall.handle(e.data);
