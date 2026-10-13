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
FRAMEWORK_CONTAINER_WORKDIR="${FRAMEWORK_CONTAINER_WORKDIR:-/workspace}"
FRAMEWORK_CONTAINER_HOME="${FRAMEWORK_CONTAINER_HOME:-/workspace}"
FRAMEWORK_CONTAINER_CODEX_HOME="${FRAMEWORK_CONTAINER_CODEX_HOME:-/codex-home}"
FRAMEWORK_DOCKER_ARGS="${FRAMEWORK_DOCKER_ARGS:-}"
FRAMEWORK_ENTRYPOINT="${FRAMEWORK_ENTRYPOINT:-}"
FRAMEWORK_HOST_HOME_DIR="${FRAMEWORK_HOST_HOME_DIR:-}"
FRAMEWORK_DISABLE_GPU="${FRAMEWORK_DISABLE_GPU:-0}"
FRAMEWORK_COMMAND_LABEL="${FRAMEWORK_COMMAND_LABEL:-$FRAMEWORK_RUNTIME_COMMAND}"
FRAMEWORK_NATIVE_ENTRYPOINT="${FRAMEWORK_NATIVE_ENTRYPOINT:?FRAMEWORK_NATIVE_ENTRYPOINT is required}"
FRAMEWORK_KIMI_INJECTION="${FRAMEWORK_KIMI_INJECTION:?FRAMEWORK_KIMI_INJECTION is required}"
FRAMEWORK_NATIVE_LOG_MARKER="${FRAMEWORK_NATIVE_LOG_MARKER:?FRAMEWORK_NATIVE_LOG_MARKER is required}"
FRAMEWORK_EXECUTOR_KIND="${FRAMEWORK_EXECUTOR_KIND:-framework_cli}"
FRAMEWORK_NEEDS_HOST_CODEX="${FRAMEWORK_NEEDS_HOST_CODEX:-0}"
HOST_NODE_ROOT="${REAL_EVAL_HOST_NODE_ROOT:?set REAL_EVAL_HOST_NODE_ROOT to a host node installation}"
CONTAINER_NODE_ROOT="/opt/researchclaweval-node"
DATASET_ROOT="${ARC_WBE_2026_DATASET_ROOT:-$(real_eval_resolve_topic_dataset "$ROOT" arc_wbe_2026)}"
CONTRACT_FILE="${ARC_WBE_2026_CONTRACT_FILE:-$ROOT/automation/arc_wbe_2026_contract.md}"
PROVIDER_CONFIG="${PROVIDER_CONFIG:-$ROOT/api/codex_gpt54_shubiaobiao.toml}"
ARC_WBE_2026_MODEL="${ARC_WBE_2026_MODEL:-$(sed -n 's/^[[:space:]]*model[[:space:]]*=[[:space:]]*"\(.*\)"[[:space:]]*$/\1/p' "$PROVIDER_CONFIG" | head -1)}"
SEMANTIC_SOURCE="${SEMANTIC_SOURCE:-$ROOT/api/_semantic_scholar_api_usage.md}"
PROVIDER_BASE_URL="$(sed -n 's/^[[:space:]]*base_url[[:space:]]*=[[:space:]]*"\(.*\)"[[:space:]]*$/\1/p' "$PROVIDER_CONFIG" | head -1)"
FRAMEWORK_PROVIDER_BASE_URL="${PROVIDER_BASE_URL%/}"
if [[ "$FRAMEWORK_PROVIDER_BASE_URL" != */v1 ]]; then
  FRAMEWORK_PROVIDER_BASE_URL="$FRAMEWORK_PROVIDER_BASE_URL/v1"
fi

