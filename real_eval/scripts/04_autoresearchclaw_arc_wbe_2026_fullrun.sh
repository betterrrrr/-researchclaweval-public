#!/usr/bin/env bash
set -euo pipefail
ROOT="${RESEARCHCLAWEVAL_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
source "$ROOT/real_eval/scripts/lib_real_eval.sh"
export FRAMEWORK_NAME="AutoResearchClaw"
export FRAMEWORK_SLUG="04_autoresearchclaw_arc_wbe_2026_fullrun"
export FRAMEWORK_SRC="$(real_eval_resolve_framework_source "$ROOT" 04)"
export FRAMEWORK_ENTRY_PATHS=$(cat <<'EOF'
AutoResearchClaw/config.arc.yaml
AutoResearchClaw/topic.txt
real_eval/scripts/lib_autoresearchclaw_handoff.sh
real_eval/scripts/patch_autoresearchclaw_literature_screen.py
real_eval/scripts/patch_autoresearchclaw_framework.py
real_eval/scripts/patch_autoresearchclaw_max_tokens.py
docs/arc_wbe_2026_summary.md
automation/arc_wbe_2026_contract.md
automation/arc_wbe_2026_execution_budget.md
EOF
)
export FRAMEWORK_RUNTIME_KIND="docker"
export FRAMEWORK_RUNTIME_IMAGE="autoresearchclaw:runtime-opencode"
export FRAMEWORK_ENTRYPOINT="bash"
export FRAMEWORK_NATIVE_ENTRYPOINT="python -m researchclaw.cli run"
export FRAMEWORK_KIMI_INJECTION="config.arc.yaml OpenAI-compatible client uses OPENAI_BASE_URL, OPENAI_API_KEY, and OPENAI_MODEL"
export FRAMEWORK_NATIVE_LOG_MARKER="AUTORESEARCHCLAW_NATIVE_RUN"
export FRAMEWORK_EXECUTOR_KIND="framework_cli"
export FRAMEWORK_COMMAND_LABEL="python3 -m researchclaw.cli run --config config.arc.yaml"
export FRAMEWORK_RUNTIME_COMMAND=$(cat <<'EOF'
set -euo pipefail
ROOT="${ROOT:-/workspace}"
# GPU allocation: this docker/NVIDIA-runtime combination silently ignores the
# device list in `--gpus <ids>` (the container still sees every host GPU and
# torch.cuda.device_count() reports all of them), so the restriction is applied
# here instead. CUDA_VISIBLE_DEVICES is honoured by torch and re-indexes cuda:0
# onto the first allowed device. GPUs 0-3 must stay untouched.
export CUDA_VISIBLE_DEVICES="${CUDA_VISIBLE_DEVICES:-4,5,6,7}"
echo "AUTORESEARCHCLAW_NATIVE_RUN"
echo "CUDA_VISIBLE_DEVICES=$CUDA_VISIBLE_DEVICES"
topic="$(tr '\n' ' ' < topic.txt)"
topic="$topic CODE_GEN: ONLY valid Python. No markdown. Every .py must pass ast.parse(). ASCII only. USE GPU: torch.device("cuda" if torch.cuda.is_available() else "cpu") — move models/tensors to device. THAT GPU RULE APPLIES TO YOUR EXPERIMENT CODE ONLY, NOT TO estimator.py.
GRADER-SANDBOX-CONTRACT (read before writing estimator.py): the official grader runs estimator.py inside a sealed sandbox that provides ONLY the Python standard library, flopscope.numpy (import it as fnp), and the whestbench API (BaseEstimator, MLP, SetupContext). There is no dependency install step and no third-party package. estimator.py must NOT import torch, numpy, scipy, sklearn, pandas or any other third-party module — a single such import makes the grader refuse the file and the whole run scores nothing at all. Use flopscope.numpy as fnp for every array operation, or plain Python math. The only tolerated exception is scipy.special.erf, for which a shim is injected; do not rely on any other scipy name.
ARC-WBE-CONTRACT: (1) estimator.py must be importable and must define EITHER a class named exactly Estimator, instantiated with no constructor arguments, OR a factory function build_estimator() taking no arguments and returning that object. That object must have a method predict(self, mlp) — a self-taking METHOD, NOT a bare module-level predict(mlp) — returning a real numpy prediction matrix of shape (32,256) (predicted mean activation of each of 256 hidden neurons in each of 32 layers), derived from mlp.weights. This exact shape matters: the official scoring adapter imports estimator.py, instantiates Estimator() (or calls build_estimator()), and calls that method. A module-level predict function, or a class with any other name, is not discovered and scores nothing at all. (2) Use the REAL weight data from the parquet file — do NOT generate synthetic targets/activations. (3) RUNTIME INTERFACE — read this carefully: the experiment runs as a plain standalone python3 main.py process inside this container. There is NO host callback, no evaluator service, no split-provider, and no data-fetch API at runtime. Call ONLY functions and classes that you yourself define in the files you generate; calling anything else (for example an ExperimentHarness method that you did not implement) raises at import/run time and has already made previous runs fail. (4) Do NOT try to obtain ground-truth labels or a validation split — they are not available to your process. Implement predict(mlp) for every mlp_id present in the parquet, run your conditions, and print your metrics (including the primary metric) to stdout. The host selects and evaluates its own fixed validation subset out of band, after your process has exited; your job is only to emit genuine weight-derived predictions and your own honest self-reported metrics. (5) Scalar, zero-filled, synthetic, placeholder, copied, or fallback predictions are ALL INADMISSIBLE and will be rejected.
DATASET-PATH-CONTRACT: The dataset is mounted at /data/arc_wbe_2026/. The parquet weight file is at /data/arc_wbe_2026/data/arc_wbe_2026_weights-00000-of-00001.parquet. The column 'weights' contains float32 arrays of shape (32,256,256) and the column 'mlp_id' contains int32 IDs. Use pyarrow.parquet.read_table() to load it. DO NOT guess the path — use this EXACT path."
eval_contract="EVAL-CONTRACT: Run 2-4 materially different framework-chosen experiments and write these four final artifacts to the workspace ROOT using these EXACT absolute paths: /workspace/estimator.py, /workspace/submission.json, /workspace/experiment_trace.json, /workspace/final_report.md. NEVER create and NEVER overwrite /workspace/research_idea.json or /workspace/research_idea_lock_event.json: the framework Stage 8 synthesis owns those two files, writes them with framework provenance marking, and locks the idea before the first experiment; overwriting them invalidates the entire run and forfeits the score. Read them if you need context, but never write them. experiment_trace.json must be a complete contract object, not a one-experiment summary, recording ALL of: framework_native_execution true; consumed_topic_input true; workspace_trace_root exactly the string /workspace; framework_internal_model, set to the exact value of the OPENAI_MODEL environment variable; framework_internal_api_base_url, set to the exact value of the OPENAI_BASE_URL environment variable including any trailing /v1; experiments, an array of 2 to 4 entries each carrying a unique non-empty experiment_id plus that experiment configuration and validation metrics; selected_experiment_id, equal to one of those experiment_id values; idea_artifact exactly the string research_idea.json; idea_locked_before_experiments true; and first_experiment_started_at, the WALL-CLOCK UTC time at which the first experiment actually started, written as an ISO-8601 string with a timezone offset such as 2026-10-07T12:34:56.789012+00:00 (use datetime.now(timezone.utc).isoformat()). It MUST be strictly later than the research idea lock timestamp. Do NOT use a monotonic or elapsed-seconds counter, a bare integer, or any value near the Unix epoch such as 1970-02-23T08:49:47Z — a monotonic clock reading converted to a timestamp is wrong and makes the provenance check fail. Emit strict JSON only: no NaN and no Infinity."
python3 real_eval/scripts/patch_autoresearchclaw_literature_screen.py
python3 real_eval/scripts/patch_autoresearchclaw_framework.py
python3 real_eval/scripts/patch_autoresearchclaw_max_tokens.py
source real_eval/scripts/lib_autoresearchclaw_handoff.sh
autoresearchclaw_validate_run_id "${REAL_EVAL_RUN_ID:?REAL_EVAL_RUN_ID is required}"
apply_autoresearchclaw_stage8_idea_lock_adapter "/workspace"
idea_provenance_contract="Before the first experiment, have the native Stage 8 synthesis write the framework-authored research_idea.json and research_idea_lock_event.json. The lock event must identify AutoResearchClaw as the framework writer, bind the finalized artifact SHA256, and carry a timezone-aware timestamp. Record research_idea.json, idea_locked_before_experiments=true, and first_experiment_started_at in experiment_trace.json."
artifact_root="/workspace/artifacts/arc-wbe-2026-${REAL_EVAL_RUN_ID}"
set +e
timeout "${ARC_WBE_2026_FRAMEWORK_TIMEOUT_SECONDS:-28800}s" python3 -m researchclaw.cli run \
  --config config.arc.yaml \
  --topic "$topic $eval_contract $idea_provenance_contract" \
  --output "$artifact_root" \
  --auto-approve
native_rc=$?
set -e
if [[ "$native_rc" -ne 0 ]]; then
  exit "$native_rc"
fi
autoresearchclaw_handoff arc_wbe_2026 /workspace "$artifact_root"
verify_framework_research_idea_json "/workspace"
EOF
)
exec "$ROOT"/real_eval/scripts/arc_framework_fullrun.sh
