#!/usr/bin/env bash
set -euo pipefail

ROOT="${RESEARCHCLAWEVAL_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
source "$ROOT/real_eval/scripts/lib_real_eval.sh"
BASE="${REAL_EVAL_RUN_ROOT:?REAL_EVAL_RUN_ROOT is required}"
RUN_ID="${REAL_EVAL_RUN_ID:?REAL_EVAL_RUN_ID is required}"
FRAMEWORK_NAME="${FRAMEWORK_NAME:?FRAMEWORK_NAME is required}"
FRAMEWORK_SLUG="${FRAMEWORK_SLUG:?FRAMEWORK_SLUG is required}"
FRAMEWORK_SRC="${FRAMEWORK_SRC:?FRAMEWORK_SRC is required}"
FRAMEWORK_ENTRY_PATHS="${FRAMEWORK_ENTRY_PATHS:?FRAMEWORK_ENTRY_PATHS is required}"
FRAMEWORK_RUNTIME_KIND="${FRAMEWORK_RUNTIME_KIND:?FRAMEWORK_RUNTIME_KIND is required}"
FRAMEWORK_RUNTIME_IMAGE="${FRAMEWORK_RUNTIME_IMAGE:?FRAMEWORK_RUNTIME_IMAGE is required}"
FRAMEWORK_RUNTIME_COMMAND="${FRAMEWORK_RUNTIME_COMMAND:?FRAMEWORK_RUNTIME_COMMAND is required}"
FRAMEWORK_CONTAINER_WORKDIR="${FRAMEWORK_CONTAINER_WORKDIR:-/workspace}"
FRAMEWORK_CONTAINER_HOME="${FRAMEWORK_CONTAINER_HOME:-/workspace}"
FRAMEWORK_CONTAINER_CODEX_HOME="${FRAMEWORK_CONTAINER_CODEX_HOME:-/codex-home}"
FRAMEWORK_DOCKER_ARGS="${FRAMEWORK_DOCKER_ARGS:-}"
FRAMEWORK_ENTRYPOINT="${FRAMEWORK_ENTRYPOINT:-}"
FRAMEWORK_DISABLE_GPU="${FRAMEWORK_DISABLE_GPU:-0}"
FRAMEWORK_NATIVE_ENTRYPOINT="${FRAMEWORK_NATIVE_ENTRYPOINT:?FRAMEWORK_NATIVE_ENTRYPOINT is required}"
FRAMEWORK_PROVIDER_INJECTION="${FRAMEWORK_PROVIDER_INJECTION:?FRAMEWORK_PROVIDER_INJECTION is required}"
FRAMEWORK_NATIVE_LOG_MARKER="${FRAMEWORK_NATIVE_LOG_MARKER:?FRAMEWORK_NATIVE_LOG_MARKER is required}"
FRAMEWORK_EXECUTOR_KIND="${FRAMEWORK_EXECUTOR_KIND:-framework_cli}"
FRAMEWORK_COMMAND_LABEL="${FRAMEWORK_COMMAND_LABEL:-$FRAMEWORK_NATIVE_ENTRYPOINT}"
FRAMEWORK_LOG_FORBIDDEN_PATTERN="${FRAMEWORK_LOG_FORBIDDEN_PATTERN:-}"
HOST_NODE_ROOT="${REAL_EVAL_HOST_NODE_ROOT:-$(dirname "$(dirname "$(command -v node)")")}"
CONTAINER_NODE_ROOT="/opt/researchclaweval-node"
DATASET_ROOT="${BABYLM_DATASET_ROOT:-$(real_eval_resolve_topic_dataset "$ROOT" babylm)}"
CONTRACT_FILE="${BABYLM_CONTRACT_FILE:-$ROOT/automation/babylm_method_free_contract.md}"
PROVIDER_CONFIG="${PROVIDER_CONFIG:-$ROOT/api/codex_gpt54_shubiaobiao.toml}"
EVAL_MODEL="${BABYLM_MODEL:-$(sed -n 's/^[[:space:]]*model[[:space:]]*=[[:space:]]*"\(.*\)"[[:space:]]*$/\1/p' "$PROVIDER_CONFIG" | head -1)}"
PROVIDER_BASE_URL="$(sed -n 's/^[[:space:]]*base_url[[:space:]]*=[[:space:]]*"\(.*\)"[[:space:]]*$/\1/p' "$PROVIDER_CONFIG" | head -1)"
FRAMEWORK_PROVIDER_BASE_URL="${PROVIDER_BASE_URL%/}"
if [[ "$FRAMEWORK_PROVIDER_BASE_URL" != */v1 ]]; then
  FRAMEWORK_PROVIDER_BASE_URL="$FRAMEWORK_PROVIDER_BASE_URL/v1"
