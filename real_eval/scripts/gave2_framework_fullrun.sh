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
FRAMEWORK_RUNTIME_IMAGE="${FRAMEWORK_RUNTIME_IMAGE:-}"
FRAMEWORK_RUNTIME_COMMAND="${FRAMEWORK_RUNTIME_COMMAND:-}"
FRAMEWORK_BLOCK_REASON="${FRAMEWORK_BLOCK_REASON:-}"
FRAMEWORK_CONTAINER_WORKDIR="${FRAMEWORK_CONTAINER_WORKDIR:-/workspace}"
FRAMEWORK_CONTAINER_HOME="${FRAMEWORK_CONTAINER_HOME:-/workspace}"
FRAMEWORK_CONTAINER_CODEX_HOME="${FRAMEWORK_CONTAINER_CODEX_HOME:-/codex-home}"
FRAMEWORK_DOCKER_ARGS="${FRAMEWORK_DOCKER_ARGS:-}"
FRAMEWORK_ENTRYPOINT="${FRAMEWORK_ENTRYPOINT:-}"
FRAMEWORK_HOST_HOME_DIR="${FRAMEWORK_HOST_HOME_DIR:-}"
FRAMEWORK_DISABLE_GPU="${FRAMEWORK_DISABLE_GPU:-0}"
DATASET_ROOT="${GAVE2_DATASET_ROOT:-$(real_eval_resolve_topic_dataset "$ROOT" gave2_task2)}"
CONTRACT_FILE="${GAVE2_CONTRACT_FILE:-$ROOT/automation/gave2_task2_contract.md}"
PROVIDER_CONFIG="${PROVIDER_CONFIG:-$ROOT/api/codex_gpt54_shubiaobiao.toml}"
SEMANTIC_SOURCE="${SEMANTIC_SOURCE:-$ROOT/api/_semantic_scholar_api_usage.md}"

WORKSPACE="$BASE/workspace"
INPUT_ROOT="$BASE/inputs"
CODEX_HOME_DIR="$BASE/codex_home"
LOG_DIR="$BASE/logs"
LOG_FILE="$LOG_DIR/e2e.log"
STATE_FILE="$BASE/state.json"
MANIFEST_FILE="$BASE/fullrun_manifest.json"
ARTIFACT_MANIFEST="$BASE/artifact_manifest.json"
PROVIDER_ENV="$BASE/provider.env"
SEMANTIC_ENV="$BASE/semantic.env"
PROMPT_FILE="$BASE/runtime_prompt.txt"
WORKSPACE_DATA_MOUNT="$FRAMEWORK_CONTAINER_WORKDIR/data/gave2/task2"
repo_basename="$(basename "$FRAMEWORK_SRC")"

real_eval_require_clean_dir "$BASE"
mkdir -p "$BASE" "$INPUT_ROOT" "$CODEX_HOME_DIR" "$LOG_DIR"
if [[ -n "$FRAMEWORK_HOST_HOME_DIR" ]]; then
  mkdir -p "$FRAMEWORK_HOST_HOME_DIR"
fi

write_state() {
  local status="$1"
  local summary="$2"
  local exit_code="${3:-0}"
  python3 - "$STATE_FILE" "$RUN_ID" "$FRAMEWORK_NAME" "$FRAMEWORK_SLUG" "$status" "$summary" "$WORKSPACE" "$LOG_FILE" "$MANIFEST_FILE" "$exit_code" <<'PY'
from pathlib import Path
import json
import sys
state_path = Path(sys.argv[1])
state = {
    "run_id": sys.argv[2],
    "framework": sys.argv[3],
    "slug": sys.argv[4],
    "status": sys.argv[5],
    "summary": sys.argv[6],
    "workspace": sys.argv[7],
    "log": sys.argv[8],
    "manifest": sys.argv[9],
    "exit_code": int(sys.argv[10]),
}
state_path.write_text(json.dumps(state, ensure_ascii=False) + "\n", encoding="utf-8")
PY
}

write_state "starting" "Initializing isolated GAVE2 full-run workspace"

