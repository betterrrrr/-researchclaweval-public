#!/usr/bin/env bash
set -euo pipefail
export FRAMEWORK_NAME="EvoScientist"
export FRAMEWORK_SLUG="07_evoscientist_gave2_task2_smoke"
export SHARED_DATASET_MOUNT="/data/gave2/task2:ro"
export IMAGE="evoscientist:runtime-ready"
export CONTAINER_WORKDIR="/workspace"
export WORKSPACE_DATASET_PATH="/workspace/data/gave2/task2"
export ENTRY_MAP=$(cat <<'EOF'
EvoScientist/EVOSCIENTIST_BRIEF.md::EVOSCIENTIST_BRIEF.md
EvoScientist/gave2_task2_start_message.txt::gave2_task2_start_message.txt
docs/gave2_task2_summary.md::docs/gave2_task2_summary.md
docs/gave2_metric_spec.md::docs/gave2_metric_spec.md
docs/gave2_submission_spec.md::docs/gave2_submission_spec.md
docs/gave2_data_layout.md::docs/gave2_data_layout.md
automation/gave2_task2_contract.md::automation/gave2_task2_contract.md
EOF
)
export SMOKE_CMD=$(cat <<'EOF'
python3 -V >/dev/null
test -f EVOSCIENTIST_BRIEF.md && test -f gave2_task2_start_message.txt
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
