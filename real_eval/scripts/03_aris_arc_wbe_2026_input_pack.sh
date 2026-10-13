#!/usr/bin/env bash
set -euo pipefail
ROOT="${RESEARCHCLAWEVAL_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
source "$ROOT/real_eval/scripts/lib_real_eval.sh"
BASE="${REAL_EVAL_RUN_ROOT:?REAL_EVAL_RUN_ROOT is required}"
FRAMEWORK_NAME="ARIS"
FRAMEWORK_SLUG="03_aris_arc_wbe_2026_input_pack"
DATASET_ROOT="${ARC_WBE_2026_DATASET_ROOT:-$(real_eval_resolve_topic_dataset "$ROOT" arc_wbe_2026)}"
CONTRACT_FILE="${ARC_WBE_2026_CONTRACT_FILE:-$ROOT/automation/arc_wbe_2026_contract.md}"
LOG_DIR="$BASE/logs"
LOG_FILE="$LOG_DIR/e2e.log"
STATE_FILE="$BASE/state.json"
MANIFEST_FILE="$BASE/native_pack_manifest.json"
ENTRY_PATHS=$(cat <<'EOF'
Auto-claude-code-research-in-sleep/ARC_WBE_2026_BRIEF.md
Auto-claude-code-research-in-sleep/.aris-codex-project/ARC_WBE_2026_BRIEF.md
docs/arc_wbe_2026_summary.md
automation/arc_wbe_2026_contract.md
EOF
)

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

python3 "$ROOT/automation/scripts/generate_arc_wbe_2026_native_inputs.py" \
  --output-root "$BASE/inputs" \
  --dataset-root "$DATASET_ROOT" \
  --contract-file "$CONTRACT_FILE" >/dev/null

{
  echo "[$(date -Is)] framework=$FRAMEWORK_NAME slug=$FRAMEWORK_SLUG"
  echo "dataset_root=$DATASET_ROOT"
  echo "contract_file=$CONTRACT_FILE"
} | tee "$LOG_FILE"

mapfile -t entries <<< "$ENTRY_PATHS"
declare -a copied=()
for rel in "${entries[@]}"; do
  [[ -z "$rel" ]] && continue
  if [[ ! -f "$BASE/inputs/$rel" ]]; then
    echo "missing generated input: $BASE/inputs/$rel" | tee -a "$LOG_FILE" >&2
    exit 23
  fi
  copied+=("inputs/$rel")
  echo "prepared=$rel" >> "$LOG_FILE"
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
    "framework": framework,
    "slug": slug,
    "dataset_root": dataset_root,
    "contract_file": contract_file,
    "copied_inputs": copied,
}
manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
state = {
    "status": "finished",
    "framework": framework,
    "slug": slug,
    "artifact_manifest": str(manifest_path),
    "summary": "ARC native input pack prepared",
}
state_path.write_text(json.dumps(state, ensure_ascii=False) + "\n", encoding="utf-8")
PY

echo "prepared native pack for $FRAMEWORK_NAME" | tee -a "$LOG_FILE"