if [[ "$RUN_ID" == *babylm* ]] || [[ "$BASE" == *babylm* ]] || [[ "$WORKSPACE" == *babylm* ]] || [[ "$CODEX_HOME_DIR" == *babylm* ]]; then
  write_state "blocked" "Refusing BabyLM-overlapping identifiers or paths" 9
  exit 9
fi
if [[ ! -d "$DATASET_ROOT" ]]; then
  write_state "blocked" "Missing GAVE2 dataset root: $DATASET_ROOT" 21
  exit 21
fi
if [[ ! -f "$CONTRACT_FILE" ]]; then
  write_state "blocked" "Missing GAVE2 contract file: $CONTRACT_FILE" 22
  exit 22
fi
if [[ ! -d "$FRAMEWORK_SRC" ]]; then
  write_state "blocked" "Missing framework source: $FRAMEWORK_SRC" 23
  exit 23
fi

real_eval_rsync_repo "$FRAMEWORK_SRC" "$WORKSPACE"
real_eval_purge_cross_topic_residue "$WORKSPACE" gave2
real_eval_provider_env_from_codex_toml "$PROVIDER_CONFIG" "$PROVIDER_ENV"
real_eval_semantic_env_from_usage_md "$SEMANTIC_SOURCE" "$SEMANTIC_ENV"
cp "$PROVIDER_CONFIG" "$CODEX_HOME_DIR/config.toml"
chmod 755 "$CODEX_HOME_DIR"
chmod 644 "$CODEX_HOME_DIR/config.toml"

mkdir -p "$WORKSPACE/data/gave2" "$WORKSPACE/automation" "$WORKSPACE/docs"
ln -sfn "$DATASET_ROOT" "$WORKSPACE/data/gave2/task2"
if [[ -d "$ROOT/baseline_repo" ]]; then
  ln -sfn "$ROOT/baseline_repo" "$WORKSPACE/baseline_repo"
else
  ln -sfn /baseline_repo "$WORKSPACE/baseline_repo"
fi
if [[ -d "$ROOT/refs" ]]; then
  ln -sfn "$ROOT/refs" "$WORKSPACE/refs"
fi

mapfile -t entry_paths <<< "$FRAMEWORK_ENTRY_PATHS"
declare -a copied_inputs_json_parts=()
declare -a copied_inputs_for_prompt=()
for rel in "${entry_paths[@]}"; do
  [[ -z "$rel" ]] && continue
  workspace_rel="$rel"
  if [[ "$workspace_rel" == "$repo_basename/"* ]]; then
    workspace_rel="${workspace_rel#${repo_basename}/}"
    src="$FRAMEWORK_SRC/$workspace_rel"
  else
    src="$ROOT/$rel"
  fi
  if [[ ! -f "$src" ]]; then
    write_state "blocked" "Missing required input file: $src" 24
    exit 24
  fi
  dst="$WORKSPACE/$workspace_rel"
  input_dst="$INPUT_ROOT/$workspace_rel"
  mkdir -p "$(dirname "$dst")" "$(dirname "$input_dst")"
  cp "$src" "$dst"
  cp "$src" "$input_dst"
  copied_inputs_for_prompt+=("$workspace_rel")
  copied_inputs_json_parts+=("$(python3 - <<'PY' "$rel" "$workspace_rel"
import json, sys
print(json.dumps({"source_rel": sys.argv[1], "workspace_rel": sys.argv[2]}, ensure_ascii=False))
PY
)")
done

