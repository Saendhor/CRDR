#!/usr/bin/env python3

"""
Calculate image quality metrics: PSNR, LPIPS, DISTS, VMAF, and FID for BC7 DDS textures,
plus encoded bits per pixel (BPP).

Each DDS is decoded (top mip level, first array slice/face) to RGB before evaluation.
BC7, BC1 (DXT1), and BC3 (DXT5) are supported; references may be DDS, PNG, or JPG.

Usage:
    python calc_metrics_dds.py --folder <folder_path> [--ref <reference_folder>]
"""

import argparse
import os
import struct
import sys
from datetime import datetime
from pathlib import Path
from typing import List, Tuple

import numpy as np
import torch
from PIL import Image
from skimage.metrics import peak_signal_noise_ratio as psnr
from tqdm import tqdm

DDS_EXTENSIONS = (".dds",)
REFERENCE_EXTENSIONS = (".dds", ".png", ".jpg", ".jpeg")

DDS_MAGIC = b"DDS "
DDS_HEADER_SIZE = 128
DX10_HEADER_SIZE = 20

# DXGI_FORMAT -> (format name, texture2ddecoder function, block size in bytes)
DXGI_BC_FORMATS = {
    70: ("BC1", "decode_bc1", 8),   # BC1_TYPELESS
    71: ("BC1", "decode_bc1", 8),   # BC1_UNORM
    72: ("BC1", "decode_bc1", 8),   # BC1_UNORM_SRGB
    76: ("BC3", "decode_bc3", 16),  # BC3_TYPELESS
    77: ("BC3", "decode_bc3", 16),  # BC3_UNORM
    78: ("BC3", "decode_bc3", 16),  # BC3_UNORM_SRGB
    97: ("BC7", "decode_bc7", 16),  # BC7_TYPELESS
    98: ("BC7", "decode_bc7", 16),  # BC7_UNORM
    99: ("BC7", "decode_bc7", 16),  # BC7_UNORM_SRGB
}

# Legacy FourCC -> (format name, texture2ddecoder function, block size in bytes)
FOURCC_BC_FORMATS = {
    b"DXT1": ("BC1", "decode_bc1", 8),
    b"DXT5": ("BC3", "decode_bc3", 16),
    b"BC7 ": ("BC7", "decode_bc7", 16),
}


def find_files(folder: Path, extensions: Tuple[str, ...]) -> List[Path]:
    """Return files with one of the given extensions (case-insensitive), sorted by name."""
    return sorted(
        path for path in folder.iterdir()
        if path.is_file() and path.suffix.lower() in extensions
    )


