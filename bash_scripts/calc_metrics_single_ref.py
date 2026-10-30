#!/usr/bin/env python3

"""
Calculate image quality metrics: PSNR, LPIPS, DISTS, VMAF, FID, and BPP for a
folder of PNG images evaluated against a single reference PNG image.

The metric implementations are imported unchanged from calc_metrics.py.

Usage:
    python calc_metrics_single_ref.py --folder <folder_path> --source <source.png>
"""

import argparse
import shutil
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from typing import List

import numpy as np
import torch
from PIL import Image

# Reuse the exact metric implementations from calc_metrics.py (read-only import)
sys.path.insert(0, str(Path(__file__).resolve().parent))
from calc_metrics import (  # noqa: E402
    calculate_dists,
    calculate_fid,
    calculate_lpips,
    calculate_psnr,
    calculate_vmaf,
    load_images,
)


def load_single_image(image_path: Path, max_size: int = None) -> np.ndarray:
    """Load one PNG image as RGB. Mirrors load_images() for a single file."""
    img = Image.open(image_path).convert("RGB")
    if max_size:
        img.thumbnail((max_size, max_size), Image.Resampling.LANCZOS)
    return np.array(img)


def calculate_bpp(folder: Path, filenames: List[str]) -> List[float]:
    """Calculate bits per pixel from the PNG file sizes and pixel dimensions.

    bpp = (file_size_in_bytes * 8) / (width * height)
    """
    bpp_values = []
    for name in filenames:
        img_path = folder / name
        with Image.open(img_path) as img:
            width, height = img.size
        bpp_values.append(img_path.stat().st_size * 8 / (width * height))
    return bpp_values


def calculate_fid_single_ref(folder: Path, source_path: Path, max_size: int = 299) -> float:
    """Calculate FID between the evaluated folder and the single reference image.

    calculate_fid() requires a reference folder, so the source image is copied
    into a temporary folder (with a single image) and passed as the reference.
    """
    tmp_ref_dir = Path(tempfile.mkdtemp(prefix="fid_ref_"))
    try:
        shutil.copy2(source_path, tmp_ref_dir / f"{source_path.stem}.png")
        return calculate_fid(folder, tmp_ref_dir, max_size=max_size)
    finally:
        shutil.rmtree(tmp_ref_dir, ignore_errors=True)


