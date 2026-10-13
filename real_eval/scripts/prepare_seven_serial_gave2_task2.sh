#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="${RESEARCHCLAWEVAL_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
DATASET_SOURCE="${GAVE2_DATASET_SOURCE_ROOT:-${GAVE2_DATASET_ROOT:-$REPO_ROOT/GAVE2_preliminary}}"
cd "$REPO_ROOT"

mkdir -p data/gave2
if [[ "$DATASET_SOURCE" != "$REPO_ROOT/data/gave2/task2" ]]; then
  ln -sfn "$DATASET_SOURCE" data/gave2/task2
fi

python3 automation/scripts/generate_gave2_task2_native_inputs.py
python3 automation/scripts/validate_gave2_task2_setup.py

echo "prepared GAVE2 Task 2 native input pack"
