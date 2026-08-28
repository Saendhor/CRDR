#!/bin/bash
# collect_dds.sh takes all the .dds files contained in each subfolder and copies them to "all-in-one/"
set -euo pipefail

DEST="all-in-one"
mkdir -p "$DEST"

count=0
for dir in */; do
    [ -d "$dir" ] || continue
    shopt -s nullglob
    for file in "$dir"*.dds "$dir"**/*.dds; do
        [ -f "$file" ] || continue
        name="${file##*/}"
        if [ -e "$DEST/$name" ]; then
            name="${dir%/}_${name}"
        fi
        cp -n "$file" "$DEST/$name"
        count=$((count + 1))
    done
done

echo "Copied $count .dds files to $DEST/"
