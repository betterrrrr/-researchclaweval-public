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
FRAMEWORK_NATIVE_ENTRYPOINT="${FRAMEWORK_NATIVE_ENTRYPOINT:?FRAMEWORK_NATIVE_ENTRYPOINT is required}"
FRAMEWORK_KIMI_INJECTION="${FRAMEWORK_KIMI_INJECTION:?FRAMEWORK_KIMI_INJECTION is required}"
FRAMEWORK_NATIVE_LOG_MARKER="${FRAMEWORK_NATIVE_LOG_MARKER:?FRAMEWORK_NATIVE_LOG_MARKER is required}"
FRAMEWORK_EXECUTOR_KIND="${FRAMEWORK_EXECUTOR_KIND:-framework_cli}"
FRAMEWORK_COMMAND_LABEL="${FRAMEWORK_COMMAND_LABEL:-$FRAMEWORK_RUNTIME_COMMAND}"
TOPIC_ROOT="${MOUNTAINCAR_CONTINUOUS_DATASET_ROOT:-$(real_eval_resolve_topic_dataset "$ROOT" mountaincar_continuous)}"
CONTRACT_FILE="${MOUNTAINCAR_CONTINUOUS_CONTRACT_FILE:-$ROOT/automation/topic2_contract.md}"
PROVIDER_CONFIG="${PROVIDER_CONFIG:-$ROOT/api/codex_gpt54_shubiaobiao.toml}"
MC_MODEL="${MOUNTAINCAR_CONTINUOUS_MODEL:-$(sed -n 's/^[[:space:]]*model[[:space:]]*=[[:space:]]*"\(.*\)"[[:space:]]*$/\1/p' "$PROVIDER_CONFIG" | head -1)}"
SEMANTIC_SOURCE="${SEMANTIC_SOURCE:-$ROOT/api/_semantic_scholar_api_usage.md}"
PROVIDER_BASE_URL="$(sed -n 's/^[[:space:]]*base_url[[:space:]]*=[[:space:]]*"\(.*\)"[[:space:]]*$/\1/p' "$PROVIDER_CONFIG" | head -1)"
# Fallback: extract base_url from model_providers section (DeepSeek relay TOML)
if [[ -z "$PROVIDER_BASE_URL" ]]; then
  PROVIDER_BASE_URL="$(python3 -c "
import tomllib, sys
with open(sys.argv[1], 'rb') as f:
    cfg = tomllib.load(f)
for key, val in cfg.get('model_providers', {}).items():
    if isinstance(val, dict) and val.get('base_url'):
        print(val['base_url'])
        break
" "$PROVIDER_CONFIG" 2>/dev/null | head -1)"
fi
FRAMEWORK_PROVIDER_BASE_URL="${PROVIDER_BASE_URL%/}"
if [[ "$FRAMEWORK_PROVIDER_BASE_URL" != */v1 ]]; then
  FRAMEWORK_PROVIDER_BASE_URL="$FRAMEWORK_PROVIDER_BASE_URL/v1"
fi
# JAX python runtime: the framework image must expose JAX at this path or the
# wrapper mounts a host venv. Default to the framework's own python.
MC_PYTHON="${MOUNTAINCAR_CONTINUOUS_PYTHON:-python3}"

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

