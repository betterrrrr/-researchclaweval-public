#!/usr/bin/env bash
set -euo pipefail

ROOT="${RESEARCHCLAWEVAL_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
source "$ROOT/real_eval/scripts/lib_real_eval.sh"
FRAMEWORK_MODEL_RAW="${REAL_EVAL_FRAMEWORK_MODEL:-${REAL_EVAL_MODEL:-gpt-5.4}}"
FRAMEWORK_NAME="${FRAMEWORK_NAME:-AI-Researcher}"
AI_RESEARCHER_COMPLETION_MODEL="${AI_RESEARCHER_COMPLETION_MODEL:-openai/${FRAMEWORK_MODEL_RAW}}"
AI_RESEARCHER_CHEAP_MODEL="${AI_RESEARCHER_CHEAP_MODEL:-$AI_RESEARCHER_COMPLETION_MODEL}"
RUN_ID="${REAL_EVAL_RUN_ID:-$(date +%Y%m%d-%H%M%S)}"
BASE="${REAL_EVAL_RUN_ROOT:?REAL_EVAL_RUN_ROOT is required}"
SRC="${RESEARCHCLAWEVAL_AI_RESEARCHER_ROOT:-$(real_eval_resolve_framework_source "$ROOT" 01)}"
WORKSPACE="$BASE/workspace"
REPO="$WORKSPACE/AI-Researcher"
INPUT_ROOT="$BASE/inputs"
FRAMEWORK_DATASET_ROOT="$INPUT_ROOT/arc_wbe_2026_weights_only"
LOG_DIR="$BASE/logs"
LOG_FILE="$BASE/logs/e2e.log"
STATE_FILE="$BASE/state.json"
MANIFEST_FILE="$BASE/fullrun_manifest.json"
CODEX_HOME_DIR="$BASE/codex_home"
DATASET_ROOT="${ARC_WBE_2026_DATASET_ROOT:-$(real_eval_resolve_topic_dataset "$ROOT" arc_wbe_2026)}"
# 与 arc_framework_fullrun.sh 保持一致：框架自评集 / host 评分集互斥。
ARC_VISIBLE_VALIDATION_ROOT="$DATASET_ROOT/visible-validation"
ARC_SCORING_ROOT="$DATASET_ROOT/scoring"
CONTRACT_FILE="${ARC_WBE_2026_CONTRACT_FILE:-$ROOT/automation/arc_wbe_2026_contract.md}"
PROVIDER_CONFIG="${PROVIDER_CONFIG:-$ROOT/api/codex_gpt54_shubiaobiao.toml}"
PROVIDER_BASE_URL="$(sed -n 's/^[[:space:]]*base_url[[:space:]]*=[[:space:]]*"\(.*\)"[[:space:]]*$/\1/p' "$PROVIDER_CONFIG" | head -1)"
FRAMEWORK_PROVIDER_BASE_URL="${PROVIDER_BASE_URL%/}"
if [[ "$FRAMEWORK_PROVIDER_BASE_URL" != */v1 ]]; then
  FRAMEWORK_PROVIDER_BASE_URL="$FRAMEWORK_PROVIDER_BASE_URL/v1"
fi
SEMANTIC_SOURCE="${SEMANTIC_SOURCE:-$ROOT/api/_semantic_scholar_api_usage.md}"
PROVIDER_ENV="$BASE/provider.env"
SEMANTIC_ENV="$BASE/semantic.env"
OUTER_IMAGE="ai-researcher:runtime-ready"
OUTER_CONTAINER_NAME="ai_researcher_arc_wbe_2026_outer_${RUN_ID}"
INNER_CONTAINER_NAME="arc_wbe_2026_eval_${RUN_ID}"
TOPIC_INSTANCE_REL="AI-Researcher/benchmark/final/arc_wbe_2026/arc_wbe_2026.json"
TOPIC_METAPROMPT_REL="AI-Researcher/benchmark/process/dataset_candidate/arc_wbe_2026/metaprompt.py"
TOPIC_SUMMARY_REL="docs/arc_wbe_2026_summary.md"
TOPIC_CONTRACT_REL="automation/arc_wbe_2026_contract.md"
TOPIC_BUDGET_REL="automation/arc_wbe_2026_execution_budget.md"
SCORE_SOURCE_ARTIFACT="${ARC_WBE_2026_LOCAL_SCORE_ARTIFACT:-}"
WEIGHTS_ONLY_PYTHON="${ARC_WBE_2026_WHEST_PYTHON:-/tmp/whest-starterkit/.venv/bin/python}"

