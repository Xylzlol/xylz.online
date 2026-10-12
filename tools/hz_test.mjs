// The fluid must move the same at any refresh rate: stir it once, advance one second of real time at
// 60, 144 and 540 Hz, compare the displacement field and how long it stays active.
import fs from "node:fs";
import vm from "node:vm";
import path from "node:path";
import { fileURLToPath } from "node:url";
const here = path.dirname(fileURLToPath(import.meta.url));
const src = fs.readFileSync(path.join(here, "..", "site", "wall.js"), "utf8");
function run(hz) {
  const sb = { self: {}, performance: { now: () => 0 }, console };
  vm.createContext(sb);
  vm.runInContext(src.replace("  function createWall(", "  self.__f = { createFluid, fluidSplat, fluidAdvance };\n  function createWall("), sb);
  const { createFluid, fluidSplat, fluidAdvance } = sb.self.__f;
  const F = createFluid(90, 60);
  fluidSplat(F, 40, 30, 1.2, 0.6, 3.5);
  const dt = 1000 / hz;
  let t = 0, activeFor = null;
  const snaps = {};
  while (t < 3000) {
    fluidAdvance(F, 16, dt);
    t += dt;
    for (const s of [250, 500, 1000]) if (snaps[s] === undefined && t >= s) snaps[s] = Math.hypot(...[...F.dx].slice(2690, 2700));
    if (!F.active && activeFor === null) activeFor = t;
  }
  return { hz, activeForMs: Math.round(activeFor), disp250: snaps[250].toFixed(4), disp500: snaps[500].toFixed(4), disp1000: snaps[1000].toFixed(4) };
}
for (const hz of [60, 144, 540]) console.log(JSON.stringify(run(hz)));
