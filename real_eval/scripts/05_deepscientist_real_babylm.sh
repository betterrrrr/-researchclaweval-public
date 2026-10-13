#!/usr/bin/env bash
set -euo pipefail

ROOT="${RESEARCHCLAWEVAL_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
source "$ROOT/real_eval/scripts/lib_real_eval.sh"
RUN_ID="${REAL_EVAL_RUN_ID:-$(date +%Y%m%d-%H%M%S)}"
BASE="${REAL_EVAL_RUN_ROOT:-$ROOT/real_eval/runs/$RUN_ID/05_deepscientist}"
HOME_DIR="$BASE/home"
WORK="$BASE/workspace"
LOG_DIR="$BASE/logs"
DATASET_ROOT="${BABYLM_DATASET_ROOT:-$ROOT/BabyLM-2026-Strict-Small}"
CONTRACT_FILE="${BABYLM_CONTRACT_FILE:-$ROOT/BabyLM-10M_七框架任务包装与分发指南.md}"
PORT="${DEEPSCIENTIST_PORT:-20999}"
CODEX_HOME_DIR="$HOME_DIR/.codex"
PROVIDER_CONFIG="${PROVIDER_CONFIG:-$ROOT/api/codex_gpt54_shubiaobiao.toml}"
SEMANTIC_SOURCE="${SEMANTIC_SOURCE:-$ROOT/api/_semantic_scholar_api_usage.md}"
PROVIDER_ENV="$BASE/provider.env"
SEMANTIC_ENV="$BASE/semantic.env"
CONTAINER_NAME="deepscientist_babylm_${RUN_ID}"

cleanup_container() {
  docker ps -a --format '{{.Names}}' | rg "^${CONTAINER_NAME}$" | xargs -r docker rm -f >/dev/null 2>&1 || true
}
trap cleanup_container EXIT

real_eval_require_clean_dir "$BASE"
mkdir -p "$HOME_DIR" "$WORK/data" "$WORK/input" "$LOG_DIR" "$CODEX_HOME_DIR" "$HOME_DIR/config"
cp "$PROVIDER_CONFIG" "$CODEX_HOME_DIR/config.toml"
real_eval_provider_env_from_codex_toml "$PROVIDER_CONFIG" "$PROVIDER_ENV"
real_eval_semantic_env_from_usage_md "$SEMANTIC_SOURCE" "$SEMANTIC_ENV"

cat > "$HOME_DIR/config/runners.yaml" <<'EOF'
codex:
  enabled: true
  binary: codex
  config_dir: ~/.codex
  profile: ""
  model: inherit
  model_reasoning_effort: xhigh
  approval_policy: never
  sandbox_mode: danger-full-access
  retry_on_failure: true
  retry_max_attempts: 2
  retry_initial_backoff_sec: 10.0
  retry_backoff_multiplier: 2.0
  retry_max_backoff_sec: 60.0
  env: {}
EOF

cat > "$WORK/research_goal.md" <<EOF
# BabyLM-10M Real Quest

Start a DeepScientist quest for a real BabyLM-10M language-model experiment.

- Contract: /input/contract.md
- Workspace contract: /workspace/input/contract.md
- Dataset: /data/BabyLM-2026-Strict-Small
- Workspace dataset: /workspace/data/BabyLM-2026-Strict-Small
- Required: real training implementation, checkpoints, training logs, evaluation JSON, final report
- Forbidden: proxy scripts, unigram/bigram-only evaluation, iris, digits, old results, placeholder outputs
EOF

cat > "$BASE/state.json" <<EOF
{"project_id":"05","name":"DeepScientist","run_id":"$RUN_ID","status":"starting","workspace":"$WORK"}
EOF

set +e
docker run --rm --name "$CONTAINER_NAME" --gpus all --user 0:0 \
	  -e HOME=/ds-home \
	  -e DEEPSCIENTIST_HOME=/ds-home \
	  -e CODEX_HOME=/ds-home/.codex \
	  --env-file "$PROVIDER_ENV" \
	  --env-file "$SEMANTIC_ENV" \
	  -v "$HOME_DIR":/ds-home \
  -v "$WORK":/workspace \
  -v "$DATASET_ROOT":/data/BabyLM-2026-Strict-Small:ro \
  -v "$DATASET_ROOT":/workspace/data/BabyLM-2026-Strict-Small:ro \
  -v "$CONTRACT_FILE":/input/contract.md:ro \
  -v "$CONTRACT_FILE":/workspace/input/contract.md:ro \
	  -w /workspace \
	  deepscientist:runtime-ready \
	  bash -lc 'set -euo pipefail; ds --home /ds-home doctor --runner codex; ds --home /ds-home --runner codex --daemon-only --host 127.0.0.1 --port '"$PORT"' & DS_PID=$!; trap "kill $DS_PID >/dev/null 2>&1 || true" EXIT; sleep 15; codex exec --yolo --skip-git-repo-check -C /workspace "This is not a planning-only turn. Use the DeepScientist workspace and immediately execute the BabyLM-10M quest described in research_goal.md. Create or update real training code, run neural language-model training on /data/BabyLM-2026-Strict-Small or /workspace/data/BabyLM-2026-Strict-Small, save checkpoints under /workspace/artifacts/checkpoints, write training logs under /workspace/artifacts/logs, run evaluation into /workspace/artifacts/eval, and write /workspace/final_report.md from actual results before exiting. Do not use proxy scripts, iris, digits, or placeholder results."' \
	  2>&1 | tee "$LOG_DIR/e2e.log"
rc=${PIPESTATUS[0]}
set -e
if [[ "$rc" -ne 0 ]]; then
  real_eval_write_state "$BASE/state.json" "{\"project_id\":\"05\",\"name\":\"DeepScientist\",\"run_id\":\"$RUN_ID\",\"status\":\"failed\",\"workspace\":\"$WORK\",\"log\":\"$LOG_DIR/e2e.log\",\"exit_code\":$rc}"
  exit "$rc"
fi

if ! real_eval_has_artifacts "$WORK"; then
  real_eval_write_state "$BASE/state.json" "{\"project_id\":\"05\",\"name\":\"DeepScientist\",\"run_id\":\"$RUN_ID\",\"status\":\"failed_no_artifacts\",\"workspace\":\"$WORK\",\"log\":\"$LOG_DIR/e2e.log\"}"
  exit 13
fi
cat > "$BASE/state.json" <<EOF
{"project_id":"05","name":"DeepScientist","run_id":"$RUN_ID","status":"finished","workspace":"$WORK","log":"$LOG_DIR/e2e.log"}
EOF
