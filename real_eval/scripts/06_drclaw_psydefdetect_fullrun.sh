#!/usr/bin/env bash
set -euo pipefail

ROOT="${RESEARCHCLAWEVAL_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
source "$ROOT/real_eval/scripts/lib_real_eval.sh"

export FRAMEWORK_NAME="Dr. Claw"
export FRAMEWORK_SLUG="06_drclaw_psydefdetect_fullrun"
export FRAMEWORK_SRC="$(real_eval_resolve_framework_source "$ROOT" 06)"
export FRAMEWORK_ENTRY_PATHS=$(cat <<'EOF'
dr-claw/README.md
docs/psydefdetect_summary.md
automation/psydefdetect_contract.md
automation/psydefdetect_execution_budget.md
automation/drclaw_psydefdetect_authorization_20260805.md
EOF
)
export FRAMEWORK_RUNTIME_KIND="docker"
export FRAMEWORK_RUNTIME_IMAGE="${DRCLAW_RUNTIME_IMAGE:-dr-claw:runtime-ready}"
EVAL_MODEL="${PSYDEFDETECT_EVAL_MODEL:-gpt-5.4}"
DRCLAW_MAX_AGENT_TURNS="${DRCLAW_MAX_AGENT_TURNS:-50}"
export FRAMEWORK_ENTRYPOINT="bash"
export FRAMEWORK_DOCKER_ARGS=$(cat <<EOF
--user
0:0
-e
NODE_PATH=/opt/dr-claw/node_modules
-e
DRCLAW_MAX_AGENT_TURNS=$DRCLAW_MAX_AGENT_TURNS
-e
DRCLAW_PSYDEFDETECT_LOCAL_ONLY=1
EOF
)
export FRAMEWORK_NATIVE_ENTRYPOINT="node server/cli.js chat --model $EVAL_MODEL"
export FRAMEWORK_PROVIDER_INJECTION="Dr. Claw native CLI reads OPENAI_BASE_URL, OPENAI_API_KEY, and OPENAI_MODEL from the injected evaluation provider environment"
export FRAMEWORK_NATIVE_LOG_MARKER="DRCLAW_NATIVE_CHAT"
export FRAMEWORK_EXECUTOR_KIND="framework_cli"
export FRAMEWORK_COMMAND_LABEL="node server/cli.js chat --model $EVAL_MODEL"
export FRAMEWORK_RUNTIME_COMMAND=$(cat <<'EOF'
set -euo pipefail
echo "DRCLAW_NATIVE_CHAT"
python3 - server/cli-chat.js <<'PY'
from pathlib import Path
import sys

path = Path(sys.argv[1])
text = path.read_text(encoding="utf-8")
old = """      case 'Write': {
        const fp = resolve(args.path);"""
new = """      case 'Write': {
        if (
          process.env.DRCLAW_PSYDEFDETECT_LOCAL_ONLY === '1'
          && String(args.path || '').endsWith('.py')
          && /(?:\\bopenai\\b|\\brequests\\b|\\bhttpx\\b|urllib\\.request|chat\\.completions|\/v1\/responses)/i.test(String(args.content || ''))
        ) {
          return 'Blocked by the fixed local-resource policy. Choose another framework-authored experiment using installed local resources.';
        }
        const fp = resolve(args.path);"""
if old not in text:
    raise SystemExit("Dr. Claw Write guard insertion point not found")
text = text.replace(old, new, 1)
old = """      case 'Bash': {
        try {"""
new = """      case 'Bash': {
        if (
          process.env.DRCLAW_PSYDEFDETECT_LOCAL_ONLY === '1'
          && /(?:\\bpip(?:3)?\\s+install\\b|\\buv\\s+(?:add|pip)\\b|\\bcurl\\b|\\bwget\\b|huggingface-cli|(?:^|[/_ -])api(?:[._ -]|$))/i.test(String(args.command || ''))
        ) {
          return 'Blocked by the fixed local-resource policy. Pivot once to another framework-authored experiment; do not retry this command.';
        }
        try {"""
if old not in text:
    raise SystemExit("Dr. Claw Bash guard insertion point not found")
path.write_text(text.replace(old, new, 1), encoding="utf-8")
PY
prompt='Read docs/psydefdetect_summary.md, automation/psydefdetect_contract.md, automation/psydefdetect_execution_budget.md, and automation/drclaw_psydefdetect_authorization_20260805.md. Execute the complete PsyDefDetect task through the native Dr. Claw planning and tool loop in this fresh /workspace only. Use only /workspace/data/psydefdetect and the fixed split at /workspace/automation/psydefdetect_split.json. The dataset path is inside the project root; do not access /data/psydefdetect directly. Dataset schema (the host owns this input, and no other file describes it): /workspace/data/psydefdetect/PsyDefConv.json is a JSON array of 2336 records; every record is an object with exactly these fields -- id (string such as "0001"), dialogue_id (string), dialogue (a JSON array of turns, each turn an object with text (string) and speaker (string, either seeker or supporter)), current_text (string, the target utterance to classify -- this is the field to predict the label of), and label (integer 0-8, where 0 means no defence mechanism is present and labels 1-8 are the positive classes the scoring uses). The dialogue column is list-valued, so drop it or stringify it before any pandas operation that needs hashable cells. The split manifest /workspace/automation/psydefdetect_split.json lists the record ids: use train_record_ids to fit and eval_record_ids to predict and score. First write a framework-authored research_idea.json as a JSON object with four non-empty string fields: hypothesis, method_rationale, expected_failure_modes, and comparison_logic. The expected_failure_modes field must name concrete risks even if the framework expects success. The host does not prescribe an algorithm, feature representation, architecture, hyperparameter, baseline, or experiment order. Once research_idea.json is written, stop re-reading files or probing CLIs and immediately write one self-contained Python experiment file that imports only sklearn, numpy, and pandas, then execute it with Bash. Then choose and run exactly two materially different experiments using installed resources; invoke /workspace/automation/scripts/run_psydefdetect_local_score.py for each experiment with the required CLI arguments. The experiment program must call the scorer via subprocess with the full command: python /workspace/automation/scripts/run_psydefdetect_local_score.py --dataset-root /data/psydefdetect --split-manifest /workspace/automation/psydefdetect_split.json --predictions <pred_file> --output-score <score_file>. After scoring both experiments, the program must stop iterating and write at /workspace root: predictions.jsonl (the predictions from the selected experiment -- one JSON object per line, exactly {"id": "<the record id from PsyDefConv.json>", "predicted_label": <integer label>}, with exactly one line for every id listed in eval_record_ids inside /workspace/automation/psydefdetect_split.json and no other lines; the scorer matches rows to the eval split by that id field, so a predictions file without ids, or with a differently named label field, scores zero rows and is rejected as missing evaluation ids), score.json (copy the selected numeric psydefdetect_score), experiment_trace.json (exactly two experiments, selected_experiment_id, framework_native_execution=true, consumed_topic_input=true, workspace_trace_root=/workspace, framework_internal_model=OPENAI_MODEL, framework_internal_api_base_url=OPENAI_BASE_URL), and final_report.md. Once these four root artifacts exist, do not edit the code further. Do not download models, install packages, use web search, make remote requests from experiment code, reuse prior outputs, or run a third experiment. If a command fails because a resource is unavailable, stop and report the blocker rather than repeating the same command. The framework itself must write root-level research_idea.json, predictions.jsonl or submission.csv, score.json, experiment_trace.json, and final_report.md. score.json must contain only psydefdetect_score and score_key. experiment_trace.json must contain exactly two experiments, selected_experiment_id, framework_native_execution=true, consumed_topic_input=true, workspace_trace_root=/workspace, framework_internal_model from OPENAI_MODEL, and framework_internal_api_base_url from OPENAI_BASE_URL. Do not stop at a plan or explanation; continue using native tools until all required artifacts are present and then summarize the selected official score.'
printf '%s\n' "$prompt" | timeout "${DRCLAW_PSYDEFDETECT_TIMEOUT_SECONDS:-3600}s" node server/cli.js chat --model "$OPENAI_MODEL"
EOF
)
exec "$ROOT/real_eval/scripts/psydefdetect_framework_fullrun.sh"