WORKSPACE="$BASE/workspace"
INPUT_ROOT="$BASE/inputs"
CODEX_HOME_DIR="$BASE/codex_home"
LOG_DIR="$BASE/logs"
LOG_FILE="$BASE/logs/e2e.log"
STATE_FILE="$BASE/state.json"
MANIFEST_FILE="$BASE/fullrun_manifest.json"
ARTIFACT_MANIFEST="$BASE/artifact_manifest.json"
PROVIDER_ENV="$BASE/provider.env"
SEMANTIC_ENV="$BASE/semantic.env"
WORKSPACE_DATA_MOUNT="$FRAMEWORK_CONTAINER_WORKDIR/data/arc_wbe_2026"
FRAMEWORK_DATASET_ROOT="$INPUT_ROOT/arc_wbe_2026_weights_only"
WEIGHTS_ONLY_PYTHON="${ARC_WBE_2026_WHEST_PYTHON:-/tmp/whest-starterkit/.venv/bin/python}"
# final_report.md may be written to "$WORKSPACE/final_report.md" or fall back to "$BASE/artifacts/final_report.md".
repo_basename="$(basename "$FRAMEWORK_SRC")"

write_state() {
  local status="$1"
  local summary="$2"
  local exit_code="${3:-0}"
  local command="${4:-}"
  python3 - "$STATE_FILE" "$status" "$summary" "$exit_code" "$command" "$ARTIFACT_MANIFEST" <<'PY'
from datetime import datetime, timezone
from pathlib import Path
import json
import sys

payload = {
    "project_id": "arc_wbe_2026",
    "phase": "fullrun",
    "status": sys.argv[2],
    "summary": sys.argv[3],
    "updated_at": datetime.now(timezone.utc).astimezone().isoformat(),
    "exit_code": int(sys.argv[4]),
    "artifact_manifest": sys.argv[6],
}
if sys.argv[5]:
    payload["e2e_command"] = sys.argv[5]
Path(sys.argv[1]).write_text(json.dumps(payload, ensure_ascii=False) + "\n", encoding="utf-8")
PY
}

real_eval_require_clean_dir "$BASE"
trap 'docker ps -q --filter "name=arc_wbe_2026_eval_" | xargs -r docker rm -f' EXIT
mkdir -p "$BASE" "$INPUT_ROOT" "$CODEX_HOME_DIR" "$LOG_DIR"
if [[ -n "$FRAMEWORK_HOST_HOME_DIR" ]]; then
  mkdir -p "$FRAMEWORK_HOST_HOME_DIR"
fi

write_state "starting" "Initializing isolated ARC-WBE-2026 full-run workspace"

if [[ ! -d "$DATASET_ROOT" ]]; then
  write_state "blocked" "Missing ARC dataset root: $DATASET_ROOT" 21
  exit 21
fi
if [[ ! -f "$CONTRACT_FILE" ]]; then
  write_state "blocked" "Missing ARC contract file: $CONTRACT_FILE" 22
  exit 22
fi
if [[ ! -d "$FRAMEWORK_SRC" ]]; then
  write_state "blocked" "Missing framework source: $FRAMEWORK_SRC" 23
  exit 23
fi
if [[ -z "$FRAMEWORK_RUNTIME_COMMAND" ]]; then
  write_state "blocked" "Framework runtime command is empty" 26
  exit 26
fi
if [[ "$FRAMEWORK_NEEDS_HOST_CODEX" == "1" && ! -x "$HOST_NODE_ROOT/bin/codex" ]]; then
  write_state "blocked" "Missing host Codex CLI for native framework runner: $HOST_NODE_ROOT/bin/codex" 29
  exit 29
fi

if [[ ! -x "$WEIGHTS_ONLY_PYTHON" ]]; then
  write_state "blocked" "Missing Python runtime for ARC weights-only projection: $WEIGHTS_ONLY_PYTHON" 25
  exit 25
fi
"$WEIGHTS_ONLY_PYTHON" "$ROOT/automation/scripts/generate_arc_wbe_2026_weights_only_dataset.py" \
  --source-root "$DATASET_ROOT" \
  --output-root "$FRAMEWORK_DATASET_ROOT"

python3 "$ROOT/automation/scripts/generate_arc_wbe_2026_native_inputs.py" \
  --output-root "$INPUT_ROOT" \
  --dataset-root /data/arc_wbe_2026 \
  --contract-file "$CONTRACT_FILE" \
  --provider-base-url "$FRAMEWORK_PROVIDER_BASE_URL" \
  --primary-model "$ARC_WBE_2026_MODEL" >/dev/null

