#!/usr/bin/env python3
"""Merge MEAN metric values from multiple metrics.txt files.

Each run of bash_scripts/calc_metrics.py creates::

    metrics_output/metric_output_<timestamp>/metrics.txt

with a header (Folder evaluated / Reference folder / Date / Device),
a per-image table, and a final ``MEAN`` row.

This script scans all ``metrics.txt`` files under ``metrics_output/``,
extracts the ``MEAN`` values, and writes a single summary table where
each row is one evaluated folder (``results/<name>``) plus its mean
metrics.

Usage:
    python metrics_scripts/merge_metrics.py
    python metrics_scripts/merge_metrics.py --input-dir metrics_output --output metrics_output/merged_metrics.txt
    python metrics_scripts/merge_metrics.py --input-dir metrics_output --sort-by evaluated
"""

from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path

CANONICAL_ORDER = ["PSNR", "LPIPS", "DISTS", "VMAF", "FID"]
MISSING = "N/A"


def parse_metrics_file(path: Path) -> dict | None:
    """Parse one metrics.txt file.

    Returns a dict with keys: evaluated, reference, date, device,
    metric_names (list), means (dict name -> raw string value).
    Returns None (with a warning) if no MEAN row is found.
    """
    evaluated = ""
    reference = ""
    date = ""
    device = ""
    metric_names: list[str] = []
    mean_values: list[str] = []

    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        print(f"Warning: cannot read {path}: {exc}")
        return None

    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("Folder evaluated:"):
            evaluated = stripped.split(":", 1)[1].strip()
        elif stripped.startswith("Reference folder:"):
            reference = stripped.split(":", 1)[1].strip()
        elif stripped.startswith("Date:"):
            date = stripped.split(":", 1)[1].strip()
        elif stripped.startswith("Device:"):
            device = stripped.split(":", 1)[1].strip()
        elif stripped.lower().startswith("filename"):
            # Header row: "filename  PSNR  LPIPS  DISTS  VMAF  FID"
            parts = stripped.split()
            # drop the leading "filename" token
            metric_names = parts[1:]
        elif stripped.startswith("MEAN"):
            parts = stripped.split()
            mean_values = parts[1:]

    if not metric_names or not mean_values:
        print(f"Warning: no MEAN row found in {path}, skipping.")
        return None

    if len(metric_names) != len(mean_values):
        print(
            f"Warning: header/mean length mismatch in {path} "
            f"({metric_names} vs {mean_values}), truncating to common length."
        )
        common = min(len(metric_names), len(mean_values))
        metric_names = metric_names[:common]
        mean_values = mean_values[:common]

    return {
        "evaluated": evaluated,
        "reference": reference,
        "date": date,
        "device": device,
        "metric_names": metric_names,
        "means": dict(zip(metric_names, mean_values)),
        "source_file": path,
    }


def collect_results(input_dir: Path, output_path: Path | None) -> list[dict]:
    """Find all metrics.txt files under input_dir (excluding the output file)."""
    candidates = sorted(input_dir.rglob("metrics.txt"))
    if output_path is not None:
        try:
            resolved_out = output_path.resolve()
            candidates = [p for p in candidates if p.resolve() != resolved_out]
        except OSError:
            pass
    results = []
    for path in candidates:
        parsed = parse_metrics_file(path)
        if parsed is None:
            continue
        # run name = parent folder of metrics.txt, relative to input_dir
        try:
            run = str(path.parent.relative_to(input_dir))
        except ValueError:
            run = path.parent.name
        parsed["run"] = run
        results.append(parsed)
    return results


def order_metrics(results: list[dict]) -> list[str]:
    """Union of metric names, canonical order first, extras appended."""
    seen: list[str] = []
    for r in results:
        for m in r["metric_names"]:
            if m not in seen:
                seen.append(m)
    ordered = [m for m in CANONICAL_ORDER if m in seen]
    ordered += [m for m in seen if m not in ordered]
    return ordered


