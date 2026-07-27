# Calculate metrics
uv run python scripts/calc_metrics.py --real_dir PATH/TO/DATASET --fake_dir PATH/TO/RECONSTRUCTIONS -d cuda

# Test command
# poetry run python scripts/calc_metrics.py --real_dir ./datasets/CLIC/test --fake_dir ./results/crdr_q150_b384_CLIC -d cuda