fi
SEMANTIC_SOURCE="${SEMANTIC_SOURCE:-$ROOT/api/_semantic_scholar_api_usage.md}"

WORKSPACE="$BASE/workspace"
INPUT_ROOT="$BASE/inputs"
RUNTIME_DATASET_ROOT="$INPUT_ROOT/data/BabyLM-2026-Strict-Small"
RUNTIME_CONTRACT_FILE="$INPUT_ROOT/automation/babylm_contract.md"
CODEX_HOME_DIR="$BASE/codex_home"
LOG_DIR="$BASE/logs"
LOG_FILE="$LOG_DIR/e2e.log"
STATE_FILE="$BASE/state.json"
MANIFEST_FILE="$BASE/fullrun_manifest.json"
ARTIFACT_MANIFEST="$BASE/artifact_manifest.json"
PROVIDER_ENV="$BASE/provider.env"
SEMANTIC_ENV="$BASE/semantic.env"
TEMPLATE_ARTIFACTS_BEFORE="$BASE/template_forbidden_artifacts.before"
repo_basename="$(basename "$FRAMEWORK_SRC")"
entry_prefix="${FRAMEWORK_ENTRY_PREFIX:-$repo_basename}"

check_template_clean() {
  if [[ -f "$TEMPLATE_ARTIFACTS_BEFORE" ]]; then
    real_eval_assert_no_new_forbidden_artifacts "$FRAMEWORK_SRC" "$TEMPLATE_ARTIFACTS_BEFORE"
  fi
}
trap 'check_template_clean; docker ps -q --filter "name=ai_researcher_babylm_" | xargs -r docker rm -f' EXIT

write_state() {
  local status="$1"
  local summary="$2"
  local exit_code="${3:-0}"
  python3 - "$STATE_FILE" "$status" "$summary" "$exit_code" "$ARTIFACT_MANIFEST" <<'PY'
from datetime import datetime, timezone
from pathlib import Path
import json
import sys
payload = {
    "project_id": "babylm",
    "phase": "fullrun",
    "status": sys.argv[2],
    "summary": sys.argv[3],
    "updated_at": datetime.now(timezone.utc).astimezone().isoformat(),
    "exit_code": int(sys.argv[4]),
    "artifact_manifest": sys.argv[5],
}
Path(sys.argv[1]).write_text(json.dumps(payload, ensure_ascii=False) + "\n", encoding="utf-8")
PY
}

real_eval_require_clean_dir "$BASE"
mkdir -p "$BASE" "$INPUT_ROOT" "$WORKSPACE" "$CODEX_HOME_DIR" "$LOG_DIR"
write_state "starting" "Initializing BabyLM GPT full-run workspace"

if [[ ! -d "$DATASET_ROOT" ]]; then
  write_state "blocked" "Missing BabyLM dataset root: $DATASET_ROOT" 21
  exit 21
fi
if [[ ! -f "$CONTRACT_FILE" ]]; then
  write_state "blocked" "Missing BabyLM contract file: $CONTRACT_FILE" 22
  exit 22
fi
if [[ -z "$EVAL_MODEL" ]]; then
  write_state "blocked" "Unable to determine evaluation model from $PROVIDER_CONFIG" 26
  exit 26
fi
if [[ ! -d "$FRAMEWORK_SRC" ]]; then
  write_state "blocked" "Missing framework source: $FRAMEWORK_SRC" 23
  exit 23
fi
if [[ ! -x "$HOST_NODE_ROOT/bin/codex" ]]; then
  write_state "blocked" "Missing host Codex CLI under $HOST_NODE_ROOT/bin/codex" 25
  exit 25
fi

