#!/usr/bin/env bash
set -euo pipefail

ROOT="${RESEARCHCLAWEVAL_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
source "$ROOT/real_eval/scripts/lib_real_eval.sh"
BASE_RUN_ROOT="${REAL_EVAL_RUN_ROOT:-$ROOT/real_eval/runs/preflight-arc-wbe-2026}"
DEFAULT_CONFIG="${REAL_EVAL_DEFAULT_CONFIG:-$ROOT/real_eval/config/arc_wbe_2026_input_pack_frameworks.json}"
TOPIC_ID="${REAL_EVAL_TOPIC_ID:-arc_wbe_2026}"
MODE="${REAL_EVAL_MODE:-input_pack}"
export REAL_EVAL_USE_REGISTRY="${REAL_EVAL_USE_REGISTRY:-1}"
mkdir -p "$BASE_RUN_ROOT"
CONFIG="$(real_eval_select_framework_config "$ROOT" "$BASE_RUN_ROOT" "$DEFAULT_CONFIG" "$TOPIC_ID" "$MODE")"
DATASET_ROOT="${ARC_WBE_2026_DATASET_ROOT:-$(real_eval_resolve_topic_dataset "$ROOT" arc_wbe_2026)}"
CONTRACT_FILE="${ARC_WBE_2026_CONTRACT_FILE:-$ROOT/automation/arc_wbe_2026_contract.md}"

if [[ ! -f "$CONFIG" ]]; then
  echo "missing config: $CONFIG" >&2
  exit 2
fi
if [[ ! -d "$DATASET_ROOT" ]]; then
  echo "missing dataset root: $DATASET_ROOT" >&2
  echo "prepare it with: python3 $ROOT/automation/scripts/prepare_arc_wbe_2026_dataset.py --output-root $DATASET_ROOT" >&2
  exit 3
fi
if [[ ! -f "$CONTRACT_FILE" ]]; then
  echo "missing contract file: $CONTRACT_FILE" >&2
  exit 4
fi

python3 - "$ROOT" "$CONFIG" "$MODE" <<'PY'
from pathlib import Path
import json
import sys

root = Path(sys.argv[1])
config = Path(sys.argv[2])
mode = sys.argv[3]
data = json.loads(config.read_text(encoding="utf-8"))
errors = []

for item in data["frameworks"]:
    wrapper = root / item["wrapper"]
    wrapper_ok = wrapper.exists()
    missing_paths = [p for p in item.get("required_paths", []) if not (root / p).exists()]
    row = {
        "id": item["id"],
        "name": item["name"],
        "mode": mode,
        "wrapper": item["wrapper"],
        "wrapper_ok": wrapper_ok,
        "missing_paths": missing_paths,
    }
    if mode == "fullrun":
        expected_status = item.get("expected_status")
        native_entrypoint = item.get("native_entrypoint")
        kimi_injection = item.get("kimi_injection")
        wrapper_text = wrapper.read_text(encoding="utf-8", errors="ignore") if wrapper_ok else ""
        native_metadata_ok = bool(
            expected_status == "unsupported_native_entrypoint"
            or (isinstance(native_entrypoint, str) and native_entrypoint.strip()
                and isinstance(kimi_injection, str) and kimi_injection.strip())
        )
        generic_codex = (
            "codex exec" in wrapper_text
            and "FRAMEWORK_EXECUTOR_KIND=\"framework_skill_executor\"" not in wrapper_text
            and "FRAMEWORK_EXECUTOR_KIND=\"official_framework_skill\"" not in wrapper_text
        )
        cross_topic = any(marker in wrapper_text.lower() for marker in ("gave2", "psydefdetect", "tdc_admet_tox", "babylm"))
        row.update({
            "native_entrypoint": native_entrypoint,
            "kimi_injection": kimi_injection,
            "native_metadata_ok": native_metadata_ok,
            "generic_codex_wrapper": generic_codex,
            "cross_topic_wrapper": cross_topic,
        })
        if not native_metadata_ok or generic_codex or cross_topic:
            errors.append(item["id"])
    print(json.dumps(row, ensure_ascii=False))
    if (not wrapper_ok) or missing_paths:
        errors.append(item["id"])

if errors:
    raise SystemExit(10)
PY
