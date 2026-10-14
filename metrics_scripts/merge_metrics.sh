#!/bin/bash
#
# Merge MEAN metric values from multiple metrics.txt files.
#
# Each run of bash_scripts/calc_metrics.py creates:
#     metrics_output/metric_output_<timestamp>/metrics.txt
# with a header (Folder evaluated / Reference folder / Date / Device),
# a per-image table, and a final MEAN row.
#
# This script scans all metrics.txt files under metrics_output/,
# extracts the MEAN values, and writes a single summary table where
# each row is one evaluated folder (results/<name>) plus its mean metrics.
#
# Usage:
#   ./merge_metrics.sh
#   ./merge_metrics.sh --input-dir metrics_output --output metrics_output/merged_metrics.txt
#   ./merge_metrics.sh --input-dir metrics_output --sort-by evaluated
#
# No Python required (pure bash + coreutils).

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# ---------- helpers ----------
abspath() {
    if command -v realpath >/dev/null 2>&1; then
        realpath -m "$1"
    else
        readlink -f "$1"
    fi
}

trim() {
    sed 's/^[[:space:]]*//;s/[[:space:]]*$//' <<<"$1"
}

usage() {
    cat <<EOF
Usage: $(basename "$0") [--input-dir DIR] [--output FILE] [--sort-by run|evaluated|date]

Merge MEAN values from <input-dir>/*/metrics.txt into a single summary .txt file.

Options:
  --input-dir DIR   Folder containing metric_output_*/ subfolders
                    (default: ./metrics_output, or <repo_root>/metrics_output
                    relative to this script).
  --output FILE     Output .txt path (default: <input-dir>/merged_metrics.txt).
  --sort-by KEY     Row sort order: run (chronological, default), evaluated, date.
  -h, --help        Show this help and exit.
EOF
}

# ---------- args ----------
INPUT_DIR=""
OUTPUT=""
SORT_BY="run"

