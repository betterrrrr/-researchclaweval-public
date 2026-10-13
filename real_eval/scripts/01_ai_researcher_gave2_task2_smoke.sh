#!/usr/bin/env bash
set -euo pipefail
export FRAMEWORK_NAME="AI-Researcher"
export FRAMEWORK_SLUG="01_ai_researcher_gave2_task2_smoke"
export SHARED_DATASET_MOUNT="/data/gave2/task2:ro"
export IMAGE="ai-researcher:runtime-ready"
export CONTAINER_WORKDIR="/workspace/AI-Researcher"
export WORKSPACE_DATASET_PATH="/workspace/AI-Researcher/data/gave2/task2"
export ENTRY_MAP=$(cat <<'EOF'
AI-Researcher/benchmark/final/medical_image_analysis/gave2_task2_multimodal_av_segmentation.json::benchmark/final/medical_image_analysis/gave2_task2_multimodal_av_segmentation.json
docs/gave2_task2_summary.md::docs/gave2_task2_summary.md
docs/gave2_metric_spec.md::docs/gave2_metric_spec.md
docs/gave2_submission_spec.md::docs/gave2_submission_spec.md
docs/gave2_data_layout.md::docs/gave2_data_layout.md
automation/gave2_task2_contract.md::automation/gave2_task2_contract.md
EOF
)
export SMOKE_CMD=$(cat <<'EOF'
test -f benchmark/final/medical_image_analysis/gave2_task2_multimodal_av_segmentation.json
EOF
)
export EXTRA_DOCKER_ARGS=$(cat <<'EOF'
--entrypoint
bash

EOF
)
exec "${RESEARCHCLAWEVAL_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"/real_eval/scripts/gave2_framework_smoke.sh
