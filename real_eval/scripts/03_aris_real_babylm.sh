#!/usr/bin/env bash
set -euo pipefail

ROOT="${RESEARCHCLAWEVAL_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
source "$ROOT/real_eval/scripts/lib_real_eval.sh"
RUN_ID="${REAL_EVAL_RUN_ID:-$(date +%Y%m%d-%H%M%S)}"
BASE="${REAL_EVAL_RUN_ROOT:-$ROOT/real_eval/runs/$RUN_ID/03_aris}"
ARIS_SRC="$ROOT/Auto-claude-code-research-in-sleep"
PROJECT="$BASE/workspace"
CODEX_HOME_DIR="$BASE/codex_home"
LOG_DIR="$BASE/logs"
DATASET_ROOT="${BABYLM_DATASET_ROOT:-$ROOT/BabyLM-2026-Strict-Small}"
CONTRACT_FILE="${BABYLM_CONTRACT_FILE:-$ROOT/BabyLM-10M_七框架任务包装与分发指南.md}"
PROVIDER_CONFIG="${PROVIDER_CONFIG:-$ROOT/api/codex_gpt54_shubiaobiao.toml}"
SEMANTIC_SOURCE="${SEMANTIC_SOURCE:-$ROOT/api/_semantic_scholar_api_usage.md}"
SEMANTIC_ENV="$BASE/semantic.env"
CONTAINER_NAME="aris_babylm_${RUN_ID}"

cleanup_container() {
  docker ps -a --format '{{.Names}}' | rg "^${CONTAINER_NAME}$" | xargs -r docker rm -f >/dev/null 2>&1 || true
}
trap cleanup_container EXIT

real_eval_require_clean_dir "$BASE"
mkdir -p "$PROJECT/data" "$PROJECT/input" "$CODEX_HOME_DIR" "$LOG_DIR"
cp "$PROVIDER_CONFIG" "$CODEX_HOME_DIR/config.toml"
real_eval_semantic_env_from_usage_md "$SEMANTIC_SOURCE" "$SEMANTIC_ENV"

bash "$ARIS_SRC/tools/install_aris_codex.sh" "$PROJECT" --quiet --aris-repo "$ARIS_SRC"
test -f "$PROJECT/.agents/skills/research-pipeline/SKILL.md"

cat > "$PROJECT/RESEARCH_BRIEF.md" <<EOF
# BabyLM-10M Real E2E Research Brief

Run the ARIS research pipeline on the real BabyLM-10M task.

- Contract file inside container: /input/contract.md
- Workspace contract file inside container: /work/input/contract.md
- Dataset root inside container: /data/BabyLM-2026-Strict-Small
- Workspace dataset root inside container: /work/data/BabyLM-2026-Strict-Small
- Required output: real training code, training logs, checkpoints, evaluation JSON, final report
- Forbidden: proxy scripts, n-gram-only evaluation, iris, digits, previous experiment results, placeholder outputs
EOF

cat > "$PROJECT/AGENTS.md" <<EOF
# ARIS BabyLM run rules

Execute the installed ARIS research workflow for the BabyLM-10M brief. Use the mounted contract and dataset. Do not call run_framework_babylm_proxy.py or any prior minimal pipeline.
EOF

cat > "$BASE/state.json" <<EOF
{"project_id":"03","name":"ARIS","run_id":"$RUN_ID","status":"starting","workspace":"$PROJECT"}
EOF

set +e
docker run --rm --name "$CONTAINER_NAME" --gpus all --user 0:0 \
  --env-file "$SEMANTIC_ENV" \
  -e HOME=/tmp \
  -e CODEX_HOME=/work/.codex-real \
  -e RESEARCHCLAWEVAL_TOPIC_LABEL=BabyLM-10M \
  -v "$PROJECT":/work \
  -v "$CODEX_HOME_DIR":/work/.codex-real \
	  -v "$DATASET_ROOT":/data/BabyLM-2026-Strict-Small:ro \
	  -v "$DATASET_ROOT":/work/data/BabyLM-2026-Strict-Small:ro \
	  -v "$CONTRACT_FILE":/input/contract.md:ro \
	  -v "$CONTRACT_FILE":/work/input/contract.md:ro \
	  -w /work \
	  aris:runtime-ready \
	  bash -lc 'rm -rf /opt/aris/results /opt/aris/tools/run_iris_minimal_pipeline.py; codex exec --yolo --skip-git-repo-check -C /work "Use the installed ARIS research-pipeline skill: /research-pipeline \"BabyLM-10M Strict-Small real language-model training\" -- AUTO_PROCEED: true, auto_write: true. Read RESEARCH_BRIEF.md, /input/contract.md, and /work/input/contract.md first. You must implement and run a real language-model training experiment on /data/BabyLM-2026-Strict-Small or /work/data/BabyLM-2026-Strict-Small, save checkpoints, run evaluation, and write a final report. Do not use proxy scripts, iris, digits, or placeholder results."' \
	  2>&1 | tee "$LOG_DIR/e2e.log"
rc=${PIPESTATUS[0]}
set -e
if [[ "$rc" -ne 0 ]]; then
  real_eval_write_state "$BASE/state.json" "{\"project_id\":\"03\",\"name\":\"ARIS\",\"run_id\":\"$RUN_ID\",\"status\":\"failed\",\"workspace\":\"$PROJECT\",\"log\":\"$LOG_DIR/e2e.log\",\"exit_code\":$rc}"
  exit "$rc"
fi

if ! real_eval_has_artifacts "$BASE"; then
  real_eval_write_state "$BASE/state.json" "{\"project_id\":\"03\",\"name\":\"ARIS\",\"run_id\":\"$RUN_ID\",\"status\":\"failed_no_artifacts\",\"workspace\":\"$PROJECT\",\"log\":\"$LOG_DIR/e2e.log\"}"
  exit 13
fi
cat > "$BASE/state.json" <<EOF
{"project_id":"03","name":"ARIS","run_id":"$RUN_ID","status":"finished","workspace":"$PROJECT","log":"$LOG_DIR/e2e.log"}
EOF
