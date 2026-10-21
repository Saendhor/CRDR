#!/usr/bin/env bash
# convert_dds_to_png.sh converts all .dds files to .png using ImageMagick
# Usage: ./convert_dds_to_png.sh [input_folder] [output_folder]
# Defaults: input_folder = current dir, output_folder = ./png
set -euo pipefail

INPUT_DIR="${1:-.}"
OUT_DIR="${2:-png}"

if [ ! -d "$INPUT_DIR" ]; then
    echo "Error: '$INPUT_DIR' is not a valid directory"
    exit 1
fi

# Read the DDS compression format (FourCC) from the file header.
# FourCC is at file offset 84 (4-byte magic + header offset 80).
# For DX10 extended headers, dxgiFormat is at file offset 132 (128 + 4).
get_dds_format() {
    local file="$1"
    # Read 4 bytes at offset 84 as hex, then convert to ASCII
    local hex
    hex=$(od -A n -t x1 -j 84 -N 4 "$file" 2>/dev/null | tr -d ' \n')
    local fourcc
    fourcc=$(printf "\\x${hex:0:2}\\x${hex:2:2}\\x${hex:4:2}\\x${hex:6:2}")

    if [ "$fourcc" = "DX10" ]; then
        # DX10 extended header: dxgiFormat is a UINT32 at file offset 132
        local dxgi
        dxgi=$(od -A n -t u4 -j 132 -N 4 "$file" 2>/dev/null | tr -d ' ')
        case "$dxgi" in
            71)  echo "BC1 (DX10)" ;;
            74)  echo "BC2 (DX10)" ;;
            77)  echo "BC3 (DX10)" ;;
            80)  echo "BC4 (DX10)" ;;
            83)  echo "BC5 (DX10)" ;;
            95)  echo "BC6H (DX10)" ;;
            98)  echo "BC7 (DX10)" ;;
            *)   echo "DX10 (dxgi=$dxgi)" ;;
        esac
    else
        case "$fourcc" in
            DXT1) echo "DXT1 (BC1)" ;;
            DXT3) echo "DXT3 (BC2)" ;;
            DXT5) echo "DXT5 (BC3)" ;;
            BC4U) echo "BC4 (ATI1)" ;;
            BC4S) echo "BC4S (ATI1 signed)" ;;
            BC5U) echo "BC5 (ATI2)" ;;
            BC5S) echo "BC5S (ATI2 signed)" ;;
            *)    echo "Unknown (hex: $hex)" ;;
        esac
    fi
}

cd "$INPUT_DIR"
mkdir -p "$OUT_DIR"

FAILED=0

shopt -s nullglob
for dds in *.dds *.DDS; do
    [ -e "$dds" ] || continue
    out="${OUT_DIR}/${dds%.dds}.png"
    [ -f "$out" ] && continue
    fmt=$(get_dds_format "$dds")
    if magick "$dds" -type TrueColor "$out"; then
        echo "OK: $dds [$fmt] -> $out"
    else
        echo "FAILED: $dds [$fmt]"
        FAILED=$((FAILED + 1))
    fi
done

echo "Done. $(find "$OUT_DIR" -name '*.png' | wc -l) images converted, $FAILED failed."
