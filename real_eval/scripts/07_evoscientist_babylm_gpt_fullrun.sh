#!/usr/bin/env bash
set -euo pipefail
ROOT="${RESEARCHCLAWEVAL_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
source "$ROOT/real_eval/scripts/lib_real_eval.sh"
export FRAMEWORK_NAME="EvoScientist"
export FRAMEWORK_SLUG="07_evoscientist_babylm_gpt_fullrun"
export FRAMEWORK_SRC="$(real_eval_resolve_framework_source "$ROOT" 07)"
export FRAMEWORK_ENTRY_PATHS=$(cat <<'EOF'
automation/babylm_method_free_contract.md
EOF
)
export FRAMEWORK_RUNTIME_KIND="docker"
export FRAMEWORK_RUNTIME_IMAGE="evoscientist:runtime-ready"
export FRAMEWORK_ENTRYPOINT="bash"
export FRAMEWORK_NATIVE_ENTRYPOINT="/opt/venv/bin/evosci --auto-mode"
export FRAMEWORK_PROVIDER_INJECTION="native framework client reads OPENAI_API_KEY from environment"
export FRAMEWORK_NATIVE_LOG_MARKER="EVOSCIENTIST_BABYLM_GPT_NATIVE"
export FRAMEWORK_EXECUTOR_KIND="framework_cli"
export FRAMEWORK_COMMAND_LABEL="/opt/venv/bin/evosci --auto-mode -p baby_lm (single-shot)"
export FRAMEWORK_RUNTIME_COMMAND=$(cat <<'EOF'
set -euo pipefail
echo "EVOSCIENTIST_BABYLM_GPT_NATIVE"
# Configure EvoScientist with the injected provider
/opt/venv/bin/evosci config set provider openai 2>/dev/null || true
/opt/venv/bin/evosci config set openai_api_key "${OPENAI_API_KEY}" 2>/dev/null || true
/opt/venv/bin/evosci config set model gpt-5.4 2>/dev/null || true
/opt/venv/bin/evosci config set auto_approve true 2>/dev/null || true
/opt/venv/bin/evosci config set auto_mode true 2>/dev/null || true
QUERY="Run 2-4 materially different experiments on BabyLM Strict-Small under the official 2026 rules using /data/BabyLM-2026-Strict-Small. The framework must own idea formation, method selection, experiment design, execution, comparison, selection, analysis, and final artifact delivery. The host does not prescribe an algorithm, architecture, hyperparameter, baseline, or experiment order. Write and lock research_idea.json before the first experiment. Run experiments, compare by validation perplexity, select the best, and write research_idea.json, experiment_trace.json, and final_report.md to /workspace. Do not use proxy scripts, toy datasets, or old results."
exec /opt/venv/bin/evosci -p "$QUERY" --auto-approve --workdir /workspace
EOF
)
exec "$ROOT"/real_eval/scripts/babylm_framework_fullrun.sh