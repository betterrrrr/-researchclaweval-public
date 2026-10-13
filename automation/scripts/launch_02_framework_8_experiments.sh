#!/usr/bin/env bash
# Launch 8 framework-02 AI-Scientist-v2 experiments across 4 topics × 2 models (deepseek, kimi)
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SCRIPTS="$ROOT/real_eval/scripts"
RUN_BASE="$ROOT/real_eval/runs"
DEEPSEEK_PROVIDER="$ROOT/api/codex_deepseek_v4_flash_bianxie_relay_container.toml"
KIMI_PROVIDER="$ROOT/api/codex_kimi_k27_code_relay_container.toml"

mkdir -p "$RUN_BASE"

launch_one() {
  local topic="$1"
  local model="$2"
  local wrapper="$3"
  local model_id="$4"

  local ts=$(date +%Y%m%d-%H%M%S)
  local run_id="f02-${topic}-${model}-${ts}-$$"
  local run_root="$RUN_BASE/$run_id"
  local unit_name="f02-${topic}-${model}-${ts}"
  local provider

  if [[ "$model" == "deepseek" ]]; then
    provider="$DEEPSEEK_PROVIDER"
  else
    provider="$KIMI_PROVIDER"
  fi

  echo "=== Launching $topic $model run_id=$run_id ==="

  # Export all variables for the systemd-run subshell
  export LAUNCH_ROOT="$ROOT"
  export LAUNCH_RUN_ID="$run_id"
  export LAUNCH_RUN_ROOT="$run_root"
  export LAUNCH_PROVIDER="$provider"
  export LAUNCH_MODEL_ID="$model_id"
  export LAUNCH_WRAPPER="$SCRIPTS/$wrapper"
  export LAUNCH_TOPIC="$topic"
  export LAUNCH_MODEL="$model"

  systemd-run --user --scope --unit="$unit_name" bash -c '
set -euo pipefail
export RESEARCHCLAWEVAL_ROOT="$LAUNCH_ROOT"
export REAL_EVAL_RUN_ID="$LAUNCH_RUN_ID"
export REAL_EVAL_RUN_ROOT="$LAUNCH_RUN_ROOT"
export PROVIDER_CONFIG="$LAUNCH_PROVIDER"
export REAL_EVAL_FRAMEWORK_MODEL="$LAUNCH_MODEL_ID"
export REAL_EVAL_MODEL="$LAUNCH_MODEL_ID"

case "$LAUNCH_TOPIC" in
  arc_wbe_2026)
    export ARC_WBE_2026_DATASET_ROOT="$LAUNCH_ROOT/data/arc_white_box_estimation_2026"
    export ARC_WBE_2026_CONTRACT_FILE="$LAUNCH_ROOT/automation/arc_wbe_2026_contract.md"
    ;;
  psydefdetect)
    export PSYDEFDETECT_DATASET_ROOT="$LAUNCH_ROOT/data/psydefdetect"
    export PSYDEFDETECT_CONTRACT_FILE="$LAUNCH_ROOT/automation/psydefdetect_contract.md"
    ;;
  babylm)
    export BABYLM_DATASET_ROOT="$LAUNCH_ROOT/BabyLM-2026-Strict-Small"
    export BABYLM_CONTRACT_FILE="$LAUNCH_ROOT/automation/babylm_method_free_contract.md"
    ;;
  tdc_admet_tox)
    export TDC_ADMET_TOX_DATASET_ROOT="$LAUNCH_ROOT/data/tdc_admet_tox/public"
    export TDC_ADMET_TOX_CONTRACT_FILE="$LAUNCH_ROOT/automation/tdc_admet_tox_contract.md"
    ;;
esac

bash "$LAUNCH_WRAPPER" 2>&1
echo "=== EXIT_CODE=$? ==="
' &>/tmp/f02-${topic}-${model}-${ts}.log &
  echo "Launched $topic $model as $unit_name (background, PID=$!)"
}

# Launch all 8
launch_one "arc_wbe_2026" "deepseek" "02_ai_scientist_v2_arc_wbe_2026_fullrun.sh" "deepseek-v4-flash"
launch_one "arc_wbe_2026" "kimi" "02_ai_scientist_v2_arc_wbe_2026_fullrun.sh" "kimi-k2.6"
launch_one "psydefdetect" "deepseek" "02_ai_scientist_v2_psydefdetect_fullrun.sh" "deepseek-v4-flash"
launch_one "psydefdetect" "kimi" "02_ai_scientist_v2_psydefdetect_fullrun.sh" "kimi-k2.6"
launch_one "babylm" "deepseek" "02_ai_scientist_v2_babylm_deepseek_fullrun.sh" "deepseek-v4-flash"
launch_one "babylm" "kimi" "02_ai_scientist_v2_babylm_kimi_fullrun.sh" "kimi-k2.6"
launch_one "tdc_admet_tox" "deepseek" "02_ai_scientist_v2_tdc_admet_tox_fullrun.sh" "deepseek-v4-flash"
launch_one "tdc_admet_tox" "kimi" "02_ai_scientist_v2_tdc_admet_tox_fullrun.sh" "kimi-k2.6"

echo "=== All 8 experiments launched ==="
systemctl --user list-units 'f02-*' --all 2>/dev/null | head -20