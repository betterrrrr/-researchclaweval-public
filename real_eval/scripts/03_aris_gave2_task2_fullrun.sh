#!/usr/bin/env bash
set -euo pipefail
ROOT="${RESEARCHCLAWEVAL_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
source "$ROOT/real_eval/scripts/lib_real_eval.sh"
export FRAMEWORK_NAME="ARIS"
export FRAMEWORK_SLUG="03_aris_gave2_task2_fullrun"
export FRAMEWORK_SRC="$(real_eval_resolve_framework_source "$ROOT" 03)"
export FRAMEWORK_ENTRY_PATHS=$(cat <<'EOF'
Auto-claude-code-research-in-sleep/RESEARCH_BRIEF.md
docs/gave2_task2_summary.md
docs/gave2_metric_spec.md
docs/gave2_submission_spec.md
docs/gave2_data_layout.md
automation/gave2_task2_contract.md
EOF
)
export FRAMEWORK_RUNTIME_KIND="docker"
export FRAMEWORK_RUNTIME_IMAGE="aris:runtime-ready"
export FRAMEWORK_DOCKER_ARGS=$(cat <<'EOF'
--user
0:0
EOF
)
export FRAMEWORK_RUNTIME_COMMAND="codex exec --yolo --skip-git-repo-check -C /workspace \"This is not a planning-only turn. Read RESEARCH_BRIEF.md, docs/gave2_metric_spec.md, docs/gave2_submission_spec.md, docs/gave2_data_layout.md, and automation/gave2_task2_contract.md first. Then execute a real GAVE2 Task 2 submission-oriented workflow inside this ARIS workspace. Use only /workspace/data/gave2/task2. Do not mention or reuse BabyLM. Produce runnable training or inference artifacts if possible; if blocked, explain the blocker clearly in files under /workspace and exit honestly.\""
exec "$ROOT"/real_eval/scripts/gave2_framework_fullrun.sh
