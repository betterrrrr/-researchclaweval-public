#!/usr/bin/env bash
set -euo pipefail

ROOT="${RESEARCHCLAWEVAL_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
source "$ROOT/real_eval/scripts/lib_real_eval.sh"
BASE="${REAL_EVAL_RUN_ROOT:?REAL_EVAL_RUN_ROOT is required}"
RUN_ID="${REAL_EVAL_RUN_ID:?REAL_EVAL_RUN_ID is required}"
FRAMEWORK_NAME="${FRAMEWORK_NAME:?FRAMEWORK_NAME is required}"
FRAMEWORK_SLUG="${FRAMEWORK_SLUG:?FRAMEWORK_SLUG is required}"
FRAMEWORK_SRC="${FRAMEWORK_SRC:?FRAMEWORK_SRC is required}"
FRAMEWORK_RUNTIME_IMAGE="${FRAMEWORK_RUNTIME_IMAGE:?FRAMEWORK_RUNTIME_IMAGE is required}"
FRAMEWORK_NATIVE_ENTRYPOINT="${FRAMEWORK_NATIVE_ENTRYPOINT:?FRAMEWORK_NATIVE_ENTRYPOINT is required}"
FRAMEWORK_NATIVE_ENTRYPOINT_FILE="${FRAMEWORK_NATIVE_ENTRYPOINT_FILE:-$FRAMEWORK_NATIVE_ENTRYPOINT}"
DATASET_ROOT="${TDC_ADMET_TOX_DATASET_ROOT:-$(real_eval_resolve_topic_dataset "$ROOT" tdc_admet_tox)}"
CONTRACT_FILE="${TDC_ADMET_TOX_CONTRACT_FILE:-$ROOT/automation/tdc_admet_tox_contract.md}"
PROVIDER_CONFIG="${PROVIDER_CONFIG:-$ROOT/api/codex_gpt54_shubiaobiao.toml}"
EVAL_VARIANT="${TDC_ADMET_TOX_EVAL_VARIANT:-gpt}"
HOST_NODE_ROOT="${REAL_EVAL_HOST_NODE_ROOT:-$(dirname "$(dirname "$(command -v node)")")}" 
CONTAINER_NODE_ROOT="/opt/researchclaweval-node"

WORKSPACE="$BASE/workspace"
INPUT_ROOT="$BASE/inputs"
CODEX_HOME_DIR="$BASE/codex_home"
LOG_DIR="$BASE/logs"
LOG_FILE="$LOG_DIR/smoke.log"
STATE_FILE="$BASE/state.json"
MANIFEST_FILE="$BASE/smoke_manifest.json"
PROVIDER_ENV="$BASE/provider.env"
UPSTREAM_ENV="$BASE/upstream_relay.env"
RELAY_EVIDENCE="$BASE/provider_relay_evidence.json"
RELAY_LOG_FILE="$LOG_DIR/provider_relay.log"
TEMPLATE_ARTIFACTS_BEFORE="$BASE/template_forbidden_artifacts.before"
RELAY_IMAGE="${TDC_ADMET_TOX_GPT_RELAY_IMAGE:-researchclaweval/codex-kimi-relay:test}"
CLIENT_RELAY_BASE_URL="http://tdc-gpt-relay:8787/v1"
RUN_TOKEN="$(python3 - "$RUN_ID" "$FRAMEWORK_SLUG" <<'PY'
import hashlib, re, sys
raw = re.sub(r"[^A-Za-z0-9_.-]", "-", f"{sys.argv[1]}-{sys.argv[2]}")
print(f"{raw[:28]}-{hashlib.sha256(raw.encode()).hexdigest()[:10]}")
PY
)"
NETWORK_NAME="tdc-smoke-int-$RUN_TOKEN"
RELAY_NAME="tdc-smoke-relay-$RUN_TOKEN"
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
    "project_id": "tdc_admet_tox",
    "phase": "smoke",
    "status": sys.argv[2],
    "summary": sys.argv[3],
    "updated_at": datetime.now(timezone.utc).astimezone().isoformat(),
    "exit_code": int(sys.argv[4]),
}
Path(sys.argv[1]).write_text(json.dumps(payload, ensure_ascii=True) + "\n", encoding="utf-8")
PY
}

