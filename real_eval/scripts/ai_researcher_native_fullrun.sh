#!/usr/bin/env bash
# ai_researcher_native_fullrun.sh — shared native fullrun runner for AI-Researcher
#
# Usage:
#   ai_researcher_native_fullrun.sh <topic_id>
#
# Reads topic config from real_eval/config/ai_researcher_topics.json.
# Calls only research_agent/run_infer_idea.py as the native entrypoint.
# Runs preflight/admission checks before native launch.
# Requires a fresh run directory (reuse exits 10).
# Handles lifecycle, state, and evidence collection.
#
# Expected env vars (set by the 01 wrapper before calling this script):
#   REAL_EVAL_RUN_ROOT     — absolute path to the fresh run directory
#   REAL_EVAL_RUN_ID       — unique run identifier
#   FRAMEWORK_NAME         — "AI-Researcher"
#   FRAMEWORK_SLUG         — unique slug for this wrapper
#   FRAMEWORK_SRC          — path to the framework source tree
#   FRAMEWORK_RUNTIME_IMAGE — Docker image tag
#   FRAMEWORK_MODEL_RAW    — raw model name (e.g. gpt-5.4)
#   AI_RESEARCHER_COMPLETION_MODEL — full model path (e.g. openai/gpt-5.4)
#   AI_RESEARCHER_CHEAP_MODEL      — cheap model path
#   PROVIDER_CONFIG        — path to provider codex.toml
#   SEMANTIC_SOURCE        — path to Semantic Scholar usage markdown
#
# Optional env vars:
#   RESEARCHCLAWEVAL_ROOT  — repo root (default: $(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd))
#   AI_RESEARCHER_RUNTIME_IMAGE — override for runtime image
#   AI_RESEARCHER_EXEC_RUNTIME_IMAGE — inner exec container image
#   AI_RESEARCHER_REFERENCE_CATALOG_ONLY — compact reference-catalog mode
#   AI_RESEARCHER_PORT     — port for inner container communication
#   AI_RESEARCHER_PREPARE_MAX_TURNS — prepare agent turn budget
#   FRAMEWORK_DISABLE_GPU  — set to "1" to disable GPU passthrough

set -euo pipefail

TOPIC_ID="${1:-${REAL_EVAL_TOPIC_ID:?Usage: ai_researcher_native_fullrun.sh <topic_id>}}"

ROOT="${RESEARCHCLAWEVAL_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
TOPIC_CONFIG="$ROOT/real_eval/config/ai_researcher_topics.json"
source "$ROOT/real_eval/scripts/lib_real_eval.sh"

# ── Read topic config ──────────────────────────────────────────────────────
read_topic_config() {
  python3 - "$TOPIC_CONFIG" "$TOPIC_ID" <<'PY'
import json, sys
from pathlib import Path

config_path = Path(sys.argv[1])
topic_id = sys.argv[2]
payload = json.loads(config_path.read_text(encoding="utf-8"))
topics = payload.get("topics", {})
topic = topics.get(topic_id)
if topic is None:
    available = ", ".join(sorted(topics.keys()))
    raise SystemExit(f"Unknown topic_id '{topic_id}'. Available: {available}")
topic["native_entrypoint"] = payload.get("native_entrypoint", "research_agent/run_infer_idea.py")
topic["framework"] = payload.get("framework", "AI-Researcher")
print(json.dumps(topic, ensure_ascii=False))
PY
}

TOPIC_JSON="$(read_topic_config)"
read_topic_field() {
  python3 -c "import json,sys; print(json.loads(sys.argv[1]).get(sys.argv[2],''))" "$TOPIC_JSON" "$1"
}

