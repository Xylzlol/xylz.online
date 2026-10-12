#!/bin/sh
# A/B of the wall: the same scenario suite on the old wall.js (port 8766) and the new (8765),
# alternated so whatever else the machine is doing falls on both alike.
# Usage: ab_frames.sh out.txt [extra frames_test args]
out=$1; shift
cd "$(dirname "$0")/.."
: > "$out"
for mode in --gpu --sw; do
  for rep in 1 2; do
    for side in A B; do
      port=8766; [ $side = B ] && port=8765
      echo "=== $mode rep $rep $side ($port)" >> "$out"
      python tools/frames_test.py $mode --headless --noleak --url "http://localhost:$port/?debug" "$@" 2>&1 | grep -v "^ *LoAF" | sed -n '1,16p' >> "$out"
    done
  done
done
echo "=== done" >> "$out"
