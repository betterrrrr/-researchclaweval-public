#!/usr/bin/env bash
set -euo pipefail

ROOT="${RESEARCHCLAWEVAL_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
source "$ROOT/real_eval/scripts/lib_real_eval.sh"
export FRAMEWORK_NAME="AutoResearchClaw"
export FRAMEWORK_SLUG="04_autoresearchclaw_tdc_admet_tox_fullrun"
export FRAMEWORK_SRC="$(real_eval_resolve_framework_source "$ROOT" 04)"
export FRAMEWORK_ENTRY_PREFIX="AutoResearchClaw"
export FRAMEWORK_ENTRY_PATHS=$(cat <<'EOF'
AutoResearchClaw/config.tdc_admet_tox.yaml
AutoResearchClaw/topic.tdc_admet_tox.txt
real_eval/scripts/lib_autoresearchclaw_handoff.sh
real_eval/scripts/patch_autoresearchclaw_framework.py
AutoResearchClaw/TDC_ADMET_TOX_BRIEF.md
real_eval/adapters/tdc_admet_tox/patch_autoresearchclaw.py
automation/tdc_admet_tox_contract.md
automation/tdc_admet_tox_execution_budget.md
EOF
)
export FRAMEWORK_RUNTIME_IMAGE="${AUTORESEARCHCLAW_RUNTIME_IMAGE:-autoresearchclaw:runtime-opencode}"
export FRAMEWORK_NATIVE_ENTRYPOINT="python -m researchclaw.cli run"
export FRAMEWORK_NATIVE_ENTRYPOINT_FILE="researchclaw/cli.py"
export FRAMEWORK_NATIVE_ENTRYPOINT_SOURCE="README.md"
export FRAMEWORK_PROVIDER_INJECTION="AutoResearchClaw openai-compatible config reads the isolated OPENAI_BASE_URL, OPENAI_API_KEY, and OPENAI_MODEL"
export FRAMEWORK_NATIVE_LOG_MARKER="AUTORESEARCHCLAW_NATIVE_RUN_TDC"
export FRAMEWORK_NATIVE_PROCESS_MARKERS="NATIVE_CMD> timeout 14400s python3 -m researchclaw.cli run"
export FRAMEWORK_EXECUTOR_KIND="framework_cli"
export FRAMEWORK_COMMAND_LABEL="python -m researchclaw.cli run --config config.tdc_admet_tox.yaml --auto-approve"
export FRAMEWORK_RUNTIME_COMMAND=$(cat <<'EOF'
set -euo pipefail
ROOT="${ROOT:-/workspace}"
echo "AUTORESEARCHCLAW_NATIVE_RUN_TDC"
python3 real_eval/adapters/tdc_admet_tox/patch_autoresearchclaw.py
# Simplified topic instead of the verbose auto-generated one
topic='TDC-ADMET-Tox: Run 2-4 materially different experiments on molecular ADMET prediction (AMES, hERG, DILI endpoints). Data: train.csv (has labels), validation.csv (has labels), test.csv (NO labels). Metric: macro average AUROC across endpoints. Use SMILES-based features from RDKit. No external data, no network calls. Framework must own idea, method selection, experiment design, execution, comparison, selection, and artifact delivery.'
topic="$topic CODE_GEN: USE GPU: torch.device("cuda" if torch.cuda.is_available() else "cpu") — move models/tensors to device. USE CPU-FRIENDLY METHODS: sklearn, RandomForest, XGBoost, LogisticRegression ONLY. Generate code that finishes training + evaluation in under 30 minutes CPU time. DATA: All endpoints (AMES, hERG, DILI) in a SINGLE train.csv/validation.csv. train.csv has label column. test.csv has NO labels — only for prediction. Path: /data/tdc_admet_tox/train.csv, NOT endpoint-subdirectories. Use endpoint column to filter.
CRITICAL: RDKit is NOT available in the sandbox. Do NOT import rdkit. Use pandas/numpy/sklearn only. Compute features from SMILES strings using simple approaches: molecule weight, atom counts, bond counts, or Morgan fingerprints via an internal helper if available. If Morgan fails, fall back to basic scalar features.
OUTPUT: After training, predict on test.csv and save predictions.csv at the workspace root. Format: CSV header "sample_id,endpoint,probability" followed by one row per (test_sample, endpoint) combination. sample_id must use the EXACT same values as the test.csv sample_id column (e.g. "AMES_test_000000"), endpoint is one of AMES/hERG/DILI, probability is the predicted probability of the positive class (float 0-1). Write predictions.csv ONLY at the very end of the script after all training and prediction is complete — do NOT create it earlier."
python3 real_eval/scripts/patch_autoresearchclaw_framework.py
source real_eval/scripts/lib_autoresearchclaw_handoff.sh
autoresearchclaw_validate_run_id "${REAL_EVAL_RUN_ID:?REAL_EVAL_RUN_ID is required}"
apply_autoresearchclaw_stage8_idea_lock_adapter "/workspace"
idea_provenance_contract="Before the first experiment, have the native Stage 8 synthesis write the framework-authored research_idea.json and research_idea_lock_event.json. The lock event must identify AutoResearchClaw as the framework writer, bind the finalized artifact SHA256, and carry a timezone-aware timestamp. Record research_idea.json, idea_locked_before_experiments=true, and first_experiment_started_at in experiment_trace.json."
artifact_root="/workspace/artifacts/tdc-admet-tox-${REAL_EVAL_RUN_ID}"
export AUTORESEARCHCLAW_ARTIFACT_ROOT="${artifact_root}/deliverables"
PS4='NATIVE_CMD> '
set -x
set +e
timeout 14400s python3 -m researchclaw.cli run \
  --config config.tdc_admet_tox.yaml \
  --topic "$topic $idea_provenance_contract" \
  --output "$artifact_root" \
  --auto-approve \
  --skip-noncritical-stage
native_rc=$?
set -e
# Promote predictions.csv from sandbox to deliverables if missing
if [[ "$native_rc" -eq 0 && ! -f "$AUTORESEARCHCLAW_ARTIFACT_ROOT/predictions.csv" ]]; then
  found_predictions="$(find "$artifact_root" -name "predictions.csv" -type f 2>/dev/null | head -1)"
  if [[ -n "$found_predictions" ]]; then
    cp "$found_predictions" "$AUTORESEARCHCLAW_ARTIFACT_ROOT/predictions.csv"
    echo "NATIVE_CMD> Promoted predictions.csv from $found_predictions"
  fi
fi
if [[ "$native_rc" -ne 0 ]]; then
  exit "$native_rc"
fi
autoresearchclaw_handoff tdc_admet_tox /workspace "$artifact_root"
WORKSPACE=/workspace python3 real_eval/adapters/tdc_admet_tox/patch_autoresearchclaw.py --handoff
verify_framework_research_idea_json "/workspace"
EOF
)
exec "$ROOT/real_eval/scripts/tdc_admet_tox_framework_fullrun.sh"