COPIED_INPUTS_JSON="[$(IFS=,; echo "${copied_inputs_json_parts[*]}")]"
python3 - "$MANIFEST_FILE" "$RUN_ID" "$FRAMEWORK_NAME" "$FRAMEWORK_SLUG" "$FRAMEWORK_RUNTIME_KIND" "$FRAMEWORK_RUNTIME_IMAGE" "$FRAMEWORK_RUNTIME_COMMAND" "$DATASET_ROOT" "$WORKSPACE" "$CODEX_HOME_DIR" "$PROVIDER_ENV" "$SEMANTIC_ENV" "$PROMPT_FILE" "$FRAMEWORK_CONTAINER_WORKDIR" "$FRAMEWORK_CONTAINER_HOME" "$FRAMEWORK_CONTAINER_CODEX_HOME" "$COPIED_INPUTS_JSON" <<'PY'
from pathlib import Path
import json
import sys
manifest = {
    "run_id": sys.argv[2],
    "framework": sys.argv[3],
    "slug": sys.argv[4],
    "runtime_kind": sys.argv[5],
    "runtime_image": sys.argv[6],
    "runtime_command": sys.argv[7],
    "dataset_root": sys.argv[8],
    "workspace": sys.argv[9],
    "codex_home": sys.argv[10],
    "provider_env": sys.argv[11],
    "semantic_env": sys.argv[12],
    "prompt_file": sys.argv[13],
    "container_workdir": sys.argv[14],
    "container_home": sys.argv[15],
    "container_codex_home": sys.argv[16],
    "copied_inputs": json.loads(sys.argv[17]),
}
Path(sys.argv[1]).write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding='utf-8')
PY

if [[ -n "$FRAMEWORK_BLOCK_REASON" ]]; then
  write_state "blocked" "$FRAMEWORK_BLOCK_REASON" 25
  exit 25
fi
if [[ -z "$FRAMEWORK_RUNTIME_COMMAND" ]]; then
  write_state "blocked" "Framework runtime command is empty" 26
  exit 26
fi

cat > "$PROMPT_FILE" <<EOF
GAVE2 Task 2 real full-run for $FRAMEWORK_NAME.
Workspace: $WORKSPACE
Dataset root: $DATASET_ROOT
Read and follow the framework-native inputs already copied into this workspace, especially:
$(printf -- '- %s\n' "${copied_inputs_for_prompt[@]}")
Hard constraints:
- This is NOT BabyLM.
- Use only this fresh isolated workspace.
- Do not reuse or resume any BabyLM topic, output, codex_home, or run root.
- Optimize GAVE2 Task 2 official score and produce real runnable artifacts only.
- If blocked, write the blocker clearly in logs and report files; do not fake success.
EOF

{
  echo "[$(date -Is)] framework=$FRAMEWORK_NAME slug=$FRAMEWORK_SLUG"
  echo "workspace=$WORKSPACE"
  echo "dataset_root=$DATASET_ROOT"
  echo "runtime_kind=$FRAMEWORK_RUNTIME_KIND"
  echo "runtime_image=$FRAMEWORK_RUNTIME_IMAGE"
  echo "runtime_command=$FRAMEWORK_RUNTIME_COMMAND"
  echo "prompt_file=$PROMPT_FILE"
} | tee "$LOG_FILE"

write_state "running" "Framework runtime launched"

