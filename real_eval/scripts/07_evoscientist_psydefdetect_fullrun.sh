#!/usr/bin/env bash
set -euo pipefail
ROOT="${RESEARCHCLAWEVAL_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
source "$ROOT/real_eval/scripts/lib_real_eval.sh"
EVOSCIENTIST_MODEL="${REAL_EVAL_FRAMEWORK_MODEL:-${REAL_EVAL_MODEL:-${PSYDEFDETECT_EVAL_MODEL:-gpt-5.4}}}"
export FRAMEWORK_NAME="EvoScientist"
export FRAMEWORK_SLUG="07_evoscientist_psydefdetect_fullrun"
export FRAMEWORK_SRC="${RESEARCHCLAWEVAL_EVOSCIENTIST_ROOT:-$(real_eval_resolve_framework_source "$ROOT" 07)}"
export FRAMEWORK_ENTRY_PATHS=$(cat <<'EOF'
automation/psydefdetect_contract.md
automation/psydefdetect_execution_budget.md
EvoScientist/PSYDEFDETECT_BRIEF.md
EvoScientist/psydefdetect_start_message.txt
EOF
)
export FRAMEWORK_RUNTIME_KIND="docker"
export FRAMEWORK_RUNTIME_IMAGE="${EVOSCIENTIST_RUNTIME_IMAGE:-evoscientist:runtime-ready}"
export FRAMEWORK_ENTRYPOINT="bash"
export FRAMEWORK_NATIVE_ENTRYPOINT="evoscientist --use-cwd --auto-mode"
export FRAMEWORK_PROVIDER_INJECTION="custom-openai provider reads CUSTOM_OPENAI_BASE_URL, CUSTOM_OPENAI_API_KEY, and EVOSCIENTIST_MODEL"
export FRAMEWORK_NATIVE_LOG_MARKER="EVOSCIENTIST_NATIVE_CLI"
export FRAMEWORK_EXECUTOR_KIND="framework_cli"
export FRAMEWORK_LOG_FORBIDDEN_PATTERN='execute\((pip|python(3)? -m pip|uv) install|execute\((sleep|poll|tail)[[:space:]]|execute\((wget|curl|huggingface-cli)[[:space:]]'
export FRAMEWORK_COMMAND_LABEL="/opt/venv/bin/evoscientist --use-cwd --auto-mode"
export FRAMEWORK_DOCKER_ARGS=$(cat <<EOF
--user
$(id -u):$(id -g)
-e
HOME=/workspace
-e
XDG_CONFIG_HOME=/workspace/.config
-e
PYTHONPATH=/workspace/.evoscientist_runtime_patch
-e
EVOSCIENTIST_DATA_DIR=/workspace/.evoscientist
-e
EVOSCIENTIST_USE_RESPONSES_API=false
-e
EVOSCIENTIST_DISABLE_STREAMING=true
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
echo "EVOSCIENTIST_NATIVE_CLI"
export PATH="/opt/venv/bin:$PATH"
/opt/venv/bin/python -c 'import openai, langchain_openai'
mkdir -p /workspace/.config/evoscientist /workspace/.evoscientist
mkdir -p /workspace/.evoscientist_runtime_patch
case "${CUSTOM_OPENAI_BASE_URL:-}" in
  */v1) ;;
  */) export CUSTOM_OPENAI_BASE_URL="${CUSTOM_OPENAI_BASE_URL}v1" ;;
  *) export CUSTOM_OPENAI_BASE_URL="${CUSTOM_OPENAI_BASE_URL}/v1" ;;
esac
rm -rf /workspace/data/psydefdetect
mkdir -p /workspace/data/psydefdetect
cp -a /data/psydefdetect/. /workspace/data/psydefdetect/
cat > /workspace/.evoscientist_runtime_patch/sitecustomize.py <<'PY'
import os

if os.environ.get("EVOSCIENTIST_DISABLE_STREAMING", "").strip().lower() in {
    "1",
    "true",
    "yes",
    "on",
}:
    try:
        import json
        import langchain.chat_models as chat_models
        from langchain_openai.chat_models.base import BaseChatOpenAI

        _init_chat_model = chat_models.init_chat_model
        _create_chat_result = BaseChatOpenAI._create_chat_result

        def _init_chat_model_without_streaming(*args, **kwargs):
            kwargs["streaming"] = False
            return _init_chat_model(*args, **kwargs)

        def _create_chat_result_with_string_response(self, response, generation_info=None):
            if isinstance(response, str):
                try:
                    response = json.loads(response)
                except Exception:
                    response = {
                        "choices": [
                            {
                                "message": {
                                    "role": "assistant",
                                    "content": response,
                                }
                            }
                        ]
                    }
            return _create_chat_result(self, response, generation_info)

        chat_models.init_chat_model = _init_chat_model_without_streaming
        BaseChatOpenAI._create_chat_result = _create_chat_result_with_string_response
    except Exception:
        pass