cleanup_containers() {
  docker ps -a --format '{{.Names}}' | rg "^(${OUTER_CONTAINER_NAME}|${INNER_CONTAINER_NAME})$" | xargs -r docker rm -f >/dev/null 2>&1 || true
}
trap cleanup_containers EXIT

write_state() {
  local status="$1"
  local summary="$2"
  local exit_code="${3:-0}"
  local command="${4:-}"
  python3 - "$STATE_FILE" "$status" "$summary" "$exit_code" "$command" <<'PY'
from datetime import datetime, timezone
from pathlib import Path
import json
import sys

payload = {
    "project_id": "arc_wbe_2026",
    "phase": "fullrun",
    "status": sys.argv[2],
    "summary": sys.argv[3],
    "updated_at": datetime.now(timezone.utc).astimezone().isoformat(),
    "exit_code": int(sys.argv[4]),
}
if sys.argv[5]:
    payload["e2e_command"] = sys.argv[5]
Path(sys.argv[1]).write_text(json.dumps(payload, ensure_ascii=False) + "\n", encoding="utf-8")
PY
}

real_eval_require_clean_dir "$BASE"
mkdir -p "$WORKSPACE" "$INPUT_ROOT" "$LOG_DIR" "$CODEX_HOME_DIR"

[[ -d "$DATASET_ROOT" ]] || { echo "missing dataset root: $DATASET_ROOT" >&2; exit 21; }
[[ -f "$CONTRACT_FILE" ]] || { echo "missing contract file: $CONTRACT_FILE" >&2; exit 22; }
[[ -d "$SRC" ]] || { echo "missing framework source: $SRC" >&2; exit 23; }

write_state "starting" "Preparing AI-Researcher ARC-WBE-2026 fullrun workspace"

"$WEIGHTS_ONLY_PYTHON" \
  "$ROOT/automation/scripts/generate_arc_wbe_2026_weights_only_dataset.py" \
  --source-root "$DATASET_ROOT" \
  --output-root "$FRAMEWORK_DATASET_ROOT"

# 可见验证集：框架拿它自评。缺就 blocked，不静默降级
# （没有它框架算不出分，b0/bT/AUP/UR 会掉回裁判序数兜底）。
if [[ ! -d "$ARC_VISIBLE_VALIDATION_ROOT/data" || ! -d "$ARC_SCORING_ROOT/data" ]]; then
  write_state "blocked" "Missing ARC visible-validation/scoring split under $DATASET_ROOT; regenerate with automation/scripts/make_arc_wbe_2026_visible_validation.py" 28
  exit 28
fi
cp -R "$ARC_VISIBLE_VALIDATION_ROOT" "$FRAMEWORK_DATASET_ROOT/visible-validation"

python3 "$ROOT/automation/scripts/generate_arc_wbe_2026_native_inputs.py" \
  --output-root "$INPUT_ROOT" \
  --dataset-root /data/arc_wbe_2026 \
  --contract-file "$CONTRACT_FILE" \
  --provider-base-url "$FRAMEWORK_PROVIDER_BASE_URL" \
  --primary-model "$FRAMEWORK_MODEL_RAW" >/dev/null

real_eval_rsync_repo "$SRC" "$REPO"
real_eval_purge_cross_topic_residue "$REPO" "arc_wbe_2026"
rm -rf "$REPO/research_agent/terminal_tmp" "$REPO/research_agent/workplace_paper" \
  "$REPO/research_agent/workplace" "$REPO/research_agent/logs" \
  "$REPO/benchmark/final/reasoning"
