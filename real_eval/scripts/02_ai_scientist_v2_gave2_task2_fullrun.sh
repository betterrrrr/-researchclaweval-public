#!/usr/bin/env bash
set -euo pipefail
ROOT="${RESEARCHCLAWEVAL_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
source "$ROOT/real_eval/scripts/lib_real_eval.sh"
AI_SCIENTIST_MODEL="${REAL_EVAL_FRAMEWORK_MODEL:-${REAL_EVAL_MODEL:-gpt-5.4}}"
AI_SCIENTIST_VISION_MODEL="${REAL_EVAL_VISION_MODEL:-gpt-4o-2024-11-20}"
export FRAMEWORK_NAME="AI-Scientist-v2"
export FRAMEWORK_SLUG="02_ai_scientist_v2_gave2_task2_fullrun"
export FRAMEWORK_SRC="$(real_eval_resolve_framework_source "$ROOT" 02)"
export FRAMEWORK_ENTRY_PATHS=$(cat <<'EOF'
AI-Scientist-v2/ai_scientist/ideas/gave2_task2_topic.md
docs/gave2_task2_summary.md
docs/gave2_metric_spec.md
docs/gave2_submission_spec.md
docs/gave2_data_layout.md
automation/gave2_task2_contract.md
EOF
)
export FRAMEWORK_RUNTIME_KIND="docker"
export FRAMEWORK_RUNTIME_IMAGE="ai-scientist-v2:runtime-ready"
export FRAMEWORK_RUNTIME_COMMAND=$(cat <<EOF
set -euo pipefail
rm -f ai_scientist/ideas/gave2_task2_topic.json
echo "[ai-scientist-v2] step 1/3 ideation"
timeout 1800s python run_ideation.py \
  --workshop-file ai_scientist/ideas/gave2_task2_topic.md \
  --model $AI_SCIENTIST_MODEL \
  --max-num-generations 1 \
  --num-reflections 2
echo "[ai-scientist-v2] step 2/3 bfts"
set +e
timeout "${AI_SCIENTIST_BFTS_TIMEOUT_SECONDS:-14400}s" python launch_scientist_bfts.py \
  --config bfts_config.min_e2e.yaml \
  --load_ideas ai_scientist/ideas/gave2_task2_topic.json \
  --idea_idx 0 \
  --attempt_id 0 \
  --model_agg_plots $AI_SCIENTIST_MODEL \
  --model_writeup $AI_SCIENTIST_MODEL \
  --model_citation $AI_SCIENTIST_MODEL \
  --model_writeup_small $AI_SCIENTIST_MODEL \
  --model_writeup_reflection $AI_SCIENTIST_MODEL \
  --model_review $AI_SCIENTIST_MODEL \
  --model_review_vision $AI_SCIENTIST_VISION_MODEL \
  --num_cite_rounds 1 \
  --writeup-type icbinb
bfts_rc=$?
set -e
EXP_DIR=$(python - <<'PY'
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
if [[ "$bfts_rc" -eq 124 ]]; then
  python - "$EXP_DIR" <<'PY'
from pathlib import Path
import sys
exp = Path(sys.argv[1])
summary_root = exp / "logs/0-run"
required = ["baseline_summary.json", "research_summary.json"]
missing = [name for name in required if not (summary_root / name).exists()]
if missing:
    raise SystemExit(f"BFTS timed out and required summaries are missing: {missing}")
PY
  echo "[ai-scientist-v2] BFTS timed out after ${AI_SCIENTIST_BFTS_TIMEOUT_SECONDS:-14400}s; preserving experiment summaries and continuing"
elif [[ "$bfts_rc" -ne 0 ]]; then
  exit "$bfts_rc"
fi
echo "[ai-scientist-v2] step 3/3 continue_plot_writeup_existing -> $EXP_DIR"
set +e
timeout 600s python scripts/continue_plot_writeup_existing.py \
  --base-folder "$EXP_DIR" \
  --model-agg-plots $AI_SCIENTIST_MODEL \
  --model-citation $AI_SCIENTIST_MODEL \
  --model-writeup-small $AI_SCIENTIST_MODEL \
  --model-writeup $AI_SCIENTIST_MODEL \
  --model-writeup-reflection $AI_SCIENTIST_MODEL \
  --review-model $AI_SCIENTIST_MODEL \
  --vision-model $AI_SCIENTIST_VISION_MODEL \
  --num-cite-rounds 1 \
  --plot-reflections 0 \
  --writeup-reflections 1 \
  --page-limit 4
step3_rc=$?
set -e
if [[ "$step3_rc" -eq 124 ]]; then
  echo "[ai-scientist-v2] step 3/3 timed out after 600s; preserving ideation+BFTS artifacts and continuing"
elif [[ "$step3_rc" -ne 0 ]]; then
  exit "$step3_rc"
fi
EOF
)
exec "$ROOT"/real_eval/scripts/gave2_framework_fullrun.sh