def build_table(results: list[dict], metric_order: list[str]) -> tuple[str, list[str]]:
    """Build the merged fixed-width table. Returns (header, rows)."""
    # Column widths adapt to content.
    eval_w = max([len("evaluated_folder")] + [len(r["evaluated"]) for r in results])
    run_w = max([len("run")] + [len(r["run"]) for r in results])
    # Keep the table readable: cap very long folder names is not needed here,
    # data is short (e.g. "results/inf_15_256"). Just ensure a sane minimum.
    eval_w = max(eval_w, 20)
    run_w = max(run_w, 20)
    metric_w = max(14, max((len(m) for m in metric_order), default=14))

    header = (
        f"{'evaluated_folder':<{eval_w}}  "
        f"{'run':<{run_w}}  "
        + "  ".join(f"{m:>{metric_w}}" for m in metric_order)
    )
    rows = []
    for r in results:
        row = f"{r['evaluated']:<{eval_w}}  {r['run']:<{run_w}}  "
        row += "  ".join(f"{r['means'].get(m, MISSING):>{metric_w}}" for m in metric_order)
        rows.append(row)
    return header, rows


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Merge MEAN values from metrics_output/*/metrics.txt "
        "into a single summary .txt file."
    )
    parser.add_argument(
        "--input-dir",
        type=Path,
        default=None,
        help="Folder containing metric_output_*/ subfolders "
        "(default: ./metrics_output, or <repo_root>/metrics_output "
        "relative to this script).",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Output .txt path (default: <input-dir>/merged_metrics.txt).",
    )
    parser.add_argument(
        "--sort-by",
        choices=["run", "evaluated", "date"],
        default="run",
        help="Row sort order (default: run, i.e. chronological).",
    )
    args = parser.parse_args()

    # Resolve default input dir: prefer ./metrics_output, fall back to
    # <repo_root>/metrics_output next to this script's parent.
    if args.input_dir is None:
        cwd_candidate = Path.cwd() / "metrics_output"
        script_candidate = Path(__file__).resolve().parent.parent / "metrics_output"
        input_dir = (
            cwd_candidate
            if cwd_candidate.is_dir()
            else script_candidate
        )
    else:
        input_dir = args.input_dir

    if not input_dir.is_dir():
        parser.error(f"Input directory not found: {input_dir}")

    output_path = args.output or (input_dir / "merged_metrics.txt")

    results = collect_results(input_dir, output_path)

    if not results:
        print(f"No metrics.txt files with MEAN rows found under {input_dir}")
        raise SystemExit(1)

    if args.sort_by == "evaluated":
        results.sort(key=lambda r: (r["evaluated"], r["run"]))
    elif args.sort_by == "date":
        results.sort(key=lambda r: (r["date"], r["run"]))
    else:
        results.sort(key=lambda r: r["run"])

    metric_order = order_metrics(results)
    header, rows = build_table(results, metric_order)

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(f"Merged metrics ({len(results)} runs, {now})\n")
        f.write(f"Source: {input_dir.resolve()}\n")
        f.write(
            "Each row = one metrics.txt MEAN row. "
            "First column is the evaluated folder (results/<name>).\n"
        )
        f.write("\n")
        f.write(header + "\n")
        f.write("-" * len(header) + "\n")
        for row in rows:
            f.write(row + "\n")
        f.write("-" * len(header) + "\n")
        f.write("\nDetails per run:\n")
        for r in results:
            ref = f", ref={r['reference']}" if r["reference"] else ""
            date = f", date={r['date']}" if r["date"] else ""
            f.write(f"  {r['run']}: {r['evaluated']}{ref}{date}\n")

    print(f"Found {len(results)} metrics.txt files under {input_dir}")
    print(f"Metrics: {', '.join(metric_order)}")
    print(f"Merged table written to: {output_path}")


if __name__ == "__main__":
    main()