find "$REPO" -type d -name __pycache__ -prune -exec rm -rf {} +
# Copy contract tools into workspace for PYTHONPATH import
if [ -f "$ROOT/real_eval_contract_tools.py" ]; then
  cp "$ROOT/real_eval_contract_tools.py" "$REPO/real_eval_contract_tools.py"
fi
if ! real_eval_assert_no_cross_topic_residue "$REPO" "arc_wbe_2026"; then
  write_state "blocked" "Cross-topic residue remains in the AI-Researcher runtime snapshot" 27
  exit 27
fi
real_eval_provider_env_from_codex_toml "$PROVIDER_CONFIG" "$PROVIDER_ENV"
real_eval_semantic_env_from_usage_md "$SEMANTIC_SOURCE" "$SEMANTIC_ENV"
cp "$PROVIDER_CONFIG" "$CODEX_HOME_DIR/config.toml"
chmod 755 "$CODEX_HOME_DIR"
chmod 644 "$CODEX_HOME_DIR/config.toml"

mkdir -p \
  "$REPO/benchmark/final/arc_wbe_2026" \
  "$REPO/benchmark/process/dataset_candidate/arc_wbe_2026" \
  "$WORKSPACE/docs" \
  "$WORKSPACE/automation"
cp "$INPUT_ROOT/$TOPIC_INSTANCE_REL" "$REPO/benchmark/final/arc_wbe_2026/arc_wbe_2026.json"
cp "$INPUT_ROOT/$TOPIC_METAPROMPT_REL" "$REPO/benchmark/process/dataset_candidate/arc_wbe_2026/metaprompt.py"
cp "$INPUT_ROOT/$TOPIC_SUMMARY_REL" "$WORKSPACE/docs/arc_wbe_2026_summary.md"
cp "$INPUT_ROOT/$TOPIC_CONTRACT_REL" "$WORKSPACE/automation/arc_wbe_2026_contract.md"
cp "$INPUT_ROOT/$TOPIC_BUDGET_REL" "$WORKSPACE/automation/arc_wbe_2026_execution_budget.md"
mkdir -p "$WORKSPACE/automation/scripts"
cp "$INPUT_ROOT/automation/scripts/run_arc_wbe_2026_local_score.py" "$WORKSPACE/automation/scripts/"
cp "$INPUT_ROOT/automation/scripts/arc_wbe_2026_official_adapter.py" "$WORKSPACE/automation/scripts/"
cp "$INPUT_ROOT/automation/scripts/prepare_arc_wbe_2026_dataset.py" "$WORKSPACE/automation/scripts/"

python3 - "$REPO/research_agent/inno/environment/utils.py" <<'PY'
from pathlib import Path
import sys

p = Path(sys.argv[1])
s = p.read_text(encoding="utf-8")
old = '''def setup_dataset(category: str, local_workplace: str):
    # 构建目标路径
    dataset_candidate_path = os.path.join(local_workplace, "dataset_candidate")
    
    # 检查目标目录是否存在
    if os.path.exists(dataset_candidate_path):
        print("dataset_candidate exists")
        return
    
    # 检查源目录是否存在
    source_path = f"../benchmark/process/dataset_candidate/{category}"
    if not os.path.exists(source_path):
        raise Exception(f"source path {source_path} not exists")
    
    try:
        # 复制整个目录内容到 dataset_candidate
        shutil.copytree(source_path, dataset_candidate_path)
        print(f"copy {source_path} to {dataset_candidate_path} success")
    except Exception as e:
        raise Exception(f"copy {source_path} to {dataset_candidate_path} failed: {str(e)}")
'''
new = '''def setup_dataset(category: str, local_workplace: str):
    dataset_candidate_path = os.path.join(local_workplace, "dataset_candidate")
    if os.path.exists(dataset_candidate_path):
        print("dataset_candidate exists")
        return

    repo_root = Path(__file__).resolve().parents[3]
    source_path = repo_root / "benchmark" / "process" / "dataset_candidate" / category
    if not source_path.exists():
        raise Exception(f"source path {source_path} not exists")

    if category == "arc_wbe_2026":
        real_dataset = os.getenv("RESEARCHCLAWEVAL_TOPIC_DATASET_ROOT")
        if not real_dataset or not os.path.isdir(real_dataset):
            raise Exception(f"ARC dataset root not available: {real_dataset}")
        try:
            os.makedirs(dataset_candidate_path, exist_ok=True)
            shutil.copy2(source_path / "metaprompt.py", os.path.join(dataset_candidate_path, "metaprompt.py"))
            copied_dataset = os.path.join(dataset_candidate_path, "arc_wbe_2026")
            shutil.copytree(real_dataset, copied_dataset)
            project_dir = os.path.join(local_workplace, "project")
            target = os.path.join(project_dir, "data", "arc_wbe_2026")
            os.makedirs(os.path.dirname(target), exist_ok=True)
            if not os.path.exists(target):
                shutil.copytree(real_dataset, target)
            print(f"copy ARC dataset {real_dataset} to {dataset_candidate_path} success")
            return
        except Exception as e:
            raise Exception(f"copy ARC dataset to {dataset_candidate_path} failed: {str(e)}")

    try:
        shutil.copytree(source_path, dataset_candidate_path)
        print(f"copy {source_path} to {dataset_candidate_path} success")
    except Exception as e:
        raise Exception(f"copy {source_path} to {dataset_candidate_path} failed: {str(e)}")
'''
if old not in s:
    raise SystemExit("setup_dataset block not found")
