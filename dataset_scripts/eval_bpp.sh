#!/bin/bash

if [ -z "$1" ] || [ -z "$2" ]; then
    echo "Usage: $0 <original_folder> <compressed_folder>"
    exit 1
fi

original_folder="$1"
compressed_folder="$2"

if [ ! -d "$original_folder" ]; then
    echo "Error: '$original_folder' is not a directory"
    exit 1
fi

if [ ! -d "$compressed_folder" ]; then
    echo "Error: '$compressed_folder' is not a directory"
    exit 1
fi

output="output.txt"

echo "filename;orig_width;orig_height;orig_bytes;orig_bpp;comp_bytes;comp_bpp;ratio" > "$output"

sum_orig_bpp=0
sum_comp_bpp=0
sum_ratio=0
count=0

for img in "$original_folder"/*.png; do
    [ -f "$img" ] || continue

    filename=$(basename "$img")
    comp_img="$compressed_folder/$filename"

    if [ ! -f "$comp_img" ]; then
        echo "Warning: '$filename' not found in compressed folder, skipping"
        continue
    fi

    orig_size=$(stat --format="%s" "$img")
    comp_size=$(stat --format="%s" "$comp_img")
    dims=$(identify -format "%w %h" "$img")
    width=$(echo "$dims" | awk '{print $1}')
    height=$(echo "$dims" | awk '{print $2}')
    pixels=$((width * height))

    orig_bpp=$(echo "$orig_size $pixels" | awk '{printf "%.6f", ($1 * 8) / $2}')
    comp_bpp=$(echo "$comp_size $pixels" | awk '{printf "%.6f", ($1 * 8) / $2}')
    ratio=$(echo "$orig_bpp $comp_bpp" | awk '{if ($2 > 0) printf "%.4f", $1 / $2; else print "inf"}')

    echo "$filename;$width;$height;$orig_size;$orig_bpp;$comp_size;$comp_bpp;$ratio" >> "$output"

    sum_orig_bpp=$(echo "$sum_orig_bpp $orig_bpp" | awk '{printf "%.6f", $1 + $2}')
    sum_comp_bpp=$(echo "$sum_comp_bpp $comp_bpp" | awk '{printf "%.6f", $1 + $2}')
    sum_ratio=$(echo "$sum_ratio $ratio" | awk '{printf "%.6f", $1 + $2}')
    count=$((count + 1))
done

if [ "$count" -gt 0 ]; then
    mean_orig_bpp=$(echo "$sum_orig_bpp $count" | awk '{printf "%.6f", $1 / $2}')
    mean_comp_bpp=$(echo "$sum_comp_bpp $count" | awk '{printf "%.6f", $1 / $2}')
    mean_ratio=$(echo "$sum_ratio $count" | awk '{printf "%.4f", $1 / $2}')

    echo "" >> "$output"
    echo "mean_orig_bpp;$mean_orig_bpp" >> "$output"
    echo "mean_comp_bpp;$mean_comp_bpp" >> "$output"
    echo "mean_compression_ratio;$mean_ratio" >> "$output"

    echo ""
    echo "Summary:"
    echo "  Original mean BPP:   $mean_orig_bpp"
    echo "  Compressed mean BPP: $mean_comp_bpp"
    echo "  Compression ratio:   ${mean_ratio}x (higher = more compression)"
fi

echo "Results saved to $output"
