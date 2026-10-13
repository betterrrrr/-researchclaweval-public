#!/usr/bin/env bash
set -euo pipefail

ROOT="${RESEARCHCLAWEVAL_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
source "$ROOT/real_eval/scripts/lib_real_eval.sh"
RUN_ID="${REAL_EVAL_RUN_ID:-$(date +%Y%m%d-%H%M%S)}"
BASE="${REAL_EVAL_RUN_ROOT:-$ROOT/real_eval/runs/$RUN_ID/02_ai_scientist_v2_real_babylm}"
SRC="$ROOT/AI-Scientist-v2"
REPO="$BASE/repo"
LOG_DIR="$BASE/logs"
AI_SCIENTIST_MODEL="${REAL_EVAL_FRAMEWORK_MODEL:-${REAL_EVAL_MODEL:-deepseek-v4-flash}}"
API_DIR="$BASE/api"
DATASET_ROOT="${BABYLM_DATASET_ROOT:-$ROOT/BabyLM-2026-Strict-Small}"
IMAGE="${AI_SCIENTIST_V2_IMAGE:-ai-scientist-v2:runtime-ready}"
CONTAINER_NAME="ai_scientist_v2_babylm_${RUN_ID}"
UNIFIED_ENV_FILE="${AI_SCIENTIST_UNIFIED_ENV_FILE:-$ROOT/api/unified_gpt54.env}"
SEMANTIC_ENV_FILE="${AI_SCIENTIST_SEMANTIC_ENV_FILE:-$ROOT/api/semantic_scholar.env}"

cleanup_container() {
  docker ps -a --format '{{.Names}}' | rg "^${CONTAINER_NAME}$" | xargs -r docker rm -f >/dev/null 2>&1 || true
}
trap cleanup_container EXIT

real_eval_require_clean_dir "$BASE"
mkdir -p "$BASE" "$LOG_DIR" "$API_DIR"
real_eval_rsync_repo "$SRC" "$REPO"
cp "$UNIFIED_ENV_FILE" "$API_DIR/unified_gpt54.env"
cp "$SEMANTIC_ENV_FILE" "$API_DIR/semantic_scholar.env"

cat > "$BASE/state.json" <<EOF
{"project_id":"02","name":"AI-Scientist-v2","run_id":"$RUN_ID","status":"starting","repo":"$REPO"}
EOF

set +e
docker run --rm \
  --name "$CONTAINER_NAME" \
  --gpus all \
  --ipc=host \
  --ulimit memlock=-1 \
  --ulimit stack=67108864 \
  -e AI_SCIENTIST_MODEL=$AI_SCIENTIST_MODEL \
  -e AI_SCIENTIST_UNIFIED_ENV_FILE=/repo/api/unified_gpt54.env \
  -e AI_SCIENTIST_SEMANTIC_ENV_FILE=/repo/api/semantic_scholar.env \
  -e BABYLM_DATA_DIR=/repo/BabyLM-2026-Strict-Small \
  -e PYTHONUNBUFFERED=1 \
  -v "$API_DIR":/repo/api:ro \
  -v "$DATASET_ROOT":/repo/BabyLM-2026-Strict-Small:ro \
  -v "$DATASET_ROOT":/data/BabyLM-2026-Strict-Small:ro \
  -v "$ROOT/real_eval/adapters/ai_scientist_v2/patch_ai_scientist_v2_common.py":/workspace/real_eval/adapters/ai_scientist_v2/patch_ai_scientist_v2_common.py:ro \
  -v "$REPO":/workspace \
  -w /workspace \
  "$IMAGE" \
  bash -lc 'set -euo pipefail
source scripts/use_bianxie_env.sh >/dev/null
echo "[ai-scientist-v2] shared adapter"
python3 real_eval/adapters/ai_scientist_v2/patch_ai_scientist_v2_common.py
echo "[ai-scientist-v2] generating workshop file"
mkdir -p ai_scientist/ideas
cat > ai_scientist/ideas/babylm_topic.md <<'MARKDOWN'
# Title: Language Model Optimization for BabyLM Strict-Small

## Keywords
language model, autoregressive, BabyLM, perplexity, multi-domain

## TL;DR
Train language models on BabyLM Strict-Small. Compare 2-4 configurations, measure word-level perplexity.

