#!/usr/bin/env bash
# eval_bpp_folder.sh evaluates bits-per-pixel (bpp) for all images in a folder
# using ImageMagick. Supports .png, .jpg/.jpeg and .dds (case-insensitive).
# Usage: ./eval_bpp_folder.sh [input_folder] [output_csv]
# Defaults: input_folder = current dir, output_csv = ./bpp_results.csv
# Formula per image: bpp = (file_bytes * 8) / (width * height)
#   - file_bytes: on-disk size via stat (full file, DDS header included)
#   - width/height: via ImageMagick identify
set -euo pipefail

INPUT_DIR="${1:-.}"
OUTPUT="${2:-bpp_results.csv}"

if [ ! -d "$INPUT_DIR" ]; then
    echo "Error: '$INPUT_DIR' is not a valid directory" >&2
    exit 1
fi

# Prefer IM7 'magick identify', fall back to standalone 'identify' (IM6).
if command -v magick >/dev/null 2>&1; then
    IDENTIFY=(magick identify)
elif command -v identify >/dev/null 2>&1; then
    IDENTIFY=(identify)
else
    echo "Error: ImageMagick not found (need 'magick' or 'identify')" >&2
    exit 1
fi

shopt -s nullglob nocaseglob

files=()
for ext in png jpg jpeg dds; do
    for f in "$INPUT_DIR"/*."$ext"; do
        [ -f "$f" ] || continue
        files+=("$f")
    done
done

if [ "${#files[@]}" -eq 0 ]; then
    echo "No .png/.jpg/.jpeg/.dds images found in '$INPUT_DIR'" >&2
    exit 1
fi

echo "filename;width;height;bytes;bpp" > "$OUTPUT"

count=0
failed=0
sum_bpp="0"
min_bpp=""
max_bpp=""
total_bytes=0

for img in "${files[@]}"; do
    filename=$(basename "$img")

    if ! bytes=$(stat -c%s "$img" 2>/dev/null); then
        echo "WARN: cannot stat '$filename', skipping" >&2
        failed=$((failed + 1))
        continue
    fi

    if ! dims=$("${IDENTIFY[@]}" -format "%w %h" "$img" 2>/dev/null); then
        echo "WARN: identify failed for '$filename', skipping" >&2
        failed=$((failed + 1))
        continue
    fi
    width=$(echo "$dims" | awk '{print $1}')
    height=$(echo "$dims" | awk '{print $2}')

    if ! [[ "$width" =~ ^[0-9]+$ && "$height" =~ ^[0-9]+$ ]] || [ "$width" -eq 0 ] || [ "$height" -eq 0 ]; then
        echo "WARN: invalid dimensions for '$filename' ('$dims'), skipping" >&2
        failed=$((failed + 1))
        continue
    fi

    pixels=$((width * height))
    bpp=$(echo "$bytes $pixels" | awk '{printf "%.6f", ($1 * 8) / $2}')

    echo "$filename;$width;$height;$bytes;$bpp" >> "$OUTPUT"

    sum_bpp=$(echo "$sum_bpp $bpp" | awk '{printf "%.6f", $1 + $2}')
    if [ -z "$min_bpp" ] || [ "$(echo "$bpp $min_bpp" | awk '{print ($1 < $2)}')" -eq 1 ]; then
        min_bpp="$bpp"
    fi
    if [ -z "$max_bpp" ] || [ "$(echo "$bpp $max_bpp" | awk '{print ($1 > $2)}')" -eq 1 ]; then
        max_bpp="$bpp"
    fi
    total_bytes=$((total_bytes + bytes))
    count=$((count + 1))
done

shopt -u nocaseglob

if [ "$count" -eq 0 ]; then
    echo "No readable images (all ${failed} failed)." >&2
    exit 1
fi

mean_bpp=$(echo "$sum_bpp $count" | awk '{printf "%.6f", $1 / $2}')

{
    echo ""
    echo "count;$count"
    echo "total_bytes;$total_bytes"
    echo "mean_bpp;$mean_bpp"
    echo "min_bpp;$min_bpp"
    echo "max_bpp;$max_bpp"
} >> "$OUTPUT"

echo ""
echo "Evaluated $count images ($failed failed) in '$INPUT_DIR':"
echo "  Total bytes: $total_bytes"
echo "  Mean BPP:    $mean_bpp"
echo "  Min BPP:     $min_bpp"
echo "  Max BPP:     $max_bpp"
echo "Results saved to $OUTPUT"