while [[ $# -gt 0 ]]; do
    case "$1" in
        --input-dir)
            [[ $# -lt 2 ]] && { echo "Error: --input-dir needs a value" >&2; exit 1; }
            INPUT_DIR="$2"; shift 2
            ;;
        --output)
            [[ $# -lt 2 ]] && { echo "Error: --output needs a value" >&2; exit 1; }
            OUTPUT="$2"; shift 2
            ;;
        --sort-by)
            [[ $# -lt 2 ]] && { echo "Error: --sort-by needs a value" >&2; exit 1; }
            SORT_BY="$2"; shift 2
            ;;
        -h|--help)
            usage; exit 0
            ;;
        *)
            echo "Error: unknown argument: $1" >&2
            usage >&2
            exit 1
            ;;
    esac
done

case "$SORT_BY" in
    run|evaluated|date) ;;
    *) echo "Error: --sort-by must be one of: run, evaluated, date" >&2; exit 1 ;;
esac

# ---------- resolve dirs ----------
if [[ -z "$INPUT_DIR" ]]; then
    if [[ -d "metrics_output" ]]; then
        INPUT_DIR="metrics_output"
    else
        INPUT_DIR="$(dirname "$SCRIPT_DIR")/metrics_output"
    fi
fi

if [[ ! -d "$INPUT_DIR" ]]; then
    echo "Error: input directory not found: $INPUT_DIR" >&2
    exit 1
fi

if [[ -z "$OUTPUT" ]]; then
    OUTPUT="$INPUT_DIR/merged_metrics.txt"
fi

INPUT_ABS="$(abspath "$INPUT_DIR")"
OUTPUT_ABS="$(abspath "$OUTPUT")"

# ---------- collect files ----------
mapfile -t ALL_FILES < <(find "$INPUT_ABS" -name "metrics.txt" -type f | LC_ALL=C sort)

# Exclude the output file itself in case it is named metrics.txt
FILES=()
for f in "${ALL_FILES[@]}"; do
    if [[ "$(abspath "$f")" != "$OUTPUT_ABS" ]]; then
        FILES+=("$f")
    fi
done

if [[ ${#FILES[@]} -eq 0 ]]; then
    echo "No metrics.txt files found under $INPUT_ABS" >&2
    exit 1
fi

# ---------- parse ----------
CANONICAL=(PSNR LPIPS DISTS VMAF FID)
MISSING="N/A"

declare -a RUNS=()
declare -a EVALS=()
declare -a REFS=()
declare -a DATES=()
declare -a SEEN_METRICS=()
declare -A MEANS=()   # key: "<idx>__<metric>" -> value

seen_has() {
    local needle="$1"
    local m
    for m in "${SEEN_METRICS[@]}"; do
        [[ "$m" == "$needle" ]] && return 0
    done
    return 1
}

count=0
for f in "${FILES[@]}"; do
    # run = parent dir relative to input dir
    parent="$(dirname "$f")"
    if [[ "$parent" == "$INPUT_ABS" ]]; then
        run="."
    else
        run="${parent#"$INPUT_ABS"/}"
    fi

    evaluated="$(trim "$(grep -m1 '^Folder evaluated:' "$f" | cut -d: -f2- || true)")"
    reference="$(trim "$(grep -m1 '^Reference folder:' "$f" | cut -d: -f2- || true)")"
    date="$(trim "$(grep -m1 '^Date:' "$f" | cut -d: -f2- || true)")"
    header_line="$(grep -m1 -i '^filename' "$f" || true)"
    mean_line="$(grep -m1 '^MEAN' "$f" || true)"

    if [[ -z "$header_line" || -z "$mean_line" ]]; then
        echo "Warning: no MEAN row found in $f, skipping."
        continue
    fi

    # shellcheck disable=SC2206
    read -ra hparts <<<"$header_line"
    # shellcheck disable=SC2206
    read -ra mparts <<<"$mean_line"
    # drop leading token ("filename" / "MEAN")
    hnames=("${hparts[@]:1}")
    mvals=("${mparts[@]:1}")

    if [[ ${#hnames[@]} -ne ${#mvals[@]} ]]; then
        echo "Warning: header/mean length mismatch in $f, truncating to common length."
        n=${#hnames[@]}
        [[ ${#mvals[@]} -lt $n ]] && n=${#mvals[@]}
        hnames=("${hnames[@]:0:$n}")
        mvals=("${mvals[@]:0:$n}")
    fi

    idx=$count
    RUNS+=("$run")
    EVALS+=("$evaluated")
    REFS+=("$reference")
    DATES+=("$date")

    for i in "${!hnames[@]}"; do
        m="${hnames[$i]}"
        MEANS["${idx}__${m}"]="${mvals[$i]}"
        if ! seen_has "$m"; then
            SEEN_METRICS+=("$m")
        fi
    done
    count=$((count + 1))
done

if [[ $count -eq 0 ]]; then
    echo "No metrics.txt files with MEAN rows found under $INPUT_ABS" >&2
    exit 1
fi

# ---------- metric order: canonical first, extras appended ----------
METRIC_ORDER=()
for m in "${CANONICAL[@]}"; do
    if seen_has "$m"; then
        METRIC_ORDER+=("$m")
    fi
done
for m in "${SEEN_METRICS[@]}"; do
    skip=0
    for c in "${METRIC_ORDER[@]}"; do
        [[ "$c" == "$m" ]] && { skip=1; break; }
    done
    [[ $skip -eq 0 ]] && METRIC_ORDER+=("$m")
done

# ---------- column widths ----------
eval_w=16  # len("evaluated_folder")
run_w=3    # len("run")
for e in "${EVALS[@]}"; do
    [[ ${#e} -gt $eval_w ]] && eval_w=${#e}
done
for r in "${RUNS[@]}"; do
    [[ ${#r} -gt $run_w ]] && run_w=${#r}
done
[[ $eval_w -lt 20 ]] && eval_w=20
[[ $run_w -lt 20 ]] && run_w=20

metric_w=14
for m in "${METRIC_ORDER[@]}"; do
    [[ ${#m} -gt $metric_w ]] && metric_w=${#m}
done

# ---------- sort ----------
declare -a ORDER=()
case "$SORT_BY" in
    run)
        mapfile -t sorted_lines < <(
            for i in "${!RUNS[@]}"; do printf '%s\t%s\n' "${RUNS[$i]}" "$i"; done \
            | LC_ALL=C sort -t $'\t' -k1,1 -k2,2n
        )
        ;;
    evaluated)
        mapfile -t sorted_lines < <(
            for i in "${!RUNS[@]}"; do printf '%s\t%s\t%s\n' "${EVALS[$i]}" "${RUNS[$i]}" "$i"; done \
            | LC_ALL=C sort -t $'\t' -k1,1 -k2,2 -k3,3n
        )
        ;;
    date)
        mapfile -t sorted_lines < <(
            for i in "${!RUNS[@]}"; do printf '%s\t%s\t%s\n' "${DATES[$i]}" "${RUNS[$i]}" "$i"; done \
            | LC_ALL=C sort -t $'\t' -k1,1 -k2,2 -k3,3n
        )
        ;;
esac
for line in "${sorted_lines[@]}"; do
    ORDER+=("${line##*$'\t'}")
done

# ---------- build table ----------
printf -v header "%-${eval_w}s  %-${run_w}s" "evaluated_folder" "run"
for m in "${METRIC_ORDER[@]}"; do
    printf -v cell "%${metric_w}s" "$m"
    header+="  $cell"
done

rows=()
for idx in "${ORDER[@]}"; do
    printf -v row "%-${eval_w}s  %-${run_w}s" "${EVALS[$idx]}" "${RUNS[$idx]}"
    for m in "${METRIC_ORDER[@]}"; do
        val="${MEANS["${idx}__${m}"]:-$MISSING}"
        printf -v cell "%${metric_w}s" "$val"
        row+="  $cell"
    done
    rows+=("$row")
done

sep="$(printf '%*s' "${#header}" '' | tr ' ' '-')"
now="$(date '+%Y-%m-%d %H:%M:%S')"

# ---------- write ----------
{
    echo "Merged metrics ($count runs, $now)"
    echo "Source: $INPUT_ABS"
    echo "Each row = one metrics.txt MEAN row. First column is the evaluated folder (results/<name>)."
    echo ""
    echo "$header"
    echo "$sep"
    printf '%s\n' "${rows[@]}"
    echo "$sep"
    echo ""
    echo "Details per run:"
    for idx in "${ORDER[@]}"; do
        detail="  ${RUNS[$idx]}: ${EVALS[$idx]}"
        [[ -n "${REFS[$idx]}" ]] && detail+=", ref=${REFS[$idx]}"
        [[ -n "${DATES[$idx]}" ]] && detail+=", date=${DATES[$idx]}"
        echo "$detail"
    done
} > "$OUTPUT"

echo "Found $count metrics.txt files under $INPUT_ABS"
metrics_str=""
for m in "${METRIC_ORDER[@]}"; do
    [[ -n "$metrics_str" ]] && metrics_str+=", "
    metrics_str+="$m"
done
echo "Metrics: $metrics_str"
echo "Merged table written to: $OUTPUT"
