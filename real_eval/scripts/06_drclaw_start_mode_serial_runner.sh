#!/usr/bin/env bash
set -euo pipefail

ROOT="${REAL_EVAL_RUN_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/runs}"
INPUTS="$ROOT/start_mode_inputs"
RUNS="$ROOT/runs"
IMAGE="dr-claw:start-mode-v2"
API_KEY="${REAL_EVAL_API_KEY:?REAL_EVAL_API_KEY must be set}"
API_BASE="${REAL_EVAL_API_BASE:-https://api.bianxie.ai/v1}"
GPU_DEVICES="4,5,6,7"
MAX_RETRIES=2
MAX_WAIT_SECONDS=14400

declare -A DATASETS
DATASETS[babylm]="${BABYLM_DATASET_ROOT:?set BABYLM_DATASET_ROOT}"
DATASETS[arc]="${ARC_WBE_2026_DATASET_ROOT:?set ARC_WBE_2026_DATASET_ROOT}"
DATASETS[mountaincar]="${MOUNTAINCAR_CONTINUOUS_DATASET_ROOT:?set MOUNTAINCAR_CONTINUOUS_DATASET_ROOT}"
DATASETS[psydef]="${PSYDEFDETECT_DATASET_ROOT:?set PSYDEFDETECT_DATASET_ROOT}"
DATASETS[tdc]="${TDC_ADMET_TOX_DATASET_ROOT:?set TDC_ADMET_TOX_DATASET_ROOT}"

declare -A CONTAINER_DS
CONTAINER_DS[babylm]="/data/BabyLM-2026-Strict-Small"
CONTAINER_DS[arc]="/data/ARC-WBE-2026"
CONTAINER_DS[mountaincar]="/data/MountainCar-Continuous"
CONTAINER_DS[psydef]="/data/PsyDefDetect"
CONTAINER_DS[tdc]="/data/TDC-ADMET-Tox"

EXPERIMENTS=(
  "babylm-deepseek BabyLM deepseek-v4-flash babylm"
  "babylm-luna BabyLM gpt-5.6-luna babylm"
  "mountaincar-deepseek MountainCar deepseek-v4-flash mountaincar"
  "mountaincar-luna MountainCar gpt-5.6-luna mountaincar"
  "arc-deepseek ARC deepseek-v4-flash arc"
  "arc-luna ARC gpt-5.6-luna arc"
  "psydef-deepseek PsyDefDetect deepseek-v4-flash psydef"
  "psydef-luna PsyDefDetect gpt-5.6-luna psydef"
  "tdc-deepseek TDC deepseek-v4-flash tdc"
  "tdc-luna TDC gpt-5.6-luna tdc"
)

echo "============================================"
echo "Dr. Claw Start Mode v2 - Serial Runner"
echo "Image: $IMAGE | GPU: $GPU_DEVICES"
echo "Start: $(date)"
echo "============================================"

for exp in "${EXPERIMENTS[@]}"; do
  IFS=' ' read -r slug topic model input_dir <<< "$exp"
  retry=0
  success=false

  while [ $retry -le $MAX_RETRIES ]; do
    RUN_ID="f06-start-${input_dir}-${model//./-}-$(date +%Y%m%d-%H%M%S)"
    RUN_DIR="$RUNS/$RUN_ID"
    CNAME="drclaw_start_${slug}_r${retry}"

    echo "--- [$topic x $model] Attempt $((retry+1))/$((MAX_RETRIES+1)) ---"
    echo "Run ID: $RUN_ID"

    DS_HOST="${DATASETS[$input_dir]:-}"
    DS_CONTAINER="${CONTAINER_DS[$input_dir]:-/data/$input_dir}"
    if [ -z "$DS_HOST" ] || [ ! -d "$DS_HOST" ]; then
      echo "ERROR: Dataset not found at $DS_HOST"; break
    fi

    mkdir -p "$RUN_DIR"
    docker rm -f "$CNAME" 2>/dev/null || true

    docker run -d --name "$CNAME" \
      --gpus all \
      --ipc=host \
      --ulimit memlock=-1 \
      --ulimit stack=67108864 \
      -e CUDA_VISIBLE_DEVICES="$GPU_DEVICES" \
      -e OPENAI_API_KEY="$API_KEY" \
      -e OPENAI_BASE_URL="$API_BASE" \
      -e DRCLAW_PROJECT_NAME="$RUN_ID" \
      -e DRCLAW_MODEL="$model" \
      -e DRCLAW_PROVIDER="openrouter" \
      -e DRCLAW_OUTPUT_DIR="/workspace/output" \
      -e JWT_SECRET="dev-secret" \
      -v "$INPUTS/$input_dir:/workspace/input:ro" \
      -v "$DS_HOST:$DS_CONTAINER:ro" \
      -v "$RUN_DIR:/workspace/output" \
      "$IMAGE" > /dev/null 2>&1

    elapsed=0
    while [ $elapsed -lt $MAX_WAIT_SECONDS ]; do
      sleep 60
      elapsed=$((elapsed + 60))
      CSTATE=$(docker inspect "$CNAME" --format '{{.State.Status}}' 2>/dev/null || echo "not_found")
      if [ "$CSTATE" = "exited" ] || [ "$CSTATE" = "not_found" ]; then
        echo "[$(date '+%H:%M:%S')] Exited after ${elapsed}s"
        docker logs "$CNAME" 2>&1 > "$RUN_DIR/e2e.log" 2>/dev/null || true
        ac=0
        for f in research_idea.json experiment_trace.json final_report.md; do
          [ -f "$RUN_DIR/$f" ] && ac=$((ac + 1))
        done
        auto_ok=false
        grep -q "latestRun completed" "$RUN_DIR/e2e.log" 2>/dev/null && auto_ok=true
        if [ "$ac" -ge 3 ] || [ "$auto_ok" = true ]; then
          success=true
          echo "SUCCESS: $ac artifacts (auto_ok=$auto_ok)"
        else
          echo "PARTIAL: $ac/3 artifacts (auto_ok=$auto_ok)"
        fi
        break
      fi
      [ $((elapsed % 300)) -eq 0 ] && docker logs "$CNAME" 2>&1 | grep -E "Turn|Status:" | tail -2 || true
    done

    [ $elapsed -ge $MAX_WAIT_SECONDS ] && echo "TIMEOUT" && docker kill "$CNAME" 2>/dev/null || true
    docker logs "$CNAME" 2>&1 > "$RUN_DIR/e2e.log" 2>/dev/null || true
    docker rm -f "$CNAME" 2>/dev/null || true

    $success && echo "Completed: $topic x $model (attempt $((retry+1)))" && break
    retry=$((retry + 1))
    [ $retry -le $MAX_RETRIES ] && echo "Retry in 30s..." && sleep 30
  done

  [ "$success" != true ] && echo "FAILED: $topic x $model"
  sleep 15
done

echo "All done at $(date)"
