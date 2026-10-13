#!/usr/bin/env bash
set -euo pipefail
export FRAMEWORK_NAME="AutoResearchClaw"
export FRAMEWORK_SLUG="04_autoresearchclaw_gave2_task2_input_pack"
export ENTRY_PATHS=$(cat <<'EOF'
AutoResearchClaw/config.arc.yaml
AutoResearchClaw/topic.txt
docs/gave2_task2_summary.md
docs/gave2_metric_spec.md
docs/gave2_submission_spec.md
docs/gave2_data_layout.md
automation/gave2_task2_contract.md
EOF
)
exec "${RESEARCHCLAWEVAL_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"/real_eval/scripts/gave2_framework_input_pack.sh
