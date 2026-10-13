#!/usr/bin/env bash
set -euo pipefail
export FRAMEWORK_NAME="AI-Scientist-v2"
export FRAMEWORK_SLUG="02_ai_scientist_v2_gave2_task2_smoke"
export SHARED_DATASET_MOUNT="/data/gave2/task2:ro"
export IMAGE="ai-scientist-v2:runtime-ready"
export CONTAINER_WORKDIR="/workspace"
export WORKSPACE_DATASET_PATH="/workspace/data/gave2/task2"
export ENTRY_MAP=$(cat <<'EOF'
AI-Scientist-v2/ai_scientist/ideas/gave2_task2_topic.md::ai_scientist/ideas/gave2_task2_topic.md
AI-Scientist-v2/ai_scientist/ideas/my_research_topic.md::ai_scientist/ideas/my_research_topic.md
docs/gave2_task2_summary.md::docs/gave2_task2_summary.md
docs/gave2_metric_spec.md::docs/gave2_metric_spec.md
docs/gave2_submission_spec.md::docs/gave2_submission_spec.md
docs/gave2_data_layout.md::docs/gave2_data_layout.md
automation/gave2_task2_contract.md::automation/gave2_task2_contract.md
EOF
)
export SMOKE_CMD=$(cat <<'EOF'
test -f ai_scientist/ideas/gave2_task2_topic.md && test -f ai_scientist/ideas/my_research_topic.md
EOF
)
export EXTRA_DOCKER_ARGS=$(cat <<'EOF'
--entrypoint
bash
--gpus
all
EOF
)
exec "${RESEARCHCLAWEVAL_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"/real_eval/scripts/gave2_framework_smoke.sh