real_eval_rsync_repo "$FRAMEWORK_SRC" "$WORKSPACE"
real_eval_purge_cross_topic_residue "$WORKSPACE" "arc_wbe_2026"
if [ -f "$ROOT/real_eval_contract_tools.py" ]; then
  cp "$ROOT/real_eval_contract_tools.py" "$WORKSPACE/real_eval_contract_tools.py"
fi
if ! real_eval_assert_no_cross_topic_residue "$WORKSPACE" "arc_wbe_2026"; then
  write_state "blocked" "Cross-topic residue remains in the framework runtime snapshot" 27
  exit 27
fi
real_eval_provider_env_from_codex_toml "$PROVIDER_CONFIG" "$PROVIDER_ENV"
real_eval_semantic_env_from_usage_md "$SEMANTIC_SOURCE" "$SEMANTIC_ENV"
cp "$PROVIDER_CONFIG" "$CODEX_HOME_DIR/config.toml"
chmod 700 "$CODEX_HOME_DIR"
chmod 600 "$CODEX_HOME_DIR/config.toml"

mkdir -p "$WORKSPACE/data" "$WORKSPACE/docs" "$WORKSPACE/automation"
mkdir -p "$WORKSPACE/data/arc_wbe_2026"

mapfile -t entry_paths <<< "$FRAMEWORK_ENTRY_PATHS"
declare -a copied_inputs_json_parts=()
declare -a copied_inputs_for_prompt=()
for rel in "${entry_paths[@]}"; do
  [[ -z "$rel" ]] && continue
  workspace_rel="$rel"
  input_override="$INPUT_ROOT/$rel"
  if [[ "$workspace_rel" == "$repo_basename/"* ]]; then
    workspace_rel="${workspace_rel#${repo_basename}/}"
    src="$FRAMEWORK_SRC/$workspace_rel"
  else
    src="$ROOT/$rel"
  fi
  if [[ -f "$input_override" ]]; then
    src="$input_override"
  fi
  if [[ ! -f "$src" ]]; then
    write_state "blocked" "Missing required input file: $src" 24
    exit 24
  fi
  dst="$WORKSPACE/$workspace_rel"
  mkdir -p "$(dirname "$dst")"
  cp "$src" "$dst"
  copied_inputs_for_prompt+=("$workspace_rel")
  copied_inputs_json_parts+=("$(python3 - <<'PY' "$rel" "$workspace_rel"
import json, sys
print(json.dumps({"source_rel": sys.argv[1], "workspace_rel": sys.argv[2]}, ensure_ascii=False))
PY
)")
done

# The same budget is always available at the workspace root, even when a framework
# does not list it among its native entry paths.
cp "$INPUT_ROOT/automation/arc_wbe_2026_execution_budget.md" "$WORKSPACE/automation/arc_wbe_2026_execution_budget.md"
mkdir -p "$WORKSPACE/automation/scripts"
cp "$INPUT_ROOT/automation/scripts/run_arc_wbe_2026_local_score.py" "$WORKSPACE/automation/scripts/"
cp "$INPUT_ROOT/automation/scripts/arc_wbe_2026_official_adapter.py" "$WORKSPACE/automation/scripts/"
cp "$INPUT_ROOT/automation/scripts/prepare_arc_wbe_2026_dataset.py" "$WORKSPACE/automation/scripts/"

COPIED_INPUTS_JSON="[$(IFS=,; echo "${copied_inputs_json_parts[*]}")]"
python3 - "$MANIFEST_FILE" "$FRAMEWORK_NAME" "$FRAMEWORK_SLUG" "$FRAMEWORK_RUNTIME_KIND" "$FRAMEWORK_RUNTIME_IMAGE" "$FRAMEWORK_RUNTIME_COMMAND" "$DATASET_ROOT" "$WORKSPACE" "$COPIED_INPUTS_JSON" "$FRAMEWORK_NATIVE_ENTRYPOINT" "$FRAMEWORK_KIMI_INJECTION" "$FRAMEWORK_NATIVE_LOG_MARKER" "$FRAMEWORK_EXECUTOR_KIND" "$ARC_WBE_2026_MODEL" "$FRAMEWORK_PROVIDER_BASE_URL" <<'PY'
from pathlib import Path
import json
import sys

