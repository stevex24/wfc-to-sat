#!/usr/bin/env bash

set -euo pipefail

die() {
    printf 'compare_sat_wfc: %s\n' "$*" >&2
    exit 2
}

if [[ $# -ne 1 ]]; then
    die "usage: $0 path/to/image.png"
fi

script_dir="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd -P)"
input_image=$1
python_bin=${COMPARE_SAT_WFC_PYTHON:-python}

[[ -f "$input_image" ]] || die "input image not found: $input_image"
command -v "$python_bin" >/dev/null 2>&1 || die "Python executable not found: $python_bin"

for required_program in \
    "$script_dir/export_visualizer_instance.py" \
    "$script_dir/solve_trace.py" \
    "$script_dir/play_trace.py"
do
    [[ -f "$required_program" ]] || die "required program not found: $required_program"
done

if ! "$python_bin" -c 'from PIL import Image' >/dev/null 2>&1; then
    die "Pillow is not installed; run: $python_bin -m pip install -r \"$script_dir/requirements.txt\""
fi
if ! "$python_bin" -c 'import pysat; from pysat.solvers import Cadical195' >/dev/null 2>&1; then
    die "PySAT with Cadical195 is not installed; run: $python_bin -m pip install -r \"$script_dir/requirements.txt\""
fi

image_dir="$(CDPATH= cd -- "$(dirname -- "$input_image")" && pwd -P)"
image_file="$(basename -- "$input_image")"
image_path="$image_dir/$image_file"
image_stem=${image_file%.*}
[[ -n "$image_stem" ]] || die "could not derive an output name from: $image_file"

output_prefix="$image_dir/$image_stem-n3-8x8"
cnf_path="$output_prefix.cnf"
mapping_path="$output_prefix.map.json"
solver_trace="$output_prefix-solver.jsonl.gz"
wfc_trace="$output_prefix-wfc.jsonl.gz"

printf 'Compiling %s with N=3 onto an 8x8 placement grid...\n' "$image_path"
if ! "$python_bin" "$script_dir/export_visualizer_instance.py" "$image_path" \
    --pattern-size 3 \
    --width 8 \
    --height 8 \
    --output-prefix "$output_prefix"
then
    die "image preprocessing or CNF export failed"
fi

printf 'Recording the SAT/CDCL solver trace...\n'
if ! "$python_bin" "$script_dir/solve_trace.py" "$cnf_path" \
    --mapping "$mapping_path" \
    --output "$solver_trace" \
    --heuristic solver \
    --watchable
then
    die "SAT/CDCL trace generation failed"
fi

printf 'Recording the WFC-heuristic trace...\n'
if ! "$python_bin" "$script_dir/solve_trace.py" "$cnf_path" \
    --mapping "$mapping_path" \
    --output "$wfc_trace" \
    --heuristic wfc \
    --seed 7 \
    --watchable
then
    die "WFC trace generation failed"
fi

printf '\nGenerated files:\n'
printf '  %s\n' "$cnf_path" "$mapping_path" "$solver_trace" "$wfc_trace"
printf '\nSide-by-side visualizer command:\n  '
printf '%q ' "$python_bin" "$script_dir/play_trace.py" "$solver_trace" "$wfc_trace"
printf '\n'

if [[ ${COMPARE_SAT_WFC_NO_PLAYER:-0} == 1 ]]; then
    printf 'Visualizer launch skipped because COMPARE_SAT_WFC_NO_PLAYER=1.\n'
else
    exec "$python_bin" "$script_dir/play_trace.py" "$solver_trace" "$wfc_trace"
fi
