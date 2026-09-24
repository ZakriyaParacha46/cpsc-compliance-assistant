#!/usr/bin/env bash
# mkgif.sh <frames-dir> <out.gif> <seconds-per-step> <seconds-on-last>
set -euo pipefail
dir="$1"; out="$2"; per="$3"; last="$4"
list="$dir/list.txt"; : > "$list"
frames=("$dir"/*.png)
for f in "${frames[@]}"; do echo "file '$(basename "$f")'" >> "$list"; echo "duration $per" >> "$list"; done
sed -i '' '$d' "$list"; echo "duration $last" >> "$list"; echo "file '$(basename "${frames[${#frames[@]}-1]}")'" >> "$list"
ffmpeg -v error -y -f concat -safe 0 -i "$list" -vf "palettegen=max_colors=96:stats_mode=full" "$dir/palette.png"
ffmpeg -v error -y -f concat -safe 0 -i "$list" -i "$dir/palette.png" -lavfi "[0:v][1:v]paletteuse=dither=none" -fps_mode vfr -loop 0 "$out"
echo "$out $(stat -f%z "$out") bytes"
