# Script for inference
uv run python scripts/compress.py --config_path ./config/crdr.yaml --model_path ./crdr.pth.tar --img_dir dataset --save_dir ./results/crdr_q000_b384_fnv1 -q 0.00 -b 3.84 --decompress -d cuda

# Test command
# poetry run python scripts/compress.py --config_path ./config/crdr.yaml --model_path ./crdr.pth.tar --img_dir ./demo_images --save_dir ./demo_results/crdr_q000_b384_kodak -q 0.00 -b 3.84 --decompress -d cuda
