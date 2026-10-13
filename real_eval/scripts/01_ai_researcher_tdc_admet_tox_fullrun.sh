#!/usr/bin/env bash
set -euo pipefail

ROOT="${RESEARCHCLAWEVAL_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
source "$ROOT/real_eval/scripts/lib_real_eval.sh"
MODEL="${TDC_ADMET_TOX_EVAL_MODEL:-gpt-5.4}"
export FRAMEWORK_NAME="AI-Researcher"
export FRAMEWORK_SLUG="01_ai_researcher_tdc_admet_tox_fullrun"
export FRAMEWORK_SRC="$(real_eval_resolve_framework_source "$ROOT" 01)"
export FRAMEWORK_ENTRY_PREFIX="AI-Researcher"
export FRAMEWORK_ENTRY_PATHS=$(cat <<'EOF'
AI-Researcher/benchmark/final/tdc_admet_tox/tdc_admet_tox.json
AI-Researcher/benchmark/process/dataset_candidate/tdc_admet_tox/metaprompt.py
real_eval/adapters/tdc_admet_tox/patch_ai_researcher.py
automation/tdc_admet_tox_contract.md
automation/tdc_admet_tox_execution_budget.md
EOF
)
export FRAMEWORK_RUNTIME_IMAGE="${AI_RESEARCHER_RUNTIME_IMAGE:-ai-researcher:runtime-ready}"
export FRAMEWORK_NATIVE_ENTRYPOINT="python research_agent/run_infer_idea.py"
export FRAMEWORK_NATIVE_ENTRYPOINT_FILE="research_agent/run_infer_idea.py"
export FRAMEWORK_NATIVE_ENTRYPOINT_SOURCE="README.md"
export FRAMEWORK_PROVIDER_INJECTION="MetaChain COMPLETION_MODEL/CHEEP_MODEL/API_BASE_URL use the isolated GPT relay; experiments execute inside the framework container without a host Docker socket"
export FRAMEWORK_NATIVE_LOG_MARKER="AI_RESEARCHER_NATIVE_INFER_IDEA_TDC"
export FRAMEWORK_NATIVE_PROCESS_MARKERS="NATIVE_CMD> timeout 7000s python3 research_agent/run_infer_idea.py"
export FRAMEWORK_EXECUTOR_KIND="framework_cli"
export FRAMEWORK_COMMAND_LABEL="python research_agent/run_infer_idea.py --category tdc_admet_tox"
export FRAMEWORK_DOCKER_ARGS=$(cat <<EOF
-e
COMPLETION_MODEL=openai/$MODEL
-e
CHEEP_MODEL=openai/$MODEL
-e
PYTHONPATH=/workspace
-e
TDC_ADMET_TOX_NATIVE_RUN=1
EOF
)
export FRAMEWORK_RUNTIME_COMMAND=$(cat <<'EOF'
set -euo pipefail
echo "AI_RESEARCHER_NATIVE_INFER_IDEA_TDC"
python3 real_eval/adapters/tdc_admet_tox/patch_ai_researcher.py
python3 - <<'PY'
from research_agent.inno.tools import (
    execute_command,
    gen_code_tree_structure,
    plan_dataset,
    plan_testing,
    plan_training,
    read_file,
    run_python,
)
import research_agent.inno.agents.inno_agent.judge_agent
import research_agent.inno.agents.inno_agent.ml_agent
import research_agent.inno.agents.inno_agent.plan_agent
import research_agent.run_infer_idea

required_tools = (
    execute_command,
    gen_code_tree_structure,
    plan_dataset,
    plan_testing,
    plan_training,
    read_file,
    run_python,
)
assert all(callable(tool) for tool in required_tools)
print("AI_RESEARCHER_TDC_IMPORT_GATE_OK")
PY
PS4='NATIVE_CMD> '
set -x
timeout 7000s python3 research_agent/run_infer_idea.py \
  --instance_path benchmark/final/tdc_admet_tox/tdc_admet_tox.json \
  --container_name tdc_ai_researcher \
  --model "$OPENAI_MODEL" \
  --workplace_name . \
  --cache_path cache_tdc_admet_tox \
  --port 12372 \
  --max_iter_times 1 \
  --category tdc_admet_tox
EOF
)
exec "$ROOT/real_eval/scripts/tdc_admet_tox_framework_fullrun.sh"
