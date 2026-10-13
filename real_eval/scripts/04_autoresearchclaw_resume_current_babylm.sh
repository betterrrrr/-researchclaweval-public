#!/usr/bin/env bash
set -euo pipefail

ROOT="${RESEARCHCLAWEVAL_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
source "$ROOT/real_eval/scripts/lib_real_eval.sh"
RUN_ID="${REAL_EVAL_RUN_ID:?REAL_EVAL_RUN_ID must point at the existing run}"
BASE="${REAL_EVAL_RUN_ROOT:-$ROOT/real_eval/runs/$RUN_ID/04_autoresearchclaw_real_babylm}"
REPO="$BASE/repo"
LOG_DIR="$BASE/logs"
DATASET_ROOT="${BABYLM_DATASET_ROOT:-$ROOT/BabyLM-2026-Strict-Small}"
CONTRACT_FILE="${BABYLM_CONTRACT_FILE:-$ROOT/BabyLM-10M_七框架任务包装与分发指南.md}"
PROVIDER_CONFIG="${PROVIDER_CONFIG:-$ROOT/api/codex_gpt54_shubiaobiao.toml}"
SEMANTIC_SOURCE="${SEMANTIC_SOURCE:-$ROOT/api/_semantic_scholar_api_usage.md}"
PROVIDER_ENV="$BASE/provider.env"
SEMANTIC_ENV="$BASE/semantic.env"
CONTAINER_NAME="autoresearchclaw_babylm_${RUN_ID}"
ARTIFACT_DIR="$REPO/artifacts/babylm-real-${RUN_ID}"

if [[ ! -d "$REPO" || ! -f "$REPO/config.babylm.yaml" ]]; then
  echo "AutoResearchClaw resume requires existing repo/config at $REPO" >&2
  exit 20
fi
if [[ ! -d "$ARTIFACT_DIR" ]]; then
  echo "AutoResearchClaw resume requires existing artifacts at $ARTIFACT_DIR" >&2
  exit 21
fi

mkdir -p "$LOG_DIR"
if [[ ! -f "$PROVIDER_ENV" ]]; then
  real_eval_provider_env_from_codex_toml "$PROVIDER_CONFIG" "$PROVIDER_ENV"
fi
if [[ ! -f "$SEMANTIC_ENV" ]]; then
  real_eval_semantic_env_from_usage_md "$SEMANTIC_SOURCE" "$SEMANTIC_ENV"
fi

python3 - "$REPO/config.babylm.yaml" "$REPO/topic.babylm.txt" <<'PY'
from pathlib import Path
import re
import sys

config = Path(sys.argv[1])
topic_path = Path(sys.argv[2])
s = config.read_text(encoding="utf-8")

def set_line(text: str, pattern: str, replacement: str) -> str:
    new, count = re.subn(pattern, replacement, text, flags=re.MULTILINE)
    if count == 0:
        raise SystemExit(f"Missing config line for pattern: {pattern}")
    return new

s = set_line(s, r"^  time_budget_sec:\s*\d+\s*$", "  time_budget_sec: 3600")
s = set_line(s, r"^  max_iterations:\s*\d+\s*$", "  max_iterations: 2")
if re.search(r"^  max_refine_duration_sec:", s, flags=re.MULTILINE):
    s = set_line(s, r"^  max_refine_duration_sec:\s*\d+\s*$", "  max_refine_duration_sec: 3600")
else:
    s = s.replace("  max_iterations: 2\n", "  max_iterations: 2\n  max_refine_duration_sec: 3600\n", 1)
s = set_line(s, r"^    tree_search_enabled:\s*(true|false)\s*$", "    tree_search_enabled: false")
s = set_line(s, r"^    tree_search_candidates:\s*\d+\s*$", "    tree_search_candidates: 1")
s = set_line(s, r"^    tree_search_max_depth:\s*\d+\s*$", "    tree_search_max_depth: 1")
s = set_line(s, r"^    tree_search_eval_timeout_sec:\s*\d+\s*$", "    tree_search_eval_timeout_sec: 30")
s = set_line(s, r"^    exec_fix_timeout_sec:\s*\d+\s*$", "    exec_fix_timeout_sec: 30")
s = set_line(s, r"^    timeout_sec:\s*\d+\s*$", "    timeout_sec: 900")
s = set_line(s, r'^    network_policy:\s*"[^"]*"\s*$', '    network_policy: "setup_only"')
config.write_text(s, encoding="utf-8")