patched = s.replace(old, new)
if "from pathlib import Path" not in patched:
    patched = "from pathlib import Path\n" + patched
p.write_text(patched, encoding="utf-8")
PY

python3 - "$REPO/research_agent/inno/tools/__init__.py" "$REPO/research_agent/constant.py" "$REPO/research_agent/inno/environment/markdown_browser/mdconvert.py" "$REPO/research_agent/inno/environment/markdown_browser/requests_markdown_browser.py" "$REPO/research_agent/run_infer_idea.py" <<'PY'
from pathlib import Path
import sys

tools = Path(sys.argv[1])
text = tools.read_text(encoding="utf-8")
old = "import_tools_recursively(current_dir, 'inno.tools')"
new = '''for module_name in (
    "terminal_tools",
    "inner",
    "inno_tools.planning_tools",
    "inno_tools.web_tools",
):
    importlib.import_module(f"research_agent.inno.tools.{module_name}")'''
if old not in text:
    print("SKIP: tool registration insertion point not found")
text = text.replace(old, new)
tools.write_text(text, encoding="utf-8")
constants = Path(sys.argv[2])
text = constants.read_text(encoding="utf-8")
if "PLATFORM =" not in text:
    constants.write_text(text + "\nPLATFORM = 'linux/amd64'\n", encoding="utf-8")
mdconvert = Path(sys.argv[3])
text = mdconvert.read_text(encoding="utf-8")
import re
m = re.search(r'^(\s*)(from docling\.document_converter import DocumentConverter as DocLingDocumentConverter)', text, re.MULTILINE)
if m:
    ind = m.group(1)
    old = m.group(0)
    new = f"""{ind}try:
{ind}    from docling.document_converter import DocumentConverter as DocLingDocumentConverter
{ind}except ModuleNotFoundError:
{ind}    class DocLingDocumentConverter:
{ind}        def convert(self, *_args, **_kwargs):
{ind}            raise RuntimeError("docling is unavailable in this runtime")
"""
    mdconvert.write_text(text.replace(old, new, 1), encoding="utf-8")
browser = Path(sys.argv[4])
text = browser.read_text(encoding="utf-8")
old = "        self._memory = PaperMemory(project_path=\"./paper_db\", db_name=\".paper_memory_\" + platform, platform=platform, api_key=os.getenv(\"OPENAI_API_KEY\"), embedding_model='text-embedding-3-small')"
new = '''        class _ArcNoopPaperMemory:
            def count(self, *_args, **_kwargs):
                return 1
            def add_paper_content(self, *_args, **_kwargs):
                return None
            def query_paper_content(self, *_args, **_kwargs):
                return []
        self._memory = _ArcNoopPaperMemory()'''
if old not in text:
    print("SKIP: PaperMemory initialization insertion point not found")
