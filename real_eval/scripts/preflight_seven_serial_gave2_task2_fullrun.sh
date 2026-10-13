#!/usr/bin/env bash
set -euo pipefail

ROOT="${RESEARCHCLAWEVAL_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
source "$ROOT/real_eval/scripts/lib_real_eval.sh"
CONFIG="${REAL_EVAL_FRAMEWORK_CONFIG:-$ROOT/real_eval/config/seven_gave2_fullrun_frameworks.json}"
DATASET_ROOT="${GAVE2_DATASET_ROOT:-$(real_eval_resolve_topic_dataset "$ROOT" gave2_task2)}"
CONTRACT_FILE="${GAVE2_CONTRACT_FILE:-$ROOT/automation/gave2_task2_contract.md}"
PREP_SCRIPT="$ROOT/real_eval/scripts/prepare_seven_serial_gave2_task2.sh"

[[ -f "$CONFIG" ]] || { echo "missing config: $CONFIG" >&2; exit 2; }
bash "$PREP_SCRIPT" >/dev/null
[[ -d "$DATASET_ROOT" ]] || { echo "missing dataset root: $DATASET_ROOT" >&2; exit 3; }
[[ -f "$CONTRACT_FILE" ]] || { echo "missing contract file: $CONTRACT_FILE" >&2; exit 4; }
[[ -x "$ROOT/real_eval/scripts/gave2_framework_fullrun.sh" ]] || { echo "missing helper: real_eval/scripts/gave2_framework_fullrun.sh" >&2; exit 5; }

python3 - "$ROOT" "$CONFIG" <<'PY'
from pathlib import Path
import json
import sys
root = Path(sys.argv[1])
config = Path(sys.argv[2])
data = json.loads(config.read_text(encoding='utf-8'))
errors = []
for item in data['frameworks']:
    wrapper = root / item['wrapper']
    wrapper_ok = wrapper.exists()
    missing_paths = [p for p in item.get('required_paths', []) if not (root / p).exists()]
    row = {
        'id': item['id'],
        'name': item['name'],
        'wrapper': item['wrapper'],
        'wrapper_ok': wrapper_ok,
        'missing_paths': missing_paths,
    }
    print(json.dumps(row, ensure_ascii=False))
    if (not wrapper_ok) or missing_paths:
        errors.append(item['id'])
if errors:
    raise SystemExit(10)
PY