CATEGORY="$(read_topic_field category)"
INPUT_GENERATOR="$(read_topic_field input_generator)"
DATASET_ENV="$(read_topic_field dataset_env)"
CONTRACT_FILE_REL="$(read_topic_field contract_file)"
DATASET_MOUNT="$(read_topic_field dataset_mount)"
CONTRACT_MOUNT="$(read_topic_field contract_mount)"
SCORER_OWNERSHIP="$(read_topic_field scorer_ownership)"
TIMEOUT_SECONDS="$(read_topic_field timeout_seconds)"
EXPERIMENT_COUNT_MIN="$(read_topic_field experiment_count_min)"
EXPERIMENT_COUNT_MAX="$(read_topic_field experiment_count_max)"
MAX_ITER_TIMES="$(read_topic_field max_iter_times)"
INSTANCE_PATH="$(read_topic_field instance_path)"
METAPROMPT_PATH="$(read_topic_field metaprompt_path)"
TOPIC_LABEL="$(read_topic_field topic_label)"
DISABLE_GPU="$(read_topic_field disable_gpu)"
CONTAINER_WORKDIR="$(read_topic_field container_workdir)"
CONTAINER_NAME_SUFFIX="$(read_topic_field container_name_suffix)"
REQUIRED_ARTIFACTS_JSON="$(read_topic_field required_artifacts)"

mapfile -t REQUIRED_ARTIFACTS < <(
  python3 -c "import json,sys; [print(a) for a in json.loads(sys.argv[1])]" "$REQUIRED_ARTIFACTS_JSON"
)

# ── Resolve runtime paths ──────────────────────────────────────────────────
BASE="${REAL_EVAL_RUN_ROOT:?REAL_EVAL_RUN_ROOT is required}"
RUN_ID="${REAL_EVAL_RUN_ID:?REAL_EVAL_RUN_ID is required}"
FRAMEWORK_NAME="${FRAMEWORK_NAME:?FRAMEWORK_NAME is required}"
FRAMEWORK_SLUG="${FRAMEWORK_SLUG:?FRAMEWORK_SLUG is required}"
FRAMEWORK_SRC="${FRAMEWORK_SRC:?FRAMEWORK_SRC is required}"
FRAMEWORK_RUNTIME_IMAGE="${AI_RESEARCHER_RUNTIME_IMAGE:-${FRAMEWORK_RUNTIME_IMAGE:?FRAMEWORK_RUNTIME_IMAGE is required}}"
FRAMEWORK_MODEL_RAW="${FRAMEWORK_MODEL_RAW:?FRAMEWORK_MODEL_RAW is required}"
AI_RESEARCHER_COMPLETION_MODEL="${AI_RESEARCHER_COMPLETION_MODEL:?AI_RESEARCHER_COMPLETION_MODEL is required}"
AI_RESEARCHER_CHEAP_MODEL="${AI_RESEARCHER_CHEAP_MODEL:-$AI_RESEARCHER_COMPLETION_MODEL}"
PROVIDER_CONFIG="${PROVIDER_CONFIG:?PROVIDER_CONFIG is required}"
SEMANTIC_SOURCE="${SEMANTIC_SOURCE:-$ROOT/api/_semantic_scholar_api_usage.md}"

DATASET_ROOT="${!DATASET_ENV:-$(real_eval_resolve_topic_dataset "$ROOT" "$TOPIC_ID")}"
CONTRACT_FILE="${!TOPIC_ID}_CONTRACT_FILE:-}"
if [[ -z "$CONTRACT_FILE" ]]; then
  CONTRACT_FILE="$ROOT/$CONTRACT_FILE_REL"
fi

WORKSPACE="$BASE/workspace"
LOG_DIR="$BASE/logs"
LOG_FILE="$LOG_DIR/e2e.log"
STATE_FILE="$BASE/state.json"
MANIFEST_FILE="$BASE/fullrun_manifest.json"
PROVIDER_ENV="$BASE/provider.env"
SEMANTIC_ENV="$BASE/semantic.env"
CODEX_HOME_DIR="$BASE/codex_home"
INPUT_ROOT="$BASE/inputs"
OUTER_CONTAINER_NAME="ai_researcher_${CONTAINER_NAME_SUFFIX}_outer_${RUN_ID}"