browser.write_text(text.replace(old, new, 1), encoding="utf-8")
entrypoint = Path(sys.argv[5])
text = entrypoint.read_text(encoding="utf-8")
old = "    main(args)"
new = "    main(args, references=\"\")"
if old not in text:
    # Already patched, skip
    pass
text = text.replace(old, new, 1)
old = '        github_result = self.git_search({"metadata": metadata})'
new = '        github_result = "" if category == "arc_wbe_2026" else self.git_search({"metadata": metadata})'
if old not in text:
    print("SKIP: AI-Researcher GitHub-search insertion point not found")
entrypoint.write_text(text.replace(old, new, 1), encoding="utf-8")
PY

python3 - "$REPO/research_agent/inno/tools/terminal_tools.py" <<'PY'
from pathlib import Path
import sys

p = Path(sys.argv[1])
s = p.read_text(encoding="utf-8")
old = 'command = f"tree {directory}"'
new = 'command = f"find {directory} -type f -o -type d 2>/dev/null | head -200"'
if old not in s:
    print("SKIP: gen_code_tree_structure tree command not found")
s = s.replace(old, new, 1)
p.write_text(s, encoding="utf-8")
PY

python3 - "$REPO/research_agent/inno/environment/docker_env.py" <<'PY'
from pathlib import Path
import sys

p = Path(sys.argv[1])
s = p.read_text(encoding="utf-8")
old = '''        gpu_cmd = ["--gpus", GPUS] if GPUS else []
        docker_command = [
            "docker", "run", "-d", "--platform", PLATFORM, "--userns=host",] + gpu_cmd + ["--name", self.container_name, 
            "--user", "root", "-v", f"{self.local_workplace}:{self.docker_workplace}",
            "-w", f"{self.docker_workplace}", "-p", f"{self.communication_port}:8000", 
            "--restart", "unless-stopped", BASE_IMAGES
        ]'''
new = '''        gpu_cmd = ["--gpus", GPUS] if GPUS else []
        extra_mounts = []
        host_repo = os.getenv("RESEARCHCLAWEVAL_AI_RESEARCHER_HOST_REPO", "")
        local_workplace = self.local_workplace
        if host_repo and local_workplace.startswith("/workspace/AI-Researcher/"):
            local_workplace = os.path.join(host_repo, local_workplace.removeprefix("/workspace/AI-Researcher/"))
        host_dataset = os.getenv("RESEARCHCLAWEVAL_TOPIC_HOST_DATASET_ROOT", "")
        if host_dataset:
            extra_mounts.extend(["-v", f"{host_dataset}:/data/arc_wbe_2026:ro"])
        host_contract = os.getenv("RESEARCHCLAWEVAL_TOPIC_HOST_CONTRACT_FILE", "")
        if host_contract:
            extra_mounts.extend(["-v", f"{host_contract}:/input/contract.md:ro"])
        docker_command = [
            "docker", "run", "-d", "--platform", PLATFORM, "--userns=host",] + gpu_cmd + ["--name", self.container_name,
            "--user", "root", "-v", f"{local_workplace}:{self.docker_workplace}",
        ] + extra_mounts + [
            "-w", f"{self.docker_workplace}", "-p", f"{self.communication_port}:8000",
            "--restart", "unless-stopped", BASE_IMAGES
        ]'''
if old not in s:
    raise SystemExit("docker_command block not found")
s = s.replace(old, new)
s = s.replace(
    "assert port_info and (port_info[0] == port_info[1])",
    "assert port_info",
)
s = s.replace(
    "hostname = 'localhost'",
    "hostname = os.getenv('RESEARCHCLAWEVAL_DOCKER_HOST', 'localhost')",
)
p.write_text(s, encoding="utf-8")
PY

RUNTIME_COMMAND=$(cat <<EOF
set -euo pipefail
echo "AI_RESEARCHER_NATIVE_INFER_IDEA"
cd /workspace/AI-Researcher/research_agent
PORT=\$(python - <<'PY'
import socket
s = socket.socket()
s.bind(('127.0.0.1', 0))
print(s.getsockname()[1])
s.close()
PY
)
python run_infer_idea.py \
  --instance_path ../benchmark/final/arc_wbe_2026/arc_wbe_2026.json \
  --container_name ${INNER_CONTAINER_NAME} \
  --model $AI_RESEARCHER_COMPLETION_MODEL \
  --workplace_name workplace \
  --cache_path cache_${RUN_ID} \
  --port "\$PORT" \
  --max_iter_times 0 \
  --category arc_wbe_2026
EOF
)

