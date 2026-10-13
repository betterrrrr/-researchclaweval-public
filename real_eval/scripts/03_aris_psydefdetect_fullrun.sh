#!/usr/bin/env bash
set -euo pipefail
ROOT="${RESEARCHCLAWEVAL_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
source "$ROOT/real_eval/scripts/lib_real_eval.sh"
export FRAMEWORK_NAME="ARIS"
export FRAMEWORK_SLUG="03_aris_psydefdetect_fullrun"
export FRAMEWORK_SRC="${RESEARCHCLAWEVAL_ARIS_ROOT:-$(real_eval_resolve_framework_source "$ROOT" 03)}"
export FRAMEWORK_ENTRY_PATHS=$(cat <<'EOF'
Auto-claude-code-research-in-sleep/PSYDEFDETECT_BRIEF.md
automation/psydefdetect_contract.md
automation/psydefdetect_execution_budget.md
EOF
)
export FRAMEWORK_RUNTIME_KIND="docker"
export FRAMEWORK_RUNTIME_IMAGE="${ARIS_RUNTIME_IMAGE:-aris:runtime-ready}"
export FRAMEWORK_DOCKER_ARGS=$(cat <<'EOF'
--user
0:0
EOF
)
export FRAMEWORK_NATIVE_ENTRYPOINT="ARIS /experiment-bridge skill"
export FRAMEWORK_PROVIDER_INJECTION="ARIS Codex executor reads the injected evaluation provider configuration from /codex-home/config.toml"
export FRAMEWORK_NATIVE_LOG_MARKER="ARIS_NATIVE_EXPERIMENT_BRIDGE"
export FRAMEWORK_EXECUTOR_KIND="official_framework_skill"
export FRAMEWORK_COMMAND_LABEL='codex exec --yolo -C /workspace "/experiment-bridge PSYDEFDETECT_BRIEF.md"'
export FRAMEWORK_RUNTIME_COMMAND=$(cat <<'EOF'
set -euo pipefail
test -f skills/skills-codex/experiment-bridge/SKILL.md
echo "ARIS_NATIVE_EXPERIMENT_BRIDGE"
timeout "${ARIS_PSYDEFDETECT_TIMEOUT_SECONDS:-7200}s" \
  codex exec --yolo --skip-git-repo-check -C /workspace \
  "/experiment-bridge PSYDEFDETECT_BRIEF.md — CODE_REVIEW: false, RESCUE_ON_FAILURE: false, AUTO_DEPLOY: true, BACKENDS: local, SANITY_FIRST: true, MAX_PARALLEL_RUNS: 1. This is the official ARIS Codex skill workflow. Plan and execute exactly 2 materially different experiments, compare the fixed-split local scores, then immediately select and promote one result. Any API classification must batch at least 25 evaluation records per request and use no more than 40 remote requests total. Do not issue one request per record, run background jobs, use sleep/poll loops, install packages, spawn a reviewer with another model, or call any public provider. Keep only a compact experiment ledger in context. Never print or paste the full PsyDefConv dataset, prediction files, or generated source into the conversation; inspect schema and aggregate summaries only. The framework itself must write root-level predictions.jsonl or submission.csv, score.json, experiment_trace.json, and final_report.md. experiment_trace.json must be one JSON object with exactly these fields: framework_native_execution set to true, consumed_topic_input set to true, workspace_trace_root set to /workspace, framework_internal_model set to the OPENAI_MODEL environment variable value, framework_internal_api_base_url set to the OPENAI_BASE_URL environment variable value, experiments as exactly 2 records, selected_experiment_id, prediction_artifact, and score_artifact. Write research_idea.json before experiment_trace.json so the idea file timestamp is earlier. Use only the injected evaluation provider configuration and the PsyDefDetect inputs."
EOF
)
exec "$ROOT"/real_eval/scripts/psydefdetect_framework_fullrun.sh
