#!/usr/bin/env bash
set -euo pipefail

ROOT="${RESEARCHCLAWEVAL_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
source "$ROOT/real_eval/scripts/lib_real_eval.sh"
BASE="${REAL_EVAL_RUN_ROOT:?REAL_EVAL_RUN_ROOT is required}"
FRAMEWORK_NAME="${FRAMEWORK_NAME:?FRAMEWORK_NAME is required}"
FRAMEWORK_SLUG="${FRAMEWORK_SLUG:?FRAMEWORK_SLUG is required}"
ENTRY_PATHS="${ENTRY_PATHS:?ENTRY_PATHS is required}"
DATASET_ROOT="${GAVE2_DATASET_ROOT:-$(real_eval_resolve_topic_dataset "$ROOT" gave2_task2)}"
CONTRACT_FILE="${GAVE2_CONTRACT_FILE:-$ROOT/automation/gave2_task2_contract.md}"
LOG_DIR="$BASE/logs"
LOG_FILE="$LOG_DIR/e2e.log"
STATE_FILE="$BASE/state.json"
MANIFEST_FILE="$BASE/native_pack_manifest.json"

real_eval_require_clean_dir "$BASE"

mkdir -p "$BASE/inputs" "$LOG_DIR"

if [[ ! -d "$DATASET_ROOT" ]]; then
  echo "missing dataset root: $DATASET_ROOT" >&2
  exit 21
fi
if [[ ! -f "$CONTRACT_FILE" ]]; then
  echo "missing contract file: $CONTRACT_FILE" >&2
  exit 22
fi

if [[ ! -f "$ROOT/automation/gave2_task2_manifest.json" ]]; then
  bash "$ROOT/real_eval/scripts/prepare_seven_serial_gave2_task2.sh" >/dev/null
fi

{
  echo "[$(date -Is)] framework=$FRAMEWORK_NAME slug=$FRAMEWORK_SLUG"
  echo "dataset_root=$DATASET_ROOT"
  echo "contract_file=$CONTRACT_FILE"
} | tee "$LOG_FILE"

mapfile -t entries <<< "$ENTRY_PATHS"
declare -a copied=()
for rel in "${entries[@]}"; do
  [[ -z "$rel" ]] && continue
  src="$ROOT/$rel"
  dst="$BASE/inputs/$rel"
  if [[ ! -f "$src" ]]; then
    echo "missing source input: $src" | tee -a "$LOG_FILE" >&2
    exit 23
  fi
  mkdir -p "$(dirname "$dst")"
  cp "$src" "$dst"
  copied+=("inputs/$rel")
  echo "copied=$rel" >> "$LOG_FILE"
done

python3 - "$MANIFEST_FILE" "$STATE_FILE" "$FRAMEWORK_NAME" "$FRAMEWORK_SLUG" "$DATASET_ROOT" "$CONTRACT_FILE" "${copied[@]}" <<'PY'
from pathlib import Path
import json
import sys

manifest_path = Path(sys.argv[1])
state_path = Path(sys.argv[2])
framework = sys.argv[3]
slug = sys.argv[4]
dataset_root = sys.argv[5]
contract_file = sys.argv[6]
copied = sys.argv[7:]
manifest = {
    'framework': framework,
    'slug': slug,
    'dataset_root': dataset_root,
    'contract_file': contract_file,
    'copied_inputs': copied,
}
manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding='utf-8')
state = {
    'status': 'finished',
    'framework': framework,
    'slug': slug,
    'artifact_manifest': str(manifest_path),
    'summary': 'GAVE2 native input pack prepared',
}
state_path.write_text(json.dumps(state, ensure_ascii=False) + "\n", encoding='utf-8')
PY

echo "prepared native pack for $FRAMEWORK_NAME" | tee -a "$LOG_FILE"
