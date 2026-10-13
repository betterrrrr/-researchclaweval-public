#!/usr/bin/env bash
set -euo pipefail

ROOT="${RESEARCHCLAWEVAL_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
source "$ROOT/real_eval/scripts/lib_real_eval.sh"
RUN_ID="${REAL_EVAL_RUN_ID:-$(date +%Y%m%d-%H%M%S)}"
BASE="${REAL_EVAL_RUN_ROOT:-$ROOT/real_eval/runs/$RUN_ID/07_evoscientist}"
WORK="$BASE/workspace"
LOG_DIR="$BASE/logs"
DATASET_ROOT="${BABYLM_DATASET_ROOT:-$ROOT/BabyLM-2026-Strict-Small}"
CONTRACT_FILE="${BABYLM_CONTRACT_FILE:-$ROOT/BabyLM-10M_七框架任务包装与分发指南.md}"
PROVIDER_CONFIG="${PROVIDER_CONFIG:-$ROOT/api/codex_gpt54_shubiaobiao.toml}"
SEMANTIC_SOURCE="${SEMANTIC_SOURCE:-$ROOT/api/_semantic_scholar_api_usage.md}"
PROVIDER_ENV="$BASE/provider.env"
SEMANTIC_ENV="$BASE/semantic.env"
CONTAINER_NAME="evoscientist_babylm_${RUN_ID}"

cleanup_container() {
  docker ps -a --format '{{.Names}}' | rg "^${CONTAINER_NAME}$" | xargs -r docker rm -f >/dev/null 2>&1 || true
}
trap cleanup_container EXIT

real_eval_require_clean_dir "$BASE"
mkdir -p "$WORK" "$LOG_DIR" "$WORK/input" "$WORK/data" "$WORK/artifacts"
touch "$WORK/final_report.md"
real_eval_provider_env_from_codex_toml "$PROVIDER_CONFIG" "$PROVIDER_ENV"
real_eval_semantic_env_from_usage_md "$SEMANTIC_SOURCE" "$SEMANTIC_ENV"
cp "$CONTRACT_FILE" "$WORK/input/contract.md"

mkdir -p "$WORK/.config/evoscientist"
cat > "$WORK/.config/evoscientist/config.yaml" <<'EOF'
provider: custom-openai
model: gpt-5.4
openai_auth_mode: api_key
default_mode: daemon
default_workdir: /workspace
ui_backend: cli
show_thinking: false
enable_async_subagents: true
EOF

cat > "$WORK/prompt.md" <<EOF
Read input/contract.md and use data/BabyLM-2026-Strict-Small for a real BabyLM-10M end-to-end research run.

The same inputs are also mounted at /input/contract.md and /data/BabyLM-2026-Strict-Small.

You must design and run a real neural language-model training experiment, save checkpoints under artifacts/checkpoints, write training logs, evaluate the trained model, and write final_report.md from actual results.

Use Lite code generation mode. Do not ask for a mode choice and do not stop for clarification; proceed directly to implementation, training, evaluation, and report writing.

The Docker container has GPU access through --gpus all and CUDA_VISIBLE_DEVICES=0. Do not set CUDA_VISIBLE_DEVICES to an empty string or otherwise hide CUDA. Use torch.cuda.is_available() and train on CUDA. Write all artifacts under the workspace-relative artifacts/ directory. /artifacts is bind-mounted to the same workspace artifacts directory, so /artifacts is also acceptable for training artifacts. Write the final report to /workspace/final_report.md; /final_report.md is also bind-mounted to that same file.

Before exiting, verify and record that the actual training device is cuda. A CPU run is invalid for this evaluation.

Forbidden: proxy scripts, unigram/bigram-only scoring, iris, digits, previous experiment results, placeholder reports.
EOF

cat > "$BASE/state.json" <<EOF
{"project_id":"07","name":"EvoScientist","run_id":"$RUN_ID","status":"starting","workspace":"$WORK"}
EOF

