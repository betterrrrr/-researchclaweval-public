#!/usr/bin/env bash
set -euo pipefail

ROOT="${RESEARCHCLAWEVAL_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
source "$ROOT/real_eval/scripts/lib_real_eval.sh"
BASE="${REAL_EVAL_RUN_ROOT:?REAL_EVAL_RUN_ROOT is required}"
RUN_ID="${REAL_EVAL_RUN_ID:?REAL_EVAL_RUN_ID is required}"
FRAMEWORK_NAME="${FRAMEWORK_NAME:?FRAMEWORK_NAME is required}"
FRAMEWORK_SLUG="${FRAMEWORK_SLUG:?FRAMEWORK_SLUG is required}"
FRAMEWORK_SRC="${FRAMEWORK_SRC:?FRAMEWORK_SRC is required}"
FRAMEWORK_RUNTIME_KIND="${FRAMEWORK_RUNTIME_KIND:?FRAMEWORK_RUNTIME_KIND is required}"
FRAMEWORK_RUNTIME_IMAGE="${FRAMEWORK_RUNTIME_IMAGE:?FRAMEWORK_RUNTIME_IMAGE is required}"
FRAMEWORK_CONTAINER_WORKDIR="${FRAMEWORK_CONTAINER_WORKDIR:-/workspace}"
FRAMEWORK_CONTAINER_HOME="${FRAMEWORK_CONTAINER_HOME:-/workspace}"
FRAMEWORK_CONTAINER_CODEX_HOME="${FRAMEWORK_CONTAINER_CODEX_HOME:-/codex-home}"
FRAMEWORK_DOCKER_ARGS="${FRAMEWORK_DOCKER_ARGS:-}"
FRAMEWORK_ENTRYPOINT="${FRAMEWORK_ENTRYPOINT:-}"
FRAMEWORK_DISABLE_GPU="${FRAMEWORK_DISABLE_GPU:-0}"
DATASET_ROOT="${PSYDEFDETECT_DATASET_ROOT:-$(real_eval_resolve_topic_dataset "$ROOT" psydefdetect)}"
CONTRACT_FILE="${PSYDEFDETECT_CONTRACT_FILE:-$ROOT/automation/psydefdetect_contract.md}"
PROVIDER_CONFIG="${PROVIDER_CONFIG:-$ROOT/api/codex_gpt54_shubiaobiao.toml}"
SEMANTIC_SOURCE="${SEMANTIC_SOURCE:-$ROOT/api/_semantic_scholar_api_usage.md}"

WORKSPACE="$BASE/workspace"
INPUT_ROOT="$BASE/inputs"
RUNTIME_DATASET_ROOT="$INPUT_ROOT/data/psydefdetect"
RUNTIME_CONTRACT_FILE="$INPUT_ROOT/automation/psydefdetect_contract.md"
CODEX_HOME_DIR="$BASE/codex_home"
LOG_DIR="$BASE/logs"
LOG_FILE="$LOG_DIR/smoke.log"
STATE_FILE="$BASE/state.json"
MANIFEST_FILE="$BASE/smoke_manifest.json"
PROVIDER_ENV="$BASE/provider.env"
SEMANTIC_ENV="$BASE/semantic.env"
TEMPLATE_ARTIFACTS_BEFORE="$BASE/template_forbidden_artifacts.before"

check_template_clean() {
  if [[ -f "$TEMPLATE_ARTIFACTS_BEFORE" ]]; then
    real_eval_assert_no_new_forbidden_artifacts "$FRAMEWORK_SRC" "$TEMPLATE_ARTIFACTS_BEFORE"
  fi
}
trap check_template_clean EXIT

write_state() {
  local status="$1"
  local summary="$2"
  local exit_code="${3:-0}"
  python3 - "$STATE_FILE" "$status" "$summary" "$exit_code" <<'PY'
from datetime import datetime, timezone
from pathlib import Path
import json
import sys
payload = {
    "project_id": "psydefdetect",
    "phase": "smoke",
    "status": sys.argv[2],
    "summary": sys.argv[3],
    "updated_at": datetime.now(timezone.utc).astimezone().isoformat(),
    "exit_code": int(sys.argv[4]),
}
Path(sys.argv[1]).write_text(json.dumps(payload, ensure_ascii=False) + "\n", encoding="utf-8")
PY
}