python3 "$ROOT/automation/scripts/generate_babylm_native_inputs.py" \
  --output-root "$INPUT_ROOT" \
  --dataset-root "$DATASET_ROOT" \
  --contract-file "$CONTRACT_FILE" \
  --provider-base-url "${FRAMEWORK_PROVIDER_BASE_URL:-https://api.openai.com/v1}" \
  --primary-model "$EVAL_MODEL" >/dev/null

real_eval_snapshot_forbidden_artifacts "$FRAMEWORK_SRC" "$TEMPLATE_ARTIFACTS_BEFORE"
real_eval_rsync_repo "$FRAMEWORK_SRC" "$WORKSPACE"
real_eval_purge_cross_topic_residue "$WORKSPACE" babylm
chmod -R a+rwX "$WORKSPACE"
if [ -f "$ROOT/real_eval_contract_tools.py" ]; then
  cp "$ROOT/real_eval_contract_tools.py" "$WORKSPACE/real_eval_contract_tools.py"
fi
mkdir -p "$(dirname "$RUNTIME_DATASET_ROOT")" "$(dirname "$RUNTIME_CONTRACT_FILE")"
real_eval_rsync_repo "$DATASET_ROOT" "$RUNTIME_DATASET_ROOT"
cp "$CONTRACT_FILE" "$RUNTIME_CONTRACT_FILE"
chmod -R a+rX "$INPUT_ROOT"
real_eval_provider_env_from_codex_toml "$PROVIDER_CONFIG" "$PROVIDER_ENV"
real_eval_semantic_env_from_usage_md "$SEMANTIC_SOURCE" "$SEMANTIC_ENV"
cp "$PROVIDER_CONFIG" "$CODEX_HOME_DIR/config.toml"
chmod 700 "$CODEX_HOME_DIR"
chmod 600 "$CODEX_HOME_DIR/config.toml"

mapfile -t entry_paths <<< "$FRAMEWORK_ENTRY_PATHS"
declare -a copied_inputs_json_parts=()
for rel in "${entry_paths[@]}"; do
  [[ -z "$rel" ]] && continue
  workspace_rel="$rel"
  if [[ "$workspace_rel" == "$entry_prefix/"* ]]; then
    workspace_rel="${workspace_rel#${entry_prefix}/}"
    src="$FRAMEWORK_SRC/$workspace_rel"
  else
    src="$ROOT/$rel"
  fi
  if [[ -f "$INPUT_ROOT/$rel" ]]; then
    src="$INPUT_ROOT/$rel"
  fi
  if [[ ! -f "$src" ]]; then
    write_state "blocked" "Missing required input file: $src" 24
    exit 24
  fi
  dst="$WORKSPACE/$workspace_rel"
  input_dst="$INPUT_ROOT/$workspace_rel"
  mkdir -p "$(dirname "$dst")" "$(dirname "$input_dst")"
  cp "$src" "$dst"
  if [[ "$src" != "$input_dst" ]]; then
    cp "$src" "$input_dst"
  fi
  copied_inputs_json_parts+=("$(python3 - <<'PY' "$rel" "$workspace_rel"
import json, sys
print(json.dumps({"source_rel": sys.argv[1], "workspace_rel": sys.argv[2]}, ensure_ascii=False))
PY
)")
done
chmod -R a+rwX "$WORKSPACE"
chmod -R a+rX "$INPUT_ROOT"

COPIED_INPUTS_JSON="[$(IFS=,; echo "${copied_inputs_json_parts[*]}")]"
python3 - "$MANIFEST_FILE" "$FRAMEWORK_NAME" "$FRAMEWORK_SLUG" "$FRAMEWORK_RUNTIME_IMAGE" "$DATASET_ROOT" "$CONTRACT_FILE" "$WORKSPACE" "$COPIED_INPUTS_JSON" "$FRAMEWORK_RUNTIME_COMMAND" "$FRAMEWORK_NATIVE_ENTRYPOINT" "$FRAMEWORK_PROVIDER_INJECTION" "$FRAMEWORK_NATIVE_LOG_MARKER" "$FRAMEWORK_EXECUTOR_KIND" "$FRAMEWORK_COMMAND_LABEL" "$EVAL_MODEL" "$FRAMEWORK_PROVIDER_BASE_URL" <<'PY'
from pathlib import Path
import json
import sys
payload = {
    "framework": sys.argv[2],
    "slug": sys.argv[3],
    "runtime_kind": "docker",
    "runtime_image": sys.argv[4],
    "dataset_root": sys.argv[5],
    "contract_file": sys.argv[6],
    "workspace": sys.argv[7],
    "copied_inputs": json.loads(sys.argv[8]),
    "runtime_command": sys.argv[9],
    "framework_orchestration": True,
    "native_entrypoint": sys.argv[10],
    "provider_injection": sys.argv[11],
    "native_log_marker": sys.argv[12],
    "executor_kind": sys.argv[13],
    "command_label": sys.argv[14],
    "evaluation_model": sys.argv[15],
    "provider_base_url": sys.argv[16],
    "required_outputs": ["research_idea.json", "experiment_trace.json", "final_report.md", "submission_artifacts"],
}
Path(sys.argv[1]).write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
PY

