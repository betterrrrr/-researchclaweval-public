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
FRAMEWORK_RUNTIME_IMAGE="${FRAMEWORK_RUNTIME_IMAGE:?FRAMEWORK_RUNTIME_IMAGE is required}"
FRAMEWORK_RUNTIME_COMMAND="${FRAMEWORK_RUNTIME_COMMAND:?FRAMEWORK_RUNTIME_COMMAND is required}"
FRAMEWORK_NATIVE_ENTRYPOINT="${FRAMEWORK_NATIVE_ENTRYPOINT:?FRAMEWORK_NATIVE_ENTRYPOINT is required}"
FRAMEWORK_NATIVE_ENTRYPOINT_FILE="${FRAMEWORK_NATIVE_ENTRYPOINT_FILE:?FRAMEWORK_NATIVE_ENTRYPOINT_FILE is required}"
FRAMEWORK_NATIVE_ENTRYPOINT_SOURCE="${FRAMEWORK_NATIVE_ENTRYPOINT_SOURCE:?FRAMEWORK_NATIVE_ENTRYPOINT_SOURCE is required}"
FRAMEWORK_PROVIDER_INJECTION="${FRAMEWORK_PROVIDER_INJECTION:?FRAMEWORK_PROVIDER_INJECTION is required}"
FRAMEWORK_NATIVE_LOG_MARKER="${FRAMEWORK_NATIVE_LOG_MARKER:?FRAMEWORK_NATIVE_LOG_MARKER is required}"
FRAMEWORK_NATIVE_PROCESS_MARKERS="${FRAMEWORK_NATIVE_PROCESS_MARKERS:?FRAMEWORK_NATIVE_PROCESS_MARKERS is required}"
FRAMEWORK_COMMAND_LABEL="${FRAMEWORK_COMMAND_LABEL:?FRAMEWORK_COMMAND_LABEL is required}"
FRAMEWORK_EXECUTOR_KIND="${FRAMEWORK_EXECUTOR_KIND:-framework_cli}"
FRAMEWORK_ENTRY_PREFIX="${FRAMEWORK_ENTRY_PREFIX:-$(basename "$FRAMEWORK_SRC")}"
FRAMEWORK_ENTRYPOINT="${FRAMEWORK_ENTRYPOINT:-bash}"
FRAMEWORK_CONTAINER_WORKDIR="${FRAMEWORK_CONTAINER_WORKDIR:-/workspace}"
FRAMEWORK_CONTAINER_HOME="${FRAMEWORK_CONTAINER_HOME:-/workspace}"
FRAMEWORK_CONTAINER_CODEX_HOME="${FRAMEWORK_CONTAINER_CODEX_HOME:-/codex-home}"
FRAMEWORK_DOCKER_ARGS="${FRAMEWORK_DOCKER_ARGS:-}"
FRAMEWORK_LOG_FORBIDDEN_PATTERN="${FRAMEWORK_LOG_FORBIDDEN_PATTERN:-}"
FRAMEWORK_NEEDS_HOST_CODEX="${FRAMEWORK_NEEDS_HOST_CODEX:-0}"
FRAMEWORK_WORKSPACE_DATASET_PROJECTION="${FRAMEWORK_WORKSPACE_DATASET_PROJECTION:-0}"
HOST_NODE_ROOT="${REAL_EVAL_HOST_NODE_ROOT:-$(dirname "$(dirname "$(command -v node)")")}" 
CONTAINER_NODE_ROOT="/opt/researchclaweval-node"

DATASET_ROOT="${TDC_ADMET_TOX_DATASET_ROOT:-$(real_eval_resolve_topic_dataset "$ROOT" tdc_admet_tox)}"
HIDDEN_LABELS_ROOT="${TDC_ADMET_TOX_HIDDEN_LABELS_ROOT:?TDC_ADMET_TOX_HIDDEN_LABELS_ROOT is required on the host}"
HIDDEN_LABELS_FILE="$HIDDEN_LABELS_ROOT/test_labels.csv"
CONTRACT_FILE="${TDC_ADMET_TOX_CONTRACT_FILE:-$ROOT/automation/tdc_admet_tox_contract.md}"
PROVIDER_CONFIG="${PROVIDER_CONFIG:-$ROOT/api/codex_gpt54_shubiaobiao.toml}"
RELAY_IMAGE="${TDC_ADMET_TOX_GPT_RELAY_IMAGE:-researchclaweval/codex-kimi-relay:test}"
EVAL_VARIANT="${TDC_ADMET_TOX_EVAL_VARIANT:-gpt}"
CLIENT_RELAY_BASE_URL="http://tdc-${EVAL_VARIANT}-relay:8787/v1"