topic = """BabyLM-10M real end-to-end language-model research resume.
Continue the existing AutoResearchClaw artifacts from the checkpoint; do not restart literature review, ideation, or code generation.
For Stage 13, repair the generated experiment so it runs real neural language-model training on /data/BabyLM-2026-Strict-Small or data/BabyLM-2026-Strict-Small using the contract at /input/contract.md or input/contract.md.
No proxy scripts, no iris/digits/toy datasets, and no old results.
To finish within the current recovery budget while staying real, use exactly two conditions, one seed per condition, and a compact CUDA transformer.
Each condition must consume the real BabyLM 10M-token training budget, save checkpoints, print TRAIN_PROGRESS at least every 1M tokens, write results JSON, and write a paper/report.
Avoid pure-Python BPE over the full corpus; use byte-level tokenization or an installed tokenizer implementation.
If a run becomes unstable, lower learning rate, disable mixed precision, clip gradients, and keep the same real BabyLM input rather than replacing it with synthetic data.
"""
topic_path.write_text(topic, encoding="utf-8")
PY

cat > "$REPO/run_resume_real_babylm.sh" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
topic="$(cat topic.babylm.txt)"
python3 -m researchclaw.cli run \
  --config config.babylm.yaml \
  --topic "$topic" \
  --output "artifacts/babylm-real-${RUN_ID}" \
  --resume \
  --auto-approve \
  --skip-noncritical-stage
EOF
chmod +x "$REPO/run_resume_real_babylm.sh"

cat > "$BASE/state.json" <<EOF
{"project_id":"04","name":"AutoResearchClaw","run_id":"$RUN_ID","status":"resuming_from_stage13","repo":"$REPO","artifact_dir":"$ARTIFACT_DIR"}
EOF

docker rm -f "$CONTAINER_NAME" >/dev/null 2>&1 || true

set +e
docker run --rm --name "$CONTAINER_NAME" --gpus all --entrypoint bash \
  -e HOME=/tmp \
  -e CODEX_HOME=/workspace/AutoResearchClaw/.codex-real \
  -e RUN_ID="$RUN_ID" \
  --env-file "$PROVIDER_ENV" \
  --env-file "$SEMANTIC_ENV" \
  --env-file "$ROOT/AutoResearchClaw/project4.env" \
  -v "$REPO":/workspace/AutoResearchClaw \
  -v "$DATASET_ROOT":/data/BabyLM-2026-Strict-Small:ro \
  -v "$DATASET_ROOT":/workspace/AutoResearchClaw/data/BabyLM-2026-Strict-Small:ro \
  -v "$CONTRACT_FILE":/input/contract.md:ro \
  -v "$CONTRACT_FILE":/workspace/AutoResearchClaw/input/contract.md:ro \
  -w /workspace/AutoResearchClaw \
  autoresearchclaw:runtime-opencode \
  -lc './run_resume_real_babylm.sh' \
  2>&1 | tee "$LOG_DIR/e2e_resume_stage13.log"
rc=${PIPESTATUS[0]}
set -e

if [[ "$rc" -ne 0 ]]; then
  real_eval_write_state "$BASE/state.json" "{\"project_id\":\"04\",\"name\":\"AutoResearchClaw\",\"run_id\":\"$RUN_ID\",\"status\":\"failed\",\"repo\":\"$REPO\",\"log\":\"$LOG_DIR/e2e_resume_stage13.log\",\"exit_code\":$rc}"
  exit "$rc"
fi

if ! real_eval_has_artifacts "$BASE"; then
  real_eval_write_state "$BASE/state.json" "{\"project_id\":\"04\",\"name\":\"AutoResearchClaw\",\"run_id\":\"$RUN_ID\",\"status\":\"failed_no_artifacts\",\"repo\":\"$REPO\",\"log\":\"$LOG_DIR/e2e_resume_stage13.log\"}"
  exit 13
fi

cat > "$BASE/state.json" <<EOF
{"project_id":"04","name":"AutoResearchClaw","run_id":"$RUN_ID","status":"finished","repo":"$REPO","log":"$LOG_DIR/e2e_resume_stage13.log"}
EOF
