#!/bin/bash

if [ -z "$1" ]; then
    echo "Usage: $0 <folder_with_tga_files>"
    exit 1
fi

INPUT_DIR="$1"
OUTPUT_DIR="converted"

if [ ! -d "$INPUT_DIR" ]; then
    echo "Error: '$INPUT_DIR' is not a valid directory"
    exit 1
fi

mkdir -p "$OUTPUT_DIR"

for f in "$INPUT_DIR"/*.tga "$INPUT_DIR"/*.TGA; do
    [ -e "$f" ] || continue
    filename=$(basename "$f")
    name="${filename%.*}"
    convert "$f" "$OUTPUT_DIR/$name.png"
    echo "Converted: $filename -> $OUTPUT_DIR/$name.png"
done