manifest = {
    "framework": sys.argv[2],
    "slug": sys.argv[3],
    "runtime_kind": sys.argv[4],
    "runtime_image": sys.argv[5],
    "runtime_command": sys.argv[6],
    "dataset_root": sys.argv[7],
    "framework_dataset_root": str(Path(sys.argv[8]).parent / "inputs" / "arc_wbe_2026_weights_only"),
    "workspace": sys.argv[8],
    "copied_inputs": json.loads(sys.argv[9]),
    "framework_orchestration": True,
    "native_standard_version": "1.0",
    "native_entrypoint": sys.argv[10],
    "kimi_injection": sys.argv[11],
    "native_log_marker": sys.argv[12],
    "executor_kind": sys.argv[13],
    "evaluation_model": sys.argv[14],
    "provider_base_url": sys.argv[15],
    "result_fields": ["score", "score_source", "score_artifact", "submission_artifact"],
}
Path(sys.argv[1]).write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
PY

{
  echo "[$(date -Is)] framework=$FRAMEWORK_NAME slug=$FRAMEWORK_SLUG"
  echo "dataset_root=$DATASET_ROOT"
  echo "contract_file=$CONTRACT_FILE"
  echo "runtime_kind=$FRAMEWORK_RUNTIME_KIND"
  echo "runtime_image=$FRAMEWORK_RUNTIME_IMAGE"
  echo "e2e_command=$FRAMEWORK_COMMAND_LABEL"
  echo "runtime_command=$FRAMEWORK_RUNTIME_COMMAND"
  echo "native_entrypoint=$FRAMEWORK_NATIVE_ENTRYPOINT"
  echo "kimi_injection=$FRAMEWORK_KIMI_INJECTION"
  echo "native_log_marker=$FRAMEWORK_NATIVE_LOG_MARKER"
  echo "executor_kind=$FRAMEWORK_EXECUTOR_KIND"
} | tee "$LOG_FILE"

write_state "running" "Launching ARC framework-native execution" 0 "$FRAMEWORK_COMMAND_LABEL"

