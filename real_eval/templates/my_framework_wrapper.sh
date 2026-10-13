#!/usr/bin/env bash
# ============================================================================
# my_framework_wrapper.sh — skeleton wrapper for a new research-agent framework
#
# Copy this file to real_eval/scripts/99_myframework_<topic>_fullrun.sh, fill in
# the values marked TODO, and make it executable:
#
#   cp real_eval/templates/my_framework_wrapper.sh \
#      real_eval/scripts/99_myframework_babylm_fullrun.sh
#   chmod +x real_eval/scripts/99_myframework_babylm_fullrun.sh
#
# Read real_eval/docs/wrapper_interface.md before starting — it explains the
# native-execution proof, which is the part that most often trips people up.
#
# This file contains no machine-specific values on purpose. Do not add any.
# ============================================================================

set -euo pipefail

# Repo root: resolves relative to this script, so it works from any checkout.
ROOT="${RESEARCHCLAWEVAL_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
source "$ROOT/real_eval/scripts/lib_real_eval.sh"

# ── Identity ────────────────────────────────────────────────────────────────
export FRAMEWORK_NAME="MyFramework"                          # TODO display name
export FRAMEWORK_SLUG="99_myframework_babylm_fullrun"        # TODO run dir slug
export FRAMEWORK_SRC="$ROOT/MyFramework"                     # TODO checkout path

# ── Required ────────────────────────────────────────────────────────────────
export FRAMEWORK_RUNTIME_KIND="docker"

# Files copied into the container as task input. Repo-relative, one per line,
# no commas. These are the brief + contract + budget for the topic you run.
export FRAMEWORK_ENTRY_PATHS=$(cat <<'EOF'
automation/babylm_contract.md
automation/babylm_execution_budget.md
EOF
)

# How the LLM provider reaches your framework. Free text; recorded in the
# manifest. Be accurate — this is read by whoever audits the run.
export FRAMEWORK_PROVIDER_INJECTION="native framework client reads OPENAI_API_KEY, OPENAI_BASE_URL and OPENAI_MODEL from the environment"

# Native-execution proof. Must be unique per run configuration and must be
# echoed by your framework from INSIDE its own execution. A run that exits 0
# without this string in the log is judged non-native and is not scored.
export FRAMEWORK_NATIVE_LOG_MARKER="MYFRAMEWORK_BABYLM_NATIVE"

# ── Runtime ─────────────────────────────────────────────────────────────────
export FRAMEWORK_RUNTIME_IMAGE="myframework:runtime-ready"   # TODO image tag
export FRAMEWORK_NATIVE_ENTRYPOINT="myframework run --task chat"
export FRAMEWORK_COMMAND_LABEL="myframework run (non-interactive)"
export FRAMEWORK_EXECUTOR_KIND="framework_cli"

# Extra `docker run` args. Keep device selection out of here — use
# FRAMEWORK_GPUS so the allocation stays overridable.
export FRAMEWORK_DOCKER_ARGS=$(cat <<'EOF'
-e
MYFRAMEWORK_MAX_TURNS=100
EOF
)

# ── Evaluation target ───────────────────────────────────────────────────────
# Read the model from the environment. Never bake a model id in.
export EVAL_MODEL="${OPENAI_MODEL:-${BABYLM_MODEL:-}}"

# ── Provider config ─────────────────────────────────────────────────────────
# The provider config file belongs to the caller, not to this repository, and
# `api/` is git-ignored. Require it rather than defaulting to a path that only
# exists on one machine.
: "${PROVIDER_CONFIG:?set PROVIDER_CONFIG to your provider TOML before running}"

# ── The command executed inside the container ───────────────────────────────
export FRAMEWORK_RUNTIME_COMMAND=$(cat <<'EOF'
set -euo pipefail

# 1. Emit the native marker first, so a failed run is still attributable.
echo "MYFRAMEWORK_BABYLM_NATIVE"

# 2. Stage the task input the runner copied in.
mkdir -p /workspace/input
cp /input/babylm_contract.md /workspace/input/contract.md

# 3. Drive your framework. It must own idea formation, experiment design,
#    execution, comparison, selection and artifact delivery.
cat > /workspace/prompt.txt <<'PROMPT'
Run a BabyLM-10M end-to-end experiment using the mounted task contract and the
dataset at $BABYLM_DATASET_ROOT. Your framework must own idea formation, method
selection, experiment design, execution, comparison, selection and final
artifact delivery. Write and lock research_idea.json before the first
experiment. Run 2-4 materially different experiments, select by best
word-level validation perplexity, and deliver research_idea.json,
experiment_trace.json and final_report.md to /workspace.
PROMPT

cat /workspace/prompt.txt | myframework run --task chat

# 4. Confirm the required artifacts exist; the harness collects them from
#    /workspace after this process exits.
for f in research_idea.json experiment_trace.json final_report.md; do
  [ -f "/workspace/$f" ] && echo "Found artifact: $f"
done
EOF
)

# ── Hand off to the shared topic runner ─────────────────────────────────────
# This is the same runner for every framework on this topic. Do not reimplement
# it. Swap the filename to target a different topic.
exec "$ROOT"/real_eval/scripts/babylm_framework_fullrun.sh
