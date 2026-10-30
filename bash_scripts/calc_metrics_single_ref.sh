#!/bin/bash

# Script to calculate PSNR, LPIPS, DISTS, VMAF, FID, and BPP metrics for a folder
# of PNG images evaluated against a single reference (source) PNG image
# Usage: ./calc_metrics_single_ref.sh <folder_path> <source_image> [options]

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON_SCRIPT="${SCRIPT_DIR}/calc_metrics_single_ref.py"

# Check if Python script exists
if [ ! -f "$PYTHON_SCRIPT" ]; then
    echo "Error: Python script not found at $PYTHON_SCRIPT"
    exit 1
fi

# Parse arguments
FOLDER_PATH=""
SOURCE_IMAGE=""
EXTRA_ARGS=()

while [[ $# -gt 0 ]]; do
    case $1 in
        --max-size)
            if [ -z "$2" ]; then
                echo "Error: --max-size requires a value"
                exit 1
            fi
            EXTRA_ARGS+=("--max-size" "$2")
            shift 2
            ;;
        --skip-fid|--skip-bpp|--skip-lpips|--skip-dists|--skip-psnr|--skip-vmaf)
            EXTRA_ARGS+=("$1")
            shift
            ;;
        *)
            if [ -z "$FOLDER_PATH" ]; then
                FOLDER_PATH="$1"
            elif [ -z "$SOURCE_IMAGE" ]; then
                SOURCE_IMAGE="$1"
            else
                echo "Error: Unknown argument $1"
                exit 1
            fi
            shift
            ;;
    esac
done

# Validate arguments
if [ -z "$FOLDER_PATH" ] || [ -z "$SOURCE_IMAGE" ]; then
    echo "Usage: $0 <folder_path> <source_image> [--max-size N] [--skip-fid] [--skip-bpp] ..."
    echo ""
    echo "Arguments:"
    echo "  folder_path      Path to folder containing PNG images to evaluate"
    echo "  source_image     Path to the reference PNG image (compared against every image)"
    echo ""
    echo "Options:"
    echo "  --max-size N     Maximum image dimension (for memory efficiency)"
    echo "  --skip-psnr      Skip PSNR calculation"
    echo "  --skip-lpips     Skip LPIPS calculation"
    echo "  --skip-dists     Skip DISTS calculation"
    echo "  --skip-vmaf      Skip VMAF calculation"
    echo "  --skip-fid       Skip FID calculation"
    echo "  --skip-bpp       Skip BPP calculation"
    echo ""
    echo "Examples:"
    echo "  $0 /path/to/decoded/images /path/to/source.png"
    echo "  $0 /path/to/decoded/images /path/to/source.png --skip-fid"
    exit 1
fi

# Check if folder exists
if [ ! -d "$FOLDER_PATH" ]; then
    echo "Error: Folder not found: $FOLDER_PATH"
    exit 1
fi

# Check reference image
if [ ! -f "$SOURCE_IMAGE" ]; then
    echo "Error: Reference image not found: $SOURCE_IMAGE"
    exit 1
fi

case "$SOURCE_IMAGE" in
    *.png|*.PNG) ;;
    *)
        echo "Error: Reference image must be a .png file: $SOURCE_IMAGE"
        exit 1
        ;;
esac

# Check if folder contains PNG images (the reference image is ignored if it is inside)
PNG_COUNT=$(find "$FOLDER_PATH" -maxdepth 1 -name "*.png" -type f ! -samefile "$SOURCE_IMAGE" | wc -l)
if [ "$PNG_COUNT" -eq 0 ]; then
    echo "Error: No PNG images found in $FOLDER_PATH (excluding the reference image)"
    exit 1
fi

echo "Found $PNG_COUNT PNG images in $FOLDER_PATH"

# Resolve paths to absolute ones, since the Python script runs from the repo root
SOURCE_IMAGE="$(cd "$(dirname "$SOURCE_IMAGE")" && pwd)/$(basename "$SOURCE_IMAGE")"
FOLDER_PATH="$(cd "$FOLDER_PATH" && pwd)"

echo "Reference image: $SOURCE_IMAGE"

# Note if the reference image is inside the evaluated folder
if [ "$(dirname "$SOURCE_IMAGE")" = "$FOLDER_PATH" ]; then
    echo "Note: reference image $(basename "$SOURCE_IMAGE") is inside the evaluated folder and will be ignored"
fi

# Run Python script
echo ""
echo "Calculating metrics..."
echo "====================="

cd "$SCRIPT_DIR/.."
uv run python "$PYTHON_SCRIPT" --folder "$FOLDER_PATH" --source "$SOURCE_IMAGE" "${EXTRA_ARGS[@]}"