# ── Helper functions ───────────────────────────────────────────────────────
cleanup_containers() {
  docker ps -a --format '{{.Names}}' | rg "^${OUTER_CONTAINER_NAME}$" | xargs -r docker rm -f >/dev/null 2>&1 || true
}
trap cleanup_containers EXIT

write_state() {
  local status="$1"
  local summary="$2"
  local exit_code="${3:-0}"
  python3 - "$STATE_FILE" "$TOPIC_ID" "$status" "$summary" "$exit_code" <<'PY'
from datetime import datetime, timezone
from pathlib import Path
import json, sys

payload = {
    "project_id": sys.argv[2],
    "phase": "fullrun",
    "status": sys.argv[3],
    "summary": sys.argv[4],
    "updated_at": datetime.now(timezone.utc).astimezone().isoformat(),
    "exit_code": int(sys.argv[5]),
}
Path(sys.argv[1]).write_text(json.dumps(payload, ensure_ascii=False) + "\n", encoding="utf-8")
PY
}

artifact_validation() {
  local ws="$1"
  local missing=()
  for art in "${REQUIRED_ARTIFACTS[@]}"; do
    if [[ ! -f "$ws/$art" ]]; then
      missing+=("$art")
    fi
  done
  if [[ ${#missing[@]} -gt 0 ]]; then
    echo "missing required artifacts: ${missing[*]}" >&2
    return 1
  fi
  return 0
}

# ── Preflight: clean directory check ───────────────────────────────────────
real_eval_require_clean_dir "$BASE"

# ── Preflight: prerequisites ───────────────────────────────────────────────
if [[ ! -d "$DATASET_ROOT" ]]; then
  echo "missing dataset root ($DATASET_ENV): $DATASET_ROOT" >&2
  exit 21
fi
if [[ ! -f "$CONTRACT_FILE" ]]; then
  echo "missing contract file: $CONTRACT_FILE" >&2
  exit 22
fi
if [[ ! -d "$FRAMEWORK_SRC" ]]; then
  echo "missing framework source: $FRAMEWORK_SRC" >&2
  exit 23
fi
if [[ ! -f "$PROVIDER_CONFIG" ]]; then
  echo "missing provider config: $PROVIDER_CONFIG" >&2
  exit 24
fi

NATIVE_ENTRYPOINT_PATH="$FRAMEWORK_SRC/research_agent/run_infer_idea.py"
if [[ ! -f "$NATIVE_ENTRYPOINT_PATH" ]]; then
  echo "missing native entrypoint: $NATIVE_ENTRYPOINT_PATH" >&2
  exit 25
fi

# Derive provider base URL from config
PROVIDER_BASE_URL="$(sed -n 's/^[[:space:]]*base_url[[:space:]]*=[[:space:]]*"\(.*\)"[[:space:]]*$/\1/p' "$PROVIDER_CONFIG" | head -1)"
FRAMEWORK_PROVIDER_BASE_URL="${PROVIDER_BASE_URL%/}"
if [[ "$FRAMEWORK_PROVIDER_BASE_URL" != */v1 ]]; then
  FRAMEWORK_PROVIDER_BASE_URL="$FRAMEWORK_PROVIDER_BASE_URL/v1"
fi

# ── Create run directory structure ─────────────────────────────────────────
mkdir -p "$WORKSPACE" "$LOG_DIR" "$CODEX_HOME_DIR" "$INPUT_ROOT"
write_state "starting" "Preparing $TOPIC_ID native fullrun for $FRAMEWORK_NAME"

# ── Preflight: admission probe ─────────────────────────────────────────────
# Run a lightweight admission check: verify the provider relay is reachable
# and the framework image can import the native entrypoint.
ADMISSION_LOG="$LOG_DIR/admission.log"
echo "=== ADMISSION PROBE ===" > "$ADMISSION_LOG"
ADMISSION_PASS=1

# Check provider connectivity via the relay base URL
if ! curl -sf --max-time 10 "${FRAMEWORK_PROVIDER_BASE_URL%/v1}/healthz" >/dev/null 2>>"$ADMISSION_LOG"; then
  if ! curl -sf --max-time 10 "${FRAMEWORK_PROVIDER_BASE_URL}" >/dev/null 2>>"$ADMISSION_LOG"; then
    echo "WARNING: provider endpoint not reachable at $FRAMEWORK_PROVIDER_BASE_URL" | tee -a "$ADMISSION_LOG"
    # Non-fatal: the inner container may have its own network path
  fi
fi

# Check framework image exists
if ! docker image inspect "$FRAMEWORK_RUNTIME_IMAGE" >/dev/null 2>>"$ADMISSION_LOG"; then
  echo "ADMISSION FAIL: framework image $FRAMEWORK_RUNTIME_IMAGE not found" | tee -a "$ADMISSION_LOG"
  ADMISSION_PASS=0
fi

# Check inner exec image exists (if configured)
EXEC_IMAGE="${AI_RESEARCHER_EXEC_RUNTIME_IMAGE:-ai-researcher-exec:runtime-ready}"
if ! docker image inspect "$EXEC_IMAGE" >/dev/null 2>>"$ADMISSION_LOG"; then
  echo "WARNING: exec image $EXEC_IMAGE not found (may be pulled at runtime)" | tee -a "$ADMISSION_LOG"
fi

# Check Docker socket is accessible
if [[ ! -S /var/run/docker.sock ]]; then
  echo "ADMISSION FAIL: Docker socket not accessible" | tee -a "$ADMISSION_LOG"
  ADMISSION_PASS=0
fi

if [[ "$ADMISSION_PASS" -eq 0 ]]; then
  write_state "blocked" "Admission probe failed; see $ADMISSION_LOG" 26
  exit 26
fi
echo "Admission probe passed" | tee -a "$ADMISSION_LOG"

# ── Generate inputs (if input_generator is configured) ─────────────────────
if [[ -n "$INPUT_GENERATOR" && "$INPUT_GENERATOR" != "null" ]]; then
  GENERATOR="$ROOT/$INPUT_GENERATOR"
  if [[ -f "$GENERATOR" ]]; then
    python3 "$GENERATOR" \
      --output-root "$INPUT_ROOT" \
      --dataset-root "$DATASET_ROOT" \
      --contract-file "$CONTRACT_FILE" \
      --provider-base-url "$FRAMEWORK_PROVIDER_BASE_URL" \
      --primary-model "$FRAMEWORK_MODEL_RAW" >/dev/null 2>>"$LOG_DIR/input_generation.log"
    echo "Input generator $INPUT_GENERATOR completed" >> "$LOG_DIR/input_generation.log"
  else
    echo "WARNING: input generator not found: $GENERATOR" >&2
  fi
fi

# ── Set up provider environment ────────────────────────────────────────────
real_eval_provider_env_from_codex_toml "$PROVIDER_CONFIG" "$PROVIDER_ENV"
real_eval_semantic_env_from_usage_md "$SEMANTIC_SOURCE" "$SEMANTIC_ENV"
cp "$PROVIDER_CONFIG" "$CODEX_HOME_DIR/config.toml"
chmod 755 "$CODEX_HOME_DIR"
chmod 644 "$CODEX_HOME_DIR/config.toml"

# ── Build the runtime command ──────────────────────────────────────────────
# The runtime command calls run_infer_idea.py with topic-appropriate args.
# The 01 wrapper may export FRAMEWORK_RUNTIME_COMMAND to override entirely.
AI_RESEARCHER_PORT="${AI_RESEARCHER_PORT:-$((12372 + RANDOM % 1000))}"

if [[ -z "${FRAMEWORK_RUNTIME_COMMAND:-}" ]]; then
  FRAMEWORK_RUNTIME_COMMAND=$(cat <<EOF
set -euo pipefail
echo "AI_RESEARCHER_NATIVE_INFER_IDEA"
cd /workspace
PORT=\$(python3 - <<'PY'
import socket
s = socket.socket()
s.bind(('127.0.0.1', 0))
print(s.getsockname()[1])
s.close()
PY
)
python3 research_agent/run_infer_idea.py \
  --instance_path ${INSTANCE_PATH} \
  --container_name ai_researcher_${CONTAINER_NAME_SUFFIX}_inner_\${REAL_EVAL_RUN_ID} \
  --model ${AI_RESEARCHER_COMPLETION_MODEL} \
  --workplace_name workplace \
  --cache_path cache_\${REAL_EVAL_RUN_ID} \
  --port "\$PORT" \
  --max_iter_times ${MAX_ITER_TIMES} \
  --category ${CATEGORY}
EOF
)
fi

# ── Write manifest ─────────────────────────────────────────────────────────
python3 - "$MANIFEST_FILE" "$FRAMEWORK_NAME" "$FRAMEWORK_SLUG" "$TOPIC_ID" \
  "$FRAMEWORK_SRC" "$DATASET_ROOT" "$CONTRACT_FILE" "$FRAMEWORK_RUNTIME_IMAGE" \
  "$FRAMEWORK_RUNTIME_COMMAND" "$FRAMEWORK_MODEL_RAW" "$FRAMEWORK_PROVIDER_BASE_URL" \
  "$CATEGORY" "$INSTANCE_PATH" <<'PY'
from pathlib import Path
import json, sys

payload = {
    "framework": sys.argv[2],
    "slug": sys.argv[3],
    "topic_id": sys.argv[4],
    "source_root": sys.argv[5],
    "dataset_root": sys.argv[6],
    "contract_file": sys.argv[7],
    "runtime_image": sys.argv[8],
    "runtime_command": sys.argv[9],
    "entry_instance": sys.argv[12],
    "execution_mode": "framework_native",
    "framework_orchestration": True,
    "native_entrypoint": "research_agent/run_infer_idea.py",
    "native_log_marker": "AI_RESEARCHER_NATIVE_INFER_IDEA",
    "executor_kind": "framework_cli",
    "evaluation_model": sys.argv[10],
    "provider_base_url": sys.argv[11],
    "category": sys.argv[13],
    "result_fields": ["research_idea.json", "experiment_trace.json", "final_report.md"],
}
Path(sys.argv[1]).write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
PY

# ── Log session header ─────────────────────────────────────────────────────
{
  echo "[$(date -Is)] topic=$TOPIC_ID framework=$FRAMEWORK_NAME slug=$FRAMEWORK_SLUG"
  echo "category=$CATEGORY"
  echo "dataset_root=$DATASET_ROOT"
  echo "contract_file=$CONTRACT_FILE"
  echo "workspace=$WORKSPACE"
  echo "runtime_image=$FRAMEWORK_RUNTIME_IMAGE"
  echo "native_entrypoint=research_agent/run_infer_idea.py"
  echo "native_log_marker=AI_RESEARCHER_NATIVE_INFER_IDEA"
  echo "e2e_command=python research_agent/run_infer_idea.py --category $CATEGORY"
  echo "provider_injection=COMPLETION_MODEL/CHEEP_MODEL via provider environment"
  echo "timeout=${TIMEOUT_SECONDS}s"
  echo "experiment_range=${EXPERIMENT_COUNT_MIN}-${EXPERIMENT_COUNT_MAX}"
  echo "scorer_ownership=$SCORER_OWNERSHIP"
} | tee "$LOG_FILE"

write_state "running" "Launching $FRAMEWORK_NAME native execution for $TOPIC_ID"

# ── Build Docker command ───────────────────────────────────────────────────
declare -a docker_extra_args=()
if [[ -n "${FRAMEWORK_DOCKER_ARGS:-}" ]]; then
  while IFS= read -r arg; do
    [[ -z "$arg" ]] && continue
    docker_extra_args+=("$arg")
  done <<< "$FRAMEWORK_DOCKER_ARGS"
fi

declare -a gpu_args=()
if [[ "$DISABLE_GPU" != "true" ]]; then
  gpu_args=(--gpus all)
fi

declare -a host_docker_args=()
if [[ -S /var/run/docker.sock ]]; then
  host_docker_args+=(-v /var/run/docker.sock:/var/run/docker.sock)
fi

# ── Execute native run ─────────────────────────────────────────────────────
run_rc=0
set +e
timeout -k 30s "${TIMEOUT_SECONDS}s" docker run --rm \
  --name "$OUTER_CONTAINER_NAME" \
  --add-host=host.docker.internal:host-gateway \
  --ipc=host \
  --ulimit memlock=-1 \
  --ulimit stack=67108864 \
  "${gpu_args[@]}" \
  "${host_docker_args[@]}" \
  "${docker_extra_args[@]}" \
  -v "$WORKSPACE":/workspace \
  -v "$CODEX_HOME_DIR":/codex-home \
  -v "$DATASET_ROOT":"$DATASET_MOUNT":ro \
  -v "$CONTRACT_FILE":"$CONTRACT_MOUNT":ro \
  --env-file "$PROVIDER_ENV" \
  --env-file "$SEMANTIC_ENV" \
  -e HOME=/codex-home \
  -e CODEX_HOME=/codex-home \
  -e COMPLETION_MODEL="$AI_RESEARCHER_COMPLETION_MODEL" \
  -e CHEEP_MODEL="$AI_RESEARCHER_CHEAP_MODEL" \
  -e BASE_IMAGES="${AI_RESEARCHER_EXEC_RUNTIME_IMAGE:-ai-researcher-exec:runtime-ready}" \
  -e GPUS=all \
  -e PYTHONPATH=/workspace \
  -e RESEARCHCLAWEVAL_DOCKER_HOST=host.docker.internal \
  -e RESEARCHCLAWEVAL_TOPIC_HOST_DATASET_ROOT="$DATASET_ROOT" \
  -e RESEARCHCLAWEVAL_TOPIC_HOST_CONTRACT_FILE="$CONTRACT_FILE" \
  -e RESEARCHCLAWEVAL_TOPIC_DATASET_ROOT="$DATASET_MOUNT" \
  -e RESEARCHCLAWEVAL_TOPIC_LABEL="$TOPIC_LABEL" \
  -e RESEARCHCLAWEVAL_TOPIC_CONTRACT_FILE="$CONTRACT_MOUNT" \
  -e FRAMEWORK_NAME="$FRAMEWORK_NAME" \
  -e FRAMEWORK_SLUG="$FRAMEWORK_SLUG" \
  -e REAL_EVAL_RUN_ID="$RUN_ID" \
  -e REAL_EVAL_RUN_ROOT="$BASE" \
  -e AI_RESEARCHER_PORT="$AI_RESEARCHER_PORT" \
  -e AI_RESEARCHER_PREPARE_MAX_TURNS="${AI_RESEARCHER_PREPARE_MAX_TURNS:-8}" \
  ${AI_RESEARCHER_REFERENCE_CATALOG_ONLY:+-e AI_RESEARCHER_REFERENCE_CATALOG_ONLY=1} \
  -w "$CONTAINER_WORKDIR" \
  "$FRAMEWORK_RUNTIME_IMAGE" \
  bash -lc "$FRAMEWORK_RUNTIME_COMMAND" 2>&1 | tee -a "$LOG_FILE"
run_rc=${PIPESTATUS[0]}
set -e

# ── Evidence collection ────────────────────────────────────────────────────
# Check for native log marker in the output
if [[ "$run_rc" -eq 0 ]]; then
  if ! rg -Fq "AI_RESEARCHER_NATIVE_INFER_IDEA" "$LOG_FILE"; then
    echo "WARNING: native log marker not found in output" | tee -a "$LOG_FILE"
    # Non-fatal: some topics may not emit the marker
  fi
fi

# ── Artifact validation ────────────────────────────────────────────────────
if [[ "$run_rc" -eq 0 ]]; then
  if ! artifact_validation "$WORKSPACE"; then
    echo "Artifact validation failed — required artifacts missing" | tee -a "$LOG_FILE"
    run_rc=31
  fi
fi

# ── Experiment trace validation ────────────────────────────────────────────
if [[ "$run_rc" -eq 0 ]]; then
  python3 - "$WORKSPACE" "$FRAMEWORK_MODEL_RAW" "$FRAMEWORK_PROVIDER_BASE_URL" \
    "$EXPERIMENT_COUNT_MIN" "$EXPERIMENT_COUNT_MAX" <<'PY' || run_rc=$?
from pathlib import Path
import json, sys

workspace = Path(sys.argv[1])
expected_model = sys.argv[2]
expected_base_url = sys.argv[3].rstrip("/")
exp_min = int(sys.argv[4])
exp_max = int(sys.argv[5])

trace_path = workspace / "experiment_trace.json"
if trace_path.exists():
    trace = json.loads(trace_path.read_text(encoding="utf-8"))
    if not isinstance(trace, dict):
        raise SystemExit("experiment_trace.json must be a JSON object")
    if trace.get("framework_native_execution") is not True:
        raise SystemExit("experiment_trace.json must set framework_native_execution=true")
    if trace.get("consumed_topic_input") is not True:
        raise SystemExit("experiment_trace.json must set consumed_topic_input=true")
    experiments = trace.get("experiments")
    if not isinstance(experiments, list) or len(experiments) < exp_min:
        raise SystemExit(f"experiment_trace.json must record at least {exp_min} experiments")
    if len(experiments) > exp_max:
        raise SystemExit(f"experiment_trace.json may record at most {exp_max} experiments")
    if trace.get("framework_internal_model") != expected_model:
        raise SystemExit(f"experiment_trace.json framework_internal_model mismatch")
    if not isinstance(trace.get("framework_internal_api_base_url"), str) or not trace["framework_internal_api_base_url"].strip():
        raise SystemExit("experiment_trace.json must include framework_internal_api_base_url")
    api_url = trace["framework_internal_api_base_url"].rstrip("/")
    if api_url != expected_base_url:
        raise SystemExit(f"experiment_trace.json framework_internal_api_base_url mismatch")
    selected = trace.get("selected_experiment_id")
    if not isinstance(selected, (str, int)) or (isinstance(selected, str) and not selected.strip()):
        raise SystemExit("experiment_trace.json must include a non-empty selected_experiment_id")

idea_path = workspace / "research_idea.json"
if idea_path.exists():
    idea = json.loads(idea_path.read_text(encoding="utf-8"))
    if not isinstance(idea, dict):
        raise SystemExit("research_idea.json must be a JSON object")
    for key in ("hypothesis", "method_rationale", "expected_failure_modes", "comparison_logic"):
        value = idea.get(key)
        if isinstance(value, dict):
            value = str(value)
        if not isinstance(value, str) or not value.strip():
            raise SystemExit(f"research_idea.json must contain non-empty {key}")

print("Experiment trace validation passed")
PY
fi

# ── Write final state ──────────────────────────────────────────────────────
if [[ "$run_rc" -ne 0 ]]; then
  write_state "failed" "$FRAMEWORK_NAME native execution failed for $TOPIC_ID; see log" "$run_rc"
  exit "$run_rc"
fi

write_state "finished" "$FRAMEWORK_NAME native execution completed successfully for $TOPIC_ID" 0