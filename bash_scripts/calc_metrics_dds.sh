#!/bin/bash

# Script to calculate PSNR, LPIPS, DISTS, FID, and BPP metrics for a folder of DDS images (BC7)
# Usage: ./calc_metrics_dds.sh <folder_path> [--ref <reference_folder>]

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON_SCRIPT="${SCRIPT_DIR}/calc_metrics_dds.py"

# Check if Python script exists
if [ ! -f "$PYTHON_SCRIPT" ]; then
    echo "Error: Python script not found at $PYTHON_SCRIPT"
    exit 1
fi

# Parse arguments
FOLDER_PATH=""
REF_FOLDER=""

while [[ $# -gt 0 ]]; do
    case $1 in
        --ref)
            REF_FOLDER="$2"
            shift 2
            ;;
        *)
            if [ -z "$FOLDER_PATH" ]; then
                FOLDER_PATH="$1"
            else
                echo "Error: Unknown argument $1"
                exit 1
            fi
            shift
            ;;
    esac
done

# Validate folder path
if [ -z "$FOLDER_PATH" ]; then
    echo "Usage: $0 <folder_path> [--ref <reference_folder>]"
    echo ""
    echo "Arguments:"
    echo "  folder_path      Path to folder containing DDS (BC7) images to evaluate"
    echo "  --ref             Path to reference folder (DDS/PNG/JPG; required for PSNR, LPIPS, DISTS)"
    echo ""
    echo "Examples:"
    echo "  $0 /path/to/decoded/images --ref /path/to/original/images"
    echo "  $0 /path/to/folder  # Only calculates FID against itself"
    exit 1
fi

# Check if folder exists
if [ ! -d "$FOLDER_PATH" ]; then
    echo "Error: Folder not found: $FOLDER_PATH"
    exit 1
fi

# Check if folder contains DDS images
DDS_COUNT=$(find "$FOLDER_PATH" -maxdepth 1 -iname "*.dds" -type f | wc -l)
if [ "$DDS_COUNT" -eq 0 ]; then
    echo "Error: No DDS images found in $FOLDER_PATH"
    exit 1
fi

echo "Found $DDS_COUNT DDS images in $FOLDER_PATH"

# Check reference folder if provided
if [ -n "$REF_FOLDER" ]; then
    if [ ! -d "$REF_FOLDER" ]; then
        echo "Error: Reference folder not found: $REF_FOLDER"
        exit 1
    fi
    
    REF_IMAGE_COUNT=$(find "$REF_FOLDER" -maxdepth 1 -type f \( -iname "*.dds" -o -iname "*.png" -o -iname "*.jpg" -o -iname "*.jpeg" \) | wc -l)
    if [ "$REF_IMAGE_COUNT" -eq 0 ]; then
        echo "Error: No images found in reference folder: $REF_FOLDER"
        exit 1
    fi
    
    echo "Found $REF_IMAGE_COUNT images in reference folder: $REF_FOLDER"
fi

# Run Python script
echo ""
echo "Calculating metrics..."
echo "====================="

cd "$SCRIPT_DIR/.."
uv run --with texture2ddecoder python "$PYTHON_SCRIPT" --folder "$FOLDER_PATH" ${REF_FOLDER:+--ref "$REF_FOLDER"}