WORKSPACE="$BASE/workspace"
INPUT_ROOT="$BASE/inputs"
CODEX_HOME_DIR="$BASE/codex_home"
LOG_DIR="$BASE/logs"
LOG_FILE="$LOG_DIR/e2e.log"
NATIVE_STDOUT_FILE="$LOG_DIR/native_stdout.log"
NATIVE_PROCESS_EVIDENCE_FILE="$BASE/native_process_evidence.json"
RELAY_LOG_FILE="$LOG_DIR/provider_relay.log"
STATE_FILE="$BASE/state.json"
MANIFEST_FILE="$BASE/fullrun_manifest.json"
OUTCOME_FILE="$BASE/outcome.json"
FRAMEWORK_AUDIT_FILE="$BASE/framework_audit.json"
FINAL_AUDIT_FILE="$BASE/final_audit.json"
PROVIDER_ENV="$BASE/provider.env"
UPSTREAM_ENV="$BASE/upstream_relay.env"
RELAY_EVIDENCE="$BASE/provider_relay_evidence.json"
TEMPLATE_ARTIFACTS_BEFORE="$BASE/template_forbidden_artifacts.before"

RUN_TOKEN="$(python3 - "$RUN_ID" "$FRAMEWORK_SLUG" <<'PY'
import hashlib, re, sys
raw = re.sub(r"[^A-Za-z0-9_.-]", "-", f"{sys.argv[1]}-{sys.argv[2]}")
print(f"{raw[:28]}-{hashlib.sha256(raw.encode()).hexdigest()[:10]}")
PY
)"
NETWORK_NAME="tdc-int-$RUN_TOKEN"
RELAY_NAME="tdc-relay-$RUN_TOKEN"
RELAY_STARTED=0
NETWORK_CREATED=0

on_exit() {
  local rc="$?"
  local template_rc=0
  trap - EXIT
  set +e
  if [[ "$RELAY_STARTED" == "1" ]]; then
    docker logs "$RELAY_NAME" > "$RELAY_LOG_FILE" 2>&1
    docker rm -f "$RELAY_NAME" >/dev/null 2>&1
  fi
  if [[ "$NETWORK_CREATED" == "1" ]]; then
    docker network rm "$NETWORK_NAME" >/dev/null 2>&1
  fi
  if [[ -f "$TEMPLATE_ARTIFACTS_BEFORE" ]]; then
    real_eval_assert_no_new_forbidden_artifacts "$FRAMEWORK_SRC" "$TEMPLATE_ARTIFACTS_BEFORE"
    template_rc=$?
  fi
  if [[ "$rc" -eq 0 && "$template_rc" -ne 0 ]]; then
    rc="$template_rc"
  fi
  exit "$rc"
}
trap on_exit EXIT

real_eval_require_clean_dir "$BASE"
mkdir -p "$WORKSPACE" "$INPUT_ROOT/automation/scripts" "$INPUT_ROOT/docs" "$CODEX_HOME_DIR" "$LOG_DIR"
chmod 700 "$CODEX_HOME_DIR"

for required in \
  "$DATASET_ROOT/train.csv" \
  "$DATASET_ROOT/validation.csv" \
  "$DATASET_ROOT/test.csv" \
  "$DATASET_ROOT/dataset_manifest.json" \
  "$HIDDEN_LABELS_FILE" \
  "$CONTRACT_FILE" \
  "$PROVIDER_CONFIG"; do
  [[ -f "$required" ]] || { echo "missing required Topic 5 host input" >&2; exit 21; }
