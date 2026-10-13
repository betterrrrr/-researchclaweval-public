#!/usr/bin/env bash
set -euo pipefail
export FRAMEWORK_NAME="ARIS"
export FRAMEWORK_SLUG="03_aris_gave2_task2_smoke"
export SHARED_DATASET_MOUNT="/data/gave2/task2:ro"
export IMAGE="aris:runtime-ready"
export CONTAINER_WORKDIR="/work"
export WORKSPACE_DATASET_PATH="/work/data/gave2/task2"
export ENTRY_MAP=$(cat <<'EOF'
Auto-claude-code-research-in-sleep/RESEARCH_BRIEF.md::RESEARCH_BRIEF.md
Auto-claude-code-research-in-sleep/.aris-codex-project/RESEARCH_BRIEF.md::.aris-codex-project/RESEARCH_BRIEF.md
docs/gave2_task2_summary.md::docs/gave2_task2_summary.md
docs/gave2_metric_spec.md::docs/gave2_metric_spec.md
docs/gave2_submission_spec.md::docs/gave2_submission_spec.md
docs/gave2_data_layout.md::docs/gave2_data_layout.md
automation/gave2_task2_contract.md::automation/gave2_task2_contract.md
EOF
)
export SMOKE_CMD=$(cat <<'EOF'
test -f RESEARCH_BRIEF.md && test -f .aris-codex-project/RESEARCH_BRIEF.md
EOF
)
export EXTRA_DOCKER_ARGS=$(cat <<'EOF'
--entrypoint
bash
--gpus
all
-e
HOME=/tmp
EOF
)
exec "${RESEARCHCLAWEVAL_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"/real_eval/scripts/gave2_framework_smoke.sh
