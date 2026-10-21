#!/usr/bin/env bash
# convert_png_to_jpg.sh converts all .png files to .jpg using ImageMagick
# Usage: ./convert_png_to_jpg.sh [input_folder] [output_folder] [quality]
# Defaults: input_folder = current dir, output_folder = ./jpg, quality = 92
# Notes: JPG has no alpha channel, so transparency is flattened onto
#   a white background (-background white -alpha remove -alpha off).
#   Quality: 1-100, higher = better quality / larger files. 92 is a good default.
set -euo pipefail

INPUT_DIR="${1:-.}"
OUT_DIR="${2:-jpg}"
QUALITY="${3:-92}"

if [ ! -d "$INPUT_DIR" ]; then
    echo "Error: '$INPUT_DIR' is not a valid directory"
    exit 1
fi

mkdir -p "$OUT_DIR"

FAILED=0
COUNT=0

shopt -s nullglob
for png in "$INPUT_DIR"/*.png "$INPUT_DIR"/*.PNG; do
    [ -e "$png" ] || continue
    filename=$(basename "$png")
    name="${filename%.*}"
    out="$OUT_DIR/${name}.jpg"
    if [ -f "$out" ]; then
        echo "SKIP: $filename (already exists)"
        continue
    fi
    if magick "$png" -background white -alpha remove -alpha off -quality "$QUALITY" "$out"; then
        echo "OK: $filename -> $out"
        COUNT=$((COUNT + 1))
    else
        echo "FAILED: $filename"
        FAILED=$((FAILED + 1))
    fi
done

echo "Done. $COUNT images converted, $FAILED failed. Output: $OUT_DIR/"
