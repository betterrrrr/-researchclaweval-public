#!/usr/bin/env bash
set -euo pipefail

ROOT="${RESEARCHCLAWEVAL_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
source "$ROOT/real_eval/scripts/lib_real_eval.sh"
export FRAMEWORK_NAME="AI-Scientist-v2"
export FRAMEWORK_SLUG="02_ai_scientist_v2_tdc_admet_tox_fullrun"
export FRAMEWORK_SRC="$(real_eval_resolve_framework_source "$ROOT" 02)"
export FRAMEWORK_ENTRY_PREFIX="AI-Scientist-v2"
export FRAMEWORK_ENTRY_PATHS=$(cat <<'EOF'
AI-Scientist-v2/ai_scientist/ideas/tdc_admet_tox_topic.md
real_eval/adapters/ai_scientist_v2/patch_ai_scientist_v2_common.py
real_eval/adapters/tdc_admet_tox/patch_ai_scientist_v2.py
automation/tdc_admet_tox_contract.md
automation/tdc_admet_tox_execution_budget.md
EOF
)
export FRAMEWORK_RUNTIME_IMAGE="${AI_SCIENTIST_V2_RUNTIME_IMAGE:-ai-scientist-v2:runtime-ready}"
export FRAMEWORK_NATIVE_ENTRYPOINT="perform_ideation_temp_free.py -> launch_scientist_bfts.py"
export FRAMEWORK_NATIVE_ENTRYPOINT_FILE="ai_scientist/perform_ideation_temp_free.py"
export FRAMEWORK_NATIVE_ENTRYPOINT_SOURCE="README.md"
export FRAMEWORK_PROVIDER_INJECTION="AI-Scientist-v2 OpenAI clients use OPENAI_BASE_URL, OPENAI_API_KEY, and OPENAI_MODEL from the isolated relay"
export FRAMEWORK_NATIVE_LOG_MARKER="AI_SCIENTIST_V2_NATIVE_BFTS_TDC"
export FRAMEWORK_NATIVE_PROCESS_MARKERS=$(cat <<'EOF'
NATIVE_CMD> timeout 1800s python3 ai_scientist/perform_ideation_temp_free.py
NATIVE_CMD> timeout 5100s python3 launch_scientist_bfts.py
EOF
)
export FRAMEWORK_EXECUTOR_KIND="framework_cli"
export FRAMEWORK_COMMAND_LABEL="python ai_scientist/perform_ideation_temp_free.py; python launch_scientist_bfts.py"
export FRAMEWORK_DOCKER_ARGS=$(cat <<'EOF'
-e
TDC_ADMET_TOX_NATIVE_RUN=1
-e
CUDA_VISIBLE_DEVICES=
EOF
)
export FRAMEWORK_RUNTIME_COMMAND=$(cat <<'EOF'
set -euo pipefail
echo "AI_SCIENTIST_V2_NATIVE_BFTS_TDC"
python3 real_eval/adapters/ai_scientist_v2/patch_ai_scientist_v2_common.py
echo "[tdc-wrapper] shared adapter applied"
python3 real_eval/adapters/tdc_admet_tox/patch_ai_scientist_v2.py
echo "[tdc-wrapper] preflight relay check"
python3 -c "
import os, urllib.request, sys
base_url = os.environ.get('OPENAI_BASE_URL', '')
if base_url:
    # Try /healthz first (relay native), then /models (OpenAI standard)
    for suffix in ('/healthz', '/models'):
        url = base_url.rstrip('/') + suffix
        try:
            req = urllib.request.Request(url, method='GET')
            with urllib.request.urlopen(req, timeout=10) as resp:
                print(f'relay reachable: {url} -> {resp.status}')
                break
        except urllib.error.HTTPError as exc:
            if exc.code in (404, 405):
                # Endpoint not found/method not allowed -> relay is reachable
                print(f'relay reachable: {url} -> {exc.code} (relay up, endpoint N/A)')
                break
            print(f'WARNING: relay error at {url}: {exc.code} {exc.reason}')
            sys.exit(1)
        except Exception as exc:
            if url == url:  # last attempt failed
                print(f'WARNING: relay unreachable at {url}: {exc}')
                sys.exit(1)
"
echo "[tdc-wrapper] relay check passed"
rm -f ai_scientist/ideas/tdc_admet_tox_topic.json
PS4='NATIVE_CMD> '
set -x
for attempt in 1 2 3; do
  rm -f ai_scientist/ideas/tdc_admet_tox_topic.json
  timeout 1800s python3 ai_scientist/perform_ideation_temp_free.py \
    --workshop-file ai_scientist/ideas/tdc_admet_tox_topic.md \
    --model "$OPENAI_MODEL" \
    --max-num-generations 1 \
    --num-reflections 5
  test -s ai_scientist/ideas/tdc_admet_tox_topic.json && break
  echo "ideation produced 0 ideas on attempt $attempt; retrying"
done
test -s ai_scientist/ideas/tdc_admet_tox_topic.json
timeout 5100s python3 launch_scientist_bfts.py \
  --load_ideas ai_scientist/ideas/tdc_admet_tox_topic.json \
  --model_writeup "$OPENAI_MODEL" \
  --model_writeup_small "$OPENAI_MODEL" \
  --model_citation "$OPENAI_MODEL" \
  --model_review "$OPENAI_MODEL" \
  --model_agg_plots "$OPENAI_MODEL" \
  --num_cite_rounds 0 \
  --skip_writeup \
  --skip_review
EOF
)
exec "$ROOT/real_eval/scripts/tdc_admet_tox_framework_fullrun.sh"
