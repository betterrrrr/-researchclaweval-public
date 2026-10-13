#!/usr/bin/env bash
set -euo pipefail
export FRAMEWORK_NAME="DeepScientist"
export FRAMEWORK_SLUG="05_deepscientist_gave2_task2_smoke"
export SHARED_DATASET_MOUNT="/data/gave2/task2:ro"
export IMAGE="deepscientist:runtime-ready"
export CONTAINER_WORKDIR="/workspace"
export WORKSPACE_DATASET_PATH="/workspace/data/gave2/task2"
export ENTRY_MAP=$(cat <<'EOF'
DeepScientist/DEEPSCIENTIST_BRIEF.md::DEEPSCIENTIST_BRIEF.md
docs/gave2_task2_summary.md::docs/gave2_task2_summary.md
docs/gave2_metric_spec.md::docs/gave2_metric_spec.md
docs/gave2_submission_spec.md::docs/gave2_submission_spec.md
docs/gave2_data_layout.md::docs/gave2_data_layout.md
automation/gave2_task2_contract.md::automation/gave2_task2_contract.md
EOF
)
export SMOKE_CMD=$(cat <<'EOF'
command -v ds >/dev/null && test -f DEEPSCIENTIST_BRIEF.md
EOF
)
export EXTRA_DOCKER_ARGS=$(cat <<'EOF'
--entrypoint
bash
--gpus
all
-e
HOME=/ds-home
-e
DEEPSCIENTIST_HOME=/ds-home
EOF
)
exec "${RESEARCHCLAWEVAL_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"/real_eval/scripts/gave2_framework_smoke.sh