def main():
    parser = argparse.ArgumentParser(
        description="Calculate image quality metrics against a single reference image"
    )
    parser.add_argument("--folder", type=Path, required=True,
                        help="Path to folder containing PNG images to evaluate")
    parser.add_argument("--source", type=Path, required=True,
                        help="Path to the reference PNG image")
    parser.add_argument("--max-size", type=int, default=None,
                        help="Maximum image dimension (for memory efficiency)")
    parser.add_argument("--skip-fid", action="store_true",
                        help="Skip FID calculation")
    parser.add_argument("--skip-bpp", action="store_true",
                        help="Skip BPP calculation")
    parser.add_argument("--skip-lpips", action="store_true",
                        help="Skip LPIPS calculation")
    parser.add_argument("--skip-dists", action="store_true",
                        help="Skip DISTS calculation")
    parser.add_argument("--skip-psnr", action="store_true",
                        help="Skip PSNR calculation")
    parser.add_argument("--skip-vmaf", action="store_true",
                        help="Skip VMAF calculation")

    args = parser.parse_args()

    # Check if folder exists
    if not args.folder.exists():
        print(f"Error: Folder not found: {args.folder}")
        sys.exit(1)

    # Check if reference image exists
    if not args.source.exists():
        print(f"Error: Reference image not found: {args.source}")
        sys.exit(1)

    if not args.source.is_file():
        print(f"Error: Reference is not a file: {args.source}")
        sys.exit(1)

    # Check for PNG images
    folder_pngs = list(args.folder.glob("*.png"))
    if not folder_pngs:
        print(f"Error: No PNG images found in {args.folder}")
        sys.exit(1)

    print(f"Found {len(folder_pngs)} PNG images in {args.folder}")
    print(f"Reference image: {args.source}")

    # Set device
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"Using device: {device}")

    results = {}
    filenames = []

    # Load images if needed for PSNR, LPIPS, DISTS, VMAF or BPP
    need_images = (not args.skip_psnr or not args.skip_lpips or not args.skip_dists
                   or not args.skip_vmaf or not args.skip_bpp)

    if need_images:
        print("\nLoading images...")
        filenames, images = load_images(args.folder, args.max_size)
        source_image = load_single_image(args.source, args.max_size)
        # Every image is compared against the same reference image
        ref_images = [source_image] * len(images)

    # Calculate PSNR
    if not args.skip_psnr:
        print("\nCalculating PSNR...")
        psnr_values = calculate_psnr(images, ref_images)
        results["PSNR"] = psnr_values
        mean_psnr = np.mean(psnr_values)
        print(f"PSNR: {mean_psnr:.4f} dB (mean)")

    # Calculate LPIPS
    if not args.skip_lpips:
        print("\nCalculating LPIPS...")
        lpips_values = calculate_lpips(images, ref_images, device)
        results["LPIPS"] = lpips_values
        mean_lpips = np.mean(lpips_values)
        print(f"LPIPS: {mean_lpips:.6f} (mean)")

    # Calculate DISTS
    if not args.skip_dists:
        print("\nCalculating DISTS...")
        dists_values = calculate_dists(images, ref_images, device)
        results["DISTS"] = dists_values
        mean_dists = np.mean(dists_values)
        print(f"DISTS: {mean_dists:.6f} (mean)")

    # Calculate VMAF
    if not args.skip_vmaf:
        print("\nCalculating VMAF...")
        vmaf_values = calculate_vmaf(images, ref_images, device)
        results["VMAF"] = vmaf_values
        mean_vmaf = np.mean(vmaf_values)
        print(f"VMAF: {mean_vmaf:.4f} (mean)")

    # Calculate BPP
    if not args.skip_bpp:
        print("\nCalculating BPP...")
        bpp_values = calculate_bpp(args.folder, filenames)
        results["BPP"] = bpp_values
        mean_bpp = np.mean(bpp_values)
        print(f"BPP: {mean_bpp:.6f} (mean)")

    # Calculate FID
    if not args.skip_fid:
        print("\nCalculating FID...")
        fid_size = args.max_size if args.max_size else 299
        try:
            fid_value = calculate_fid_single_ref(args.folder, args.source, max_size=fid_size)
        except Exception as e:
            print(f"Warning: FID calculation failed ({e}). Skipping...")
            fid_value = None

        if fid_value is not None:
            results["FID"] = fid_value
            print(f"FID: {fid_value:.4f}")

    # Print summary (means)
    print("\n" + "=" * 50)
    print("METRICS SUMMARY (MEANS)")
    print("=" * 50)
    if "PSNR" in results:
        print(f"    PSNR: {np.mean(results['PSNR']):.4f} dB")
    if "LPIPS" in results:
        print(f"   LPIPS: {np.mean(results['LPIPS']):.6f}")
    if "DISTS" in results:
        print(f"   DISTS: {np.mean(results['DISTS']):.6f}")
    if "VMAF" in results:
        print(f"   VMAF: {np.mean(results['VMAF']):.4f}")
    if "BPP" in results:
        print(f"     BPP: {np.mean(results['BPP']):.6f}")
    if "FID" in results:
        print(f"      FID: {results['FID']:.4f}")
    print("=" * 50)

    # Save per-image results to file
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = Path("metrics_output") / f"metric_output_{timestamp}"
    output_dir.mkdir(parents=True, exist_ok=True)

    output_file = output_dir / "metrics.txt"
    with open(output_file, "w") as f:
        f.write(f"Folder evaluated: {args.folder}\n")
        f.write(f"Reference image: {args.source}\n")
        f.write(f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"Device: {device}\n\n")

        # Header
        metric_names = [k for k in ["PSNR", "LPIPS", "DISTS", "VMAF", "BPP"]
                        if k in results]
        header = f"{'filename':<40}" + "".join(f"{m:>14}" for m in metric_names)
        if "FID" in results:
            header += f"{'FID':>14}"
        f.write(header + "\n")
        f.write("-" * len(header) + "\n")

        # Per-image rows
        num_images = len(filenames)
        for i in range(num_images):
            row = f"{filenames[i]:<40}"
            for m in metric_names:
                row += f"{results[m][i]:>14.6f}"
            if "FID" in results:
                row += f"{results['FID']:>14.4f}"
            f.write(row + "\n")

        # Mean row
        f.write("-" * len(header) + "\n")
        mean_row = f"{'MEAN':<40}"
        for m in metric_names:
            mean_row += f"{np.mean(results[m]):>14.6f}"
        if "FID" in results:
            mean_row += f"{results['FID']:>14.4f}"
        f.write(mean_row + "\n")

    print(f"\nPer-image results saved to: {output_file}")


if __name__ == "__main__":
    main()
