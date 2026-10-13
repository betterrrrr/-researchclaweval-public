#!/usr/bin/env bash
set -euo pipefail
ROOT="${RESEARCHCLAWEVAL_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
source "$ROOT/real_eval/scripts/lib_real_eval.sh"
EVOSCIENTIST_MODEL="${REAL_EVAL_FRAMEWORK_MODEL:-${REAL_EVAL_MODEL:-gpt-5.4}}"
export FRAMEWORK_NAME="EvoScientist"
export FRAMEWORK_SLUG="07_evoscientist_gave2_task2_fullrun"
export FRAMEWORK_SRC="$(real_eval_resolve_framework_source "$ROOT" 07)"
export FRAMEWORK_ENTRY_PATHS=$(cat <<'EOF'
EvoScientist/EVOSCIENTIST_BRIEF.md
EvoScientist/gave2_task2_start_message.txt
docs/gave2_task2_summary.md
docs/gave2_metric_spec.md
docs/gave2_submission_spec.md
docs/gave2_data_layout.md
automation/gave2_task2_contract.md
EOF
)
export FRAMEWORK_RUNTIME_KIND="docker"
export FRAMEWORK_RUNTIME_IMAGE="evoscientist:runtime-ready"
export FRAMEWORK_ENTRYPOINT="bash"
export FRAMEWORK_DOCKER_ARGS=$(cat <<EOF
--user
$(id -u):$(id -g)
-e
HOME=/workspace
-e
XDG_CONFIG_HOME=/workspace/.config
-e
EVOSCIENTIST_DATA_DIR=/workspace/.evoscientist
-e
EVOSCIENTIST_USE_RESPONSES_API=false
-e
MPLCONFIGDIR=/tmp
-e
EVOSCIENTIST_LOG_LEVEL=info
-e
EVOSCIENTIST_MODEL=$EVOSCIENTIST_MODEL
EOF
)
export FRAMEWORK_RUNTIME_COMMAND=$(cat <<'EOF'
set -euo pipefail
mkdir -p /workspace/.config/evoscientist
cat > /workspace/.config/evoscientist/config.yaml <<YAML
provider: custom-openai
model: ${EVOSCIENTIST_MODEL}
openai_auth_mode: api_key
default_mode: daemon
default_workdir: /workspace
show_thinking: false
enable_async_subagents: true
YAML
prompt="$(cat gave2_task2_start_message.txt)"
/opt/venv/bin/evoscientist --use-cwd -p "$prompt" --auto-mode --auto-approve --ui cli --no-thinking
EOF
)
exec "$ROOT"/real_eval/scripts/gave2_framework_fullrun.sh
