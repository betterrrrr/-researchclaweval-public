#!/usr/bin/env bash
set -euo pipefail
ROOT="${RESEARCHCLAWEVAL_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
source "$ROOT/real_eval/scripts/lib_real_eval.sh"
export FRAMEWORK_NAME="AutoResearchClaw"
export FRAMEWORK_SLUG="${FRAMEWORK_SLUG:-04_autoresearchclaw_babylm_gpt_fullrun}"
export FRAMEWORK_SRC="$(real_eval_resolve_framework_source "$ROOT" 04)"
export FRAMEWORK_ENTRY_PATHS=$(cat <<'EOF'
automation/babylm_method_free_contract.md
real_eval/scripts/lib_autoresearchclaw_handoff.sh
real_eval/scripts/patch_autoresearchclaw_literature_screen.py
real_eval/scripts/patch_autoresearchclaw_framework.py
EOF
)
export FRAMEWORK_ENTRYPOINT="bash"
export FRAMEWORK_RUNTIME_KIND="docker"
export FRAMEWORK_RUNTIME_IMAGE="autoresearchclaw:runtime-opencode"
export FRAMEWORK_NATIVE_ENTRYPOINT="researchclaw run --auto-approve"
export FRAMEWORK_PROVIDER_INJECTION="native framework client reads OPENAI_BASE_URL, OPENAI_API_KEY, and OPENAI_MODEL from environment"
export FRAMEWORK_NATIVE_LOG_MARKER="${FRAMEWORK_NATIVE_LOG_MARKER:-AUTORESEARCHCLAW_BABYLM_GPT_NATIVE}"
export FRAMEWORK_EXECUTOR_KIND="framework_cli"
export FRAMEWORK_COMMAND_LABEL="researchclaw run --topic babylm --auto-approve"
export FRAMEWORK_DISABLE_GPU="0"
export FRAMEWORK_RUNTIME_COMMAND=$(cat <<'EOF'
set -eu
ROOT="${ROOT:-/workspace}"
echo "${FRAMEWORK_NATIVE_LOG_MARKER}"
export PYTHONPATH="/workspace:${PYTHONPATH:-}"
export PATH="/opt/researchclaweval-node/bin:$PATH"
# Ensure Codex CLI is available at ./bin/codex (ACP agent requirement)
mkdir -p /workspace/bin
if command -v codex &>/dev/null; then
  ln -sf "$(command -v codex)" /workspace/bin/codex
  echo "[autoresearchclaw] Codex CLI linked at /workspace/bin/codex"
elif [[ -f /opt/researchclaweval-node/bin/codex ]]; then
  ln -sf /opt/researchclaweval-node/bin/codex /workspace/bin/codex
  echo "[autoresearchclaw] Codex CLI linked from /opt/researchclaweval-node/bin/codex"
fi
# Install OpenCode for Beast Mode if not already installed
if ! command -v opencode &>/dev/null; then
  npm install -g opencode-ai@latest --prefix /workspace/.opencode 2>&1 || echo "opencode install failed, continuing without"
  export PATH="/workspace/.opencode/bin:$PATH"
fi
# Create a minimal config file for researchclaw run
cat > /workspace/config.arc.yaml <<YAML
project:
  name: "babylm-research"
research:
  topic: "BabyLM Strict-Small benchmark. Validation and test use separate fixed splits. Never compute val and test metrics on the same data."
  quality_threshold: 0.3
llm:
  provider: "acp"
  primary_model: "${OPENAI_MODEL:-gpt-5.4}"
  acp:
    agent: "codex"
    cwd: "/workspace"
experiment:
  mode: "sandbox"
  time_budget_sec: 28800
  code_agent:
    enabled: true
    architecture_planning: true
    sequential_generation: true
    hard_validation: true
    hard_validation_max_repairs: 4
    exec_fix_max_iterations: 3
    exec_fix_timeout_sec: 600
  sandbox:
    python_path: "/usr/bin/python3"
runtime:
  timezone: "Asia/Shanghai"
notifications:
  channel: "none"
knowledge_base:
  root: "/workspace/knowledge"
prompts:
  extra_prompts:
    code_generation: "CRITICAL: Generate ONLY valid Python code. No markdown, no explanation text mixed with code. Every .py file must contain pure Python that passes ast.parse(). Use only ASCII. Every string literal must be properly terminated."
YAML
mkdir -p /workspace/knowledge
# Write topic to file to avoid shell escaping issues
cat > /workspace/topic.txt <<'TOPIC'
BabyLM Strict-Small: Run 2-4 materially different experiments on the BabyLM Strict-Small dataset under the official 2026 rules. The host does not prescribe an algorithm, architecture, hyperparameter, baseline, or experiment order. Use the dataset at /data/BabyLM-2026-Strict-Small. The framework must own idea formation, method selection, experiment design, execution, comparison, selection, analysis, and final artifact delivery. Write and lock research_idea.json before the first experiment. Compare by word-level validation perplexity, select the best, and write research_idea.json, experiment_trace.json, and final_report.md to /workspace.

DATASET LOADING RULES: The dataset has ONLY .txt files (train files, no separate validation set). Filter by extension .txt. Split train/val yourself. Do NOT silently catch file-reading exceptions — always log and raise. Verify loaded data is non-empty.

TRACE: experiment_trace.json must use fields "experiments" (array of {experiment_id, name, validation_perplexity}), "selected_experiment_id", "framework_native_execution", "consumed_topic_input", "workspace_trace_root", "framework_internal_model", "framework_internal_api_base_url", "idea_artifact", "idea_locked_before_experiments". All JSON must be strict — no NaN/Infinity (convert to null).

	CODE_GEN: ONLY valid Python. No markdown. Every .py must pass ast.parse(). ASCII only. USE GPU: torch.device("cuda" if torch.cuda.is_available() else "cpu") — move models/tensors to device. Test: python3 -c "import ast; ast.parse(open(file).read())" should exit 0 for every .py file.

	NUMERICAL STABILITY: To prevent NaN loss during training, ALWAYS: (a) use torch.nn.utils.clip_grad_norm_(model.parameters(), max_norm=1.0); (b) use AdamW with lr=1e-4 and weight_decay=0.01; (c) check batch loss with torch.isnan(loss).any() — if NaN, skip batch (continue) instead of backward(); (d) add a small epsilon (1e-8) inside log computations; (e) use float32, NOT float16/bfloat16.
TOPIC
# Verify import works
python3 -c "from researchclaw.cli import main; print('OK')" 2>&1 || {
  echo "researchclaw.cli not found, reinstalling..."
  pip uninstall -y researchclaw 2>/dev/null || true
  pip install -e /workspace --quiet 2>&1 || { echo "pip install failed"; exit 1; }
}
python3 /workspace/real_eval/scripts/patch_autoresearchclaw_literature_screen.py
python3 /workspace/real_eval/scripts/patch_autoresearchclaw_framework.py
echo "=== Starting researchclaw run ==="
source real_eval/scripts/lib_autoresearchclaw_handoff.sh
autoresearchclaw_validate_run_id "${REAL_EVAL_RUN_ID:?REAL_EVAL_RUN_ID is required}"
apply_autoresearchclaw_stage8_idea_lock_adapter "/workspace"
idea_provenance_contract="Before the first experiment, have the native Stage 8 synthesis write the framework-authored research_idea.json and research_idea_lock_event.json. The lock event must identify AutoResearchClaw as the framework writer, bind the finalized artifact SHA256, and carry a timezone-aware timestamp. Record research_idea.json, idea_locked_before_experiments=true, and first_experiment_started_at in experiment_trace.json."
artifact_root="/workspace/artifacts/babylm-${REAL_EVAL_RUN_ID}"
set +e
python3 -m researchclaw.cli run \
  --topic "$(cat /workspace/topic.txt) $idea_provenance_contract" \
  --config /workspace/config.arc.yaml \
  --output "$artifact_root" \
  --auto-approve
native_rc=$?
set -e
if [[ "$native_rc" -ne 0 ]]; then
  exit "$native_rc"
fi
autoresearchclaw_handoff babylm /workspace "$artifact_root"
verify_framework_research_idea_json "/workspace"
EOF
)
exec "$ROOT"/real_eval/scripts/babylm_framework_fullrun.sh