declare -a docker_extra_args=()
if [[ -n "$FRAMEWORK_DOCKER_ARGS" ]]; then
  while IFS= read -r arg; do
    [[ -z "$arg" ]] && continue
    docker_extra_args+=("$arg")
  done <<< "$FRAMEWORK_DOCKER_ARGS"
fi
declare -a docker_host_args=()
if grep -q 'host\.docker\.internal' "$PROVIDER_ENV" 2>/dev/null \
  || [[ "$FRAMEWORK_DOCKER_ARGS" == *host.docker.internal* ]] \
  || [[ "$FRAMEWORK_RUNTIME_COMMAND" == *host.docker.internal* ]]; then
  docker_host_args+=(--add-host=host.docker.internal:host-gateway)
fi
docker_runtime_command='export PATH="/opt/researchclaweval-node/bin:$PATH"; '"$FRAMEWORK_RUNTIME_COMMAND"

{
  echo "[$(date -Is)] framework=$FRAMEWORK_NAME slug=$FRAMEWORK_SLUG"
  echo "workspace=$WORKSPACE"
  echo "dataset_root=$DATASET_ROOT"
  echo "contract_file=$CONTRACT_FILE"
  echo "runtime_image=$FRAMEWORK_RUNTIME_IMAGE"
  echo "e2e_command=$FRAMEWORK_COMMAND_LABEL"
  echo "native_entrypoint=$FRAMEWORK_NATIVE_ENTRYPOINT"
  echo "provider_injection=$FRAMEWORK_PROVIDER_INJECTION"
  echo "native_log_marker=$FRAMEWORK_NATIVE_LOG_MARKER"
  echo "executor_kind=$FRAMEWORK_EXECUTOR_KIND"
} | tee "$LOG_FILE"

