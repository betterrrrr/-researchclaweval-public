#!/usr/bin/env bash
set -euo pipefail

ROOT="${RESEARCHCLAWEVAL_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
source "$ROOT/real_eval/scripts/lib_real_eval.sh"
CONFIG="${REAL_EVAL_FRAMEWORK_CONFIG:-$ROOT/real_eval/config/seven_gave2_frameworks.json}"
DATASET_ROOT="${GAVE2_DATASET_ROOT:-$(real_eval_resolve_topic_dataset "$ROOT" gave2_task2)}"
CONTRACT_FILE="${GAVE2_CONTRACT_FILE:-$ROOT/automation/gave2_task2_contract.md}"
PREP_SCRIPT="$ROOT/real_eval/scripts/prepare_seven_serial_gave2_task2.sh"

if [[ ! -f "$CONFIG" ]]; then
  echo "missing config: $CONFIG" >&2
  exit 2
fi
bash "$PREP_SCRIPT" > /dev/null
if [[ ! -d "$DATASET_ROOT" ]]; then
  echo "missing dataset root: $DATASET_ROOT" >&2
  exit 3
fi
if [[ ! -f "$CONTRACT_FILE" ]]; then
  echo "missing contract file: $CONTRACT_FILE" >&2
  exit 4
fi

python3 - "$ROOT" "$CONFIG" <<'PY'
from pathlib import Path
import json
import sys

root = Path(sys.argv[1])
config = Path(sys.argv[2])
data = json.loads(config.read_text(encoding='utf-8'))
errors = []
rows = []
for item in data['frameworks']:
    wrapper = root / item['wrapper']
    wrapper_ok = wrapper.exists()
    missing_paths = []
    for rel_path in item.get('required_paths', []):
        p = root / rel_path
        if not p.exists():
            missing_paths.append(rel_path)
    rows.append({
        'id': item['id'],
        'name': item['name'],
        'wrapper': str(wrapper.relative_to(root)) if wrapper.exists() else item['wrapper'],
        'wrapper_ok': wrapper_ok,
        'missing_paths': missing_paths,
    })
    if (not wrapper_ok) or missing_paths:
        errors.append(item['id'])

for row in rows:
    print(json.dumps(row, ensure_ascii=False))

if errors:
    raise SystemExit(10)
PY
