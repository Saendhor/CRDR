#!/usr/bin/env bash
# convert_png_to_dds.sh converts all .png files to .dds using ImageMagick
# Usage: ./convert_png_to_dds.sh [input_folder] [output_folder] [compression] [quality] [mipmaps]
# Defaults: input_folder = current dir, output_folder = ./dds, compression = DXT5, quality = 100, mipmaps = 0
# Compression options: DXT1 (no alpha), DXT3 (1-bit alpha), DXT5 (smooth alpha), none (uncompressed)
# Quality: 1-100, higher = better quality (100 = best). Note: DDS is fixed-rate,
#   so quality does not change bpp (DXT1=4bpp, DXT5=8bpp).
# Mipmaps: 0 = disabled (lowest bpp, recommended for bpp comparison), 1 = enabled (+~33% size).
#   To match CRDR bpp as closely as possible use DXT1 + mipmaps=0.
set -euo pipefail

INPUT_DIR="${1:-.}"
OUT_DIR="${2:-dds}"
COMPRESSION="${3:-DXT5}"
QUALITY="${4:-100}"
MIPMAPS="${5:-0}"

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
    out="$OUT_DIR/${name}.dds"
    if [ -f "$out" ]; then
        echo "SKIP: $filename (already exists)"
        continue
    fi
    if magick "$png" -type TrueColor -quality "$QUALITY" -define "dds:compression=$COMPRESSION" -define "dds:mipmaps=$MIPMAPS" "$out"; then
        echo "OK: $filename -> $out"
        COUNT=$((COUNT + 1))
    else
        echo "FAILED: $filename"
        FAILED=$((FAILED + 1))
    fi
done

echo "Done. $COUNT images converted, $FAILED failed. Output: $OUT_DIR/"