run_rc=0
set +e
case "$FRAMEWORK_RUNTIME_KIND" in
  docker)
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
    declare -a host_codex_args=()
    if [[ "$FRAMEWORK_NEEDS_HOST_CODEX" == "1" ]]; then
      host_codex_args+=(-v "$HOST_NODE_ROOT:$CONTAINER_NODE_ROOT:ro")
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
      docker_cmd+=(--gpus "${FRAMEWORK_GPUS:-all}")
    fi
    if [[ -n "$FRAMEWORK_ENTRYPOINT" ]]; then
      docker_cmd+=(--entrypoint "$FRAMEWORK_ENTRYPOINT")
    fi
    if [[ -n "$FRAMEWORK_HOST_HOME_DIR" ]]; then
      docker_cmd+=(-v "$FRAMEWORK_HOST_HOME_DIR":$FRAMEWORK_CONTAINER_HOME)
    fi
    docker_cmd+=(
      "${docker_extra_args[@]}"
      "${host_codex_args[@]}"
      --env-file "$PROVIDER_ENV"
      --env-file "$SEMANTIC_ENV"
      -e HOME="$FRAMEWORK_CONTAINER_HOME"
      -e CODEX_HOME="$FRAMEWORK_CONTAINER_CODEX_HOME"
      -e RESEARCHCLAWEVAL_TOPIC_LABEL=ARC-WBE-2026
      -e RESEARCHCLAWEVAL_TOPIC_DATASET_ROOT=/data/arc_wbe_2026
      -e RESEARCHCLAWEVAL_TOPIC_CONTRACT_FILE=$FRAMEWORK_CONTAINER_WORKDIR/automation/arc_wbe_2026_contract.md
      -e ARC_WBE_2026_FRAMEWORK_TIMEOUT_SECONDS="${ARC_WBE_2026_FRAMEWORK_TIMEOUT_SECONDS:-3600}"
      -e FRAMEWORK_NAME="$FRAMEWORK_NAME"
      -e FRAMEWORK_SLUG="$FRAMEWORK_SLUG"
      -e REAL_EVAL_RUN_ID="$RUN_ID"
      -e REAL_EVAL_RUN_ROOT="$BASE"
      -e ACP_TIMEOUT_SEC="${ACP_TIMEOUT_SEC:-3600}"
      -e ARIS_FULLPIPE_CODEX_TIMEOUT_SECONDS="${ARIS_FULLPIPE_CODEX_TIMEOUT_SECONDS:-7000}"
      -v "$WORKSPACE":$FRAMEWORK_CONTAINER_WORKDIR
      -v "$CODEX_HOME_DIR":$FRAMEWORK_CONTAINER_CODEX_HOME
      -v "$FRAMEWORK_DATASET_ROOT":/data/arc_wbe_2026:ro
      -v "$FRAMEWORK_DATASET_ROOT":$WORKSPACE_DATA_MOUNT:ro
      -w "$FRAMEWORK_CONTAINER_WORKDIR"
      "$FRAMEWORK_RUNTIME_IMAGE"
    )
    if [[ -n "$FRAMEWORK_ENTRYPOINT" && ( "$FRAMEWORK_ENTRYPOINT" == "bash" || "$FRAMEWORK_ENTRYPOINT" == "/bin/bash" || "$FRAMEWORK_ENTRYPOINT" == "sh" || "$FRAMEWORK_ENTRYPOINT" == "/bin/sh" ) ]]; then
      docker_cmd+=(-lc "$FRAMEWORK_RUNTIME_COMMAND")
    else
      docker_cmd+=(bash -lc "$FRAMEWORK_RUNTIME_COMMAND")
    fi
    "${docker_cmd[@]}" 2>&1 \
      | python3 "$ROOT/real_eval/scripts/redact_env_secrets.py" \
          --env-file "$PROVIDER_ENV" --env-file "$SEMANTIC_ENV" \
      | tee -a "$LOG_FILE"
    run_rc=${PIPESTATUS[0]}
    ;;
  host)
    bash -lc "$FRAMEWORK_RUNTIME_COMMAND" 2>&1 \
      | python3 "$ROOT/real_eval/scripts/redact_env_secrets.py" \
          --env-file "$PROVIDER_ENV" --env-file "$SEMANTIC_ENV" \
      | tee -a "$LOG_FILE"
    run_rc=${PIPESTATUS[0]}
    ;;
  *)
    echo "unknown runtime kind: $FRAMEWORK_RUNTIME_KIND" | tee -a "$LOG_FILE"
    run_rc=28
    ;;
esac
set -e

if [[ "$run_rc" -eq 0 ]] && ! rg -Fq "$FRAMEWORK_NATIVE_LOG_MARKER" "$LOG_FILE"; then
  echo "missing framework-native log marker: $FRAMEWORK_NATIVE_LOG_MARKER" | tee -a "$LOG_FILE"
  run_rc=41
fi

if [[ "$run_rc" -eq 0 ]]; then
  set +e
  python3 - "$WORKSPACE" "$ARC_WBE_2026_MODEL" "$FRAMEWORK_PROVIDER_BASE_URL" <<'PY'
from pathlib import Path
import json
import re
import sys

workspace = Path(sys.argv[1])
expected_model = sys.argv[2]
expected_base_url = sys.argv[3].rstrip("/")
required = ["research_idea.json", "estimator.py", "submission.json", "experiment_trace.json", "final_report.md"]
missing = [name for name in required if not (workspace / name).is_file() or not (workspace / name).stat().st_size]
if missing:
    raise SystemExit("missing framework-native ARC handoff artifacts before scoring: " + ", ".join(missing))

def load(name: str) -> dict:
    try:
        value = json.loads((workspace / name).read_text(encoding="utf-8"))
    except Exception as exc:
        raise SystemExit(f"invalid {name}: {exc}") from exc
    if not isinstance(value, dict):
        raise SystemExit(f"{name} must be a JSON object")
    return value

trace = load("experiment_trace.json")
if trace.get("framework_native_execution") is not True or trace.get("consumed_topic_input") is not True:
    raise SystemExit("experiment_trace.json must prove framework-native ARC execution and topic input consumption")
if trace.get("workspace_trace_root") != "/workspace":
    raise SystemExit("experiment_trace.json must set workspace_trace_root=/workspace")
