#!/usr/bin/env bash
set -euo pipefail

ROOT="${RESEARCHCLAWEVAL_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
source "$ROOT/real_eval/scripts/lib_real_eval.sh"
RUN_ID="${REAL_EVAL_RUN_ID:-seven-psydefdetect-smoke-$(date +%Y%m%d-%H%M%S)}"
BASE_RUN_ROOT="${REAL_EVAL_RUN_ROOT:-$ROOT/real_eval/runs/$RUN_ID}"
DEFAULT_CONFIG="$ROOT/real_eval/config/seven_psydefdetect_smoke_frameworks.json"
PREFLIGHT_SCRIPT="${REAL_EVAL_PREFLIGHT_SCRIPT:-$ROOT/real_eval/scripts/preflight_seven_serial_psydefdetect.sh}"
SUMMARY_FILE="$BASE_RUN_ROOT/serial_summary.md"
STATUS_FILE="$BASE_RUN_ROOT/serial_status.json"
TMP_LIST="$BASE_RUN_ROOT/frameworks.tsv"
CONTINUE_ON_FAILURE="${REAL_EVAL_CONTINUE_ON_FAILURE:-0}"

mkdir -p "$BASE_RUN_ROOT"
CONFIG="$(real_eval_select_framework_config "$ROOT" "$BASE_RUN_ROOT" "$DEFAULT_CONFIG" psydefdetect smoke)"

if [[ "${REAL_EVAL_SKIP_PREFLIGHT:-0}" != "1" ]]; then
  REAL_EVAL_MODE=smoke REAL_EVAL_DEFAULT_CONFIG="$DEFAULT_CONFIG" bash "$PREFLIGHT_SCRIPT" | tee "$BASE_RUN_ROOT/preflight.jsonl"
fi

if [[ "${REAL_EVAL_DRY_RUN:-0}" == "1" ]]; then
  real_eval_write_serial_dry_run "$CONFIG" "$BASE_RUN_ROOT/dry_run.jsonl"
  exit 0
fi

real_eval_write_frameworks_tsv "$CONFIG" "$TMP_LIST"
if [[ -n "${REAL_EVAL_FRAMEWORK_IDS:-}" ]]; then
  python3 - "$TMP_LIST" "$REAL_EVAL_FRAMEWORK_IDS" <<'PY'
from pathlib import Path
import sys

path = Path(sys.argv[1])
allowed = {item.strip() for item in sys.argv[2].split(",") if item.strip()}
rows = path.read_text(encoding="utf-8").splitlines()
if not allowed:
    raise SystemExit("REAL_EVAL_FRAMEWORK_IDS must contain at least one framework id")
missing = allowed - {row.split("\t", 1)[0] for row in rows}
if missing:
    raise SystemExit("Unknown framework ids: " + ", ".join(sorted(missing)))
path.write_text(
    "\n".join(row for row in rows if row.split("\t", 1)[0] in allowed) + "\n",
    encoding="utf-8",
)
PY
fi

{
  echo "# Seven PsyDefDetect Smoke Run"
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
  python3 "$ROOT/real_eval/scripts/validate_framework_run.py" --framework "$validator" --run-root "$run_root" --state-file "$run_root/state.json" > "$run_root/validator.json"
  validator_rc=$?
  set -e

  final_status="$(real_eval_state_status "$run_root/state.json")"
  notes="ok"
  if [[ "$validator_rc" -ne 0 ]]; then
    notes="validator_failed"
  fi
  if [[ "$wrapper_rc" -ne 0 && "$validator_rc" -ne 0 ]]; then
    notes="wrapper_and_validator_failed"
  elif [[ "$wrapper_rc" -ne 0 && "$validator_rc" -eq 0 ]]; then
    notes="wrapper_failed_but_state_valid"
  fi

  printf '| %s | %s | %s | %s | %s | %s |\n' "$framework_id" "$framework_name" "$wrapper_rc" "$validator_rc" "$final_status" "$notes" >> "$SUMMARY_FILE"
  status_rows+=("{\"id\":\"$framework_id\",\"name\":\"$framework_name\",\"run_root\":\"$run_root\",\"wrapper_rc\":$wrapper_rc,\"validator_rc\":$validator_rc,\"status\":\"$final_status\",\"notes\":\"$notes\"}")

  if [[ "$validator_rc" -ne 0 ]]; then
    any_failure=1
    if [[ "$CONTINUE_ON_FAILURE" != "1" ]]; then
      break
    fi
  fi
done < "$TMP_LIST"

real_eval_write_serial_status "$STATUS_FILE" "${status_rows[@]}"
echo >> "$SUMMARY_FILE"
echo "- Finished: $(date -Is)" >> "$SUMMARY_FILE"
[[ "$any_failure" -eq 0 ]]
