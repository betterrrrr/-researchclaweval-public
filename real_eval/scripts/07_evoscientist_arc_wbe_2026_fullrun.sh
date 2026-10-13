#!/usr/bin/env bash
set -euo pipefail
ROOT="${RESEARCHCLAWEVAL_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
source "$ROOT/real_eval/scripts/lib_real_eval.sh"
EVOSCIENTIST_MODEL="${REAL_EVAL_FRAMEWORK_MODEL:-${REAL_EVAL_MODEL:-kimi-k2.6}}"
export FRAMEWORK_NAME="EvoScientist"
export FRAMEWORK_SLUG="07_evoscientist_arc_wbe_2026_fullrun"
export FRAMEWORK_SRC="$(real_eval_resolve_framework_source "$ROOT" 07)"
export FRAMEWORK_ENTRY_PATHS=$(cat <<'EOF'
EvoScientist/EVOSCIENTIST_BRIEF.md
EvoScientist/arc_wbe_2026_start_message.txt
docs/arc_wbe_2026_summary.md
automation/arc_wbe_2026_contract.md
automation/arc_wbe_2026_execution_budget.md
EOF
)
export FRAMEWORK_RUNTIME_KIND="docker"
export FRAMEWORK_RUNTIME_IMAGE="evoscientist:runtime-ready"
export FRAMEWORK_ENTRYPOINT="bash"
export FRAMEWORK_NATIVE_ENTRYPOINT="evoscientist --use-cwd --auto-mode"
export FRAMEWORK_KIMI_INJECTION="custom-openai provider reads CUSTOM_OPENAI_BASE_URL, CUSTOM_OPENAI_API_KEY, and EVOSCIENTIST_MODEL"
export FRAMEWORK_NATIVE_LOG_MARKER="EVOSCIENTIST_NATIVE_CLI"
export FRAMEWORK_EXECUTOR_KIND="framework_cli"
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
export FRAMEWORK_COMMAND_LABEL="/opt/venv/bin/evoscientist --use-cwd -p @arc_wbe_2026_start_message.txt"
export FRAMEWORK_RUNTIME_COMMAND=$(cat <<'EOF'
set -euo pipefail
echo "EVOSCIENTIST_NATIVE_CLI"
rm -rf /workspace/workspace /workspace/verify_workspace
mkdir -p /workspace/.config/evoscientist
cat > /workspace/.config/evoscientist/config.yaml <<YAML
provider: custom-openai
model: ${EVOSCIENTIST_MODEL}
openai_auth_mode: api_key
default_mode: run
default_workdir: /workspace
show_thinking: false
enable_async_subagents: false
YAML
prompt='Environment note (read first): you are ALREADY running inside the native entrypoint of this framework. Do NOT launch, import, pip-install, uv-run, or otherwise bootstrap the framework itself, and do not create virtualenvs -- the host has already configured the runtime and the injected provider for you. A ModuleNotFoundError from importing the framework source with a different interpreter is not an environment blocker and must not be reported as one. Spend the run on the research task itself and write the required root-level artifacts; exploration that produces no artifact wastes the budget.

# ARC-WBE-2026 Native Evaluation Brief

This is a framework-capability evaluation. The framework'\''s documented native entrypoint must own hypothesis generation, experiment design, implementation, execution, comparison, selection, and the final report.

## Visible inputs

- `/data/arc_wbe_2026`: real parquet records with 100 MLP samples and 32 weight matrices of shape (256,256); target labels remain host-only
- `/workspace/automation/arc_wbe_2026_contract.md`
- `/workspace/automation/arc_wbe_2026_execution_budget.md`
- `/workspace/docs/arc_wbe_2026_summary.md`
- `/workspace/automation/scripts/arc_wbe_2026_official_adapter.py`
- `/workspace/automation/scripts/run_arc_wbe_2026_local_score.py`

## Task description

The goal is to predict the mean hidden activation of each neuron in every layer of a 32-layer MLP. Input: mlp.weights is a list of 32 weight matrices, each (256, 256), with ReLU activation. Output: predicted per-neuron mean activations for all 32 layers — a (depth, width) = (32, 256) fnp.ndarray of predicted values. This is a REGRESSION task, NOT classification.

## Estimator interface

`/workspace/estimator.py` must be self-contained. The official scorer imports it, instantiates the estimator class, and calls `predict(mlp)` without calling `fit` first. The estimator class `__init__` must load all trained parameters embedded directly in the source code (as Python literal values: lists, floats, np.array([...])). Do NOT reference external JSON, pickle, NPY, or any other data files.

`predict(mlp)` must accept the official scorer'\''s MLP object. mlp.weights is a list of 32 (256, 256) matrices. mlp.depth=32, mlp.width=256. Return a fnp.ndarray of shape (32, 256) — predicted mean activation of each of the 256 hidden neurons in each of the 32 layers. The scorer sandbox has only flopscope.numpy (import as fnp) — do NOT import numpy, scipy, or torch. flopscope arrays are immutable — do NOT use item assignment (arr[i] = ...) or indexed in-place updates (arr[i] += ...). Build the result functionally using fnp.stack() / fnp.concatenate() or a list comprehension. Do NOT predict a scalar score or class label.

## Required native workflow

1. Propose a hypothesis using only the visible inputs.
2. Complete 2 to 4 materially distinct framework-chosen experimental configurations.
3. Immediately after the final experiment, select the best result and promote the selected artifacts.
4. Before exit, write root-level: `/workspace/research_idea.json`, `/workspace/estimator.py`, `/workspace/submission.json`, `/workspace/experiment_trace.json`, `/workspace/final_report.md`.
5. In experiment_trace.json, record framework_internal_model and framework_internal_api_base_url. The host creates score.json after native exit.

## experiment_trace.json schema

experiment_trace.json must be a complete contract object, not a one-experiment summary. Record every required field: framework_native_execution (true), consumed_topic_input (true), workspace_trace_root, framework_internal_model, framework_internal_api_base_url, experiments (2-4 entries, each with an id, configuration, validation metrics, and log references), selected_experiment_id (must equal one of the experiment ids), idea_artifact (research_idea.json), and idea_locked_before_experiments (true).

## Constraints

- Use only the injected evaluation provider (OPENAI_BASE_URL, OPENAI_API_KEY, OPENAI_MODEL) for all internal API calls.
- Do not install packages, access unmapped paths, or perform downloads.
- The framework owns the method choice; the host prescribes no algorithm family, feature representation, architecture, hyperparameters, or experiment sequence. Never write a zero-filled, broadcast, synthetic, or placeholder estimator. If the real weights-only records cannot be used to produce a genuine estimator, stop with a concrete blocker and do not create score.json.'
timeout "${EVOSCIENTIST_ARC_TIMEOUT_SECONDS:-7200}s" /opt/venv/bin/evoscientist --use-cwd -p "$prompt" --auto-mode --auto-approve --ui cli --no-thinking
EOF
)
exec "$ROOT"/real_eval/scripts/arc_framework_fullrun.sh