write_state "running" "Launching BabyLM framework-native full run"
run_rc=0
set +e
declare -a docker_cmd=(
  docker run --rm
  --name "$(printf '%s' "$FRAMEWORK_SLUG-$RUN_ID-fullrun" | tr -c 'A-Za-z0-9_.-' '-')"
  --ipc=host
  --ulimit memlock=-1
  --ulimit stack=67108864
  "${docker_host_args[@]}"
)
if [[ "$FRAMEWORK_DISABLE_GPU" != "1" ]]; then
  docker_cmd+=(--gpus "${FRAMEWORK_GPUS:-all}")
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
  -e RESEARCHCLAWEVAL_HOST_WORKSPACE="$WORKSPACE"
  -e RESEARCHCLAWEVAL_TOPIC_HOST_DATASET_ROOT="$DATASET_ROOT"
  -e RESEARCHCLAWEVAL_TOPIC_HOST_CONTRACT_FILE="$CONTRACT_FILE"
  -e RESEARCHCLAWEVAL_TOPIC_LABEL=BabyLM-10M
  -e COMPLETION_MODEL="openai/${EVAL_MODEL:-gpt-5.4}"
  -e RESEARCHCLAWEVAL_TOPIC_DATASET_ROOT=/data/BabyLM-2026-Strict-Small
  -e RESEARCHCLAWEVAL_TOPIC_CONTRACT_FILE=/input/babylm_contract.md
  -e FRAMEWORK_NAME="$FRAMEWORK_NAME"
  -e FRAMEWORK_SLUG="$FRAMEWORK_SLUG"
  -e FRAMEWORK_NATIVE_LOG_MARKER="$FRAMEWORK_NATIVE_LOG_MARKER"
  -e HF_ENDPOINT=https://hf-mirror.com
  -e BABYLM_MODEL="$EVAL_MODEL"
  -e BABYLM_FRAMEWORK_TIMEOUT="${BABYLM_FRAMEWORK_TIMEOUT:-3600}"
  -e BABYLM_IDEA_TIMEOUT="${BABYLM_IDEA_TIMEOUT:-3600}"
  -e BABYLM_EXPERIMENT_TIMEOUT="${BABYLM_EXPERIMENT_TIMEOUT:-7200}"
  -e BABYLM_WRITE_TIMEOUT="${BABYLM_WRITE_TIMEOUT:-3600}"
  -e REAL_EVAL_RUN_ID="$RUN_ID"
  -e REAL_EVAL_RUN_ROOT="$BASE"
  # 2026-10-10: ACPClient 的 per-prompt 预算是 os.environ["ACP_TIMEOUT_SEC"]
  # 优先，缺省则回落 config.py:1155 的 1800s。这个白名单原先不含该项，
  # 所以 babylm 无论 launcher 把 ACP_TIMEOUT_SEC 设成多少都只有 1800s ——
  # F04×babylm×Kimi 正是以 "ACP prompt timed out after 1800s" 收场。
  # 与 v2 协议里 opencode.timeout_sec / ACP_TIMEOUT_SEC 的预算调整同类。
  -e ACP_TIMEOUT_SEC="${ACP_TIMEOUT_SEC:-3600}"
  -e ACP_SESSION_TIMEOUT_SEC="${ACP_SESSION_TIMEOUT_SEC:-180}"
  -v "$WORKSPACE":$FRAMEWORK_CONTAINER_WORKDIR
  -v "$HOST_NODE_ROOT":$CONTAINER_NODE_ROOT:ro
  -v "$CODEX_HOME_DIR":$FRAMEWORK_CONTAINER_CODEX_HOME
  -v "$RUNTIME_DATASET_ROOT":/data/BabyLM-2026-Strict-Small:ro
  -v "$RUNTIME_CONTRACT_FILE":/input/babylm_contract.md:ro
  -w "$FRAMEWORK_CONTAINER_WORKDIR"
  "$FRAMEWORK_RUNTIME_IMAGE"
)
if [[ -n "$FRAMEWORK_ENTRYPOINT" && ( "$FRAMEWORK_ENTRYPOINT" == "bash" || "$FRAMEWORK_ENTRYPOINT" == "/bin/bash" || "$FRAMEWORK_ENTRYPOINT" == "sh" || "$FRAMEWORK_ENTRYPOINT" == "/bin/sh" ) ]]; then
  docker_cmd+=(-lc "$docker_runtime_command")
else
  docker_cmd+=(bash -lc "$docker_runtime_command")
fi
"${docker_cmd[@]}" 2>&1 \
  | python3 "$ROOT/real_eval/scripts/redact_env_secrets.py" \
      --env-file "$PROVIDER_ENV" --env-file "$SEMANTIC_ENV" \
  | tee -a "$LOG_FILE"
run_rc=${PIPESTATUS[0]}
set -e

if [[ "$run_rc" -eq 0 ]] && ! rg -Fq "$FRAMEWORK_NATIVE_LOG_MARKER" "$LOG_FILE"; then
  echo "missing framework-native log marker: $FRAMEWORK_NATIVE_LOG_MARKER" | tee -a "$LOG_FILE"
  run_rc=41
fi

if [[ "$run_rc" -eq 0 && -n "$FRAMEWORK_LOG_FORBIDDEN_PATTERN" ]] && rg -q "$FRAMEWORK_LOG_FORBIDDEN_PATTERN" "$LOG_FILE"; then
  echo "framework log contains a prohibited runtime action" | tee -a "$LOG_FILE"
  run_rc=43
fi

if [[ "$run_rc" -eq 0 ]]; then
  python3 - "$WORKSPACE" "$EVAL_MODEL" <<'PY'
from __future__ import annotations

import json
import sys
from pathlib import Path

