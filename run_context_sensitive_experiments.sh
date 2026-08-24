#!/usr/bin/env bash
set -euo pipefail
script_dir="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd -P)"
python_bin=${CONTEXT_EXPERIMENT_PYTHON:-python}
"$python_bin" "$script_dir/experiments/context_sensitive/core_experiment.py" "$@"
if [[ " $* " != *" --quick "* ]]; then
    "$python_bin" "$script_dir/experiments/context_sensitive/benchmark_experiment.py"
fi
