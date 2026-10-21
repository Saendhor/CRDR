#!/usr/bin/env bash
# convert_jpg_to_png.sh converts all .jpg/.jpeg files to .png using ImageMagick
# Usage: ./convert_jpg_to_png.sh [input_folder] [output_folder]
# Defaults: input_folder = current dir, output_folder = ./png
set -euo pipefail

INPUT_DIR="${1:-.}"
OUT_DIR="${2:-png}"

if [ ! -d "$INPUT_DIR" ]; then
    echo "Error: '$INPUT_DIR' is not a valid directory"
    exit 1
fi

mkdir -p "$OUT_DIR"

FAILED=0
COUNT=0

shopt -s nullglob
for jpg in "$INPUT_DIR"/*.jpg "$INPUT_DIR"/*.JPG "$INPUT_DIR"/*.jpeg "$INPUT_DIR"/*.JPEG; do
    [ -e "$jpg" ] || continue
    filename=$(basename "$jpg")
    name="${filename%.*}"
    out="$OUT_DIR/${name}.png"
    if [ -f "$out" ]; then
        echo "SKIP: $filename (already exists)"
        continue
    fi
    if magick "$jpg" "$out"; then
        echo "OK: $filename -> $out"
        COUNT=$((COUNT + 1))
    else
        echo "FAILED: $filename"
        FAILED=$((FAILED + 1))
    fi
done

echo "Done. $COUNT images converted, $FAILED failed. Output: $OUT_DIR/"