## Abstract
This project trains language models on the BabyLM 2026 Strict-Small dataset (10M words, 6 domains). The framework selects the algorithm family, architecture, hyperparameters, and training procedure. The evaluation metric is word-level validation perplexity on a held-out split. The framework must compare 2-4 materially different configurations. The host does not prescribe an algorithm, architecture, hyperparameter, baseline, or experiment order. Use the dataset at /data/BabyLM-2026-Strict-Small. Write and lock research_idea.json before the first experiment. Write experiment_trace.json with word-level validation_perplexity for each experiment, and final_report.md.
MARKDOWN
echo "[ai-scientist-v2] step 1/3 ideation"
rm -f ai_scientist/ideas/babylm_topic.json
timeout 1800s python ai_scientist/perform_ideation_temp_free.py \
  --workshop-file ai_scientist/ideas/babylm_topic.md \
  --model $AI_SCIENTIST_MODEL \
  --max-num-generations 1 \
  --num-reflections 2
echo "[ai-scientist-v2] step 2/3 bfts"
timeout 7200s python launch_scientist_bfts.py \
  --config bfts_config.min_e2e.yaml \
  --load_ideas ai_scientist/ideas/babylm_topic.json \
  --idea_idx 0 \
  --attempt_id 0 \
  --model_agg_plots $AI_SCIENTIST_MODEL \
  --model_writeup $AI_SCIENTIST_MODEL \
  --model_citation $AI_SCIENTIST_MODEL \
  --model_writeup_small $AI_SCIENTIST_MODEL \
  --model_writeup_reflection $AI_SCIENTIST_MODEL \
  --model_review $AI_SCIENTIST_MODEL \
  --model_review_vision $AI_SCIENTIST_MODEL \
  --num_cite_rounds 1 \
  --writeup-type icbinb
EXP_DIR=$(python - <<'"'"'PY'"'"'
from pathlib import Path
exp_root = Path("experiments")
choices = sorted([p for p in exp_root.glob("*_attempt_*") if p.is_dir()], key=lambda p: p.stat().st_mtime)
print(choices[-1] if choices else "")
PY
)
if [[ -z "$EXP_DIR" ]]; then
  echo "No experiment directory created under /workspace/experiments" >&2
  exit 24
fi
echo "[ai-scientist-v2] step 3/3 continue_plot_writeup_existing -> $EXP_DIR"
timeout 1200s python scripts/continue_plot_writeup_existing.py \
  --base-folder "$EXP_DIR" \
  --model-agg-plots $AI_SCIENTIST_MODEL \
  --model-citation $AI_SCIENTIST_MODEL \
  --model-writeup-small $AI_SCIENTIST_MODEL \
  --model-writeup $AI_SCIENTIST_MODEL \
  --model-writeup-reflection $AI_SCIENTIST_MODEL \
  --review-model $AI_SCIENTIST_MODEL \
  --vision-model $AI_SCIENTIST_MODEL \
  --num-cite-rounds 1 \
  --plot-reflections 0 \
  --writeup-reflections 1 \
  --page-limit 4
' 2>&1 | tee "$LOG_DIR/e2e.log"
rc=${PIPESTATUS[0]}
set -e

if [[ "$rc" -ne 0 ]]; then
  real_eval_write_state "$BASE/state.json" "{\"project_id\":\"02\",\"name\":\"AI-Scientist-v2\",\"run_id\":\"$RUN_ID\",\"status\":\"failed\",\"repo\":\"$REPO\",\"log\":\"$LOG_DIR/e2e.log\",\"exit_code\":$rc}"
else
  real_eval_write_state "$BASE/state.json" "{\"project_id\":\"02\",\"name\":\"AI-Scientist-v2\",\"run_id\":\"$RUN_ID\",\"status\":\"completed_container\",\"repo\":\"$REPO\",\"log\":\"$LOG_DIR/e2e.log\"}"
fi

python3 "$ROOT/real_eval/scripts/validate_framework_run.py" \
  --framework ai_scientist_v2 \
  --run-root "$BASE" \
  --state-file "$BASE/state.json" \
  > "$LOG_DIR/validator.json"
validator_rc=$?

if [[ "$validator_rc" -eq 0 ]]; then
  exit 0
fi
exit "${rc:-$validator_rc}"
