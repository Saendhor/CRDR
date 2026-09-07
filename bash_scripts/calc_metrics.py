#!/usr/bin/env python3

"""
Calculate image quality metrics: PSNR, LPIPS, DISTS, VMAF, and FID.

Usage:
    python calc_metrics.py --folder <folder_path> [--ref <reference_folder>]
"""

import argparse
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import List, Tuple

import numpy as np
import torch
from PIL import Image
from skimage.metrics import peak_signal_noise_ratio as psnr
from tqdm import tqdm


def ensure_same_dimensions(img: np.ndarray, ref: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
    """Resize ref to match img dimensions if they differ."""
    if img.shape != ref.shape:
        ref_pil = Image.fromarray(ref)
        ref_pil = ref_pil.resize((img.shape[1], img.shape[0]), Image.Resampling.LANCZOS)
        ref = np.array(ref_pil)
    return img, ref


def load_images(folder: Path, max_size: int = None) -> Tuple[List[str], List[np.ndarray]]:
    """Load all PNG images from a folder. Returns (filenames, images)."""
    filenames = []
    images = []
    image_files = sorted(folder.glob("*.png"))
    
    for img_path in tqdm(image_files, desc="Loading images"):
        filenames.append(img_path.name)
        img = Image.open(img_path).convert("RGB")
        if max_size:
            img.thumbnail((max_size, max_size), Image.Resampling.LANCZOS)
        images.append(np.array(img))
    
    return filenames, images


def calculate_psnr(images: List[np.ndarray], ref_images: List[np.ndarray]) -> List[float]:
    """Calculate PSNR between two sets of images."""
    if len(images) != len(ref_images):
        raise ValueError(f"Number of images mismatch: {len(images)} vs {len(ref_images)}")
    
    psnr_values = []
    for img, ref in tqdm(zip(images, ref_images), desc="Calculating PSNR", total=len(images)):
        img, ref = ensure_same_dimensions(img, ref)
        psnr_val = psnr(ref, img, data_range=255)
        psnr_values.append(psnr_val)
    
    return psnr_values


def calculate_lpips(images: List[np.ndarray], ref_images: List[np.ndarray], 
                    device: torch.device) -> List[float]:
    """Calculate LPIPS between two sets of images."""
    import lpips
    
    if len(images) != len(ref_images):
        raise ValueError(f"Number of images mismatch: {len(images)} vs {len(ref_images)}")
    
    loss_fn = lpips.LPIPS(net="alex").to(device)
    
    lpips_values = []
    for img, ref in tqdm(zip(images, ref_images), desc="Calculating LPIPS", total=len(images)):
        img, ref = ensure_same_dimensions(img, ref)
        
        # Resize to minimum 64x64 to avoid AlexNet pooling errors on small images
        min_dim = 64
        h, w = img.shape[:2]
        if h < min_dim or w < min_dim:
            scale = max(min_dim / h, min_dim / w)
            new_h, new_w = int(h * scale), int(w * scale)
            img = np.array(Image.fromarray(img).resize((new_w, new_h), Image.Resampling.LANCZOS))
            ref = np.array(Image.fromarray(ref).resize((new_w, new_h), Image.Resampling.LANCZOS))
        
        # Convert to tensor and normalize to [-1, 1]
        img_tensor = torch.from_numpy(img).permute(2, 0, 1).unsqueeze(0).float() / 127.5 - 1
        ref_tensor = torch.from_numpy(ref).permute(2, 0, 1).unsqueeze(0).float() / 127.5 - 1
        
        img_tensor = img_tensor.to(device)
        ref_tensor = ref_tensor.to(device)
        
        with torch.no_grad():
            lpips_val = loss_fn(ref_tensor, img_tensor)
        
        lpips_values.append(lpips_val.item())
    
    return lpips_values


def calculate_dists(images: List[np.ndarray], ref_images: List[np.ndarray], 
                    device: torch.device) -> List[float]:
    """Calculate DISTS between two sets of images."""
    from DISTS_pytorch import DISTS
    
    if len(images) != len(ref_images):
        raise ValueError(f"Number of images mismatch: {len(images)} vs {len(ref_images)}")
    
    loss_fn = DISTS().to(device)
    
    dists_values = []
    for img, ref in tqdm(zip(images, ref_images), desc="Calculating DISTS", total=len(images)):
        img, ref = ensure_same_dimensions(img, ref)
        # Convert to tensor and normalize to [0, 1]
        img_tensor = torch.from_numpy(img).permute(2, 0, 1).unsqueeze(0).float() / 255.0
        ref_tensor = torch.from_numpy(ref).permute(2, 0, 1).unsqueeze(0).float() / 255.0
        
        img_tensor = img_tensor.to(device)
        ref_tensor = ref_tensor.to(device)
        
        with torch.no_grad():
            dists_val = loss_fn(ref_tensor, img_tensor)
        
        dists_values.append(dists_val.item())
    
    return dists_values


def calculate_vmaf(images: List[np.ndarray], ref_images: List[np.ndarray],
                   device: torch.device) -> List[float]:
    """Calculate VMAF between two sets of images."""
    from vmaf_torch import VMAF

    if len(images) != len(ref_images):
        raise ValueError(f"Number of images mismatch: {len(images)} vs {len(ref_images)}")

    vmaf_fn = VMAF(enable_motion=False, clip_score=True).to(device)

    vmaf_values = []
    for img, ref in tqdm(zip(images, ref_images), desc="Calculating VMAF", total=len(images)):
        img, ref = ensure_same_dimensions(img, ref)

        # Resize to minimum 64x64 to avoid wavelet decomposition errors on small images
        min_dim = 64
        h, w = img.shape[:2]
        if h < min_dim or w < min_dim:
            scale = max(min_dim / h, min_dim / w)
            new_h, new_w = int(h * scale), int(w * scale)
            img = np.array(Image.fromarray(img).resize((new_w, new_h), Image.Resampling.LANCZOS))
            ref = np.array(Image.fromarray(ref).resize((new_w, new_h), Image.Resampling.LANCZOS))

        # Convert RGB uint8 to Y-channel (luma) tensor [1,1,H,W] float [0,255]
        ref_luma = 0.299 * ref[:, :, 0] + 0.587 * ref[:, :, 1] + 0.114 * ref[:, :, 2]
        img_luma = 0.299 * img[:, :, 0] + 0.587 * img[:, :, 1] + 0.114 * img[:, :, 2]

        ref_tensor = torch.from_numpy(ref_luma).unsqueeze(0).unsqueeze(0).float().to(device)
        img_tensor = torch.from_numpy(img_luma).unsqueeze(0).unsqueeze(0).float().to(device)

        with torch.no_grad():
            vmaf_score = vmaf_fn(ref_tensor, img_tensor)

        vmaf_values.append(vmaf_score.item())

    return vmaf_values


def calculate_fid(folder: Path, ref_folder: Path = None, max_size: int = 299) -> float:
    """Calculate FID score using pytorch-fid.
    
    Resizes all images to (max_size, max_size) in a temp directory since
    pytorch-fid requires uniform image sizes.
    """
    import shutil
    import tempfile
    from pytorch_fid import fid_score

    if not ref_folder:
        return 0.0

    tmp_dir = Path(tempfile.mkdtemp(prefix="fid_"))

    try:
        for src_folder, label in [(folder, "images"), (ref_folder, "ref")]:
            dst = tmp_dir / label
            dst.mkdir(parents=True, exist_ok=True)
            for img_path in sorted(src_folder.glob("*.png")):
                img = Image.open(img_path).convert("RGB")
                img = img.resize((max_size, max_size), Image.Resampling.LANCZOS)
                img.save(dst / img_path.name)

        device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        fid_value = fid_score.calculate_fid_given_paths(
            [str(tmp_dir / "images"), str(tmp_dir / "ref")],
            batch_size=50,
            device=device,
            dims=2048,
            num_workers=0
        )
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)

    return fid_value