def read_dds(path: Path) -> Tuple[int, int, str, str, bytes]:
    """Parse a DDS header and return (width, height, format, decoder, top-level payload)."""
    data = path.read_bytes()
    if len(data) < DDS_HEADER_SIZE or data[:4] != DDS_MAGIC:
        raise ValueError(f"{path.name}: not a valid DDS file")

    height, width = struct.unpack_from("<II", data, 12)
    fourcc = data[84:88]
    data_offset = DDS_HEADER_SIZE

    if fourcc == b"DX10":
        if len(data) < DDS_HEADER_SIZE + DX10_HEADER_SIZE:
            raise ValueError(f"{path.name}: truncated DX10 header")
        dxgi_format, = struct.unpack_from("<I", data, DDS_HEADER_SIZE)
        fmt = DXGI_BC_FORMATS.get(dxgi_format)
        format_label = f"DXGI {dxgi_format}"
        data_offset += DX10_HEADER_SIZE
    else:
        fmt = FOURCC_BC_FORMATS.get(fourcc)
        format_label = fourcc.decode("ascii", errors="replace")

    if fmt is None:
        raise ValueError(
            f"{path.name}: unsupported DDS format ({format_label}); "
            "supported formats are BC7, BC1/DXT1, and BC3/DXT5"
        )

    format_name, decoder_name, block_size = fmt
    blocks_x = max(1, (width + 3) // 4)
    blocks_y = max(1, (height + 3) // 4)
    payload_size = blocks_x * blocks_y * block_size

    payload = data[data_offset:data_offset + payload_size]
    if len(payload) != payload_size:
        raise ValueError(
            f"{path.name}: truncated DDS data (expected {payload_size} bytes, "
            f"got {len(payload)})"
        )

    return width, height, format_name, decoder_name, payload


def calculate_bpp(folder: Path) -> List[float]:
    """Compute bits per pixel from each DDS top-level encoded payload.

    DDS headers are excluded, so this is the actual storage cost of the
    compressed top mip level (e.g. 8.0 for BC7, 4.0 for BC1, 8.0 for BC3).
    """
    bpp_values = []
    for path in find_files(folder, DDS_EXTENSIONS):
        width, height, _, _, payload = read_dds(path)
        bpp_values.append(len(payload) * 8 / (width * height))
    return bpp_values


def load_dds(path: Path) -> Image.Image:
    """Decode a DDS texture to an RGB PIL image."""
    try:
        import texture2ddecoder
    except ImportError as exc:
        raise RuntimeError(
            "texture2ddecoder is required to decode DDS files. Run this script "
            "through calc_metrics_dds.sh or install it with "
            "`uv pip install texture2ddecoder`."
        ) from exc

    width, height, format_name, decoder_name, payload = read_dds(path)
    decode = getattr(texture2ddecoder, decoder_name)
    rgba = decode(payload, width, height)

    # Decoders may return full 4x4-padded blocks; crop back to the texture size.
    # texture2ddecoder returns BGRA byte order.
    padded_width = max(4, (width + 3) // 4 * 4)
    padded_height = max(4, (height + 3) // 4 * 4)
    if len(rgba) == padded_width * padded_height * 4:
        img = Image.frombytes("RGBA", (padded_width, padded_height), rgba, "raw", "BGRA")
        img = img.crop((0, 0, width, height))
    elif len(rgba) == width * height * 4:
        img = Image.frombytes("RGBA", (width, height), rgba, "raw", "BGRA")
    else:
        raise ValueError(
            f"{path.name}: unexpected decoded size for {format_name} "
            f"({len(rgba)} bytes for {width}x{height})"
        )

    return img.convert("RGB")


def load_image(path: Path, max_size: int = None) -> np.ndarray:
    """Load a single DDS/PNG/JPG image as an RGB numpy array."""
    if path.suffix.lower() in DDS_EXTENSIONS:
        img = load_dds(path)
    else:
        img = Image.open(path).convert("RGB")
    if max_size:
        img.thumbnail((max_size, max_size), Image.Resampling.LANCZOS)
    return np.array(img)


def ensure_same_dimensions(img: np.ndarray, ref: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
    """Resize ref to match img dimensions if they differ."""
    if img.shape != ref.shape:
        ref_pil = Image.fromarray(ref)
        ref_pil = ref_pil.resize((img.shape[1], img.shape[0]), Image.Resampling.LANCZOS)
        ref = np.array(ref_pil)
    return img, ref


def load_images(folder: Path, extensions: Tuple[str, ...],
                max_size: int = None) -> Tuple[List[str], List[np.ndarray]]:
    """Load all supported images from a folder. Returns (filenames, images)."""
    filenames = []
    images = []
    image_files = find_files(folder, extensions)
    
    for img_path in tqdm(image_files, desc="Loading images"):
        filenames.append(img_path.name)
        images.append(load_image(img_path, max_size))
    
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
        for src_folder, label, extensions in [
            (folder, "images", DDS_EXTENSIONS),
            (ref_folder, "ref", REFERENCE_EXTENSIONS),
        ]:
            dst = tmp_dir / label
            dst.mkdir(parents=True, exist_ok=True)
            for img_path in find_files(src_folder, extensions):
                img = Image.fromarray(load_image(img_path))
                img = img.resize((max_size, max_size), Image.Resampling.LANCZOS)
                save_name = img_path.stem if img_path.suffix else img_path.name
                img.save(dst / f"{save_name}.png")

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
                        help="Path to folder containing DDS images to evaluate")
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
    
    # Check for DDS images
    folder_dds = find_files(args.folder, DDS_EXTENSIONS)
    if not folder_dds:
        print(f"Error: No DDS images found in {args.folder}")
        sys.exit(1)
    
    print(f"Found {len(folder_dds)} DDS images in {args.folder}")
    
    if args.ref:
        ref_images_found = find_files(args.ref, REFERENCE_EXTENSIONS)
        if not ref_images_found:
            print(f"Error: No images found in reference folder: {args.ref}")
            sys.exit(1)
        print(f"Found {len(ref_images_found)} images in reference folder: {args.ref}")
    
    # Set device
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"Using device: {device}")
    
    results = {}
    filenames = []

    # Bits per pixel is computed directly from the encoded target files
    results["BPP"] = calculate_bpp(args.folder)
    
    # Load images if needed for PSNR, LPIPS, or DISTS
    need_images = not args.skip_psnr or not args.skip_lpips or not args.skip_dists or not args.skip_vmaf
    
    if need_images and args.ref:
        print("\nLoading images...")
        filenames, images = load_images(args.folder, DDS_EXTENSIONS, args.max_size)
        _, ref_images = load_images(args.ref, REFERENCE_EXTENSIONS, args.max_size)
        
        if len(images) != len(ref_images):
            print(f"Warning: Number of images mismatch ({len(images)} vs {len(ref_images)})")
            print("Only comparing matching images (by index)")
            min_len = min(len(images), len(ref_images))
            filenames = filenames[:min_len]
            images = images[:min_len]
            ref_images = ref_images[:min_len]
            results["BPP"] = results["BPP"][:min_len]
    
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
    if "BPP" in results:
        print(f"     BPP: {np.mean(results['BPP']):.4f} bits/pixel")
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
        metric_names = [k for k in ["PSNR", "LPIPS", "DISTS", "VMAF", "BPP"] if k in results]
        header = f"{'filename':<40}" + "".join(f"{m:>14}" for m in metric_names)
        if "FID" in results:
            header += f"{'FID':>14}"
        f.write(header + "\n")
        f.write("-" * len(header) + "\n")
        
        # Per-image rows
        if not filenames:
            filenames = [path.name for path in find_files(args.folder, DDS_EXTENSIONS)]
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
