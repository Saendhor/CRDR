#Make sure you're in the proper directory
#cd "/leonardo/home/userexternal/spennisi/CRDR"

# Script for inference
uv run python -m scripts.compress --config_path ./config/crdr.yaml --model_path ./crdr.pth.tar --img_dir dataset/Fourth --save_dir ./results/inf_00_512 -q 0.0 -b 5.12 --decompress -d cuda

# --quality adjusts the bitrate. Float value [0.0, 4.0] - 0.0: Low bitrate, 4.0: High bitrate
# --beta adjusts realism. Float value [0.0, 5.12] - 0.0: Low distortion, 5.12: High realism


# Test command
# poetry run python scripts/compress.py --config_path ./config/crdr.yaml --model_path ./crdr.pth.tar --img_dir ./demo_images --save_dir ./demo_results/crdr_q000_b384_kodak -q 0.00 -b 3.84 --decompress -d cuda