real_eval_require_clean_dir "$BASE"
mkdir -p "$WORKSPACE" "$INPUT_ROOT/automation/scripts" "$INPUT_ROOT/docs" "$CODEX_HOME_DIR" "$LOG_DIR"
chmod 700 "$CODEX_HOME_DIR"
write_state "starting" "Initializing isolated TDC-ADMET-Tox smoke workspace"

if [[ ! -d "$DATASET_ROOT" || ! -f "$DATASET_ROOT/dataset_manifest.json" ]]; then
  write_state "blocked" "Missing materialized TDC-ADMET-Tox public dataset: $DATASET_ROOT" 21
  exit 21
fi
if [[ ! -f "$CONTRACT_FILE" ]]; then
  write_state "blocked" "Missing TDC-ADMET-Tox contract: $CONTRACT_FILE" 22
  exit 22
fi
if [[ ! -d "$FRAMEWORK_SRC" || ! -f "$FRAMEWORK_SRC/$FRAMEWORK_NATIVE_ENTRYPOINT_FILE" ]]; then
  write_state "blocked" "Missing framework source or native entrypoint" 23
  exit 23
fi
if [[ ! -x "$HOST_NODE_ROOT/bin/codex" ]]; then
  write_state "blocked" "Host Codex CLI is unavailable under $HOST_NODE_ROOT" 24
  exit 24
fi

real_eval_snapshot_forbidden_artifacts "$FRAMEWORK_SRC" "$TEMPLATE_ARTIFACTS_BEFORE"
real_eval_rsync_repo "$FRAMEWORK_SRC" "$WORKSPACE"
real_eval_purge_cross_topic_residue "$WORKSPACE" tdc_admet_tox
chmod -R a+rwX "$WORKSPACE"

cp "$CONTRACT_FILE" "$INPUT_ROOT/automation/tdc_admet_tox_contract.md"
cp "$ROOT/automation/tdc_admet_tox_execution_budget.md" "$INPUT_ROOT/automation/"
cp "$ROOT/automation/scripts/run_tdc_admet_tox_validation_score.py" "$INPUT_ROOT/automation/scripts/"
cp "$ROOT/docs/tdc_admet_tox_"*.md "$INPUT_ROOT/docs/"
cat > "$INPUT_ROOT/smoke_prompt.txt" <<EOF
Perform only a TDC-ADMET-Tox wiring smoke check. Do not train a model, install packages, use public internet, or create predictions.csv, score.json, experiment_trace.json, paper.md, or environment.json.

Use local shell/Python tools to verify:
1. /workspace/$FRAMEWORK_NATIVE_ENTRYPOINT_FILE exists as the declared native entrypoint source for $FRAMEWORK_NAME.
2. /data/tdc_admet_tox contains exactly train.csv, validation.csv, test.csv, and dataset_manifest.json.
3. train.csv and validation.csv have sample_id,endpoint,smiles,label; test.csv has sample_id,endpoint,smiles and no label.
4. The endpoint set is exactly AMES, hERG, DILI in every split.
5. /input/automation/tdc_admet_tox_contract.md and /input/docs/tdc_admet_tox_compute_budget.md are readable.
 6. No environment variable name or mounted path exposes host-only test labels. Topic-identifier variables such as RESEARCHCLAWEVAL_TOPIC_LABEL (value "TDC-ADMET-Tox") are allowed. Flag only variables or paths whose name or value points to hidden labels (for example, any name containing hidden_labels_root or test_labels, or a path to a file with test labels). Never print environment variable values or credential values; inspect names only (for example, with env | cut -d= -f1).

Write /workspace/tdc_admet_tox_smoke_evidence.json with task_id "tdc_admet_tox", framework "$FRAMEWORK_NAME", a checks object containing six true booleans named native_entrypoint, public_files, schemas, endpoints, contracts, hidden_labels_absent, and all_passed true. Keep the final response short.
EOF
chmod -R a+rX "$INPUT_ROOT"

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
chmod 700 "$CODEX_HOME_DIR"
chmod 600 "$CODEX_HOME_DIR/config.toml"
chmod 600 "$PROVIDER_ENV" "$UPSTREAM_ENV"
real_eval_assert_no_credential_copies "$WORKSPACE"