python3 - "$MANIFEST_FILE" "$SRC" "$REPO" "$DATASET_ROOT" "$CONTRACT_FILE" "$OUTER_IMAGE" "$RUNTIME_COMMAND" "$FRAMEWORK_MODEL_RAW" "$FRAMEWORK_PROVIDER_BASE_URL" <<'PY'
from pathlib import Path
import json
import sys

payload = {
    "framework": "AI-Researcher",
    "slug": "01_ai_researcher_arc_wbe_2026_fullrun",
    "source_root": sys.argv[2],
    "workspace_repo": sys.argv[3],
    "dataset_root": sys.argv[4],
    "contract_file": sys.argv[5],
    "runtime_image": sys.argv[6],
    "runtime_command": sys.argv[7],
    "entry_instance": "benchmark/final/arc_wbe_2026/arc_wbe_2026.json",
    "entry_metaprompt": "benchmark/process/dataset_candidate/arc_wbe_2026/metaprompt.py",
    "execution_mode": "framework_native",
    "native_standard_version": "1.0",
    "framework_orchestration": True,
    "native_entrypoint": "research_agent/run_infer_idea.py",
    "kimi_injection": "COMPLETION_MODEL/CHEEP_MODEL with OPENAI_BASE_URL from the injected provider environment",
    "native_log_marker": "AI_RESEARCHER_NATIVE_INFER_IDEA",
    "executor_kind": "framework_cli",
    "evaluation_model": sys.argv[8],
    "provider_base_url": sys.argv[9],
    "result_fields": ["score", "score_source", "score_artifact", "submission_artifact"],
}
Path(sys.argv[1]).write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
PY

{
  echo "[$(date -Is)] framework=AI-Researcher slug=01_ai_researcher_arc_wbe_2026_fullrun"
  echo "dataset_root=$DATASET_ROOT"
  echo "contract_file=$CONTRACT_FILE"
  echo "workspace_repo=$REPO"
  echo "entry_instance=benchmark/final/arc_wbe_2026/arc_wbe_2026.json"
  echo "entry_metaprompt=benchmark/process/dataset_candidate/arc_wbe_2026/metaprompt.py"
  echo "runtime_image=$OUTER_IMAGE"
  echo "native_entrypoint=research_agent/run_infer_idea.py"
  echo "provider_injection=COMPLETION_MODEL/CHEEP_MODEL with OPENAI_BASE_URL from injected environment"
  echo "native_log_marker=AI_RESEARCHER_NATIVE_INFER_IDEA"
  echo "e2e_command=python run_infer_idea.py --category arc_wbe_2026"
} | tee "$LOG_FILE"

write_state "running" "Launching AI-Researcher ARC native execution" "0" "python run_infer_idea.py --category arc_wbe_2026"