done
[[ -d "$FRAMEWORK_SRC" ]] || { echo "missing framework source: $FRAMEWORK_SRC" >&2; exit 22; }
[[ -f "$FRAMEWORK_SRC/$FRAMEWORK_NATIVE_ENTRYPOINT_FILE" ]] || {
  echo "missing native entrypoint file: $FRAMEWORK_NATIVE_ENTRYPOINT_FILE" >&2
  exit 23
}
[[ -f "$FRAMEWORK_SRC/$FRAMEWORK_NATIVE_ENTRYPOINT_SOURCE" ]] || {
  echo "missing native entrypoint source evidence: $FRAMEWORK_NATIVE_ENTRYPOINT_SOURCE" >&2
  exit 24
}
if [[ "$FRAMEWORK_COMMAND_LABEL" == *"codex exec"* && "$FRAMEWORK_EXECUTOR_KIND" != "official_framework_skill" ]]; then
  echo "generic codex exec is forbidden as a Topic 5 full-run owner" >&2
  exit 25
fi
case "$FRAMEWORK_EXECUTOR_KIND" in
  framework_cli|framework_internal_codex_runner|official_framework_skill) ;;
  *) echo "unsupported framework executor kind: $FRAMEWORK_EXECUTOR_KIND" >&2; exit 26 ;;
