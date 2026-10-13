#!/usr/bin/env bash
set -euo pipefail

ROOT="${RESEARCHCLAWEVAL_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
source "$ROOT/real_eval/scripts/lib_real_eval.sh"
RUN_ID="${REAL_EVAL_RUN_ID:-$(date +%Y%m%d-%H%M%S)}"
BASE="${REAL_EVAL_RUN_ROOT:-$ROOT/real_eval/runs/$RUN_ID/04_autoresearchclaw}"
SRC="$ROOT/AutoResearchClaw"
REPO="$BASE/repo"
LOG_DIR="$BASE/logs"
DATASET_ROOT="${BABYLM_DATASET_ROOT:-$ROOT/BabyLM-2026-Strict-Small}"
CONTRACT_FILE="${BABYLM_CONTRACT_FILE:-$ROOT/BabyLM-10M_七框架任务包装与分发指南.md}"
PROVIDER_CONFIG="${PROVIDER_CONFIG:-$ROOT/api/codex_gpt54_shubiaobiao.toml}"
SEMANTIC_SOURCE="${SEMANTIC_SOURCE:-$ROOT/api/_semantic_scholar_api_usage.md}"
PROVIDER_ENV="$BASE/provider.env"
SEMANTIC_ENV="$BASE/semantic.env"
CONTAINER_NAME="autoresearchclaw_babylm_${RUN_ID}"

cleanup_container() {
  docker ps -a --format '{{.Names}}' | rg "^${CONTAINER_NAME}$" | xargs -r docker rm -f >/dev/null 2>&1 || true
}
trap cleanup_container EXIT

real_eval_require_clean_dir "$BASE"
mkdir -p "$BASE" "$LOG_DIR"
real_eval_rsync_repo "$SRC" "$REPO"
mkdir -p "$REPO/.codex-real" "$REPO/data" "$REPO/input"
cp "$PROVIDER_CONFIG" "$REPO/.codex-real/config.toml"
real_eval_provider_env_from_codex_toml "$PROVIDER_CONFIG" "$PROVIDER_ENV"
real_eval_semantic_env_from_usage_md "$SEMANTIC_SOURCE" "$SEMANTIC_ENV"

cat > "$REPO/topic.babylm.txt" <<EOF
BabyLM-10M real end-to-end language-model research. Read /input/contract.md or input/contract.md and train on /data/BabyLM-2026-Strict-Small or data/BabyLM-2026-Strict-Small. The run must include ideation, literature/context review, experiment design, real neural language-model training, checkpoint saving, evaluation, analysis, and paper/report generation. Do not use proxy scripts, iris, digits, or old results.
EOF

cp "$SRC/config.project4.yaml" "$REPO/config.babylm.yaml"
python3 - "$REPO/config.babylm.yaml" <<'PY'
from pathlib import Path
import sys
p = Path(sys.argv[1])
s = p.read_text()
s = s.replace('project4-autoresearchclaw', 'babylm-real-autoresearchclaw')
s = s.replace('project4', 'babylm-real')
s = s.replace('time_budget_sec: 120', 'time_budget_sec: 86400')
s = s.replace('max_iterations: 2', 'max_iterations: 8')
s = s.replace('gpu_required: false', 'gpu_required: true')
s = s.replace('tree_search_enabled: false', 'tree_search_enabled: true')
s = s.replace('tree_search_candidates: 1', 'tree_search_candidates: 3')
s = s.replace('tree_search_max_depth: 1', 'tree_search_max_depth: 2')
s = s.replace('network_policy: "none"', 'network_policy: "restricted"')
p.write_text(s)
PY
python3 - "$REPO/config.babylm.yaml" "$SEMANTIC_ENV" <<'PY'
from pathlib import Path
import sys

config = Path(sys.argv[1])
env_path = Path(sys.argv[2])
env = {}
for line in env_path.read_text().splitlines():
    if not line or line.startswith("#") or "=" not in line:
        continue
    k, v = line.split("=", 1)
    env[k] = v
s2_key = env.get("S2_API_KEY") or env.get("SEMANTIC_SCHOLAR_OFFICIAL_API_KEY") or ""
ai4_key = env.get("AI4SCHOLAR_API_KEY") or env.get("SEMANTIC_SCHOLAR_API_KEY") or ""
s = config.read_text()
if "  s2_api_key:" not in s:
    s = s.replace("  fallback_models:\n", f"  s2_api_key: \"{s2_key}\"\n  ai4scholar_api_key: \"{ai4_key}\"\n  fallback_models:\n", 1)
else:
    lines = []
    for line in s.splitlines():
        if line.startswith("  s2_api_key:"):
            lines.append(f"  s2_api_key: \"{s2_key}\"")
        elif line.startswith("  ai4scholar_api_key:"):
            lines.append(f"  ai4scholar_api_key: \"{ai4_key}\"")
        else:
            lines.append(line)
    s = "\n".join(lines) + "\n"
config.write_text(s)
PY

cat > "$BASE/state.json" <<EOF
{"project_id":"04","name":"AutoResearchClaw","run_id":"$RUN_ID","status":"starting","repo":"$REPO"}
EOF

cat > "$REPO/run_real_babylm.sh" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
topic="$(cat topic.babylm.txt)"
python3 -m researchclaw.cli run \
  --config config.babylm.yaml \
  --topic "$topic" \
  --output "artifacts/babylm-real-${RUN_ID}" \
  --auto-approve
EOF
chmod +x "$REPO/run_real_babylm.sh"

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
	  -lc './run_real_babylm.sh' \
	  2>&1 | tee "$LOG_DIR/e2e.log"
rc=${PIPESTATUS[0]}
set -e
if [[ "$rc" -ne 0 ]]; then
  real_eval_write_state "$BASE/state.json" "{\"project_id\":\"04\",\"name\":\"AutoResearchClaw\",\"run_id\":\"$RUN_ID\",\"status\":\"failed\",\"repo\":\"$REPO\",\"log\":\"$LOG_DIR/e2e.log\",\"exit_code\":$rc}"
  exit "$rc"
fi

if ! real_eval_has_artifacts "$BASE"; then
  real_eval_write_state "$BASE/state.json" "{\"project_id\":\"04\",\"name\":\"AutoResearchClaw\",\"run_id\":\"$RUN_ID\",\"status\":\"failed_no_artifacts\",\"repo\":\"$REPO\",\"log\":\"$LOG_DIR/e2e.log\"}"
  exit 13
fi
cat > "$BASE/state.json" <<EOF
{"project_id":"04","name":"AutoResearchClaw","run_id":"$RUN_ID","status":"finished","repo":"$REPO","log":"$LOG_DIR/e2e.log"}
EOF
