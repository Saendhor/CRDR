#!/usr/bin/env python3

"""
Calculate image quality metrics: PSNR, LPIPS, DISTS, and FID.

Usage:
    python calc_metrics.py --folder <folder_path> [--ref <reference_folder>]
"""

import argparse
import os
import sys
from pathlib import Path
from typing import List, Tuple

import numpy as np
import torch
from PIL import Image
from skimage.metrics import peak_signal_noise_ratio as psnr
from tqdm import tqdm


def load_images(folder: Path, max_size: int = None) -> List[np.ndarray]:
    """Load all PNG images from a folder."""
    images = []
    image_files = sorted(folder.glob("*.png"))
    
    for img_path in tqdm(image_files, desc="Loading images"):
        img = Image.open(img_path).convert("RGB")
        if max_size:
            img.thumbnail((max_size, max_size), Image.Resampling.LANCZOS)
        images.append(np.array(img))
    
    return images


def calculate_psnr(images: List[np.ndarray], ref_images: List[np.ndarray]) -> float:
    """Calculate PSNR between two sets of images."""
    if len(images) != len(ref_images):
        raise ValueError(f"Number of images mismatch: {len(images)} vs {len(ref_images)}")
    
    psnr_values = []
    for img, ref in tqdm(zip(images, ref_images), desc="Calculating PSNR", total=len(images)):
        psnr_val = psnr(ref, img, data_range=255)
        psnr_values.append(psnr_val)
    
    return float(np.mean(psnr_values))


def calculate_lpips(images: List[np.ndarray], ref_images: List[np.ndarray], 
                    device: torch.device) -> float:
    """Calculate LPIPS between two sets of images."""
    import lpips
    
    if len(images) != len(ref_images):
        raise ValueError(f"Number of images mismatch: {len(images)} vs {len(ref_images)}")
    
    loss_fn = lpips.LPIPS(net="alex").to(device)
    
    lpips_values = []
    for img, ref in tqdm(zip(images, ref_images), desc="Calculating LPIPS", total=len(images)):
        # Convert to tensor and normalize to [-1, 1]
        img_tensor = torch.from_numpy(img).permute(2, 0, 1).unsqueeze(0).float() / 127.5 - 1
        ref_tensor = torch.from_numpy(ref).permute(2, 0, 1).unsqueeze(0).float() / 127.5 - 1
        
        img_tensor = img_tensor.to(device)
        ref_tensor = ref_tensor.to(device)
        
        with torch.no_grad():
            lpips_val = loss_fn(ref_tensor, img_tensor)
        
        lpips_values.append(lpips_val.item())
    
    return float(np.mean(lpips_values))


def calculate_dists(images: List[np.ndarray], ref_images: List[np.ndarray], 
                    device: torch.device) -> float:
    """Calculate DISTS between two sets of images."""
    from dists_pytorch import DISTS
    
    if len(images) != len(ref_images):
        raise ValueError(f"Number of images mismatch: {len(images)} vs {len(ref_images)}")
    
    loss_fn = DISTS().to(device)
    
    dists_values = []
    for img, ref in tqdm(zip(images, ref_images), desc="Calculating DISTS", total=len(images)):
        # Convert to tensor and normalize to [0, 1]
        img_tensor = torch.from_numpy(img).permute(2, 0, 1).unsqueeze(0).float() / 255.0
        ref_tensor = torch.from_numpy(ref).permute(2, 0, 1).unsqueeze(0).float() / 255.0
        
        img_tensor = img_tensor.to(device)
        ref_tensor = ref_tensor.to(device)
        
        with torch.no_grad():
            dists_val = loss_fn(ref_tensor, img_tensor)
        
        dists_values.append(dists_val.item())
    
    return float(np.mean(dists_values))


def calculate_fid(folder: Path, ref_folder: Path = None) -> float:
    """Calculate FID score using pytorch-fid."""
    from pytorch_fid import fid_score
    
    if ref_folder:
        fid_value = fid_score.calculate_fid_given_paths(
            [str(folder), str(ref_folder)],
            batch_size=50,
            device=torch.device("cuda" if torch.cuda.is_available() else "cpu"),
            dims=2048,
            num_workers=4
        )
    else:
        # Calculate FID against itself (should be 0)
        fid_value = 0.0
    
    return fid_value