write_state() {
  local status="$1" summary="$2" exit_code="${3:-0}" command="${4:-}"
  python3 - "$STATE_FILE" "$status" "$summary" "$exit_code" "$command" "$ARTIFACT_MANIFEST" <<'PY'
from datetime import datetime, timezone
from pathlib import Path
import json, sys
payload = {
    "project_id": "mountaincar_continuous",
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
mkdir -p "$BASE" "$INPUT_ROOT" "$CODEX_HOME_DIR" "$LOG_DIR"
if [[ -n "$FRAMEWORK_HOST_HOME_DIR" ]]; then mkdir -p "$FRAMEWORK_HOST_HOME_DIR"; fi

write_state "starting" "Initializing isolated MountainCar-Continuous full-run workspace"

[[ -d "$TOPIC_ROOT" ]] || { write_state "blocked" "Missing MountainCar topic root: $TOPIC_ROOT" 21; exit 21; }
[[ -f "$CONTRACT_FILE" ]] || { write_state "blocked" "Missing MountainCar contract file: $CONTRACT_FILE" 22; exit 22; }
[[ -d "$FRAMEWORK_SRC" ]] || { write_state "blocked" "Missing framework source: $FRAMEWORK_SRC" 23; exit 23; }
[[ -n "$FRAMEWORK_RUNTIME_COMMAND" ]] || { write_state "blocked" "Framework runtime command is empty" 26; exit 26; }

# Generate framework-native inputs (briefs, prompts, contract, budget, scorer, starter copy)
python3 "$ROOT/automation/scripts/generate_mountaincar_continuous_native_inputs.py" \
  --output-root "$INPUT_ROOT" \
  --dataset-root "$TOPIC_ROOT" \
  --contract-file "$CONTRACT_FILE" \
  --provider-base-url "$FRAMEWORK_PROVIDER_BASE_URL" \
  --primary-model "$MC_MODEL" >/dev/null

# Fresh workspace: framework source (template) + starter code + protected evaluator
real_eval_rsync_repo "$FRAMEWORK_SRC" "$WORKSPACE"
real_eval_purge_cross_topic_residue "$WORKSPACE" "mountaincar_continuous"
if ! real_eval_assert_no_cross_topic_residue "$WORKSPACE" "mountaincar_continuous"; then
  write_state "blocked" "Cross-topic residue remains in the framework runtime snapshot" 27
  exit 27
fi
real_eval_provider_env_from_codex_toml "$PROVIDER_CONFIG" "$PROVIDER_ENV"
real_eval_semantic_env_from_usage_md "$SEMANTIC_SOURCE" "$SEMANTIC_ENV"
cp "$PROVIDER_CONFIG" "$CODEX_HOME_DIR/config.toml"
chmod 700 "$CODEX_HOME_DIR"
chmod 600 "$CODEX_HOME_DIR/config.toml"

# Place starter code + protected evaluator into the workspace
mkdir -p "$WORKSPACE/src" "$WORKSPACE/automation/scripts" "$WORKSPACE/docs"
cp -r "$TOPIC_ROOT/src/." "$WORKSPACE/src/"
cp "$TOPIC_ROOT/protected/evaluate.py" "$WORKSPACE/evaluate.py"
chmod 444 "$WORKSPACE/evaluate.py"
cp "$TOPIC_ROOT/protected/evaluate.py.sha256" "$WORKSPACE/evaluate.py.sha256"
mkdir -p "$WORKSPACE/checkpoints"

# Copy generated inputs (per-framework briefs etc.) into the workspace
mapfile -t entry_paths <<< "$FRAMEWORK_ENTRY_PATHS"
for rel in "${entry_paths[@]}"; do
  [[ -z "$rel" ]] && continue
  input_override="$INPUT_ROOT/$rel"
  src="$ROOT/$rel"
  [[ -f "$input_override" ]] && src="$input_override"
  [[ -f "$src" ]] || { write_state "blocked" "Missing required input file: $src" 24; exit 24; }
  dst="$WORKSPACE/$rel"
  mkdir -p "$(dirname "$dst")"
  cp "$src" "$dst"
done
# Always place the contract, budget, and host scorer at workspace root
cp "$INPUT_ROOT/automation/topic2_contract.md" "$WORKSPACE/automation/topic2_contract.md"
cp "$INPUT_ROOT/automation/topic2_execution_budget.md" "$WORKSPACE/automation/topic2_execution_budget.md"
cp "$INPUT_ROOT/automation/scripts/run_topic2_host_score.py" "$WORKSPACE/automation/scripts/"
cp "$INPUT_ROOT/docs/topic2_summary.md" "$WORKSPACE/docs/"

python3 - "$MANIFEST_FILE" "$FRAMEWORK_NAME" "$FRAMEWORK_SLUG" "$FRAMEWORK_RUNTIME_KIND" "$FRAMEWORK_RUNTIME_IMAGE" "$FRAMEWORK_RUNTIME_COMMAND" "$TOPIC_ROOT" "$WORKSPACE" "$FRAMEWORK_NATIVE_ENTRYPOINT" "$FRAMEWORK_KIMI_INJECTION" "$FRAMEWORK_NATIVE_LOG_MARKER" "$FRAMEWORK_EXECUTOR_KIND" "$MC_MODEL" "$FRAMEWORK_PROVIDER_BASE_URL" <<'PY'
from pathlib import Path
import json, sys
manifest = {
    "framework": sys.argv[2],
    "slug": sys.argv[3],
    "runtime_kind": sys.argv[4],
    "runtime_image": sys.argv[5],
    "runtime_command": sys.argv[6],
    "topic_root": sys.argv[7],
    "workspace": sys.argv[8],
    "framework_orchestration": True,
    "native_standard_version": "1.0",
    "native_entrypoint": sys.argv[9],
    "kimi_injection": sys.argv[10],
    "native_log_marker": sys.argv[11],
    "executor_kind": sys.argv[12],
    "evaluation_model": sys.argv[13],
    "provider_base_url": sys.argv[14],
    "result_fields": ["score", "reward_std", "score_source", "score_artifact"],
}
Path(sys.argv[1]).write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
PY

{
  echo "[$(date -Is)] framework=$FRAMEWORK_NAME slug=$FRAMEWORK_SLUG"
  echo "topic_root=$TOPIC_ROOT"
  echo "contract_file=$CONTRACT_FILE"
  echo "runtime_image=$FRAMEWORK_RUNTIME_IMAGE"
  echo "native_entrypoint=$FRAMEWORK_NATIVE_ENTRYPOINT"
  echo "native_log_marker=$FRAMEWORK_NATIVE_LOG_MARKER"
} | tee "$LOG_FILE"

write_state "running" "Launching MountainCar framework-native execution" 0 "$FRAMEWORK_COMMAND_LABEL"

run_rc=0
set +e
case "$FRAMEWORK_RUNTIME_KIND" in
  docker)
    declare -a docker_extra_args=()
    if [[ -n "$FRAMEWORK_DOCKER_ARGS" ]]; then
      while IFS= read -r arg; do [[ -z "$arg" ]] && continue; docker_extra_args+=("$arg"); done <<< "$FRAMEWORK_DOCKER_ARGS"
    fi
    declare -a docker_host_args=()
    if grep -q 'host\.docker\.internal' "$PROVIDER_ENV"; then docker_host_args+=(--add-host=host.docker.internal:host-gateway); fi
    declare -a docker_cmd=(
      docker run --rm
      --name "$(printf '%s' "$FRAMEWORK_SLUG-$RUN_ID" | tr -c 'A-Za-z0-9_.-' '-')"
      --ipc=host --ulimit memlock=-1 --ulimit stack=67108864
      # Memory limits to prevent OOM
      --memory=32g --memory-swap=32g --shm-size=8g
      "${docker_host_args[@]}"
    )
    if [[ "$FRAMEWORK_DISABLE_GPU" != "1" ]]; then docker_cmd+=(--gpus all); fi
    if [[ -n "$FRAMEWORK_ENTRYPOINT" ]]; then docker_cmd+=(--entrypoint "$FRAMEWORK_ENTRYPOINT"); fi
    if [[ -n "$FRAMEWORK_HOST_HOME_DIR" ]]; then docker_cmd+=(-v "$FRAMEWORK_HOST_HOME_DIR":$FRAMEWORK_CONTAINER_HOME); fi
    docker_cmd+=(
      "${docker_extra_args[@]}"
      --env-file "$PROVIDER_ENV"
      --env-file "$SEMANTIC_ENV"
      -e HOME="$FRAMEWORK_CONTAINER_HOME"
      -e CODEX_HOME="$FRAMEWORK_CONTAINER_CODEX_HOME"
      -e RESEARCHCLAWEVAL_TOPIC_LABEL=MountainCar-Continuous
      -e RESEARCHCLAWEVAL_TOPIC_ROOT=/data/mountaincar_continuous
      -e RESEARCHCLAWEVAL_TOPIC_CONTRACT_FILE=$FRAMEWORK_CONTAINER_WORKDIR/automation/topic2_contract.md
      -e MOUNTAINCAR_CONTINUOUS_TRAINING_TIMEOUT="${MOUNTAINCAR_CONTINUOUS_TRAINING_TIMEOUT:-1800}"
      # JAX/GPU memory management to prevent OOM
      -e XLA_PYTHON_CLIENT_PREALLOCATE=false
      -e XLA_PYTHON_CLIENT_MEM_FRACTION=0.6
      -e JAX_PLATFORMS=
      -e FRAMEWORK_NAME="$FRAMEWORK_NAME"
      -e FRAMEWORK_SLUG="$FRAMEWORK_SLUG"
      -e REAL_EVAL_RUN_ID="$RUN_ID"
      -e REAL_EVAL_RUN_ROOT="$BASE"
      -e ACP_TIMEOUT_SEC="${ACP_TIMEOUT_SEC:-3600}"
      -e ARIS_FULLPIPE_CODEX_TIMEOUT_SECONDS="${ARIS_FULLPIPE_CODEX_TIMEOUT_SECONDS:-7000}"
      # Session-establishment timeout (acpx sessions ensure/new).  The upstream
      # default of 30 s used to kill whole stages; the framework now defaults to
      # 180 s and this lets a caller raise it further.
      -e ACP_SESSION_TIMEOUT_SEC="${ACP_SESSION_TIMEOUT_SEC:-180}"
      # Framework-native resume.  This one MUST be forwarded explicitly: without
      # it the container sees no value, the wrapper omits --resume, and the CLI
      # silently replays all 23 stages instead of continuing from the
      # checkpoint -- which is exactly what happened on 2026-10-04 23:40.
      -e AUTORESEARCHCLAW_RESUME="${AUTORESEARCHCLAW_RESUME:-0}"
      # Topic 2 experiment code has to import the frozen starter package as
      # "from src... import ...".  The host scorer runs the frozen evaluate.py
      # with cwd=/workspace, so "src" resolves for it; the framework's own
      # experiment sandbox runs from stage-12/runs/sandbox/_project_N, where it
      # does not, and every regeneration had to rediscover sys.path (observed as
      # "ModuleNotFoundError: No module named 'src'" on successive retries).
      # Give the sandbox the same view of the workspace root.
      -e PYTHONPATH="$FRAMEWORK_CONTAINER_WORKDIR"
      # Stage 12 regeneration is high variance: consecutive retries have ranged
      # from a resolved frozen-interface call down to "NameError: name 'false'
      # is not defined" on line 1.  The framework reads this inside the
      # container to size its own retry loop, so it has to be forwarded or the
      # caller's value is silently ignored.
      -e AUTORESEARCHCLAW_MAX_EXPERIMENT_RETRY="${AUTORESEARCHCLAW_MAX_EXPERIMENT_RETRY:-5}"
      -v "$WORKSPACE":$FRAMEWORK_CONTAINER_WORKDIR
      -v "$CODEX_HOME_DIR":$FRAMEWORK_CONTAINER_CODEX_HOME
      -v "$TOPIC_ROOT":/data/mountaincar_continuous:ro
      -w "$FRAMEWORK_CONTAINER_WORKDIR"
      "$FRAMEWORK_RUNTIME_IMAGE"
    )
    if [[ -n "$FRAMEWORK_ENTRYPOINT" && ( "$FRAMEWORK_ENTRYPOINT" == "bash" || "$FRAMEWORK_ENTRYPOINT" == "/bin/bash" || "$FRAMEWORK_ENTRYPOINT" == "sh" || "$FRAMEWORK_ENTRYPOINT" == "/bin/sh" ) ]]; then
      docker_cmd+=(-lc "$FRAMEWORK_RUNTIME_COMMAND")
    else
      docker_cmd+=(bash -lc "$FRAMEWORK_RUNTIME_COMMAND")
    fi
    "${docker_cmd[@]}" 2>&1 \
      | python3 "$ROOT/real_eval/scripts/redact_env_secrets.py" --env-file "$PROVIDER_ENV" --env-file "$SEMANTIC_ENV" \
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

# Unified checkpoint post-processing: ensure checkpoints are in the right place
# Some frameworks (e.g. ARIS) may save checkpoints to subdirectories.
if [[ "$run_rc" -eq 0 ]]; then
  ckpt_dir="$WORKSPACE/checkpoints"
  ckpt_count=$(ls "$ckpt_dir"/*.pkl 2>/dev/null | wc -l)
  if [[ "$ckpt_count" -ne 5 ]]; then
    echo "checkpoints/ has $ckpt_count files (expected 5). Scanning for misplaced checkpoints..." | tee -a "$LOG_FILE"
    # Search for checkpoint files in known subdirectories
    for subdir in exp1_checkpoints exp2_checkpoints exp3_checkpoints exp4_checkpoints baseline_checkpoints best_checkpoints; do
      if [[ -d "$WORKSPACE/$subdir" ]]; then
        echo "  Found checkpoints in $subdir/" | tee -a "$LOG_FILE"
        cp "$WORKSPACE/$subdir"/*.pkl "$ckpt_dir"/ 2>/dev/null || true
      fi
    done
    # Also search for any config-42-*.pkl files anywhere in the workspace
    find "$WORKSPACE" -maxdepth 4 -name "config-42-*.pkl" ! -path "$ckpt_dir/*" -exec cp {} "$ckpt_dir"/ \; 2>/dev/null || true
    ckpt_count=$(ls "$ckpt_dir"/*.pkl 2>/dev/null | wc -l)
    echo "  After recovery: $ckpt_count checkpoint files in checkpoints/" | tee -a "$LOG_FILE"
    if [[ "$ckpt_count" -ne 5 ]]; then
      echo "  WARNING: Still have $ckpt_count checkpoints (expected 5). Handoff may fail." | tee -a "$LOG_FILE"
    fi
  fi
fi

# Validate framework handoff artifacts before host scoring
if [[ "$run_rc" -eq 0 ]]; then
  set +e
  python3 - "$WORKSPACE" "$MC_MODEL" "$FRAMEWORK_PROVIDER_BASE_URL" <<'PY'
from pathlib import Path
import json, re, sys
workspace = Path(sys.argv[1])
expected_model = sys.argv[2]
expected_base_url = sys.argv[3].rstrip("/")
required = ["research_idea.json", "experiment_trace.json", "final_report.md", "evaluate.py"]
missing = [n for n in required if not (workspace / n).is_file() or not (workspace / n).stat().st_size]
if missing:
    raise SystemExit("missing framework-native MountainCar artifacts before scoring: " + ", ".join(missing))
if not (workspace / "src" / "config.yaml").is_file():
    raise SystemExit("missing src/config.yaml")
ckpt_dir = workspace / "checkpoints"
ckpts = sorted(ckpt_dir.glob("*.pkl")) if ckpt_dir.is_dir() else []
if len(ckpts) != 5:
    raise SystemExit(f"expected exactly 5 checkpoints, found {len(ckpts)}")
def load(name):
    try:
        v = json.loads((workspace / name).read_text(encoding="utf-8"))
    except Exception as e:
        raise SystemExit(f"invalid {name}: {e}") from e
    if not isinstance(v, dict):
        raise SystemExit(f"{name} must be a JSON object")
    return v
trace = load("experiment_trace.json")
if trace.get("framework_native_execution") is not True or trace.get("consumed_topic_input") is not True:
    raise SystemExit("experiment_trace.json must prove native execution and topic input consumption")
if trace.get("workspace_trace_root") != "/workspace":
    raise SystemExit("experiment_trace.json must set workspace_trace_root=/workspace")
experiments = trace.get("experiments")
if not isinstance(experiments, list) or not 2 <= len(experiments) <= 4:
    raise SystemExit("experiment_trace.json must record 2-4 experiments")
ids = []
for row in experiments:
    eid = row.get("experiment_id") or row.get("id") if isinstance(row, dict) else None
    if not isinstance(eid, str) or not eid.strip():
        raise SystemExit("every experiment must have a non-empty experiment_id")
    ids.append(eid.strip())
if len(set(ids)) != len(ids):
    raise SystemExit("experiment_id values must be unique")
selected = trace.get("selected_experiment_id")
if not isinstance(selected, str) or selected.strip() not in ids:
    raise SystemExit("selected_experiment_id must match an experiment record")
if trace.get("framework_internal_model") != expected_model:
    raise SystemExit(f"experiment_trace.json must set framework_internal_model={expected_model}")
actual_url = trace.get("framework_internal_api_base_url")
if not isinstance(actual_url, str) or actual_url.rstrip("/") != expected_base_url:
    raise SystemExit("experiment_trace.json must set framework_internal_api_base_url")
if trace.get("idea_artifact") != "research_idea.json" or trace.get("idea_locked_before_experiments") is not True:
    raise SystemExit("experiment_trace.json must prove the idea was locked before experiments")
idea = load("research_idea.json")
for key in ("hypothesis", "method_rationale", "expected_failure_modes", "comparison_logic"):
    val = idea.get(key) or (idea.get("rationale") if key == "method_rationale" else None)
    if not val or (isinstance(val, str) and not val.strip()):
        raise SystemExit(f"research_idea.json must contain non-empty {key}")
PY
  handoff_rc=$?
  set -e
  if [[ "$handoff_rc" -ne 0 ]]; then run_rc=42; fi
fi

# Host scoring via frozen evaluator
# Remove any framework-created score.json — host must be the sole score owner
rm -f "$WORKSPACE/score.json"
if [[ "$run_rc" -eq 0 ]]; then
  if ! "$MC_PYTHON" "$ROOT/automation/scripts/run_mountaincar_continuous_host_score.py" \
    --workspace "$WORKSPACE" \
    --output-score "$WORKSPACE/score.json" \
    --dataset-root "$TOPIC_ROOT" \
    --python "$MC_PYTHON" \
    --config-fname src/config.yaml >"$LOG_DIR/official_score.log" 2>&1; then
    write_state "failed" "Official MountainCar scorer failed closed; no fallback score accepted." 43 "$FRAMEWORK_COMMAND_LABEL"
    exit 43
  fi
fi

if [[ "$run_rc" -ne 0 ]]; then
  write_state "failed" "MountainCar framework-native execution exited non-zero; see log" "$run_rc" "$FRAMEWORK_COMMAND_LABEL"
  exit "$run_rc"
fi
if python3 - "$WORKSPACE/score.json" <<'PY'
from pathlib import Path
import json, sys
p = Path(sys.argv[1])
if not p.exists():
    raise SystemExit(1)
payload = json.loads(p.read_text(encoding="utf-8"))
raise SystemExit(0 if payload.get("score_source") == "official_evaluate_py" else 1)
PY
then
  write_state "finished" "MountainCar framework-native execution completed and produced host score evidence." 0 "$FRAMEWORK_COMMAND_LABEL"
else
  write_state "finished_degraded" "MountainCar framework-native execution completed without official scoring." 0 "$FRAMEWORK_COMMAND_LABEL"
fi
