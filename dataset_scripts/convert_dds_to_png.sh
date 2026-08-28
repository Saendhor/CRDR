#!/usr/bin/env bash
# convert_dds_to_png.sh has to be placed in "all-in-one/" to create a new folder "png/" where all .dds are converted to .png
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

OUT_DIR="png"
mkdir -p "$OUT_DIR"

FAILED=0

for dds in *.dds; do
    [ -e "$dds" ] || continue
    out="${OUT_DIR}/${dds%.dds}.png"
    [ -f "$out" ] && continue
    if ffmpeg -y -loglevel error -i "$dds" "$out"; then
        echo "OK: $dds -> $out"
    else
        echo "FAILED: $dds"
        FAILED=$((FAILED + 1))
    fi
done

echo "Done. $(find "$OUT_DIR" -name '*.png' | wc -l) images converted, $FAILED failed."