def main():
    parser = argparse.ArgumentParser(description="Calculate image quality metrics")
    parser.add_argument("--folder", type=Path, required=True, 
                        help="Path to folder containing PNG images to evaluate")
    parser.add_argument("--ref", type=Path, default=None,
                        help="Path to reference folder (required for PSNR, LPIPS, DISTS, VMAF)")
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
    parser.add_argument("--skip-vmaf", action="store_true",
                        help="Skip VMAF calculation")
    
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
    filenames = []
    
    # Load images if needed for PSNR, LPIPS, or DISTS
    need_images = not args.skip_psnr or not args.skip_lpips or not args.skip_dists or not args.skip_vmaf
    
    if need_images and args.ref:
        print("\nLoading images...")
        filenames, images = load_images(args.folder, args.max_size)
        _, ref_images = load_images(args.ref, args.max_size)
        
        if len(images) != len(ref_images):
            print(f"Warning: Number of images mismatch ({len(images)} vs {len(ref_images)})")
            print("Only comparing matching images (by index)")
            min_len = min(len(images), len(ref_images))
            filenames = filenames[:min_len]
            images = images[:min_len]
            ref_images = ref_images[:min_len]
    
    # Calculate PSNR
    if not args.skip_psnr and args.ref:
        print("\nCalculating PSNR...")
        psnr_values = calculate_psnr(images, ref_images)
        results["PSNR"] = psnr_values
        mean_psnr = np.mean(psnr_values)
        print(f"PSNR: {mean_psnr:.4f} dB (mean)")
    
    # Calculate LPIPS
    if not args.skip_lpips and args.ref:
        print("\nCalculating LPIPS...")
        lpips_values = calculate_lpips(images, ref_images, device)
        results["LPIPS"] = lpips_values
        mean_lpips = np.mean(lpips_values)
        print(f"LPIPS: {mean_lpips:.6f} (mean)")
    
    # Calculate DISTS
    if not args.skip_dists and args.ref:
        print("\nCalculating DISTS...")
        dists_values = calculate_dists(images, ref_images, device)
        results["DISTS"] = dists_values
        mean_dists = np.mean(dists_values)
        print(f"DISTS: {mean_dists:.6f} (mean)")
    
    # Calculate VMAF
    if not args.skip_vmaf and args.ref:
        print("\nCalculating VMAF...")
        vmaf_values = calculate_vmaf(images, ref_images, device)
        results["VMAF"] = vmaf_values
        mean_vmaf = np.mean(vmaf_values)
        print(f"VMAF: {mean_vmaf:.4f} (mean)")
    
    # Calculate FID
    if not args.skip_fid:
        print("\nCalculating FID...")
        if args.ref:
            fid_size = args.max_size if args.max_size else 299
            fid_value = calculate_fid(args.folder, args.ref, max_size=fid_size)
        else:
            print("Warning: FID requires a reference folder. Skipping...")
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
        if args.ref:
            f.write(f"Reference folder: {args.ref}\n")
        f.write(f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"Device: {device}\n\n")
        
        # Header
        metric_names = [k for k in ["PSNR", "LPIPS", "DISTS", "VMAF", "FID"] if k in results and k != "FID"]
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