docker network create --internal "$NETWORK_NAME" >/dev/null
NETWORK_CREATED=1
docker run -d \
  --name "$RELAY_NAME" \
  --network bridge \
  --env-file "$UPSTREAM_ENV" \
  -v "$ROOT/real_eval/codex_relay/relay.py:/app/relay.py:ro" \
  "$RELAY_IMAGE" >/dev/null
RELAY_STARTED=1
docker network connect --alias tdc-gpt-relay "$NETWORK_NAME" "$RELAY_NAME"
docker exec "$RELAY_NAME" python -c \
  'from urllib.request import urlopen; assert urlopen("http://127.0.0.1:8787/healthz", timeout=5).status == 200'

{
  echo "[$(date -Is)] topic=tdc_admet_tox framework=$FRAMEWORK_NAME"
  echo "workspace=$WORKSPACE"
  echo "dataset_root=$DATASET_ROOT"
  echo "native_entrypoint=$FRAMEWORK_NATIVE_ENTRYPOINT"
  echo "runtime_image=$FRAMEWORK_RUNTIME_IMAGE"
} | tee "$LOG_FILE"

docker_runtime_command='set -euo pipefail
export PATH="/opt/researchclaweval-node/bin:$PATH"
test -x /opt/researchclaweval-node/bin/codex
test -f "/workspace/$FRAMEWORK_NATIVE_ENTRYPOINT_FILE"
test -r /data/tdc_admet_tox/test.csv
test -r /input/smoke_prompt.txt
codex exec --yolo --ephemeral --skip-git-repo-check -C /workspace -o /workspace/tdc_admet_tox_smoke_last_message.txt - < /input/smoke_prompt.txt'

write_state "running" "Launching blocking headless Codex smoke for $FRAMEWORK_NAME"
run_rc=0
set +e
docker run --rm \
  --name "$(printf '%s' "$FRAMEWORK_SLUG-$RUN_ID-smoke" | tr -c 'A-Za-z0-9_.-' '-')" \
  --network "$NETWORK_NAME" \
  --cpus 4 \
  --memory 16g \
  --pids-limit 2048 \
  --env-file "$PROVIDER_ENV" \
  -e HOME=/workspace \
  -e CODEX_HOME=/codex-home \
  -e FRAMEWORK_NATIVE_ENTRYPOINT="$FRAMEWORK_NATIVE_ENTRYPOINT" \
  -e FRAMEWORK_NATIVE_ENTRYPOINT_FILE="$FRAMEWORK_NATIVE_ENTRYPOINT_FILE" \
  -e RESEARCHCLAWEVAL_TOPIC_LABEL=TDC-ADMET-Tox \
  -e TDC_ADMET_TOX_DATASET_ROOT=/data/tdc_admet_tox \
  -e TDC_ADMET_TOX_CONTRACT_FILE=/input/automation/tdc_admet_tox_contract.md \
  -e REAL_EVAL_RUN_ID="$RUN_ID" \
  -v "$WORKSPACE":/workspace \
  -v "$INPUT_ROOT":/input:ro \
  -v "$DATASET_ROOT":/data/tdc_admet_tox:ro \
  -v "$CODEX_HOME_DIR":/codex-home \
  -v "$HOST_NODE_ROOT":$CONTAINER_NODE_ROOT:ro \
  -w /workspace \
  --entrypoint bash \
  "$FRAMEWORK_RUNTIME_IMAGE" \
  -lc "$docker_runtime_command" 2>&1 \
  | python3 "$ROOT/real_eval/scripts/redact_env_secrets.py" \
      --env-file "$PROVIDER_ENV" --env-file "$UPSTREAM_ENV" \
  | tee -a "$LOG_FILE"
run_rc=${PIPESTATUS[0]}
set -e

python3 - "$MANIFEST_FILE" "$WORKSPACE" "$DATASET_ROOT" "$FRAMEWORK_NAME" "$FRAMEWORK_RUNTIME_IMAGE" "$FRAMEWORK_NATIVE_ENTRYPOINT" "$FRAMEWORK_NATIVE_ENTRYPOINT_FILE" "$run_rc" <<'PY'
from pathlib import Path
import csv
import json
import sys