PY
cat > /workspace/.config/evoscientist/config.yaml <<YAML
provider: custom-openai
model: ${EVOSCIENTIST_MODEL}
openai_auth_mode: api_key
default_mode: daemon
default_workdir: /workspace
show_thinking: false
enable_async_subagents: true
YAML
prompt="$(cat <<'PROMPT'
Environment note (read first): you are ALREADY running inside the native entrypoint of this framework. Do NOT launch, import, pip-install, uv-run, or otherwise bootstrap the framework itself, and do not create virtualenvs -- the host has already configured the runtime and the injected provider for you. A ModuleNotFoundError from importing the framework source with a different interpreter is not an environment blocker and must not be reported as one. Spend the run on the research task itself and write the required root-level artifacts; exploration that produces no artifact wastes the budget. The PsyDefDetect contract is summarized here, so do not spend a first step reading it:
- Task: predict one of nine psychological defense mechanism labels for a target help-seeker utterance with prior supportive conversation context.
- Labels: 0 No Defense, 1 Action Defenses, 2 Major Image-Distorting, 3 Disavowal, 4 Minor Image-Distorting, 5 Neurotic, 6 Obsessional, 7 High-Adaptive, 8 Needs More Information.
- Primary metric when labels are available: macro-F1 over positive classes 1-8; class 0 is excluded.
- Input dataset root inside your tool-accessible workspace: /workspace/data/psydefdetect. Use only this dataset copy, which was copied from the read-only official /data/psydefdetect mount.
- Use the standardized split manifest at /workspace/automation/psydefdetect_split.json and the scorer at /workspace/automation/scripts/run_psydefdetect_local_score.py.
- Before the first experiment, write `/workspace/research_idea.json` with the hypothesis, method rationale, expected failure modes, and comparison logic. The host does not prescribe an algorithm, feature representation, architecture, hyperparameter, baseline, or experiment order. For this EvoScientist run, choose and execute exactly 2 materially different experiments, then immediately finalize. Keep only a compact results ledger in context.
- Every framework-internal API call must use OPENAI_BASE_URL, OPENAI_API_KEY, and OPENAI_MODEL from the injected environment. OPENAI_MODEL is __EVAL_MODEL__; do not hardcode api.openai.com. Record framework_internal_model as __EVAL_MODEL__ and the injected base URL in the trace.
- API classification must batch at least 25 evaluation records per request and make at most 40 remote requests in total. Before executing an API experiment, implement and check this batching invariant. A one-record exploratory API experiment is forbidden; use an installed local method when an experiment cannot be batched. Do not use sleep/poll loops or install packages during the run.
- The required OpenAI client is already installed and verified before startup. Run every experiment command synchronously in the foreground with a sufficient command timeout. Do not use `&`, background processes, log-tail polling, or delayed status checks.
- Before exit, write `/workspace/experiment_trace.json` as a JSON object with exactly these required fields: `framework_native_execution: true`, `consumed_topic_input: true`, `workspace_trace_root: "/workspace"`, `experiments` (the two experiment records), `selected_experiment_id`, `prediction_artifact`, `score_artifact`, `framework_internal_model: "__EVAL_MODEL__"`, and `framework_internal_api_base_url` set from `OPENAI_BASE_URL`. Do not use alternate field names such as `experiment`, `framework_internal_base_url`, `predictions_path`, or `score_path` in place of these fields.
- Immediately before exit, read back experiment_trace.json and verify all required fields, exactly two experiments, and the selected experiment are present; repair the file inside the framework workflow if that check fails.
- Use the framework's own orchestration flow as much as possible instead of a loose pile of scratch scripts.
- Do not rely on downloading new Hugging Face models during runtime. Choose both methods from already-available resources and stay within the injected network policy.
- Required outputs under /workspace: predictions.jsonl or submission.csv, score.json, experiment_trace.json, final_report.md.
- Immediately after the last allowed experiment, stop exploration, select a final experiment, and promote its final outputs to the required root-level /workspace artifact paths.
- Do not leave only per-experiment subfolders such as exp*/ or experiment_*/ without a framework-level final artifact set at /workspace.
- Do not route to any other topic wrapper. Do not copy prior outputs.
- If the framework cannot complete that finalization step inside its own flow, stop with a concrete blocker instead of silently leaving partial outputs.

Run a framework-native PsyDefDetect workflow now. Do not stop after a single lightweight baseline. Read /workspace/data/psydefdetect/PsyDefConv.json and write all artifacts under /workspace. Sentence-transformers, transformers, torch, Hugging Face model downloads, pip/uv installation, background jobs, sleep/poll loops, and whole-filesystem model scans are forbidden and unavailable; choose only resources already present in the image and stop with a concrete blocker if they are unavailable.
PROMPT
)"
timeout "${EVOSCIENTIST_PSYDEFDETECT_TIMEOUT_SECONDS:-3600}s" /opt/venv/bin/evoscientist --use-cwd -p "$prompt" --auto-mode --auto-approve --ui cli --no-thinking
/opt/venv/bin/python - <<'PY'
import json
from pathlib import Path

trace_path = Path("/workspace/experiment_trace.json")
if trace_path.exists():
    trace = json.loads(trace_path.read_text(encoding="utf-8"))
    for experiment in trace.get("experiments", []):
        requests = experiment.get("api_requests")
        if requests is None:
            continue
        batch_size = experiment.get("batch_size")
        if not isinstance(requests, int) or requests > 40:
            raise SystemExit("EvoScientist API experiment exceeded the 40-request cap")
        if batch_size is not None and (not isinstance(batch_size, int) or batch_size < 25):
            raise SystemExit("EvoScientist API experiment used a batch smaller than 25")
PY
if [[ ! -s /workspace/predictions.jsonl && ! -s /workspace/submission.csv ]]; then
  echo "EvoScientist did not produce predictions.jsonl or submission.csv" >&2
  exit 42
fi
if [[ ! -s /workspace/final_report.md ]]; then
  echo "EvoScientist did not produce final_report.md" >&2
  exit 42
fi
if [[ ! -s /workspace/score.json ]]; then
  echo "EvoScientist did not produce score.json" >&2
  exit 42
fi
if [[ ! -s /workspace/experiment_trace.json ]]; then
  echo "EvoScientist did not produce experiment_trace.json" >&2
  exit 42
fi
EOF
)
export FRAMEWORK_RUNTIME_COMMAND="${FRAMEWORK_RUNTIME_COMMAND//__EVAL_MODEL__/$EVOSCIENTIST_MODEL}"
exec "$ROOT"/real_eval/scripts/psydefdetect_framework_fullrun.sh