esac
if [[ "$FRAMEWORK_EXECUTOR_KIND" == "official_framework_skill" ]]; then
  [[ "$FRAMEWORK_NATIVE_ENTRYPOINT_SOURCE" == skills/skills-codex/* ]] || {
    echo "official framework skill has no Codex-native source evidence" >&2
    exit 26
  }
  [[ "$FRAMEWORK_RUNTIME_COMMAND" == *"install_aris_codex.sh"* && "$FRAMEWORK_RUNTIME_COMMAND" == *"research-pipeline"* ]] || {
    echo "official ARIS skill install or invocation is missing" >&2
    exit 26
  }
fi
if printf '%s\n' "$FRAMEWORK_ENTRY_PATHS" "$FRAMEWORK_RUNTIME_COMMAND" "$FRAMEWORK_COMMAND_LABEL" \
  | rg -qi 'babylm|gave2|arc_wbe_2026|arc-wbe-2026|psydefdetect'; then
  echo "Topic 5 wrapper contains another Topic marker" >&2
  exit 27
fi
if [[ "$FRAMEWORK_NEEDS_HOST_CODEX" == "1" && ! -x "$HOST_NODE_ROOT/bin/codex" ]]; then
  echo "framework-internal Codex runner is unavailable" >&2
  exit 28
fi

CLIENT_KEY="$(python3 -c 'import secrets; print(secrets.token_hex(24))')"
python3 "$ROOT/real_eval/scripts/prepare_tdc_admet_tox_gpt_relay.py" \
  --provider-config "$PROVIDER_CONFIG" \
  --client-base-url "$CLIENT_RELAY_BASE_URL" \
  --client-key "$CLIENT_KEY" \
  --upstream-env "$UPSTREAM_ENV" \
  --client-env "$PROVIDER_ENV" \
  --codex-config "$CODEX_HOME_DIR/config.toml" \
  --evidence "$RELAY_EVIDENCE" \
  --evaluation-variant "$EVAL_VARIANT"
unset CLIENT_KEY
EVAL_MODEL="$(python3 - "$RELAY_EVIDENCE" <<'PY'
import json, sys
print(json.load(open(sys.argv[1], encoding="utf-8"))["model"])
PY
)"

python3 "$ROOT/automation/scripts/generate_tdc_admet_tox_native_inputs.py" \
  --output-root "$INPUT_ROOT" \
  --primary-model "$EVAL_MODEL" \
  --provider-base-url "$CLIENT_RELAY_BASE_URL"
cp "$CONTRACT_FILE" "$INPUT_ROOT/automation/tdc_admet_tox_contract.md"
cp "$ROOT/automation/tdc_admet_tox_execution_budget.md" "$INPUT_ROOT/automation/"
cp "$ROOT/automation/scripts/run_tdc_admet_tox_validation_score.py" "$INPUT_ROOT/automation/scripts/"
cp "$ROOT/automation/scripts/validate_tdc_admet_tox_run.py" "$INPUT_ROOT/automation/scripts/"
cp "$ROOT/docs/tdc_admet_tox_"*.md "$INPUT_ROOT/docs/"

real_eval_snapshot_forbidden_artifacts "$FRAMEWORK_SRC" "$TEMPLATE_ARTIFACTS_BEFORE"
real_eval_rsync_repo "$FRAMEWORK_SRC" "$WORKSPACE"
real_eval_purge_cross_topic_residue "$WORKSPACE" tdc_admet_tox
if [ -f "$ROOT/real_eval_contract_tools.py" ]; then
  cp "$ROOT/real_eval_contract_tools.py" "$WORKSPACE/real_eval_contract_tools.py"
fi
if find "$WORKSPACE" 2>/dev/null \
  \( -iname '*babylm*' -o -iname '*gave2*' -o -iname '*arc_wbe_2026*' -o -iname '*arc-wbe-2026*' -o -iname '*psydefdetect*' \) \
  -print -quit | rg -q .; then
  echo "framework workspace still contains a cross-topic path after purge" >&2
  exit 29
fi

mkdir -p "$WORKSPACE/automation/scripts" "$WORKSPACE/docs" "$WORKSPACE/data"
rsync -a "$INPUT_ROOT/automation/" "$WORKSPACE/automation/"
rsync -a "$INPUT_ROOT/docs/" "$WORKSPACE/docs/"
if [[ "$FRAMEWORK_WORKSPACE_DATASET_PROJECTION" == "1" ]]; then
  rm -f "$WORKSPACE/data/tdc_admet_tox"
  mkdir -p "$WORKSPACE/data/tdc_admet_tox"
else
  ln -sfn /data/tdc_admet_tox "$WORKSPACE/data/tdc_admet_tox"
fi

declare -a copied_inputs=()
while IFS= read -r relative_path; do
  [[ -z "$relative_path" ]] && continue
  workspace_relative="$relative_path"
  if [[ "$workspace_relative" == "$FRAMEWORK_ENTRY_PREFIX/"* ]]; then
    workspace_relative="${workspace_relative#${FRAMEWORK_ENTRY_PREFIX}/}"
  fi
  if [[ -f "$INPUT_ROOT/$relative_path" ]]; then
    source_path="$INPUT_ROOT/$relative_path"
  elif [[ -f "$FRAMEWORK_SRC/$workspace_relative" ]]; then
    source_path="$FRAMEWORK_SRC/$workspace_relative"
  elif [[ -f "$ROOT/$relative_path" ]]; then
    source_path="$ROOT/$relative_path"
  else
    echo "missing required native input: $relative_path" >&2
    exit 30
  fi
  destination="$WORKSPACE/$workspace_relative"
  mkdir -p "$(dirname "$destination")"
  cp "$source_path" "$destination"
  copied_inputs+=("$workspace_relative")
done <<< "$FRAMEWORK_ENTRY_PATHS"
real_eval_assert_no_credential_copies "$WORKSPACE"
chmod -R u+rwX,go-rwx "$WORKSPACE"
chmod -R a+rX "$INPUT_ROOT"
chmod 700 "$CODEX_HOME_DIR"
chmod 600 "$CODEX_HOME_DIR/config.toml"
chmod 600 "$PROVIDER_ENV" "$UPSTREAM_ENV"
# Replace host.docker.internal with 172.17.0.1 in upstream env for relay DNS resolution
sed -i 's/host\.docker\.internal/172.17.0.1/g' "$UPSTREAM_ENV"

docker network create "$NETWORK_NAME" >/dev/null
NETWORK_CREATED=1
docker run -d \
  --name "$RELAY_NAME" \
  --network bridge \
  --add-host=host.docker.internal:host-gateway \
  --env-file "$UPSTREAM_ENV" \
  -v "$ROOT/real_eval/codex_relay/relay.py:/app/relay.py:ro" \
  "$RELAY_IMAGE" >/dev/null
RELAY_STARTED=1
docker network connect --alias "tdc-${EVAL_VARIANT}-relay" "$NETWORK_NAME" "$RELAY_NAME"
docker exec "$RELAY_NAME" python -c \
  'from urllib.request import urlopen; assert urlopen("http://127.0.0.1:8787/healthz", timeout=5).status == 200'
RELAY_IMAGE_ID="$(docker image inspect --format '{{.Id}}' "$RELAY_IMAGE")"
FRAMEWORK_IMAGE_ID="$(docker image inspect --format '{{.Id}}' "$FRAMEWORK_RUNTIME_IMAGE")"

COPIED_INPUTS_JSON="$(python3 - "${copied_inputs[@]}" <<'PY'
import json, sys
print(json.dumps(sys.argv[1:], ensure_ascii=True))
PY
)"
python3 - \
   "$MANIFEST_FILE" "$FRAMEWORK_NAME" "$FRAMEWORK_SLUG" "$FRAMEWORK_RUNTIME_IMAGE" \
   "$FRAMEWORK_NATIVE_ENTRYPOINT" "$FRAMEWORK_NATIVE_ENTRYPOINT_SOURCE" \
   "$FRAMEWORK_PROVIDER_INJECTION" "$FRAMEWORK_EXECUTOR_KIND" "$FRAMEWORK_COMMAND_LABEL" \
   "$FRAMEWORK_NATIVE_LOG_MARKER" "$EVAL_MODEL" "$CLIENT_RELAY_BASE_URL" \
   "$NETWORK_NAME" "$RELAY_NAME" "$RELAY_IMAGE_ID" "$FRAMEWORK_IMAGE_ID" "$COPIED_INPUTS_JSON" \
   "$FRAMEWORK_NATIVE_PROCESS_MARKERS" "$EVAL_VARIANT" <<'PY'
import json, sys
payload = {
    "task_id": "tdc_admet_tox",
    "evaluation_variant": sys.argv[19],
    "comparison_mode": "native_framework_orchestration",
    "framework": sys.argv[2],
    "slug": sys.argv[3],
    "runtime_kind": "docker",
    "runtime_image": sys.argv[4],
    "runtime_image_id": sys.argv[16],
    "framework_orchestration": True,
    "native_entrypoint": sys.argv[5],
    "native_entrypoint_source": sys.argv[6],
    "provider_injection": sys.argv[7],
    "executor_kind": sys.argv[8],
    "actual_launch_command": sys.argv[9],
    "native_log_marker": sys.argv[10],
    "native_process_markers": sys.argv[18].splitlines(),
    "native_stdout_log": "logs/native_stdout.log",
    "native_process_evidence": "native_process_evidence.json",
    "evaluation_model": sys.argv[11],
    "framework_internal_api_base_url": sys.argv[12],
    "network_isolation": {
        "framework_network": sys.argv[13],
        "framework_network_internal": True,
        "relay_container": sys.argv[14],
        "relay_image_id": sys.argv[15],
        "public_network_visible_to_framework": False,
    },
    "copied_inputs": json.loads(sys.argv[17]),
    "hidden_labels_projected": False,
    "host_score_after_framework_gate": True,
}
with open(sys.argv[1], "w", encoding="utf-8") as handle:
    json.dump(payload, handle, ensure_ascii=True, indent=2)
    handle.write("\n")
PY

declare -a docker_extra_args=()
if [[ -n "$FRAMEWORK_DOCKER_ARGS" ]]; then
  while IFS= read -r arg; do
    [[ -z "$arg" ]] && continue
    docker_extra_args+=("$arg")
  done <<< "$FRAMEWORK_DOCKER_ARGS"
fi
declare -a host_codex_args=()
if [[ "$FRAMEWORK_NEEDS_HOST_CODEX" == "1" ]]; then
  host_codex_args+=(-v "$HOST_NODE_ROOT:$CONTAINER_NODE_ROOT:ro")
fi
declare -a workspace_dataset_args=()
if [[ "$FRAMEWORK_WORKSPACE_DATASET_PROJECTION" == "1" ]]; then
  workspace_dataset_args+=(
    -v "$DATASET_ROOT:$FRAMEWORK_CONTAINER_WORKDIR/data/tdc_admet_tox:ro"
  )
fi
docker_runtime_command="$FRAMEWORK_RUNTIME_COMMAND"

{
  echo "[$(date -Is)] topic=tdc_admet_tox variant=$EVAL_VARIANT framework=$FRAMEWORK_NAME"
  echo "workspace=$WORKSPACE"
  echo "runtime_image=$FRAMEWORK_RUNTIME_IMAGE"
  echo "native_entrypoint=$FRAMEWORK_NATIVE_ENTRYPOINT"
  echo "native_entrypoint_source=$FRAMEWORK_NATIVE_ENTRYPOINT_SOURCE"
  echo "actual_launch_command=$FRAMEWORK_COMMAND_LABEL"
  echo "executor_kind=$FRAMEWORK_EXECUTOR_KIND"
  echo "evaluation_model=$EVAL_MODEL"
  echo "framework_network_internal=true"
  echo "hidden_labels_projected=false"
} | tee "$LOG_FILE"

declare -a docker_cmd=(
  docker run --rm
  --name "tdc-fw-$RUN_TOKEN"
  --network "$NETWORK_NAME"
  --cpus 4
  --memory 16g
  --pids-limit 2048
  --env-file "$PROVIDER_ENV"
  -e HOME="$FRAMEWORK_CONTAINER_HOME"
  -e CODEX_HOME="$FRAMEWORK_CONTAINER_CODEX_HOME"
  -e RESEARCHCLAWEVAL_TOPIC_LABEL=TDC-ADMET-Tox
  -e RESEARCHCLAWEVAL_TOPIC_DATASET_ROOT=/data/tdc_admet_tox
  -e RESEARCHCLAWEVAL_TOPIC_CONTRACT_FILE=/workspace/automation/tdc_admet_tox_contract.md
  -e TDC_ADMET_TOX_DATASET_ROOT=/data/tdc_admet_tox
  -e TDC_ADMET_TOX_CONTRACT_FILE=/workspace/automation/tdc_admet_tox_contract.md
  -e TDC_ADMET_TOX_EVAL_MODEL="$EVAL_MODEL"
  -e TDC_ADMET_TOX_EVAL_VARIANT="$EVAL_VARIANT"
  -e TDC_ADMET_TOX_BASELINE_TIMEOUT="${TDC_ADMET_TOX_BASELINE_TIMEOUT:-3600}"
  -e TDC_ADMET_TOX_IDEA_TIMEOUT="${TDC_ADMET_TOX_IDEA_TIMEOUT:-3600}"
  -e TDC_ADMET_TOX_EXPERIMENT_TIMEOUT="${TDC_ADMET_TOX_EXPERIMENT_TIMEOUT:-14400}"
  -e TDC_ADMET_TOX_WRITE_TIMEOUT="${TDC_ADMET_TOX_WRITE_TIMEOUT:-3600}"
  -e REAL_EVAL_RUN_ID="$RUN_ID"
  -e FRAMEWORK_NAME="$FRAMEWORK_NAME"
  -e FRAMEWORK_SLUG="$FRAMEWORK_SLUG"
  -v "$WORKSPACE:$FRAMEWORK_CONTAINER_WORKDIR"
  -v "$INPUT_ROOT:/input:ro"
  -v "$DATASET_ROOT:/data/tdc_admet_tox:ro"
  -v "$CODEX_HOME_DIR:$FRAMEWORK_CONTAINER_CODEX_HOME"
  "${workspace_dataset_args[@]}"
  "${host_codex_args[@]}"
  "${docker_extra_args[@]}"
  -w "$FRAMEWORK_CONTAINER_WORKDIR"
  --entrypoint "$FRAMEWORK_ENTRYPOINT"
  "$FRAMEWORK_RUNTIME_IMAGE"
  -lc "$docker_runtime_command"
)

set +e
native_started_epoch="$(date +%s)"
timeout 10800s "${docker_cmd[@]}" 2>&1 \
  | python3 "$ROOT/real_eval/scripts/redact_env_secrets.py" \
      --env-file "$PROVIDER_ENV" --env-file "$UPSTREAM_ENV" \
  | tee -a "$LOG_FILE" "$NATIVE_STDOUT_FILE"
native_rc=${PIPESTATUS[0]}
native_wall_seconds="$(( $(date +%s) - native_started_epoch ))"
set -e

native_evidence_ok=1
if ! rg -Fq "$FRAMEWORK_NATIVE_LOG_MARKER" "$LOG_FILE"; then
  native_evidence_ok=0
fi
if [[ -n "$FRAMEWORK_LOG_FORBIDDEN_PATTERN" ]] && rg -q "$FRAMEWORK_LOG_FORBIDDEN_PATTERN" "$LOG_FILE"; then
  native_evidence_ok=0
fi
if find "$WORKSPACE" 2>/dev/null \
  \( -iname '*babylm*' -o -iname '*gave2*' -o -iname '*arc_wbe_2026*' \
    -o -iname '*arc-wbe-2026*' -o -iname '*psydefdetect*' \
    -o -iname 'test_labels.csv' -o -iname '*hidden*labels*' \) \
  -print -quit | rg -q .; then
  native_evidence_ok=0
fi
python3 - "$NATIVE_PROCESS_EVIDENCE_FILE" "$NATIVE_STDOUT_FILE" "$FRAMEWORK_NAME" \
  "$FRAMEWORK_NATIVE_PROCESS_MARKERS" <<'PY'
import json, sys
from pathlib import Path

log_text = Path(sys.argv[2]).read_text(encoding="utf-8", errors="replace")
markers = [marker for marker in sys.argv[4].splitlines() if marker]
checks = [{"marker": marker, "found": marker in log_text} for marker in markers]
payload = {
    "framework": sys.argv[3],
    "native_stdout_log": "logs/native_stdout.log",
    "checks": checks,
    "all_passed": bool(checks) and all(row["found"] for row in checks),
}
Path(sys.argv[1]).write_text(
    json.dumps(payload, ensure_ascii=True, indent=2) + "\n", encoding="utf-8"
)
PY
if ! python3 - "$NATIVE_PROCESS_EVIDENCE_FILE" <<'PY'
import json, sys
raise SystemExit(0 if json.load(open(sys.argv[1], encoding="utf-8"))["all_passed"] else 1)
PY
then
  native_evidence_ok=0
fi
if [[ "$FRAMEWORK_EXECUTOR_KIND" == "official_framework_skill" ]]; then
  if [[ ! -s "$WORKSPACE/.aris/installed-skills-codex.txt" \
    || ! -L "$WORKSPACE/.agents/skills/research-pipeline" \
    || ! -s "$WORKSPACE/aris_tdc_admet_tox_last_message.txt" ]]; then
    native_evidence_ok=0
  fi
fi

framework_audit_rc=1
set +e
python3 "$ROOT/automation/scripts/validate_tdc_admet_tox_run.py" \
  --workspace "$WORKSPACE" \
  --stage framework \
  --public-dataset-root "$DATASET_ROOT" > "$FRAMEWORK_AUDIT_FILE" 2>&1
framework_audit_rc=$?
set -e

provider_trace_rc=1
if [[ "$framework_audit_rc" -eq 0 ]]; then
  set +e
  python3 - "$WORKSPACE/experiment_trace.json" "$EVAL_MODEL" "$CLIENT_RELAY_BASE_URL" <<'PY'
import json, sys
trace = json.load(open(sys.argv[1], encoding="utf-8"))
if trace.get("framework_native_execution") is not True:
    raise SystemExit("framework_native_execution is not true")
if trace.get("framework_internal_model") != sys.argv[2]:
    raise SystemExit("framework_internal_model does not match the injected model")
if str(trace.get("framework_internal_api_base_url", "")).rstrip("/") != sys.argv[3].rstrip("/"):
    raise SystemExit("framework_internal_api_base_url does not match the isolated relay")
PY
  provider_trace_rc=$?
  set -e
fi

research_completed=false
if [[ "$framework_audit_rc" -eq 0 && "$provider_trace_rc" -eq 0 && "$native_evidence_ok" -eq 1 ]]; then
  research_completed=true
fi

scored=false
score_rc=1
if [[ "$research_completed" == true ]]; then
  set +e
  python3 "$ROOT/automation/scripts/run_tdc_admet_tox_host_score.py" \
    --public-dataset-root "$DATASET_ROOT" \
    --hidden-labels "$HIDDEN_LABELS_FILE" \
    --predictions "$WORKSPACE/predictions.csv" \
    --output-score "$WORKSPACE/score.json" > "$LOG_DIR/host_score.log" 2>&1
  score_rc=$?
  set -e
  if [[ "$score_rc" -eq 0 ]]; then
    scored=true
  fi
fi

contract_complete=false
final_audit_rc=1
if [[ "$scored" == true ]]; then
  set +e
  python3 "$ROOT/automation/scripts/validate_tdc_admet_tox_run.py" \
    --workspace "$WORKSPACE" \
    --stage final \
    --public-dataset-root "$DATASET_ROOT" > "$FINAL_AUDIT_FILE" 2>&1
  final_audit_rc=$?
  set -e
  if [[ "$final_audit_rc" -eq 0 ]]; then
    contract_complete=true
  fi
fi

workspace_kib="$( { du -sk "$WORKSPACE" 2>/dev/null || true; } | awk 'NR==1 {gsub(/[^0-9]/,"",$1); print $1; exit}' )"
workspace_kib="${workspace_kib:-0}"
workspace_within_budget=true
if [[ "${workspace_kib//[^0-9]/}" -gt 10485760 ]]; then
  workspace_within_budget=false
  contract_complete=false
fi

engineering_complete=true
status="failed_native_research"
summary="Native framework did not produce an auditable Topic 5 handoff"
if [[ "$research_completed" == true && "$scored" == false ]]; then
  status="research_completed_unscored"
  summary="Native research completed, but host scoring failed"
elif [[ "$research_completed" == true && "$scored" == true && "$contract_complete" == false ]]; then
  status="research_completed_scored_contract_warning"
  summary="Native research completed and was scored, but final contract validation failed"
elif [[ "$contract_complete" == true ]]; then
  status="finished"
  summary="Native Topic 5 research, host scoring, and final contract validation completed"
fi

python3 - \
  "$OUTCOME_FILE" "$STATE_FILE" "$status" "$summary" "$native_rc" \
  "$research_completed" "$scored" "$contract_complete" "$engineering_complete" \
  "$framework_audit_rc" "$provider_trace_rc" "$score_rc" "$final_audit_rc" \
  "$workspace_kib" "$workspace_within_budget" "$native_wall_seconds" <<'PY'
from datetime import datetime, timezone
import json, sys

def boolean(raw):
    return raw.lower() == "true"

dimensions = {
    "research_completed": boolean(sys.argv[6]),
    "scored": boolean(sys.argv[7]),
    "contract_complete": boolean(sys.argv[8]),
    "engineering_complete": boolean(sys.argv[9]),
}
outcome = {
    "status": sys.argv[3],
    **dimensions,
    "native_exit_code": int(sys.argv[5]),
    "framework_audit_exit_code": int(sys.argv[10]),
    "provider_trace_exit_code": int(sys.argv[11]),
    "host_score_exit_code": int(sys.argv[12]),
    "final_audit_exit_code": int(sys.argv[13]),
    "workspace_kib": int(sys.argv[14]),
    "workspace_within_budget": boolean(sys.argv[15]),
    "observed_native_wall_seconds": int(sys.argv[16]),
}
state = {
    "project_id": "tdc_admet_tox",
    "phase": "fullrun",
    "status": sys.argv[3],
    "summary": sys.argv[4],
    "updated_at": datetime.now(timezone.utc).astimezone().isoformat(),
    "exit_code": 0,
    **dimensions,
}
for path, payload in ((sys.argv[1], outcome), (sys.argv[2], state)):
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=True, indent=2)
        handle.write("\n")
PY

exit 0
