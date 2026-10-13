#!/usr/bin/env bash
set -euo pipefail

ROOT="${RESEARCHCLAWEVAL_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
source "$ROOT/real_eval/scripts/lib_real_eval.sh"
MODEL="${TDC_ADMET_TOX_EVAL_MODEL:-gpt-5.4}"
export FRAMEWORK_NAME="EvoScientist"
export FRAMEWORK_SLUG="07_evoscientist_tdc_admet_tox_fullrun"
export FRAMEWORK_SRC="$(real_eval_resolve_framework_source "$ROOT" 07)"
export FRAMEWORK_ENTRY_PREFIX="EvoScientist"
export FRAMEWORK_ENTRY_PATHS=$(cat <<'EOF'
EvoScientist/TDC_ADMET_TOX_BRIEF.md
EvoScientist/tdc_admet_tox_start_message.txt
EvoScientist/tdc_admet_tox_evoscientist_config.yaml
automation/tdc_admet_tox_contract.md
automation/tdc_admet_tox_execution_budget.md
EOF
)
export FRAMEWORK_RUNTIME_IMAGE="${EVOSCIENTIST_RUNTIME_IMAGE:-evoscientist:runtime-ready}"
export FRAMEWORK_NATIVE_ENTRYPOINT="evoscientist --use-cwd --auto-mode"
export FRAMEWORK_NATIVE_ENTRYPOINT_FILE="EvoScientist/cli/__init__.py"
export FRAMEWORK_NATIVE_ENTRYPOINT_SOURCE="README.md"
export FRAMEWORK_PROVIDER_INJECTION="EvoScientist custom-openai provider reads CUSTOM_OPENAI_BASE_URL, CUSTOM_OPENAI_API_KEY, and EVOSCIENTIST_MODEL from the isolated relay"
export FRAMEWORK_NATIVE_LOG_MARKER="EVOSCIENTIST_NATIVE_CLI_TDC"
export FRAMEWORK_NATIVE_PROCESS_MARKERS="NATIVE_CMD> timeout 7000s /opt/venv/bin/evoscientist"
export FRAMEWORK_EXECUTOR_KIND="framework_cli"
export FRAMEWORK_COMMAND_LABEL="evoscientist --use-cwd --auto-mode"
export FRAMEWORK_WORKSPACE_DATASET_PROJECTION="1"
export FRAMEWORK_LOG_FORBIDDEN_PATTERN='execute\((pip|python(3)? -m pip) install|execute\(sleep[[:space:]]'
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
EVOSCIENTIST_WORKSPACE_DIR=/workspace
-e
EVOSCIENTIST_RUNS_DIR=/workspace/runs
-e
EVOSCIENTIST_USE_RESPONSES_API=false
-e
EVOSCIENTIST_DISABLE_STREAMING=true
-e
EVOSCIENTIST_LOG_LEVEL=info
-e
EVOSCIENTIST_MODEL=$MODEL
-e
MPLCONFIGDIR=/tmp
EOF
)
export FRAMEWORK_RUNTIME_COMMAND=$(cat <<'EOF'
set -euo pipefail
echo "EVOSCIENTIST_NATIVE_CLI_TDC"
export PATH="/opt/venv/bin:$PATH"
mkdir -p /workspace/logs
printf 'EvoScientist native run started\n' > /workspace/logs/native_execution.log
mkdir -p /workspace/.config/evoscientist /workspace/.evoscientist
cp tdc_admet_tox_evoscientist_config.yaml /workspace/.config/evoscientist/config.yaml
prompt="$(cat TDC_ADMET_TOX_BRIEF.md)"
PS4='NATIVE_CMD> '
set -x
timeout 7000s /opt/venv/bin/evoscientist \
  --use-cwd \
  -p "$prompt" \
  --auto-mode \
  --auto-approve \
  --ui cli \

test -s /workspace/predictions.csv
test -s /workspace/experiment_trace.json
test -s /workspace/environment.json
test -s /workspace/paper.md
test ! -e /workspace/score.json
EOF
)
exec "$ROOT/real_eval/scripts/tdc_admet_tox_framework_fullrun.sh"