experiments = trace.get("experiments")
if not isinstance(experiments, list) or not 2 <= len(experiments) <= 4:
    raise SystemExit("experiment_trace.json must record 2-4 experiments")
experiment_ids = []
for row in experiments:
    experiment_id = row.get("experiment_id") or row.get("id") if isinstance(row, dict) else None
    if not isinstance(experiment_id, str) or not experiment_id.strip():
        raise SystemExit("every experiment_trace.json experiment must have a non-empty experiment_id")
    experiment_ids.append(experiment_id.strip())
if len(set(experiment_ids)) != len(experiment_ids):
    raise SystemExit("experiment_trace.json experiment_id values must be unique")
selected_id = trace.get("selected_experiment_id")
if not isinstance(selected_id, str) or selected_id.strip() not in experiment_ids:
    raise SystemExit("selected_experiment_id must match an experiment_trace.json experiment")
if trace.get("framework_internal_model") != expected_model:
    raise SystemExit(f"experiment_trace.json must set framework_internal_model={expected_model}")
actual_base_url = trace.get("framework_internal_api_base_url")
if not isinstance(actual_base_url, str) or actual_base_url.rstrip("/") != expected_base_url:
    raise SystemExit(f"experiment_trace.json must set framework_internal_api_base_url={expected_base_url}")
if re.search(r"\$\{?[A-Z_][A-Z0-9_]*\}?", trace["framework_internal_model"] + actual_base_url):
    raise SystemExit("experiment_trace.json contains an unexpanded provider environment placeholder")
if trace.get("idea_artifact") != "research_idea.json" or trace.get("idea_locked_before_experiments") is not True:
    raise SystemExit("experiment_trace.json must prove research_idea.json was locked before experiments")

idea = load("research_idea.json")
def nonempty(value):
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, list):
        return bool(value) and all(isinstance(item, str) and item.strip() for item in value)
    return isinstance(value, dict) and bool(value)

for key in ("hypothesis", "method_rationale", "expected_failure_modes", "comparison_logic"):
    value = idea.get(key)
    if key == "method_rationale" and not nonempty(value):
        value = idea.get("rationale")
    if not nonempty(value):
        raise SystemExit(f"research_idea.json must contain non-empty {key}")
PY
  handoff_rc=$?
  set -e
  if [[ "$handoff_rc" -ne 0 ]]; then
    run_rc=42
  fi
fi

if [[ "$run_rc" -eq 0 ]]; then
  if ! "$WEIGHTS_ONLY_PYTHON" "$ROOT/automation/scripts/run_arc_wbe_2026_local_score.py" \
    --workspace "$WORKSPACE" \
    --output-score "$WORKSPACE/score.json" \
    --dataset-root "$DATASET_ROOT" \
    --framework-hint "$FRAMEWORK_NAME" \
    --whest-bin "$(dirname "$WEIGHTS_ONLY_PYTHON")/whest" >"$LOG_DIR/official_score.log" 2>&1; then
    write_state "failed" "Official ARC scorer failed closed; no fallback score was accepted." 43 "$FRAMEWORK_COMMAND_LABEL"
    exit 43
  fi
fi

if [[ "$run_rc" -eq 0 ]]; then
  set +e
  python3 - "$WORKSPACE" "$ARC_WBE_2026_MODEL" <<'PY'
from pathlib import Path
import json
import sys

workspace = Path(sys.argv[1])
expected_model = sys.argv[2]
required = ["research_idea.json", "estimator.py", "submission.json", "score.json", "experiment_trace.json", "final_report.md"]
missing = [name for name in required if not (workspace / name).is_file() or not (workspace / name).stat().st_size]
if missing:
    raise SystemExit("missing framework-native ARC handoff artifacts: " + ", ".join(missing))

def load(name: str) -> dict:
    try:
        value = json.loads((workspace / name).read_text(encoding="utf-8"))
    except Exception as exc:
        raise SystemExit(f"invalid {name}: {exc}") from exc
    if not isinstance(value, dict):
        raise SystemExit(f"{name} must be a JSON object")
    return value

trace = load("experiment_trace.json")
if trace.get("framework_native_execution") is not True or trace.get("consumed_topic_input") is not True:
    raise SystemExit("experiment_trace.json must prove framework-native ARC execution and topic input consumption")
