#!/usr/bin/env bash
set -euo pipefail
export FRAMEWORK_NAME="Dr. Claw"
export FRAMEWORK_SLUG="06_drclaw_gave2_task2_smoke"
export SHARED_DATASET_MOUNT="/data/gave2/task2:ro"
export IMAGE="dr-claw:runtime-ready"
export CONTAINER_WORKDIR="/home/evosci/dr-claw/smoke-gave2"
export WORKSPACE_DATASET_PATH="/home/evosci/dr-claw/smoke-gave2/data/gave2/task2"
export ENTRY_MAP=$(cat <<'EOF'
dr-claw/research_brief.json::research_brief.json
dr-claw/tasks.json::tasks.json
docs/gave2_task2_summary.md::docs/gave2_task2_summary.md
docs/gave2_metric_spec.md::docs/gave2_metric_spec.md
docs/gave2_submission_spec.md::docs/gave2_submission_spec.md
docs/gave2_data_layout.md::docs/gave2_data_layout.md
automation/gave2_task2_contract.md::automation/gave2_task2_contract.md
EOF
)
export SMOKE_CMD=$(cat <<'EOF'
node --version >/dev/null && test -f /workspace/dr-claw/server/cli-chat.js && /usr/local/bin/python3 - <<'PY'
import sklearn, numpy, pandas, matplotlib
print('deps-ok')
PY
test -f research_brief.json && test -f tasks.json
EOF
)
export EXTRA_DOCKER_ARGS=$(cat <<'EOF'
--entrypoint
bash
--gpus
all
-e
HOME=/home/evosci
-e
WORKSPACES_ROOT=/home/evosci/dr-claw
-e
DATABASE_PATH=/home/evosci/.dr-claw/auth.db
EOF
)
exec "${RESEARCHCLAWEVAL_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"/real_eval/scripts/gave2_framework_smoke.sh
