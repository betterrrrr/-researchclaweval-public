#!/usr/bin/env bash
set -euo pipefail
export FRAMEWORK_NAME="AutoResearchClaw"
export FRAMEWORK_SLUG="04_autoresearchclaw_gave2_task2_smoke"
export SHARED_DATASET_MOUNT="/data/gave2/task2:ro"
export IMAGE="autoresearchclaw:runtime-opencode"
export CONTAINER_WORKDIR="/workspace/AutoResearchClaw"
export WORKSPACE_DATASET_PATH="/workspace/AutoResearchClaw/data/gave2/task2"
export ENTRY_MAP=$(cat <<'EOF'
AutoResearchClaw/config.arc.yaml::config.arc.yaml
AutoResearchClaw/topic.txt::topic.txt
docs/gave2_task2_summary.md::docs/gave2_task2_summary.md
docs/gave2_metric_spec.md::docs/gave2_metric_spec.md
docs/gave2_submission_spec.md::docs/gave2_submission_spec.md
docs/gave2_data_layout.md::docs/gave2_data_layout.md
automation/gave2_task2_contract.md::automation/gave2_task2_contract.md
EOF
)
export SMOKE_CMD=$(cat <<'EOF'
python3 -V >/dev/null
test -f config.arc.yaml && test -f topic.txt
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