if trace.get("workspace_trace_root") != "/workspace":
    raise SystemExit("experiment_trace.json must set workspace_trace_root=/workspace")
experiments = trace.get("experiments")
if not isinstance(experiments, list) or not 2 <= len(experiments) <= 4:
    raise SystemExit("experiment_trace.json must record 2-4 experiments")
if not isinstance(trace.get("selected_experiment_id"), str) or not trace["selected_experiment_id"].strip():
    raise SystemExit("experiment_trace.json must identify selected_experiment_id")
if trace.get("framework_internal_model") != expected_model:
    raise SystemExit(f"experiment_trace.json must set framework_internal_model={expected_model}")
if not isinstance(trace.get("framework_internal_api_base_url"), str) or not trace["framework_internal_api_base_url"].strip():
    raise SystemExit("experiment_trace.json must record framework_internal_api_base_url")
if trace.get("idea_artifact") != "research_idea.json":
    raise SystemExit("experiment_trace.json must set idea_artifact=research_idea.json")
if trace.get("idea_locked_before_experiments") is not True:
    raise SystemExit("experiment_trace.json must prove the idea was locked before experiments")
idea = load("research_idea.json")

def nonempty_idea_field(value):
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, dict)):
        return bool(value) and all(isinstance(item, str) and item.strip() for item in value) if isinstance(value, list) else True
    return False

for key in ("hypothesis", "method_rationale", "expected_failure_modes", "comparison_logic"):
    field = idea.get(key)
    if not nonempty_idea_field(field) and key == "method_rationale":
        field = idea.get("rationale")
    if not nonempty_idea_field(field):
        raise SystemExit(f"research_idea.json must contain non-empty {key}")
score = load("score.json")
if score.get("score_source") != "official_adapter_whest_run":
    raise SystemExit("ARC score.json must be produced by the official_adapter_whest_run scorer")
load("submission.json")
PY
  handoff_rc=$?
  set -e
  if [[ "$handoff_rc" -ne 0 ]]; then
    run_rc=42
  fi
fi

mkdir -p "$BASE/artifacts"
python3 - "$WORKSPACE" "$FRAMEWORK_NAME" "$FRAMEWORK_SLUG" "$DATASET_ROOT" "$CONTRACT_FILE" "$LOG_FILE" "$ARTIFACT_MANIFEST" <<'PY'
from pathlib import Path
import json
import sys

workspace = Path(sys.argv[1])
manifest = {
    "framework": sys.argv[2], "slug": sys.argv[3], "dataset_root": sys.argv[4],
    "contract_file": sys.argv[5], "log": sys.argv[6],
    "result_fields": ["score", "score_source", "score_artifact", "submission_artifact"],
    "final_report": str(workspace / "final_report.md") if (workspace / "final_report.md").is_file() else None,
    "submission_artifact": str(workspace / "submission.json") if (workspace / "submission.json").is_file() else None,
    "score_artifact": str(workspace / "score.json") if (workspace / "score.json").is_file() else None,
    "experiment_trace": str(workspace / "experiment_trace.json") if (workspace / "experiment_trace.json").is_file() else None,
    "estimator_artifact": str(workspace / "estimator.py") if (workspace / "estimator.py").is_file() else None,
}
Path(sys.argv[7]).write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
PY

if [[ "$run_rc" -ne 0 ]]; then
  write_state "failed" "ARC framework-native execution exited non-zero; see log" "$run_rc" "$FRAMEWORK_COMMAND_LABEL"
  exit "$run_rc"
fi
if python3 - "$WORKSPACE/score.json" <<'PY'
from pathlib import Path
import json
import sys

path = Path(sys.argv[1])
if not path.exists():
    raise SystemExit(1)
payload = json.loads(path.read_text(encoding="utf-8"))
raise SystemExit(0 if payload.get("score_source") == "official_adapter_whest_run" else 1)
PY
then
  write_state "finished" "ARC framework-native execution completed and produced local official score evidence." 0 "$FRAMEWORK_COMMAND_LABEL"
else
  write_state "finished_degraded" "ARC framework-native execution completed without local official scoring." 0 "$FRAMEWORK_COMMAND_LABEL"
fi