run_rc=0
set +e
timeout -k 30s "${AI_RESEARCHER_ARC_TIMEOUT_SECONDS:-7200}s" docker run --rm \
  --name "$OUTER_CONTAINER_NAME" \
  --add-host=host.docker.internal:host-gateway \
  --ipc=host \
  --ulimit memlock=-1 \
  --ulimit stack=67108864 \
  -v /var/run/docker.sock:/var/run/docker.sock \
  -v "$WORKSPACE":/workspace \
  -v "$CODEX_HOME_DIR":/codex-home \
  -v "$FRAMEWORK_DATASET_ROOT":/data/arc_wbe_2026:ro \
  -v "$CONTRACT_FILE":/input/contract.md:ro \
  --env-file "$PROVIDER_ENV" \
  --env-file "$SEMANTIC_ENV" \
  -e HOME=/codex-home \
  -e CODEX_HOME=/codex-home \
  -e COMPLETION_MODEL=$AI_RESEARCHER_COMPLETION_MODEL \
  -e CHEEP_MODEL=$AI_RESEARCHER_CHEAP_MODEL \
  -e BASE_IMAGES=ai-researcher-exec:runtime-ready \
  -e GPUS= \
  -e PYTHONPATH=/workspace/AI-Researcher \
  -e RESEARCHCLAWEVAL_AI_RESEARCHER_HOST_REPO="$REPO" \
  -e RESEARCHCLAWEVAL_DOCKER_HOST=host.docker.internal \
  -e RESEARCHCLAWEVAL_TOPIC_HOST_DATASET_ROOT="$FRAMEWORK_DATASET_ROOT" \
  -e RESEARCHCLAWEVAL_TOPIC_HOST_CONTRACT_FILE="$CONTRACT_FILE" \
  -e RESEARCHCLAWEVAL_TOPIC_DATASET_ROOT=/data/arc_wbe_2026 \
  -w /workspace/AI-Researcher \
  "$OUTER_IMAGE" \
  bash -lc "$RUNTIME_COMMAND" 2>&1 | tee -a "$LOG_FILE"
run_rc=${PIPESTATUS[0]}
set -e

if [[ "$run_rc" -ne 0 ]]; then
  write_state "failed" "AI-Researcher ARC native execution exited non-zero; see log" "$run_rc" "python run_infer_idea.py --category arc_wbe_2026"
  exit "$run_rc"
fi

TRACE_ROOT="$REPO/research_agent/workplace"
if [[ ! -d "$TRACE_ROOT" ]]; then
  TRACE_ROOT="$(find "$REPO/research_agent" -type d \( -path '*/workplace/workplace' -o -name 'workplace' \) | head -n 1 || true)"
fi
[[ -d "$TRACE_ROOT" ]] || {
  write_state "blocked" "AI-Researcher exited successfully but did not leave the expected workplace trace root" 31 "python run_infer_idea.py --category arc_wbe_2026"
  exit 31
}

python3 - "$WORKSPACE" "${ARC_WBE_2026_MODEL:-$FRAMEWORK_MODEL_RAW}" "$FRAMEWORK_PROVIDER_BASE_URL" <<'PY'
from pathlib import Path
import json
import re
import sys

workspace = Path(sys.argv[1])
expected_model = sys.argv[2]
expected_base_url = sys.argv[3].rstrip("/")
required = ["research_idea.json", "estimator.py", "submission.json", "experiment_trace.json", "final_report.md"]
missing = [name for name in required if not (workspace / name).is_file() or not (workspace / name).stat().st_size]
if missing:
    raise SystemExit("AI-Researcher did not produce framework-native ARC artifacts before scoring: " + ", ".join(missing))

def load(name: str) -> dict:
    value = json.loads((workspace / name).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise SystemExit(f"{name} must be a JSON object")
    return value

trace = load("experiment_trace.json")
if trace.get("framework_native_execution") is not True or trace.get("consumed_topic_input") is not True:
    raise SystemExit("AI-Researcher trace does not prove native execution and Topic 3 input consumption")
if trace.get("workspace_trace_root") != "/workspace":
    raise SystemExit("AI-Researcher trace must set workspace_trace_root=/workspace")
experiments = trace.get("experiments")
if not isinstance(experiments, list) or not 2 <= len(experiments) <= 4:
    raise SystemExit("AI-Researcher trace must contain 2-4 experiments")
experiment_ids = []
for row in experiments:
    experiment_id = row.get("experiment_id") if isinstance(row, dict) else None
    if not isinstance(experiment_id, str) or not experiment_id.strip():
        raise SystemExit("AI-Researcher experiments must each have a non-empty experiment_id")
    experiment_ids.append(experiment_id.strip())
if len(set(experiment_ids)) != len(experiment_ids):
    raise SystemExit("AI-Researcher experiment_id values must be unique")
selected_id = trace.get("selected_experiment_id")
if not isinstance(selected_id, str) or selected_id.strip() not in experiment_ids:
    raise SystemExit("AI-Researcher selected_experiment_id must match an experiment record")
if trace.get("framework_internal_model") != expected_model:
    raise SystemExit("AI-Researcher trace does not prove the injected model")
actual_base_url = trace.get("framework_internal_api_base_url")
if not isinstance(actual_base_url, str) or actual_base_url.rstrip("/") != expected_base_url:
    raise SystemExit("AI-Researcher trace does not prove the injected API base URL")
if re.search(r"\$\{?[A-Z_][A-Z0-9_]*\}?", trace["framework_internal_model"] + actual_base_url):
    raise SystemExit("AI-Researcher trace contains an unexpanded provider placeholder")
if trace.get("idea_artifact") != "research_idea.json" or trace.get("idea_locked_before_experiments") is not True:
    raise SystemExit("AI-Researcher trace does not prove the idea was locked before experiments")

idea = load("research_idea.json")
def nonempty(value):
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, list):
        return bool(value) and all(isinstance(item, str) and item.strip() for item in value)
    return isinstance(value, dict) and bool(value)