real_eval_require_clean_dir "$BASE"
mkdir -p "$BASE" "$INPUT_ROOT" "$WORKSPACE" "$CODEX_HOME_DIR" "$LOG_DIR"
write_state "starting" "Initializing isolated PsyDefDetect smoke workspace"

if [[ ! -d "$DATASET_ROOT" ]]; then
  write_state "blocked" "Missing PsyDefDetect dataset root: $DATASET_ROOT" 21
  exit 21
fi
if [[ ! -f "$CONTRACT_FILE" ]]; then
  write_state "blocked" "Missing PsyDefDetect contract file: $CONTRACT_FILE" 22
  exit 22
fi
if [[ ! -d "$FRAMEWORK_SRC" ]]; then
  write_state "blocked" "Missing framework source: $FRAMEWORK_SRC" 23
  exit 23
fi

real_eval_snapshot_forbidden_artifacts "$FRAMEWORK_SRC" "$TEMPLATE_ARTIFACTS_BEFORE"
real_eval_rsync_repo "$FRAMEWORK_SRC" "$WORKSPACE"
real_eval_purge_cross_topic_residue "$WORKSPACE" psydefdetect
chmod -R a+rwX "$WORKSPACE"
mkdir -p "$(dirname "$RUNTIME_DATASET_ROOT")" "$(dirname "$RUNTIME_CONTRACT_FILE")"
real_eval_rsync_repo "$DATASET_ROOT" "$RUNTIME_DATASET_ROOT"
cp "$CONTRACT_FILE" "$RUNTIME_CONTRACT_FILE"
chmod -R a+rX "$INPUT_ROOT"
real_eval_provider_env_from_codex_toml "$PROVIDER_CONFIG" "$PROVIDER_ENV"
real_eval_semantic_env_from_usage_md "$SEMANTIC_SOURCE" "$SEMANTIC_ENV"
cp "$PROVIDER_CONFIG" "$CODEX_HOME_DIR/config.toml"
chmod 755 "$CODEX_HOME_DIR"
chmod 644 "$CODEX_HOME_DIR/config.toml"
mkdir -p "$WORKSPACE/data" "$WORKSPACE/automation"
ln -sfn "$DATASET_ROOT" "$WORKSPACE/data/psydefdetect"
cp "$CONTRACT_FILE" "$WORKSPACE/automation/psydefdetect_contract.md"
chmod -R a+rwX "$WORKSPACE"
chmod -R a+rX "$INPUT_ROOT"

declare -a docker_extra_args=()
if [[ -n "$FRAMEWORK_DOCKER_ARGS" ]]; then
  while IFS= read -r arg; do
    [[ -z "$arg" ]] && continue
    docker_extra_args+=("$arg")
  done <<< "$FRAMEWORK_DOCKER_ARGS"
fi

docker_smoke_command='set -euo pipefail
test -d "$RESEARCHCLAWEVAL_TOPIC_DATASET_ROOT"
test -f "$RESEARCHCLAWEVAL_TOPIC_CONTRACT_FILE"
test -w "$PWD"
python - <<'"'"'PY'"'"'
from pathlib import Path
root = Path("/workspace")
contract = Path("/input/psydefdetect_contract.md").read_text(encoding="utf-8", errors="ignore")
if "PsyDefDetect" not in contract:
    raise SystemExit("contract is not PsyDefDetect")
print("PsyDefDetect smoke checks passed")
PY'

{
  echo "[$(date -Is)] framework=$FRAMEWORK_NAME slug=$FRAMEWORK_SLUG"
  echo "workspace=$WORKSPACE"
  echo "dataset_root=$DATASET_ROOT"
  echo "contract_file=$CONTRACT_FILE"
  echo "runtime_image=$FRAMEWORK_RUNTIME_IMAGE"
} | tee "$LOG_FILE"

