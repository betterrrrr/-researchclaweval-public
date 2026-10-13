#!/usr/bin/env bash
set -euo pipefail

ROOT="${RESEARCHCLAWEVAL_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
source "$ROOT/real_eval/scripts/lib_real_eval.sh"
CONFIG="${REAL_EVAL_FRAMEWORK_CONFIG:-$ROOT/real_eval/config/seven_tdc_admet_tox_kimi_fullrun_frameworks.json}"
EVAL_VARIANT="$(python3 - "$CONFIG" <<'PY'
import json, sys
print(json.load(open(sys.argv[1], encoding="utf-8")).get("evaluation_variant", "kimi"))
PY
)"
EVAL_MODEL="$(python3 - "$CONFIG" <<'PY'
import json, sys
print(json.load(open(sys.argv[1], encoding="utf-8")).get("model", "kimi-k2.6"))
PY
)"
DATASET_ROOT="${TDC_ADMET_TOX_DATASET_ROOT:-$ROOT/data/tdc_admet_tox/public}"
HIDDEN_LABELS_ROOT="${TDC_ADMET_TOX_HIDDEN_LABELS_ROOT:?TDC_ADMET_TOX_HIDDEN_LABELS_ROOT is required}"
SMOKE_GATE_ROOT="${TDC_ADMET_TOX_SMOKE_GATE_ROOT:?TDC_ADMET_TOX_SMOKE_GATE_ROOT is required}"
PROVIDER_CONFIG="${PROVIDER_CONFIG:-$ROOT/api/codex_kimi_k27_code_relay_container.toml}"
RUN_ID="${REAL_EVAL_RUN_ID:-topic5-tdc-admet-tox-kimi-native-$(date +%Y%m%d-%H%M%S)}"
BASE_RUN_ROOT="${REAL_EVAL_RUN_ROOT:-$ROOT/real_eval/runs/$RUN_ID}"
SUMMARY_FILE="$BASE_RUN_ROOT/serial_summary.md"
STATUS_FILE="$BASE_RUN_ROOT/serial_status.json"
TMP_LIST="$BASE_RUN_ROOT/frameworks.tsv"
CONTINUE_ON_FAILURE="${REAL_EVAL_CONTINUE_ON_FAILURE:-1}"

mkdir -p "$BASE_RUN_ROOT"
if [[ "${REAL_EVAL_SKIP_PREFLIGHT:-0}" != "1" ]]; then
  python3 "$ROOT/real_eval/scripts/preflight_seven_serial_tdc_admet_tox.py" \
    --root "$ROOT" \
    --config "$CONFIG" \
    --mode fullrun \
    --dataset-root "$DATASET_ROOT" \
    --provider-config "$PROVIDER_CONFIG" \
    --hidden-labels-root "$HIDDEN_LABELS_ROOT" \
    --smoke-gate-root "$SMOKE_GATE_ROOT" > "$BASE_RUN_ROOT/preflight.json"
fi

if [[ "${REAL_EVAL_DRY_RUN:-0}" == "1" ]]; then
  real_eval_write_serial_dry_run "$CONFIG" "$BASE_RUN_ROOT/dry_run.jsonl"
  exit 0
fi
real_eval_write_frameworks_tsv "$CONFIG" "$TMP_LIST"

{
  echo "# Seven TDC-ADMET-Tox ${EVAL_VARIANT^^} Native Full Run"
  echo
  echo "- Run ID: $RUN_ID"
  echo "- Variant: $EVAL_VARIANT / $EVAL_MODEL"
  echo "- Started: $(date -Is)"
  echo "- Main ranking metric: macro AUROC over AMES, hERG, and DILI"
  echo "- Hidden labels: host-only scorer after framework audit"
  echo
  echo "| ID | Framework | Research | Scored | Contract | Engineering | Main Score | Validator |"
  echo "|---|---|---|---|---|---|---:|---|"
} > "$SUMMARY_FILE"

declare -a status_rows=()
any_failure=0
while IFS=$'\t' read -r framework_id framework_name run_dir wrapper validator; do
  run_root="$BASE_RUN_ROOT/$run_dir"
  set +e
  RESEARCHCLAWEVAL_ROOT="$ROOT" \
    REAL_EVAL_RUN_ID="$RUN_ID" \
    REAL_EVAL_RUN_ROOT="$run_root" \
    TDC_ADMET_TOX_DATASET_ROOT="$DATASET_ROOT" \
    TDC_ADMET_TOX_HIDDEN_LABELS_ROOT="$HIDDEN_LABELS_ROOT" \
    TDC_ADMET_TOX_CONTRACT_FILE="$ROOT/automation/tdc_admet_tox_contract.md" \
    TDC_ADMET_TOX_EVAL_MODEL="$EVAL_MODEL" \
    TDC_ADMET_TOX_EVAL_VARIANT="$EVAL_VARIANT" \
    PROVIDER_CONFIG="$PROVIDER_CONFIG" \
    bash "$ROOT/$wrapper"
  wrapper_rc=$?
  set -e

  set +e
  python3 "$ROOT/real_eval/scripts/validate_framework_run.py" \
    --framework "$validator" \
    --run-root "$run_root" \
    --state-file "$run_root/state.json" > "$run_root/validator.json"
  validator_rc=$?
  set -e

  result_tsv="$(python3 - "$run_root/state.json" "$run_root/workspace/score.json" <<'PY'
import json, sys
try:
    state = json.load(open(sys.argv[1], encoding="utf-8"))
except Exception:
    state = {}
try:
    score = json.load(open(sys.argv[2], encoding="utf-8"))
except Exception:
    score = {}
values = [
    str(state.get("research_completed", False)).lower(),
    str(state.get("scored", False)).lower(),
    str(state.get("contract_complete", False)).lower(),
    str(state.get("engineering_complete", False)).lower(),
    str(score.get("main_score", "N/A")),
    str(state.get("status", "unknown")),
]
print("\t".join(values))
PY
)"
  IFS=$'\t' read -r research scored contract engineering main_score final_status <<< "$result_tsv"
  printf '| %s | %s | %s | %s | %s | %s | %s | %s |\n' \
    "$framework_id" "$framework_name" "$research" "$scored" "$contract" \
    "$engineering" "$main_score" "$validator_rc" >> "$SUMMARY_FILE"
  status_rows+=("{\"id\":\"$framework_id\",\"name\":\"$framework_name\",\"run_root\":\"$run_root\",\"wrapper_rc\":$wrapper_rc,\"validator_rc\":$validator_rc,\"status\":\"$final_status\",\"research_completed\":$research,\"scored\":$scored,\"contract_complete\":$contract,\"engineering_complete\":$engineering,\"main_score\":\"$main_score\"}")
  if [[ "$validator_rc" -ne 0 ]]; then
    any_failure=1
    [[ "$CONTINUE_ON_FAILURE" == "1" ]] || break
  fi
done < "$TMP_LIST"

real_eval_write_serial_status "$STATUS_FILE" "${status_rows[@]}"
echo >> "$SUMMARY_FILE"
echo "- Finished: $(date -Is)" >> "$SUMMARY_FILE"
[[ "$any_failure" -eq 0 ]]