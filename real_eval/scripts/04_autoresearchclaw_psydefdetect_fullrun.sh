#!/usr/bin/env bash
set -euo pipefail
ROOT="${RESEARCHCLAWEVAL_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
source "$ROOT/real_eval/scripts/lib_real_eval.sh"
export FRAMEWORK_NAME="AutoResearchClaw"
export FRAMEWORK_SLUG="04_autoresearchclaw_psydefdetect_fullrun"
export FRAMEWORK_SRC="${RESEARCHCLAWEVAL_AUTORESEARCHCLAW_ROOT:-$(real_eval_resolve_framework_source "$ROOT" 04)}"
export FRAMEWORK_ENTRY_PREFIX="AutoResearchClaw"
export FRAMEWORK_ENTRY_PATHS=$(cat <<'EOF'
AutoResearchClaw/config.psydefdetect.yaml
AutoResearchClaw/topic.psydefdetect.txt
real_eval/scripts/lib_autoresearchclaw_handoff.sh
real_eval/scripts/patch_autoresearchclaw_literature_screen.py
real_eval/scripts/patch_autoresearchclaw_framework.py
real_eval/adapters/psydefdetect/patch_autoresearchclaw.py
AutoResearchClaw/evaluation_prompts/psydefdetect_search_strategy.md
AutoResearchClaw/evaluation_prompts/psydefdetect_literature_collect.md
AutoResearchClaw/evaluation_prompts/psydefdetect_literature_screen.md
AutoResearchClaw/evaluation_prompts/psydefdetect_experiment_design.md
AutoResearchClaw/evaluation_prompts/psydefdetect_code_generation.md
AutoResearchClaw/psydefdetect_benchmark_knowledge.yaml
docs/psydefdetect_literature_catalog.md
automation/psydefdetect_contract.md
automation/psydefdetect_execution_budget.md
EOF
)
export FRAMEWORK_RUNTIME_KIND="docker"
export FRAMEWORK_RUNTIME_IMAGE="${AUTORESEARCHCLAW_RUNTIME_IMAGE:-autoresearchclaw:runtime-opencode}"
export FRAMEWORK_ENTRYPOINT="bash"
export FRAMEWORK_NATIVE_ENTRYPOINT="python -m researchclaw.cli run"
export FRAMEWORK_PROVIDER_INJECTION="config.psydefdetect.yaml OpenAI-compatible client uses OPENAI_BASE_URL, OPENAI_API_KEY, and OPENAI_MODEL"
export FRAMEWORK_NATIVE_LOG_MARKER="AUTORESEARCHCLAW_NATIVE_RUN"
export FRAMEWORK_EXECUTOR_KIND="framework_cli"
# Use the canonical provider URL injected by the campaign. The shared relay
# network is only needed when a campaign explicitly supplies an isolated relay.
export FRAMEWORK_ISOLATED_RELAY="${REAL_EVAL_ISOLATED_RELAY:-0}"
export PSYDEFDETECT_RELAY_IMAGE="${PSYDEFDETECT_RELAY_IMAGE:-researchclaweval/codex-kimi-relay:test}"
export FRAMEWORK_COMMAND_LABEL="python3 -m researchclaw.cli run --config config.psydefdetect.yaml"
export FRAMEWORK_RUNTIME_COMMAND=$(cat <<'EOF'
set -euo pipefail
ROOT="${ROOT:-/workspace}"
echo "AUTORESEARCHCLAW_NATIVE_RUN"
python3 real_eval/adapters/psydefdetect/patch_autoresearchclaw.py "$ROOT"
topic="$(tr '\n' ' ' < topic.psydefdetect.txt)"
topic="$topic CODE_GEN: ONLY valid Python. No markdown. Every .py must pass ast.parse(). ASCII only. USE GPU: torch.device("cuda" if torch.cuda.is_available() else "cpu") — move models/tensors to device."
python3 real_eval/scripts/patch_autoresearchclaw_literature_screen.py
python3 real_eval/scripts/patch_autoresearchclaw_framework.py
source real_eval/scripts/lib_autoresearchclaw_handoff.sh
autoresearchclaw_validate_run_id "${REAL_EVAL_RUN_ID:?REAL_EVAL_RUN_ID is required}"
artifact_root="/workspace/artifacts/psydefdetect-${REAL_EVAL_RUN_ID}"
mkdir -p "$artifact_root"
apply_autoresearchclaw_stage8_idea_lock_adapter "/workspace"
idea_provenance_contract="Before the first experiment, have the native Stage 8 synthesis write the framework-authored research_idea.json and research_idea_lock_event.json. The lock event must identify AutoResearchClaw as the framework writer, bind the finalized artifact SHA256, and carry a timezone-aware timestamp. Record research_idea.json, idea_locked_before_experiments=true, and first_experiment_started_at in experiment_trace.json."
cat > "$artifact_root/execution_contract.md" <<'BRIEF'
The AutoResearchClaw pipeline owns planning, experiment execution, comparison, selection, and final delivery. Run exactly 2 materially different experiments on the fixed PsyDefDetect split, each exactly once, then immediately select and promote the better valid result. Do not add repeated seeds, refinements, pivots, ablations, or extra experimental runs after those two executions. For each condition, invoke /workspace/automation/scripts/run_psydefdetect_local_score.py with --dataset-root, --split-manifest, --predictions, and --output-score; generated scorer substitutes and fallback summaries are invalid. Before exiting, the framework must write root-level /workspace/predictions.jsonl or /workspace/submission.csv, /workspace/score.json, /workspace/experiment_trace.json, and /workspace/final_report.md. score.json must retain numeric psydefdetect_score and score_key from the official scorer. experiment_trace.json must contain exactly two experiments with unique experiment_id, numeric psydefdetect_score, complete scorer_command, and selected_experiment_id, plus framework_native_execution=true, consumed_topic_input=true, workspace_trace_root=/workspace, framework_internal_model from OPENAI_MODEL, and framework_internal_api_base_url from OPENAI_BASE_URL, and first_experiment_started_at, the WALL-CLOCK UTC time at which the first experiment actually started, written as an ISO-8601 string with a timezone offset such as 2026-10-07T12:34:56.789012+00:00 (use datetime.now(timezone.utc).isoformat()). It MUST be strictly later than the research idea lock timestamp. Do NOT use a monotonic or elapsed-seconds counter, a bare integer, or any value near the Unix epoch such as 1970-02-23T08:49:47Z — a monotonic clock reading converted to a timestamp is wrong and makes the provenance check fail. The host will validate but not promote or supplement framework artifacts.
BRIEF
set +e
timeout "${AUTORESEARCHCLAW_PSYDEFDETECT_TIMEOUT_SECONDS:-10800}s" \
  python3 -m researchclaw.cli run \
  --config config.psydefdetect.yaml \
  --topic "$topic. Run exactly two framework-selected fixed-split experiments using only the installed dependency allowlist; do not download, install packages, or make remote experiment calls. Do NOT create and do NOT overwrite research_idea.json or research_idea_lock_event.json: the framework Stage 8 synthesis owns those two files, writes them with framework provenance marking before the first experiment, and overwriting them invalidates the entire run. Read automation/psydefdetect_contract.md, automation/psydefdetect_execution_budget.md, and $artifact_root/execution_contract.md. Use only /data/psydefdetect and the injected evaluation provider. LABEL INTEGRITY: every experiment must keep the target text and the label column intact end to end — the last run failed five times with 'target text was lost' and produced zero real metrics. Do not drop, rename, mask, or recompute the target/label column, and assert per experiment that the number of scored rows is greater than zero before reporting metrics. $idea_provenance_contract" \
  --output "$artifact_root" \
  --auto-approve
native_rc=$?
set -e
if [[ "$native_rc" -ne 0 ]]; then
  exit "$native_rc"
fi
autoresearchclaw_handoff psydefdetect /workspace "$artifact_root"
verify_framework_research_idea_json "/workspace"
EOF
)
exec "$ROOT"/real_eval/scripts/psydefdetect_framework_fullrun.sh
