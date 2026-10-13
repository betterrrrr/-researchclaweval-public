#!/usr/bin/env bash
set -euo pipefail
ROOT="${RESEARCHCLAWEVAL_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
source "$ROOT/real_eval/scripts/lib_real_eval.sh"
BASE="${REAL_EVAL_RUN_ROOT:?REAL_EVAL_RUN_ROOT is required}"
FRAMEWORK_NAME="EvoScientist"
FRAMEWORK_SLUG="07_evoscientist_arc_wbe_2026_smoke"
DATASET_ROOT="${ARC_WBE_2026_DATASET_ROOT:-$(real_eval_resolve_topic_dataset "$ROOT" arc_wbe_2026)}"
CONTRACT_FILE="${ARC_WBE_2026_CONTRACT_FILE:-$ROOT/automation/arc_wbe_2026_contract.md}"
LOG_DIR="$BASE/logs"
LOG_FILE="$LOG_DIR/smoke.log"
STATE_FILE="$BASE/state.json"
MANIFEST_FILE="$BASE/smoke_manifest.json"
TOPIC_EVIDENCE="inputs/EvoScientist/EVOSCIENTIST_BRIEF.md"
START_MESSAGE="inputs/EvoScientist/arc_wbe_2026_start_message.txt"

real_eval_require_clean_dir "$BASE"
mkdir -p "$BASE/inputs" "$LOG_DIR"

[[ -d "$DATASET_ROOT" ]] || { echo "missing dataset root: $DATASET_ROOT" >&2; exit 21; }
[[ -f "$CONTRACT_FILE" ]] || { echo "missing contract file: $CONTRACT_FILE" >&2; exit 22; }

python3 "$ROOT/automation/scripts/generate_arc_wbe_2026_native_inputs.py" \
  --output-root "$BASE/inputs" \
  --dataset-root "$DATASET_ROOT" \
  --contract-file "$CONTRACT_FILE" >/dev/null

test -f "$BASE/$TOPIC_EVIDENCE"
test -f "$BASE/$START_MESSAGE"
grep -q 'ARC-WBE-2026' "$BASE/$TOPIC_EVIDENCE"
grep -q 'Start ARC-WBE-2026' "$BASE/$START_MESSAGE"

{
  echo "[$(date -Is)] framework=$FRAMEWORK_NAME slug=$FRAMEWORK_SLUG"
  echo "dataset_root=$DATASET_ROOT"
  echo "contract_file=$CONTRACT_FILE"
  echo "topic_evidence=$TOPIC_EVIDENCE"
} | tee "$LOG_FILE"

python3 - "$MANIFEST_FILE" "$STATE_FILE" "$FRAMEWORK_NAME" "$FRAMEWORK_SLUG" "$DATASET_ROOT" "$CONTRACT_FILE" "$TOPIC_EVIDENCE" "$START_MESSAGE" <<'PY'
from pathlib import Path
import json
import sys

manifest_path = Path(sys.argv[1])
state_path = Path(sys.argv[2])
framework = sys.argv[3]
slug = sys.argv[4]
dataset_root = sys.argv[5]
contract_file = sys.argv[6]
topic_evidence = sys.argv[7]
start_message = sys.argv[8]
checks = {"brief_exists": True, "start_message_exists": True, "start_message_mentions_arc": True}
manifest = {
    "framework": framework,
    "slug": slug,
    "dataset_root": dataset_root,
    "contract_file": contract_file,
    "topic_evidence": topic_evidence,
    "start_message": start_message,
    "checks": checks,
    "all_passed": all(checks.values()),
}
manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
state = {
    "status": "finished",
    "framework": framework,
    "slug": slug,
    "artifact_manifest": str(manifest_path),
    "summary": "ARC smoke topic evidence validated",
}
state_path.write_text(json.dumps(state, ensure_ascii=False) + "\n", encoding="utf-8")
PY
