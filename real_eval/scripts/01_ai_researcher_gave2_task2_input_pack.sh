#!/usr/bin/env bash
set -euo pipefail
export FRAMEWORK_NAME="AI-Researcher"
export FRAMEWORK_SLUG="01_ai_researcher_gave2_task2_input_pack"
export ENTRY_PATHS=$(cat <<'EOF'
AI-Researcher/benchmark/final/medical_image_analysis/gave2_task2_multimodal_av_segmentation.json
docs/gave2_task2_summary.md
docs/gave2_metric_spec.md
docs/gave2_submission_spec.md
docs/gave2_data_layout.md
automation/gave2_task2_contract.md
EOF
)
exec "${RESEARCHCLAWEVAL_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"/real_eval/scripts/gave2_framework_input_pack.sh