run_rc=0
set +e
case "$FRAMEWORK_RUNTIME_KIND" in
  docker)
    if [[ -z "$FRAMEWORK_RUNTIME_IMAGE" ]]; then
      echo "runtime_image is required for docker runtime" | tee -a "$LOG_FILE"
      run_rc=27
    else
      declare -a docker_extra_args=()
      if [[ -n "$FRAMEWORK_DOCKER_ARGS" ]]; then
        while IFS= read -r arg; do
          [[ -z "$arg" ]] && continue
          docker_extra_args+=("$arg")
        done <<< "$FRAMEWORK_DOCKER_ARGS"
      fi
      declare -a docker_host_args=()
      if grep -q 'host\.docker\.internal' "$PROVIDER_ENV"; then
        docker_host_args+=(--add-host=host.docker.internal:host-gateway)
      fi
      declare -a docker_cmd=(
        docker run --rm
        --name "$(printf '%s' "$FRAMEWORK_SLUG-$RUN_ID" | tr -c 'A-Za-z0-9_.-' '-')"
        --ipc=host
        --ulimit memlock=-1
        --ulimit stack=67108864
        "${docker_host_args[@]}"
      )
      if [[ "$FRAMEWORK_DISABLE_GPU" != "1" ]]; then
        docker_cmd+=(--gpus all)
      fi
      if [[ -n "$FRAMEWORK_ENTRYPOINT" ]]; then
        docker_cmd+=(--entrypoint "$FRAMEWORK_ENTRYPOINT")
      fi
      if [[ -n "$FRAMEWORK_HOST_HOME_DIR" ]]; then
        docker_cmd+=(-v "$FRAMEWORK_HOST_HOME_DIR":$FRAMEWORK_CONTAINER_HOME)
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
        -e RESEARCHCLAWEVAL_TOPIC_LABEL=GAVE2-Task2
        -e RESEARCHCLAWEVAL_TOPIC_DATASET_ROOT=/data/gave2/task2
        -e RESEARCHCLAWEVAL_TOPIC_CONTRACT_FILE=$FRAMEWORK_CONTAINER_WORKDIR/automation/gave2_task2_contract.md
        -e FRAMEWORK_NAME="$FRAMEWORK_NAME"
        -e FRAMEWORK_SLUG="$FRAMEWORK_SLUG"
        -e REAL_EVAL_RUN_ID="$RUN_ID"
        -e REAL_EVAL_RUN_ROOT="$BASE"
        -v "$WORKSPACE":$FRAMEWORK_CONTAINER_WORKDIR
        -v "$WORKSPACE":/baseline_repo
        -v "$CODEX_HOME_DIR":$FRAMEWORK_CONTAINER_CODEX_HOME
        -v "$DATASET_ROOT":/data/gave2/task2:ro
        -v "$DATASET_ROOT":$WORKSPACE_DATA_MOUNT:ro
        -w "$FRAMEWORK_CONTAINER_WORKDIR"
        "$FRAMEWORK_RUNTIME_IMAGE"
      )
      if [[ -n "$FRAMEWORK_ENTRYPOINT" && ( "$FRAMEWORK_ENTRYPOINT" == "bash" || "$FRAMEWORK_ENTRYPOINT" == "/bin/bash" || "$FRAMEWORK_ENTRYPOINT" == "sh" || "$FRAMEWORK_ENTRYPOINT" == "/bin/sh" ) ]]; then
        docker_cmd+=(-lc "$FRAMEWORK_RUNTIME_COMMAND")
      else
        docker_cmd+=(bash -lc "$FRAMEWORK_RUNTIME_COMMAND")
      fi
      "${docker_cmd[@]}" 2>&1 | tee -a "$LOG_FILE"
      run_rc=${PIPESTATUS[0]}
    fi
    ;;
  host)
    bash -lc "$FRAMEWORK_RUNTIME_COMMAND" 2>&1 | tee -a "$LOG_FILE"
    run_rc=${PIPESTATUS[0]}
    ;;
  *)
    echo "unknown runtime kind: $FRAMEWORK_RUNTIME_KIND" | tee -a "$LOG_FILE"
    run_rc=28
    ;;
esac
set -e

if [[ "$run_rc" -ne 0 ]]; then
  write_state "failed" "Framework runtime exited non-zero; see log" "$run_rc"
  python3 "$ROOT/real_eval/scripts/validate_framework_run.py" \
    --framework gave2_fullrun \
    --run-root "$BASE" \
    --state-file "$STATE_FILE" \
    --manifest-path "$ARTIFACT_MANIFEST" \
    > "$LOG_DIR/validator.json" || true
  exit "$run_rc"
fi

if [[ "$FRAMEWORK_NAME" == "AutoResearchClaw" ]]; then
  postrun_reason=""
  if ! postrun_reason="$(python3 - "$WORKSPACE" <<'PY'
import hashlib
import json
from datetime import datetime
from pathlib import Path
import sys

workspace = Path(sys.argv[1]).resolve()

def fail(message: str) -> None:
    raise SystemExit(message)

def current_path(relative: str) -> Path:
    path = workspace / relative
    if path.is_symlink():
        fail(f"required artifact is a symlink: {relative}")
    if not path.exists():
        fail(f"missing required artifact: {relative}")
    resolved = path.resolve()
    try:
        resolved.relative_to(workspace)
    except ValueError:
        fail(f"required artifact is outside current workspace: {relative}")
    return path

