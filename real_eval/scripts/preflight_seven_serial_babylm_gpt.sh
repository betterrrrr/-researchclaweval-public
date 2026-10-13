#!/usr/bin/env bash
set -euo pipefail

ROOT="${RESEARCHCLAWEVAL_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
source "$ROOT/real_eval/scripts/lib_real_eval.sh"
BASE_RUN_ROOT="${REAL_EVAL_RUN_ROOT:-$ROOT/real_eval/runs/preflight-babylm-gpt}"
DEFAULT_CONFIG="${REAL_EVAL_DEFAULT_CONFIG:-$ROOT/real_eval/config/seven_babylm_gpt_method_free_20260810_frameworks.json}"
CONFIG="${REAL_EVAL_FRAMEWORK_CONFIG:-$DEFAULT_CONFIG}"
DATASET_ROOT="${BABYLM_DATASET_ROOT:-$(real_eval_resolve_topic_dataset "$ROOT" babylm)}"
CONTRACT_FILE="${BABYLM_CONTRACT_FILE:-$ROOT/automation/babylm_method_free_contract.md}"
PROVIDER_CONFIG="${PROVIDER_CONFIG:-$ROOT/api/codex_gpt54_shubiaobiao.toml}"
EVAL_MODEL="${BABYLM_MODEL:-$(sed -n 's/^[[:space:]]*model[[:space:]]*=[[:space:]]*"\(.*\)"[[:space:]]*$/\1/p' "$PROVIDER_CONFIG" | head -1)}"

mkdir -p "$BASE_RUN_ROOT"

if [[ ! -f "$CONFIG" ]]; then
  echo "missing config: $CONFIG" >&2
  exit 2
fi
if [[ ! -d "$DATASET_ROOT" ]]; then
  echo "missing dataset root: $DATASET_ROOT" >&2
  exit 3
fi
if [[ ! -f "$CONTRACT_FILE" ]]; then
  echo "missing contract file: $CONTRACT_FILE" >&2
  exit 4
fi
if [[ ! -f "$PROVIDER_CONFIG" ]]; then
  echo "missing provider config: $PROVIDER_CONFIG" >&2
  exit 5
fi

python3 - "$ROOT" "$CONFIG" "$DATASET_ROOT" "$CONTRACT_FILE" "$PROVIDER_CONFIG" "$EVAL_MODEL" <<'PY'
from pathlib import Path
import json
import sys

root = Path(sys.argv[1])
config = Path(sys.argv[2])
dataset_root = Path(sys.argv[3])
contract_file = Path(sys.argv[4])
provider_config = Path(sys.argv[5])
effective_model = sys.argv[6]
data = json.loads(config.read_text(encoding="utf-8"))
errors = []

declared_variant = data.get("evaluation_variant")
configured_model = data.get("model")
if effective_model.startswith("gpt-"):
    variant = "gpt"
elif effective_model == "deepseek-v4-flash":
    variant = "deepseek"
else:
    variant = declared_variant
if declared_variant not in {None, variant}:
    errors.append("evaluation_variant_model_mismatch")
if variant == "gpt":
    if provider_config != root / "api/codex_gpt54_shubiaobiao.toml":
        errors.append("gpt_provider_config")
    if configured_model != "gpt-5.4" or effective_model != "gpt-5.4":
        errors.append("gpt_model")

dataset_files = [p for p in dataset_root.rglob("*") if p.is_file()]
recognized_suffixes = {".json", ".jsonl", ".csv", ".tsv", ".txt", ".parquet", ".bin", ".model"}
recognized_files = [p for p in dataset_files if p.suffix.lower() in recognized_suffixes]
dataset_ok = bool(recognized_files)
contract_text = contract_file.read_text(encoding="utf-8", errors="ignore")
contract_ok = "BabyLM" in contract_text and "perplexity" in contract_text

for item in data["frameworks"]:
    wrapper = root / item["wrapper"]
    wrapper_ok = wrapper.exists()
    wrapper_text = wrapper.read_text(encoding="utf-8", errors="ignore") if wrapper_ok else ""
    missing_paths = [rel_path for rel_path in item.get("required_paths", []) if not (root / rel_path).exists()]
    wrong_topic = any(marker in wrapper_text.lower() for marker in ["gave2", "arc_wbe_2026", "psydefdetect", "tdc_admet_tox"])
    row = {
        "id": item["id"],
        "name": item["name"],
        "wrapper": item["wrapper"],
        "wrapper_ok": wrapper_ok,
        "dataset_ok": dataset_ok,
        "contract_ok": contract_ok,
        "wrong_topic": wrong_topic,
        "missing_paths": missing_paths,
        "recognized_dataset_file_count": len(recognized_files),
    }
    print(json.dumps(row, ensure_ascii=False))
    if (
        not wrapper_ok
        or missing_paths
        or wrong_topic
        or not dataset_ok
        or not contract_ok
    ):
        errors.append(item["id"])

if errors:
    raise SystemExit(10)
PY