set +e
docker_args=(
  --rm
  --name "$CONTAINER_NAME"
  --gpus all
  --entrypoint bash
  --user "$(id -u):$(id -g)"
  -e EVOSCIENTIST_OPENAI_AUTH_MODE=api_key
  -e HOME=/workspace
  -e CUDA_VISIBLE_DEVICES=0
  -e PYTHONUSERBASE=/workspace/.local
  -e PATH=/workspace/.local/bin:/usr/local/bin:/usr/bin:/bin
  --env-file "$PROVIDER_ENV"
  --env-file "$SEMANTIC_ENV"
  --env-file "$ROOT/EvoScientist/.env.project07"
  -v "$WORK":/workspace
  -v "$WORK/artifacts":/artifacts
  -v "$WORK/final_report.md":/final_report.md
  -v "$DATASET_ROOT":/workspace/data/BabyLM-2026-Strict-Small:ro
  -v "$DATASET_ROOT":/data/BabyLM-2026-Strict-Small:ro
  -v "$CONTRACT_FILE":/input/contract.md:ro
  -v "$CONTRACT_FILE":/workspace/input/contract.md:ro
  -w /workspace
)
docker run "${docker_args[@]}" evoscientist:runtime-ready \
  -lc 'set -euo pipefail; /opt/venv/bin/evoscientist --use-cwd -p "$(cat /workspace/prompt.md)" --auto-mode --auto-approve --ui cli --no-thinking' \
  2>&1 | tee "$LOG_DIR/e2e.log"
rc=${PIPESTATUS[0]}
set -e
if [[ "$rc" -ne 0 ]]; then
  real_eval_write_state "$BASE/state.json" "{\"project_id\":\"07\",\"name\":\"EvoScientist\",\"run_id\":\"$RUN_ID\",\"status\":\"failed\",\"workspace\":\"$WORK\",\"log\":\"$LOG_DIR/e2e.log\",\"exit_code\":$rc}"
  exit "$rc"
fi

if ! real_eval_has_artifacts "$WORK"; then
  real_eval_write_state "$BASE/state.json" "{\"project_id\":\"07\",\"name\":\"EvoScientist\",\"run_id\":\"$RUN_ID\",\"status\":\"failed_no_artifacts\",\"workspace\":\"$WORK\",\"log\":\"$LOG_DIR/e2e.log\"}"
  exit 13
fi

if ! find "$WORK" -type f \( -iname 'final_report.md' -o -iname '*report*.md' \) -size +500c 2>/dev/null | head -1 | grep -q .; then
  real_eval_write_state "$BASE/state.json" "{\"project_id\":\"07\",\"name\":\"EvoScientist\",\"run_id\":\"$RUN_ID\",\"status\":\"failed_no_report\",\"workspace\":\"$WORK\",\"log\":\"$LOG_DIR/e2e.log\"}"
  exit 15
fi

if ! python3 - "$WORK" <<'PY'
import json
import sys
from pathlib import Path

root = Path(sys.argv[1])
device_values = []
for path in root.rglob("*.json"):
    if any(part.startswith(".") for part in path.relative_to(root).parts):
        continue
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        continue
    stack = [data]
    while stack:
        item = stack.pop()
        if isinstance(item, dict):
            for key, value in item.items():
                if key.lower() == "device" and isinstance(value, str):
                    device_values.append((str(path), value.lower()))
                elif isinstance(value, (dict, list)):
                    stack.append(value)
        elif isinstance(item, list):
            stack.extend(v for v in item if isinstance(v, (dict, list)))

if any(value.startswith("cuda") for _, value in device_values):
    raise SystemExit(0)

print("No CUDA device evidence found in JSON artifacts. Observed devices:", device_values, file=sys.stderr)
raise SystemExit(1)
PY
then
  real_eval_write_state "$BASE/state.json" "{\"project_id\":\"07\",\"name\":\"EvoScientist\",\"run_id\":\"$RUN_ID\",\"status\":\"failed_cpu_device\",\"workspace\":\"$WORK\",\"log\":\"$LOG_DIR/e2e.log\"}"
  exit 14
fi

cat > "$BASE/state.json" <<EOF
{"project_id":"07","name":"EvoScientist","run_id":"$RUN_ID","status":"finished","workspace":"$WORK","log":"$LOG_DIR/e2e.log"}
EOF
