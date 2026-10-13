#!/usr/bin/env bash
set -euo pipefail
ROOT="${RESEARCHCLAWEVAL_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
source "$ROOT/real_eval/scripts/lib_real_eval.sh"
BASE="${REAL_EVAL_RUN_ROOT:?REAL_EVAL_RUN_ROOT is required}"
FRAMEWORK_NAME="AI-Scientist-v2"
FRAMEWORK_SLUG="02_ai_scientist_v2_topic2_smoke"
TOPIC_ROOT="${TOPIC2_DATASET_ROOT:-$(real_eval_resolve_topic_dataset "$ROOT" topic2)}"
CONTRACT_FILE="${TOPIC2_CONTRACT_FILE:-$ROOT/automation/topic2_contract.md}"
LOG_DIR="$BASE/logs"
LOG_FILE="$LOG_DIR/smoke.log"
STATE_FILE="$BASE/state.json"
MANIFEST_FILE="$BASE/smoke_manifest.json"

real_eval_require_clean_dir "$BASE"
mkdir -p "$BASE/inputs" "$LOG_DIR"
[[ -d "$TOPIC_ROOT" ]] || { echo "missing topic root: $TOPIC_ROOT" >&2; exit 21; }
[[ -f "$CONTRACT_FILE" ]] || { echo "missing contract file: $CONTRACT_FILE" >&2; exit 22; }

python3 "$ROOT/automation/scripts/generate_topic2_native_inputs.py" \
  --output-root "$BASE/inputs" \
  --dataset-root "$TOPIC_ROOT" \
  --contract-file "$CONTRACT_FILE" >/dev/null

# Verify the framework's topic evidence was generated
python3 - "$BASE/inputs" <<'PY'
from pathlib import Path
import sys
inputs = Path(sys.argv[1])
required = ["docs/topic2_summary.md", "automation/topic2_contract.md", "automation/topic2_execution_budget.md", "starter/src/train.py", "starter/src/config.yaml", "protected/evaluate.py"]
missing = [r for r in required if not (inputs / r).is_file()]
if missing:
    raise SystemExit("missing generated inputs: " + ", ".join(missing))
print("smoke inputs present:", len(required), "files")
PY

{
  echo "[$(date -Is)] framework=$FRAMEWORK_NAME slug=$FRAMEWORK_SLUG"
  echo "topic_root=$TOPIC_ROOT"
  echo "contract_file=$CONTRACT_FILE"
} | tee "$LOG_FILE"

python3 - "$MANIFEST_FILE" "$STATE_FILE" "$FRAMEWORK_NAME" "$FRAMEWORK_SLUG" "$TOPIC_ROOT" "$CONTRACT_FILE" <<'PY'
from pathlib import Path
import json, sys
manifest = {
    "framework": sys.argv[3],
    "slug": sys.argv[4],
    "topic_root": sys.argv[5],
    "contract_file": sys.argv[6],
    "checks": {"topic_inputs_generated": True},
    "all_passed": True,
}
Path(sys.argv[1]).write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
state = {"status": "finished", "framework": sys.argv[3], "slug": sys.argv[4], "artifact_manifest": str(Path(sys.argv[1])), "summary": "MountainCar smoke inputs validated"}
Path(sys.argv[2]).write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
PY