manifest_path = Path(sys.argv[1])
workspace = Path(sys.argv[2])
dataset = Path(sys.argv[3])
evidence_path = workspace / "tdc_admet_tox_smoke_evidence.json"
forbidden_outputs = [
    "predictions.csv",
    "score.json",
    "experiment_trace.json",
    "paper.md",
    "environment.json",
]

def header(name):
    with (dataset / name).open("r", encoding="utf-8", newline="") as handle:
        return next(csv.reader(handle))

def endpoint_set(name):
    with (dataset / name).open("r", encoding="utf-8", newline="") as handle:
        return {row["endpoint"] for row in csv.DictReader(handle)}

try:
    evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
except Exception:
    evidence = None

run_root = manifest_path.parent
credential_values = []
for env_path in (run_root / "provider.env", run_root / "upstream_relay.env"):
    for line in env_path.read_text(encoding="utf-8").splitlines():
        key, separator, value = line.partition("=")
        if separator and "KEY" in key and value:
            credential_values.append(value)
log_text = (run_root / "logs" / "smoke.log").read_text(encoding="utf-8")

checks = {
    "codex_exit_zero": int(sys.argv[8]) == 0,
    "native_entrypoint_present": (workspace / sys.argv[7]).is_file(),
    "public_file_set_exact": {p.name for p in dataset.iterdir() if p.is_file()} == {
        "train.csv", "validation.csv", "test.csv", "dataset_manifest.json"
    },
    "labeled_schema": header("train.csv") == ["sample_id", "endpoint", "smiles", "label"]
        and header("validation.csv") == ["sample_id", "endpoint", "smiles", "label"],
    "test_schema_unlabeled": header("test.csv") == ["sample_id", "endpoint", "smiles"],
    "endpoint_sets_exact": all(
        endpoint_set(name) == {"AMES", "hERG", "DILI"}
        for name in ("train.csv", "validation.csv", "test.csv")
    ),
    "cross_topic_paths_absent": not any(
        any(
            marker in part.lower()
            for marker in ("babylm", "gave2", "arc_wbe_2026", "arc-wbe-2026", "psydefdetect")
        )
        for path in workspace.rglob("*")
        for part in path.relative_to(workspace).parts
    ),
    "credentials_absent_from_log": all(value not in log_text for value in credential_values),
    "agent_evidence": isinstance(evidence, dict)
        and evidence.get("task_id") == "tdc_admet_tox"
        and evidence.get("framework") == sys.argv[4]
        and (evidence.get("all_passed") is True or evidence.get("checks", {}).get("all_passed") is True)
        and isinstance(evidence.get("checks"), dict)
        and all(
            (
                evidence["checks"].get(key) is True
                or (key == "contracts" and bool(evidence["checks"].get(key)))
            )
            for key in (
                "native_entrypoint", "public_files", "schemas", "endpoints", "contracts",
                "hidden_labels_absent",
            )
        ),
    "no_final_outputs": not any((workspace / name).exists() for name in forbidden_outputs),
}
payload = {
    "topic_id": "tdc_admet_tox",
    "framework": sys.argv[4],
    "image": sys.argv[5],
    "native_entrypoint": sys.argv[6],
    "dataset_root": sys.argv[3],
    "evidence_artifact": str(evidence_path) if evidence_path.is_file() else None,
    "checks": checks,
    "all_passed": all(checks.values()),
}
manifest_path.write_text(json.dumps(payload, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")
PY

if [[ "$run_rc" -ne 0 ]]; then
  write_state "failed" "TDC-ADMET-Tox Codex smoke failed" "$run_rc"
  exit "$run_rc"
fi
if ! python3 - "$MANIFEST_FILE" <<'PY'
import json
import sys
raise SystemExit(0 if json.load(open(sys.argv[1], encoding="utf-8"))["all_passed"] else 1)
PY
then
  write_state "failed" "TDC-ADMET-Tox host smoke checks failed" 25
  exit 25
fi

write_state "finished" "TDC-ADMET-Tox blocking Codex smoke passed for $FRAMEWORK_NAME" 0
