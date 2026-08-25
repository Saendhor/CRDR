# Calculate metrics
uv run python -m scripts.calc_metrics --real_dir ./dataset/block --fake_dir ./results/inf -d cuda

# Test command
# poetry run python scripts/calc_metrics.py --real_dir ./datasets/CLIC/test --fake_dir ./results/crdr_q150_b384_CLIC -d cuda