for key in ("hypothesis", "method_rationale", "expected_failure_modes", "comparison_logic"):
    value = idea.get(key)
    if key == "method_rationale" and not nonempty(value):
        value = idea.get("rationale")
    if not nonempty(value):
        raise SystemExit(f"AI-Researcher research_idea.json lacks {key}")
PY

if ! "$WEIGHTS_ONLY_PYTHON" "$ROOT/automation/scripts/run_arc_wbe_2026_local_score.py" \
  --workspace "$WORKSPACE" \
  --output-score "$WORKSPACE/score.json" \
  --dataset-root "$ARC_SCORING_ROOT" \
  --framework-hint "$FRAMEWORK_NAME" \
  --whest-bin "$(dirname "$WEIGHTS_ONLY_PYTHON")/whest" >"$LOG_DIR/official_score.log" 2>&1; then
  write_state "failed" "Official ARC scorer failed closed; no fallback score was accepted" 43 "python run_infer_idea.py --category arc_wbe_2026"
  exit 43
fi

python3 - "$WORKSPACE" "$TRACE_ROOT" "${ARC_WBE_2026_MODEL:-$FRAMEWORK_MODEL_RAW}" <<'PY'
from pathlib import Path
import json
import sys

workspace = Path(sys.argv[1])
trace_root = Path(sys.argv[2])
expected_model = sys.argv[3]
required = ["research_idea.json", "estimator.py", "submission.json", "score.json", "experiment_trace.json", "final_report.md"]
missing = [name for name in required if not (workspace / name).is_file()]
if missing:
    raise SystemExit("AI-Researcher did not produce framework-native ARC handoff artifacts: " + ", ".join(missing))
trace = json.loads((workspace / "experiment_trace.json").read_text(encoding="utf-8"))
if trace.get("framework_internal_model") != expected_model or not trace.get("framework_internal_api_base_url"):
    raise SystemExit("AI-Researcher trace does not prove the injected model/base URL")
if trace.get("idea_artifact") != "research_idea.json" or trace.get("idea_locked_before_experiments") is not True:
    raise SystemExit("AI-Researcher trace does not prove the idea was locked before experiments")
score = json.loads((workspace / "score.json").read_text(encoding="utf-8"))
if score.get("score_source") != "official_adapter_whest_run":
    raise SystemExit("AI-Researcher score is not official_adapter_whest_run")
PY

python3 - "$MANIFEST_FILE" "$WORKSPACE" "$LOG_FILE" <<'PY'
from pathlib import Path
import json
import sys

manifest_path = Path(sys.argv[1])
workspace = Path(sys.argv[2])
log_file = sys.argv[3]
payload = json.loads(manifest_path.read_text(encoding="utf-8"))
payload.update(
    {
        "submission_artifact": str(workspace / "submission.json"),
        "final_report": str(workspace / "final_report.md"),
        "score_artifact": str(workspace / "score.json") if (workspace / "score.json").exists() else None,
        "workspace_trace_root": str(workspace / "AI-Researcher" / "research_agent" / "workplace"),
        "log": log_file,
    }
)
manifest_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
PY

write_state "finished" "AI-Researcher ARC workflow produced framework-native official score evidence." "0" "python run_infer_idea.py --category arc_wbe_2026"