write_state "running" "Launching PsyDefDetect smoke Docker checks"
run_rc=0
set +e
declare -a docker_cmd=(
  docker run --rm
  --name "$(printf '%s' "$FRAMEWORK_SLUG-$RUN_ID-smoke" | tr -c 'A-Za-z0-9_.-' '-')"
)
if [[ "$FRAMEWORK_DISABLE_GPU" != "1" ]]; then
  docker_cmd+=(--gpus all)
fi
if [[ -n "$FRAMEWORK_ENTRYPOINT" ]]; then
  docker_cmd+=(--entrypoint "$FRAMEWORK_ENTRYPOINT")
fi
docker_cmd+=(
  "${docker_extra_args[@]}"
  --env-file "$PROVIDER_ENV"
  --env-file "$SEMANTIC_ENV"
  -e HOME="$FRAMEWORK_CONTAINER_HOME"
  -e CODEX_HOME="$FRAMEWORK_CONTAINER_CODEX_HOME"
  -e RESEARCHCLAWEVAL_TOPIC_LABEL=PsyDefDetect
  -e RESEARCHCLAWEVAL_TOPIC_DATASET_ROOT=/data/psydefdetect
  -e RESEARCHCLAWEVAL_TOPIC_CONTRACT_FILE=/input/psydefdetect_contract.md
  -e FRAMEWORK_NAME="$FRAMEWORK_NAME"
  -e FRAMEWORK_SLUG="$FRAMEWORK_SLUG"
  -e REAL_EVAL_RUN_ID="$RUN_ID"
  -e REAL_EVAL_RUN_ROOT="$BASE"
  -v "$WORKSPACE":$FRAMEWORK_CONTAINER_WORKDIR
  -v "$CODEX_HOME_DIR":$FRAMEWORK_CONTAINER_CODEX_HOME
  -v "$RUNTIME_DATASET_ROOT":/data/psydefdetect:ro
  -v "$RUNTIME_CONTRACT_FILE":/input/psydefdetect_contract.md:ro
  -w "$FRAMEWORK_CONTAINER_WORKDIR"
  "$FRAMEWORK_RUNTIME_IMAGE"
)
if [[ -n "$FRAMEWORK_ENTRYPOINT" && ( "$FRAMEWORK_ENTRYPOINT" == "bash" || "$FRAMEWORK_ENTRYPOINT" == "/bin/bash" || "$FRAMEWORK_ENTRYPOINT" == "sh" || "$FRAMEWORK_ENTRYPOINT" == "/bin/sh" ) ]]; then
  docker_cmd+=(-lc "$docker_smoke_command")
else
  docker_cmd+=(bash -lc "$docker_smoke_command")
fi
"${docker_cmd[@]}" 2>&1 | tee -a "$LOG_FILE"
run_rc=${PIPESTATUS[0]}
set -e

python3 - "$MANIFEST_FILE" "$FRAMEWORK_NAME" "$FRAMEWORK_SLUG" "$FRAMEWORK_RUNTIME_IMAGE" "$DATASET_ROOT" "$CONTRACT_FILE" "$run_rc" <<'PY'
from pathlib import Path
import json
import sys
checks = {
    "docker_exit_zero": int(sys.argv[7]) == 0,
    "dataset_mounted": True,
    "contract_mounted": True,
    "workspace_writable": True,
}
payload = {
    "framework": sys.argv[2],
    "slug": sys.argv[3],
    "image": sys.argv[4],
    "dataset_root": sys.argv[5],
    "contract_file": sys.argv[6],
    "checks": checks,
    "all_passed": all(checks.values()),
}
Path(sys.argv[1]).write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
PY

if [[ "$run_rc" -ne 0 ]]; then
  write_state "failed" "PsyDefDetect smoke Docker checks failed" "$run_rc"
  exit "$run_rc"
fi
write_state "finished" "PsyDefDetect smoke Docker checks passed" 0