def main():
    parser = argparse.ArgumentParser(description="Calculate image quality metrics")
    parser.add_argument("--folder", type=Path, required=True, 
                        help="Path to folder containing PNG images to evaluate")
    parser.add_argument("--ref", type=Path, default=None,
                        help="Path to reference folder (required for PSNR, LPIPS, DISTS)")
    parser.add_argument("--max-size", type=int, default=None,
                        help="Maximum image dimension (for memory efficiency)")
    parser.add_argument("--skip-fid", action="store_true",
                        help="Skip FID calculation (FID requires two different folders)")
    parser.add_argument("--skip-lpips", action="store_true",
                        help="Skip LPIPS calculation")
    parser.add_argument("--skip-dists", action="store_true",
                        help="Skip DISTS calculation")
    parser.add_argument("--skip-psnr", action="store_true",
                        help="Skip PSNR calculation")
    
    args = parser.parse_args()
    
    # Check if folder exists
    if not args.folder.exists():
        print(f"Error: Folder not found: {args.folder}")
        sys.exit(1)
    
    # Check if reference folder exists
    if args.ref and not args.ref.exists():
        print(f"Error: Reference folder not found: {args.ref}")
        sys.exit(1)
    
    # Check for PNG images
    folder_pngs = list(args.folder.glob("*.png"))
    if not folder_pngs:
        print(f"Error: No PNG images found in {args.folder}")
        sys.exit(1)
    
    print(f"Found {len(folder_pngs)} PNG images in {args.folder}")
    
    if args.ref:
        ref_pngs = list(args.ref.glob("*.png"))
        if not ref_pngs:
            print(f"Error: No PNG images found in reference folder: {args.ref}")
            sys.exit(1)
        print(f"Found {len(ref_pngs)} PNG images in reference folder: {args.ref}")
    
    # Set device
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"Using device: {device}")
    
    results = {}
    
    # Load images if needed for PSNR, LPIPS, or DISTS
    need_images = not args.skip_psnr or not args.skip_lpips or not args.skip_dists
    
    if need_images and args.ref:
        print("\nLoading images...")
        images = load_images(args.folder, args.max_size)
        ref_images = load_images(args.ref, args.max_size)
        
        if len(images) != len(ref_images):
            print(f"Warning: Number of images mismatch ({len(images)} vs {len(ref_images)})")
            print("Only comparing matching images (by index)")
            min_len = min(len(images), len(ref_images))
            images = images[:min_len]
            ref_images = ref_images[:min_len]
    
    # Calculate PSNR
    if not args.skip_psnr and args.ref:
        print("\nCalculating PSNR...")
        psnr_value = calculate_psnr(images, ref_images)
        results["PSNR"] = f"{psnr_value:.4f} dB"
        print(f"PSNR: {psnr_value:.4f} dB")
    
    # Calculate LPIPS
    if not args.skip_lpips and args.ref:
        print("\nCalculating LPIPS...")
        lpips_value = calculate_lpips(images, ref_images, device)
        results["LPIPS"] = f"{lpips_value:.6f}"
        print(f"LPIPS: {lpips_value:.6f}")
    
    # Calculate DISTS
    if not args.skip_dists and args.ref:
        print("\nCalculating DISTS...")
        dists_value = calculate_dists(images, ref_images, device)
        results["DISTS"] = f"{dists_value:.6f}"
        print(f"DISTS: {dists_value:.6f}")
    
    # Calculate FID
    if not args.skip_fid:
        print("\nCalculating FID...")
        if args.ref:
            fid_value = calculate_fid(args.folder, args.ref)
        else:
            print("Warning: FID requires a reference folder. Skipping...")
            fid_value = None
        
        if fid_value is not None:
            results["FID"] = f"{fid_value:.4f}"
            print(f"FID: {fid_value:.4f}")
    
    # Print summary
    print("\n" + "=" * 50)
    print("METRICS SUMMARY")
    print("=" * 50)
    for metric, value in results.items():
        print(f"{metric:>8}: {value}")
    print("=" * 50)


if __name__ == "__main__":
    main()
