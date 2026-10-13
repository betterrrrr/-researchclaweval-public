#!/usr/bin/env bash
set -euo pipefail

ROOT="${RESEARCHCLAWEVAL_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
source "$ROOT/real_eval/scripts/lib_real_eval.sh"
CONFIG="${REAL_EVAL_FRAMEWORK_CONFIG:-$ROOT/real_eval/config/seven_tdc_admet_tox_gpt_smoke_frameworks.json}"
EVAL_VARIANT="$(python3 - "$CONFIG" <<'PY'
import json, sys
print(json.load(open(sys.argv[1], encoding="utf-8")).get("evaluation_variant", "gpt"))
PY
)"
EVAL_MODEL="$(python3 - "$CONFIG" <<'PY'
import json, sys
print(json.load(open(sys.argv[1], encoding="utf-8")).get("model", "gpt-5.4"))
PY
)"
DATASET_ROOT="${TDC_ADMET_TOX_DATASET_ROOT:-$ROOT/data/tdc_admet_tox/public}"
if [[ "$EVAL_VARIANT" == "ds" ]]; then
  PROVIDER_CONFIG="${PROVIDER_CONFIG:-$ROOT/api/codex_deepseek_v4_flash_bianxie_relay_host.toml}"
  RUN_ID="${REAL_EVAL_RUN_ID:-topic5-tdc-admet-tox-ds-smoke-$(date +%Y%m%d-%H%M%S)}"
else
  PROVIDER_CONFIG="${PROVIDER_CONFIG:-$ROOT/api/codex_gpt54_shubiaobiao.toml}"
  RUN_ID="${REAL_EVAL_RUN_ID:-topic5-tdc-admet-tox-gpt-smoke-$(date +%Y%m%d-%H%M%S)}"
fi
BASE_RUN_ROOT="${REAL_EVAL_RUN_ROOT:-$ROOT/real_eval/runs/$RUN_ID}"
SUMMARY_FILE="$BASE_RUN_ROOT/serial_summary.md"
STATUS_FILE="$BASE_RUN_ROOT/serial_status.json"
TMP_LIST="$BASE_RUN_ROOT/frameworks.tsv"
CONTINUE_ON_FAILURE="${REAL_EVAL_CONTINUE_ON_FAILURE:-1}"

mkdir -p "$BASE_RUN_ROOT"
python3 "$ROOT/real_eval/scripts/preflight_seven_serial_tdc_admet_tox.py" \
  --root "$ROOT" \
  --config "$CONFIG" \
  --mode smoke \
  --dataset-root "$DATASET_ROOT" \
  --provider-config "$PROVIDER_CONFIG" > "$BASE_RUN_ROOT/preflight.json"

if [[ "${REAL_EVAL_DRY_RUN:-0}" == "1" ]]; then
  real_eval_write_serial_dry_run "$CONFIG" "$BASE_RUN_ROOT/dry_run.jsonl"
  exit 0
fi
real_eval_write_frameworks_tsv "$CONFIG" "$TMP_LIST"

{
  echo "# Seven TDC-ADMET-Tox ${EVAL_VARIANT^^} Smoke"
  echo
  echo "- Run ID: $RUN_ID"
  echo "- Variant: $EVAL_VARIANT / $EVAL_MODEL"
  echo "- Started: $(date -Is)"
  echo "- Execution: blocking codex exec diagnostics only"
  echo
  echo "| ID | Framework | Wrapper RC | Validator RC | Status |"
  echo "|---|---|---:|---:|---|"
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
  final_status="$(real_eval_state_status "$run_root/state.json")"
  printf '| %s | %s | %s | %s | %s |\n' \
    "$framework_id" "$framework_name" "$wrapper_rc" "$validator_rc" "$final_status" >> "$SUMMARY_FILE"
  status_rows+=("{\"id\":\"$framework_id\",\"name\":\"$framework_name\",\"run_root\":\"$run_root\",\"wrapper_rc\":$wrapper_rc,\"validator_rc\":$validator_rc,\"status\":\"$final_status\"}")
  if [[ "$validator_rc" -ne 0 ]]; then
    any_failure=1
    [[ "$CONTINUE_ON_FAILURE" == "1" ]] || break
  fi
done < "$TMP_LIST"

real_eval_write_serial_status "$STATUS_FILE" "${status_rows[@]}"
echo >> "$SUMMARY_FILE"
echo "- Finished: $(date -Is)" >> "$SUMMARY_FILE"
[[ "$any_failure" -eq 0 ]]
