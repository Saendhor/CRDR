# ./run_flip.sh <metrics_output/new_folder> <source>.png <folder_to_evaluate>

set -euo pipefail

if [ $# -lt 2 ]; then
	  echo "usage: $0 <folder_name> <reference_image> [test_dir]" >&2
	    exit 1
    fi

    folder_name="$1"
    reference="$2"                  # ← new variable
    test_dir="${3:-tests}"

    out_dir="metrics_output/$folder_name"
    mkdir -p "$out_dir"

    uv run flip -r "$reference" -t "$test_dir"/*.png \
	        -d "$out_dir" \
		    -c "$out_dir/my_metrics.csv" \
		        -v 1

    echo "Results written to: $out_dir"
