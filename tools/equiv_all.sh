#!/bin/sh
# Every recorded session through the full computation (A, default ml/runs/wall_ref.js) and the current
# wall.js (B), at 60 and 540 Hz, and B with the fluid margins never or only partly available.
# One line per run, appended to ml/runs/equiv.log as it finishes.
cd "$(dirname "$0")/.."
A=${1:-ml/runs/wall_ref.js}
: > ml/runs/equiv.log
for rec in ml/runs/wall_rec.json ml/runs/wall_rec_stress.json; do
  for v in ml/runs/wall_new.js ml/runs/wall_nomargin.js ml/runs/wall_somemargin.js; do
    for hz in 60 540; do
      [ "$v" != ml/runs/wall_new.js ] && [ $hz = 540 ] && continue
      r=$(node --max-old-space-size=8000 tools/render_equiv.mjs "$A" "$v" "$rec" $hz 2>&1 | grep -E "Hz:|IDENTICAL|DIFFERENT|first difference|Error" | sed 's/render time.*x) //' | tr '\n' ' ')
      echo "$(basename $rec) $(basename $v) $hz Hz: $r" >> ml/runs/equiv.log
    done
  done
done
echo "done" >> ml/runs/equiv.log
