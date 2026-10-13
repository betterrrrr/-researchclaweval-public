#!/usr/bin/env bash
set -euo pipefail

ROOT="${RESEARCHCLAWEVAL_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
source "$ROOT/real_eval/scripts/lib_real_eval.sh"
BASE_RUN_ROOT="${REAL_EVAL_RUN_ROOT:-$ROOT/real_eval/runs/preflight-mountaincar-continuous}"
DEFAULT_CONFIG="${REAL_EVAL_DEFAULT_CONFIG:-$ROOT/real_eval/config/mountaincar_continuous_smoke_frameworks.json}"
TOPIC_ID="${REAL_EVAL_TOPIC_ID:-mountaincar_continuous}"
MODE="${REAL_EVAL_MODE:-smoke}"
export REAL_EVAL_USE_REGISTRY="${REAL_EVAL_USE_REGISTRY:-1}"
mkdir -p "$BASE_RUN_ROOT"
CONFIG="$(real_eval_select_framework_config "$ROOT" "$BASE_RUN_ROOT" "$DEFAULT_CONFIG" "$TOPIC_ID" "$MODE")"
TOPIC_ROOT="${MOUNTAINCAR_CONTINUOUS_DATASET_ROOT:-$(real_eval_resolve_topic_dataset "$ROOT" mountaincar_continuous)}"
CONTRACT_FILE="${MOUNTAINCAR_CONTINUOUS_CONTRACT_FILE:-$ROOT/automation/mountaincar_continuous_contract.md}"

if [[ ! -f "$CONFIG" ]]; then echo "missing config: $CONFIG" >&2; exit 2; fi
if [[ ! -d "$TOPIC_ROOT" ]]; then echo "missing topic root: $TOPIC_ROOT" >&2; exit 3; fi
if [[ ! -f "$CONTRACT_FILE" ]]; then echo "missing contract file: $CONTRACT_FILE" >&2; exit 4; fi

python3 - "$ROOT" "$CONFIG" "$MODE" <<'PY'
from pathlib import Path
import json, sys
root = Path(sys.argv[1])
config = Path(sys.argv[2])
mode = sys.argv[3]
data = json.loads(config.read_text(encoding="utf-8"))
errors = []
for item in data["frameworks"]:
    wrapper = root / item["wrapper"]
    wrapper_ok = wrapper.exists()
    missing_paths = [p for p in item.get("required_paths", []) if not (root / p).exists()]
    row = {"id": item["id"], "name": item["name"], "mode": mode, "wrapper": item["wrapper"], "wrapper_ok": wrapper_ok, "missing_paths": missing_paths}
    if mode == "fullrun":
        wrapper_text = wrapper.read_text(encoding="utf-8", errors="ignore") if wrapper_ok else ""
        cross_topic = any(m in wrapper_text.lower() for m in ("gave2", "psydefdetect", "tdc_admet_tox", "babylm", "arc_wbe"))
        row.update({"cross_topic_wrapper": cross_topic})
        if cross_topic:
            errors.append(item["id"])
    print(json.dumps(row, ensure_ascii=False))
    if (not wrapper_ok) or missing_paths:
        errors.append(item["id"])
if errors:
    raise SystemExit(10)
PY