submission = current_path("submission")
if not submission.is_dir():
    fail("required artifact is not a directory: submission/")
submission_files = [item for item in submission.rglob("*") if item.is_file()]
for item in submission_files:
    if item.is_symlink():
        fail(f"submission artifact is a symlink: {item.relative_to(workspace)}")
    try:
        item.resolve().relative_to(workspace)
    except ValueError:
        fail(f"submission artifact is outside current workspace: {item.relative_to(workspace)}")
if not submission_files:
    fail("required artifact is empty: submission/")
for relative in (
    "experiment_trace.json",
    "final_report.md",
    "research_idea.json",
    "research_idea_lock_event.json",
):
    artifact = current_path(relative)
    if artifact.stat().st_size == 0:
        fail(f"required artifact is empty: {relative}")

try:
    idea = json.loads((workspace / "research_idea.json").read_text(encoding="utf-8"))
    trace = json.loads((workspace / "experiment_trace.json").read_text(encoding="utf-8"))
    event = json.loads((workspace / "research_idea_lock_event.json").read_text(encoding="utf-8"))
except (OSError, json.JSONDecodeError) as exc:
    fail(f"invalid research idea lock evidence: {exc}")
if not isinstance(idea, dict) or idea.get("framework") != "AutoResearchClaw":
    fail("research idea is not framework-authored")
if idea.get("idea_locked_before_experiments") is not True:
    fail("research idea was not locked before experiments")
if not isinstance(idea.get("source_artifact"), str) or not idea["source_artifact"].startswith("stage-08/"):
    fail("research idea source is not native Stage 8 output")
if not isinstance(event, dict) or event.get("event") != "research_idea_locked":
    fail("missing native research_idea_locked event")
if event.get("owner") != "framework" or event.get("writer") != "AutoResearchClaw":
    fail("research idea lock event is not framework-owned")
if event.get("artifact") != "research_idea.json" or not event.get("event_id"):
    fail("research idea lock event does not identify the artifact")
if event.get("artifact_sha256") != hashlib.sha256((workspace / "research_idea.json").read_bytes()).hexdigest():
    fail("research idea lock event hash does not match artifact")
if idea.get("lock_event_id") != event["event_id"] or idea.get("locked_at") != event.get("timestamp"):
    fail("research idea lock metadata does not match lock event")
if not isinstance(trace, dict) or trace.get("idea_artifact") != "research_idea.json":
    fail("experiment trace does not identify research_idea.json")
if trace.get("idea_locked_before_experiments") is not True:
    fail("experiment trace does not confirm the pre-experiment lock")
def timestamp(value: object, name: str) -> datetime:
    if not isinstance(value, str) or not value:
        fail(f"missing {name}")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        fail(f"invalid {name}")
    if parsed.tzinfo is None:
        fail(f"timezone missing from {name}")
    return parsed
if timestamp(event.get("timestamp"), "lock timestamp") >= timestamp(
    trace.get("first_experiment_started_at"), "first_experiment_started_at"
):
    fail("research idea lock did not precede first experiment")
PY
)"; then
    write_state "failed" "AutoResearchClaw postrun artifact gate failed: $postrun_reason" 29
    python3 "$ROOT/real_eval/scripts/validate_framework_run.py" \
      --framework gave2_fullrun \
      --run-root "$BASE" \
      --state-file "$STATE_FILE" \
      --manifest-path "$ARTIFACT_MANIFEST" \
      > "$LOG_DIR/validator.json" || true
    exit 29
  fi
fi

write_state "finished" "Framework runtime exited successfully" 0
python3 "$ROOT/real_eval/scripts/validate_framework_run.py" \
  --framework gave2_fullrun \
  --run-root "$BASE" \
  --state-file "$STATE_FILE" \
  --manifest-path "$ARTIFACT_MANIFEST" \
  > "$LOG_DIR/validator.json" || true
