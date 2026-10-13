#!/usr/bin/env bash
set -euo pipefail
ROOT="${RESEARCHCLAWEVAL_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
source "$ROOT/real_eval/scripts/lib_real_eval.sh"
export FRAMEWORK_NAME="Dr. Claw"
export FRAMEWORK_SLUG="06_drclaw_gave2_task2_fullrun"
export FRAMEWORK_SRC="$(real_eval_resolve_framework_source "$ROOT" 06)"
export FRAMEWORK_ENTRY_PATHS=$(cat <<'EOF'
dr-claw/research_brief.json
dr-claw/tasks.json
docs/gave2_task2_summary.md
docs/gave2_metric_spec.md
docs/gave2_submission_spec.md
docs/gave2_data_layout.md
automation/gave2_task2_contract.md
EOF
)
export FRAMEWORK_RUNTIME_KIND="docker"
export FRAMEWORK_RUNTIME_IMAGE="dr-claw:runtime-ready"
export FRAMEWORK_DOCKER_ARGS=$(cat <<'EOF'
--user
0:0
EOF
)
export FRAMEWORK_RUNTIME_COMMAND="codex exec --yolo --skip-git-repo-check -C /workspace \"This is not a planning-only turn. Read research_brief.json, tasks.json, docs/gave2_metric_spec.md, docs/gave2_submission_spec.md, docs/gave2_data_layout.md, and automation/gave2_task2_contract.md first. Then execute a real Dr. Claw style GAVE2 Task 2 workflow in this fresh workspace only. Do not reuse BabyLM or old runs. Produce real artifacts or report a precise blocker.\""
exec "$ROOT"/real_eval/scripts/gave2_framework_fullrun.sh
