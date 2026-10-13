#!/usr/bin/env bash
set -euo pipefail

ROOT="${RESEARCHCLAWEVAL_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
source "$ROOT/real_eval/scripts/lib_real_eval.sh"
RUN_ID="${REAL_EVAL_RUN_ID:-$(date +%Y%m%d-%H%M%S)}"
BASE="${REAL_EVAL_RUN_ROOT:-$ROOT/real_eval/runs/$RUN_ID/06_drclaw}"
SRC="$ROOT/dr-claw"
REPO="$BASE/repo"
HOME_DIR="$BASE/home"
PROJECT_NAME="babylm-real-$RUN_ID"
PROJECT_DIR="$HOME_DIR/dr-claw/$PROJECT_NAME"
LOG_DIR="$BASE/logs"
DATASET_ROOT="${BABYLM_DATASET_ROOT:-$ROOT/BabyLM-2026-Strict-Small}"
CONTRACT_FILE="${BABYLM_CONTRACT_FILE:-$ROOT/automation/babylm_method_free_contract.md}"
PROVIDER_CONFIG="${PROVIDER_CONFIG:-$ROOT/api/codex_gpt56_luna_bianxie.toml}"
SEMANTIC_SOURCE="${SEMANTIC_SOURCE:-$ROOT/api/_semantic_scholar_api_usage.md}"
PROVIDER_ENV="$BASE/provider.env"
SEMANTIC_ENV="$BASE/semantic.env"
CONTAINER_NAME="drclaw_babylm_${RUN_ID}"

cleanup_container() {
  docker ps -a --format '{{.Names}}' | rg "^${CONTAINER_NAME}$" | xargs -r docker rm -f >/dev/null 2>&1 || true
}
trap cleanup_container EXIT

real_eval_require_clean_dir "$BASE"
mkdir -p "$BASE" "$HOME_DIR" "$PROJECT_DIR/.pipeline/docs" "$PROJECT_DIR/.pipeline/tasks" "$PROJECT_DIR/input" "$PROJECT_DIR/data" "$LOG_DIR"
real_eval_rsync_repo "$SRC" "$REPO"
real_eval_provider_env_from_codex_toml "$PROVIDER_CONFIG" "$PROVIDER_ENV"
real_eval_semantic_env_from_usage_md "$SEMANTIC_SOURCE" "$SEMANTIC_ENV"
python3 - "$REPO/server/cli-chat.js" <<'PY'
from pathlib import Path
import sys

p = Path(sys.argv[1])
s = p.read_text()
marker = '  const messages = [{ role: \'system\', content: systemPrompt }];\n\n  let turnInProgress = false;\n  let inputClosed = false;\n  let shuttingDown = false;\n\n  const finish = () => {'
insert = '  const messages = [{ role: \'system\', content: systemPrompt }];\n\n  if (process.env.DR_CLAW_SINGLE_PROMPT) {\n    messages.push({ role: \'user\', content: process.env.DR_CLAW_SINGLE_PROMPT });\n    return agentLoop(baseUrl, apiKey, model, messages, workingDir);\n  }\n\n  let turnInProgress = false;\n  let inputClosed = false;\n  let shuttingDown = false;\n\n  const finish = () => {'
if marker not in s:
    raise SystemExit("startChat prompt insertion point not found")
s = s.replace(marker, insert, 1)
p.write_text(s)
PY
cp "$CONTRACT_FILE" "$PROJECT_DIR/input/contract.md"

cat > "$PROJECT_DIR/.pipeline/docs/research_brief.json" <<EOF
{
  "title": "BabyLM-10M real language-model research",
  "goal": "Run a real BabyLM-10M end-to-end experiment using the mounted task contract and dataset.",
  "contract_file": "input/contract.md",
  "dataset_root": "data/BabyLM-2026-Strict-Small",
  "requirements": [
    "design a real neural language-model training experiment",
    "train on BabyLM-10M data",
    "save checkpoints and training logs",
    "run evaluation and write final report"
  ],
  "forbidden": ["run_framework_babylm_proxy.py", "run_proxy_babylm_pipeline.py", "iris", "digits", "old results", "placeholder outputs"]
}
EOF

