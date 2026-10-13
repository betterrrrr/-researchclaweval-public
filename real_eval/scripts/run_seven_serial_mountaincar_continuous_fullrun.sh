#!/usr/bin/env bash
set -euo pipefail

ROOT="${RESEARCHCLAWEVAL_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
source "$ROOT/real_eval/scripts/lib_real_eval.sh"
RUN_ID="${REAL_EVAL_RUN_ID:-seven-mountaincar-continuous-fullrun-$(date +%Y%m%d-%H%M%S)}"
BASE_RUN_ROOT="${REAL_EVAL_RUN_ROOT:-$ROOT/real_eval/runs/$RUN_ID}"
DEFAULT_CONFIG="${REAL_EVAL_FRAMEWORK_CONFIG:-$ROOT/real_eval/config/seven_mountaincar_continuous_gpt_fullrun_frameworks.json}"
PREFLIGHT_SCRIPT="${REAL_EVAL_PREFLIGHT_SCRIPT:-$ROOT/real_eval/scripts/preflight_seven_serial_mountaincar_continuous.sh}"
SUMMARY_FILE="$BASE_RUN_ROOT/serial_summary.md"
STATUS_FILE="$BASE_RUN_ROOT/serial_status.json"
TMP_LIST="$BASE_RUN_ROOT/frameworks.tsv"
CONTINUE_ON_FAILURE="${REAL_EVAL_CONTINUE_ON_FAILURE:-1}"
export REAL_EVAL_USE_REGISTRY="${REAL_EVAL_USE_REGISTRY:-1}"

mkdir -p "$BASE_RUN_ROOT"
for marker in babylm gave2 psydefdetect tdc_admet_tox tdc-admet-tox arc_wbe; do
  [[ "${RUN_ID,,}" != *"$marker"* ]] || { echo "refusing cross-topic run id marker: $marker" >&2; exit 9; }
  [[ "${BASE_RUN_ROOT,,}" != *"$marker"* ]] || { echo "refusing cross-topic run-root marker: $marker" >&2; exit 9; }
done

CONFIG="$(real_eval_select_framework_config "$ROOT" "$BASE_RUN_ROOT" "$DEFAULT_CONFIG" mountaincar_continuous fullrun)"
export REAL_EVAL_FRAMEWORK_CONFIG="$CONFIG"
export REAL_EVAL_TOPIC_ID="mountaincar_continuous"
export REAL_EVAL_MODE="fullrun"

if [[ "${REAL_EVAL_SKIP_PREFLIGHT:-0}" != "1" ]]; then
  bash "$PREFLIGHT_SCRIPT" | tee "$BASE_RUN_ROOT/preflight.jsonl"
fi
if [[ "${REAL_EVAL_DRY_RUN:-0}" == "1" ]]; then
  real_eval_write_serial_dry_run "$CONFIG" "$BASE_RUN_ROOT/dry_run.jsonl"
  exit 0
fi

real_eval_write_frameworks_tsv "$CONFIG" "$TMP_LIST"

{
  echo "# Seven MountainCar-Continuous Full-Run"
  echo
  echo "- Run ID: $RUN_ID"
  echo "- Started: $(date -Is)"
  echo "- Base Run Root: $BASE_RUN_ROOT"
  echo
  echo "| ID | Framework | Wrapper RC | Validator RC | Final Status | Notes |"
  echo "|---|---|---:|---:|---|---|"
} > "$SUMMARY_FILE"

declare -a status_rows=()
any_failure=0
while IFS=$'\t' read -r framework_id framework_name run_dir wrapper validator; do
  run_root="$BASE_RUN_ROOT/$run_dir"
  echo "=== START $framework_id $framework_name RUN_ROOT=$run_root ==="
  set +e
  RESEARCHCLAWEVAL_ROOT="$ROOT" REAL_EVAL_RUN_ID="$RUN_ID" REAL_EVAL_RUN_ROOT="$run_root" bash "$ROOT/$wrapper"
  wrapper_rc=$?
  set -e
  set +e
  python3 "$ROOT/real_eval/scripts/validate_framework_run.py" \
    --framework "$validator" --run-root "$run_root" --state-file "$run_root/state.json" > "$run_root/validator.json"
  validator_rc=$?
  set -e
  final_status="$(real_eval_state_status "$run_root/state.json")"
  notes="ok"
  if [[ "$validator_rc" -ne 0 ]]; then notes="validator_failed"; fi
  if [[ "$wrapper_rc" -ne 0 && "$validator_rc" -ne 0 ]]; then notes="wrapper_and_validator_failed"; elif [[ "$wrapper_rc" -ne 0 && "$validator_rc" -eq 0 ]]; then notes="wrapper_failed_but_state_valid"; fi
  printf '| %s | %s | %s | %s | %s | %s |\n' "$framework_id" "$framework_name" "$wrapper_rc" "$validator_rc" "$final_status" "$notes" >> "$SUMMARY_FILE"
  status_rows+=("{\"id\":\"$framework_id\",\"name\":\"$framework_name\",\"run_root\":\"$run_root\",\"wrapper_rc\":$wrapper_rc,\"validator_rc\":$validator_rc,\"status\":\"$final_status\",\"notes\":\"$notes\"}")
  if [[ "$validator_rc" -ne 0 ]]; then
    any_failure=1
    echo "=== FAIL $framework_id $framework_name ===" >&2
    if [[ "$CONTINUE_ON_FAILURE" != "1" ]]; then break; fi
  else
    echo "=== FINISH $framework_id $framework_name status=$final_status ==="
  fi
done < "$TMP_LIST"

real_eval_write_serial_status "$STATUS_FILE" "${status_rows[@]}"
echo >> "$SUMMARY_FILE"
echo "- Finished: $(date -Is)" >> "$SUMMARY_FILE"
[[ "$any_failure" -eq 0 ]]