workspace = Path(sys.argv[1])
expected_model = sys.argv[2]
required_paths = {
    "research_idea": workspace / "research_idea.json",
    "final_report": workspace / "final_report.md",
    "experiment_trace": workspace / "experiment_trace.json",
}
missing = [name for name, path in required_paths.items() if not path.exists()]
if missing:
    raise SystemExit("missing required artifacts: " + ", ".join(missing))

trace = json.loads((workspace / "experiment_trace.json").read_text(encoding="utf-8"))
if not isinstance(trace, dict):
    raise SystemExit("experiment_trace.json must be a JSON object")
idea = json.loads((workspace / "research_idea.json").read_text(encoding="utf-8"))
if not isinstance(idea, dict):
    raise SystemExit("research_idea.json must be a JSON object")
for key in ("hypothesis", "method_rationale", "expected_failure_modes", "comparison_logic"):
    value = idea.get(key)
    if key == "method_rationale" and (not isinstance(value, str) or not value.strip()):
        # ARIS framework uses "rationale" instead of "method_rationale"
        value = idea.get("rationale")
    if not isinstance(value, str) or not value.strip():
        raise SystemExit(f"research_idea.json must contain non-empty {key}")
if (workspace / "research_idea.json").stat().st_mtime_ns >= (
    workspace / "experiment_trace.json"
).stat().st_mtime_ns:
    raise SystemExit("research_idea.json must be locked before experiment_trace.json")
if trace.get("framework_native_execution") is not True:
    raise SystemExit("experiment_trace.json must set framework_native_execution=true")
if trace.get("consumed_topic_input") is not True:
    raise SystemExit("experiment_trace.json must set consumed_topic_input=true")
experiments = trace.get("experiments")
if not isinstance(experiments, list) or len(experiments) < 2:
    raise SystemExit("experiment_trace.json must record at least 2 experiments")
if len(experiments) > 4:
    raise SystemExit("experiment_trace.json may record at most 4 experiments")
if trace.get("framework_internal_model") != expected_model:
    raise SystemExit(f"experiment_trace.json must set framework_internal_model={expected_model}")
if not isinstance(trace.get("framework_internal_api_base_url"), str) or not trace["framework_internal_api_base_url"].strip():
    raise SystemExit("experiment_trace.json must include framework_internal_api_base_url")
selected_experiment_id = trace.get("selected_experiment_id")
if (
    isinstance(selected_experiment_id, bool)
    or not isinstance(selected_experiment_id, (str, int))
    or (isinstance(selected_experiment_id, str) and not selected_experiment_id.strip())
):
    raise SystemExit("experiment_trace.json must include selected_experiment_id")
if not isinstance(trace.get("workspace_trace_root"), str) or not trace["workspace_trace_root"].strip():
    raise SystemExit("experiment_trace.json must include workspace_trace_root")
PY
fi

mkdir -p "$BASE/artifacts"
python3 - "$ARTIFACT_MANIFEST" "$FRAMEWORK_NAME" "$FRAMEWORK_SLUG" "$DATASET_ROOT" "$CONTRACT_FILE" "$WORKSPACE" "$BASE/artifacts" "$LOG_FILE" <<'PY'
from pathlib import Path
import json
import sys
workspace = Path(sys.argv[6])
artifacts = Path(sys.argv[7])
def first_existing(paths):
    for path in paths:
        if path.exists():
            return path
    return None
report = first_existing([workspace / "final_report.md", artifacts / "final_report.md"])
research_idea = first_existing([workspace / "research_idea.json", artifacts / "research_idea.json"])
experiment_trace = first_existing([workspace / "experiment_trace.json", artifacts / "experiment_trace.json"])
payload = {
    "framework": sys.argv[2],
    "slug": sys.argv[3],
    "dataset_root": sys.argv[4],
    "contract_file": sys.argv[5],
    "workspace": str(workspace),
    "final_report": str(report) if report else None,
    "research_idea": str(research_idea) if research_idea else None,
    "experiment_trace": str(experiment_trace) if experiment_trace else None,
    "log": sys.argv[8],
}
Path(sys.argv[1]).write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
PY

if [[ "$run_rc" -ne 0 ]]; then
  write_state "failed" "BabyLM framework-native full run exited non-zero; see log" "$run_rc"
  exit "$run_rc"
fi
write_state "finished" "BabyLM framework-native full run exited successfully" 0