cat > "$PROJECT_DIR/.pipeline/tasks/tasks.json" <<EOF
{
  "tasks": [
    {"id": "survey", "title": "Read BabyLM contract and dataset constraints", "status": "pending", "stage": "Survey"},
    {"id": "ideation", "title": "Propose a real small language-model training idea", "status": "pending", "stage": "Ideation"},
    {"id": "experiment", "title": "Implement and run real BabyLM training with checkpoints", "status": "pending", "stage": "Experiment"},
    {"id": "evaluation", "title": "Evaluate trained checkpoint and record metrics", "status": "pending", "stage": "Experiment"},
    {"id": "paper", "title": "Write final report from actual run evidence", "status": "pending", "stage": "Publication"}
  ]
}
EOF

cat > "$BASE/state.json" <<EOF
{"project_id":"06","name":"Dr. Claw","run_id":"$RUN_ID","status":"starting","project_dir":"$PROJECT_DIR"}
EOF

set +e
docker run --rm --name "$CONTAINER_NAME" --gpus '"device=7"' --user 0:0 \
  --env-file "$PROVIDER_ENV" \
  --env-file "$SEMANTIC_ENV" \
  -e HOME=/home/evosci \
  -e WORKSPACES_ROOT=/home/evosci/dr-claw \
  -e DATABASE_PATH=/home/evosci/.dr-claw/auth.db \
  -e DR_CLAW_E2E_PROJECT_DIR="$PROJECT_NAME" \
  -e DR_CLAW_SINGLE_PROMPT="Read .pipeline/docs/research_brief.json and .pipeline/tasks/tasks.json. Execute the Dr. Claw Auto Research workflow for this BabyLM-10M project: run survey, ideation, real training experiment, evaluation, and publication. Use input/contract.md and data/BabyLM-2026-Strict-Small from the project root. Do not use proxy scripts, iris, digits, old results, or placeholders." \
  -e DRCLAW_MAX_AGENT_TURNS=100 \
  -e DRCLAW_MAX_NO_TOOL_STREAK=100 \
  -v "$REPO":/workspace/dr-claw \
  -v "$HOME_DIR":/home/evosci \
  -v "$DATASET_ROOT":"/home/evosci/dr-claw/$PROJECT_NAME/data/BabyLM-2026-Strict-Small":ro \
  -v "$DATASET_ROOT":/data/BabyLM-2026-Strict-Small:ro \
  -v "$CONTRACT_FILE":/input/contract.md:ro \
  -w "/home/evosci/dr-claw/$PROJECT_NAME" \
  dr-claw:runtime-ready \
  sh -lc 'node --version && node --input-type=module -e "const m = await import(\"/workspace/dr-claw/server/cli-chat.js\"); await m.startChat();"' \
  2>&1 | tee "$LOG_DIR/e2e.log"
rc=${PIPESTATUS[0]}
set -e
if [[ "$rc" -ne 0 ]]; then
  real_eval_write_state "$BASE/state.json" "{\"project_id\":\"06\",\"name\":\"Dr. Claw\",\"run_id\":\"$RUN_ID\",\"status\":\"failed\",\"project_dir\":\"$PROJECT_DIR\",\"log\":\"$LOG_DIR/e2e.log\",\"exit_code\":$rc}"
  exit "$rc"
fi

if ! real_eval_has_artifacts "$PROJECT_DIR"; then
  real_eval_write_state "$BASE/state.json" "{\"project_id\":\"06\",\"name\":\"Dr. Claw\",\"run_id\":\"$RUN_ID\",\"status\":\"failed_no_artifacts\",\"project_dir\":\"$PROJECT_DIR\",\"log\":\"$LOG_DIR/e2e.log\"}"
  exit 13
fi
cat > "$BASE/state.json" <<EOF
{"project_id":"06","name":"Dr. Claw","run_id":"$RUN_ID","status":"finished","project_dir":"$PROJECT_DIR","log":"$LOG_DIR/e2e.log"}
EOF