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
LOG_DIR="$BASE/logs"
LOG_FILE="$BASE/logs/e2e.log"
STATE_FILE="$BASE/state.json"
MANIFEST_FILE="$BASE/fullrun_manifest.json"
CODEX_HOME_DIR="$BASE/codex_home"
TOPIC_ROOT="${TOPIC2_DATASET_ROOT:-$(real_eval_resolve_topic_dataset "$ROOT" topic2)}"
CONTRACT_FILE="${TOPIC2_CONTRACT_FILE:-$ROOT/automation/topic2_contract.md}"
PROVIDER_CONFIG="${PROVIDER_CONFIG:-$ROOT/api/codex_gpt54_shubiaobiao.toml}"
PROVIDER_BASE_URL="$(sed -n 's/^[[:space:]]*base_url[[:space:]]*=[[:space:]]*"\(.*\)"[[:space:]]*$/\1/p' "$PROVIDER_CONFIG" | head -1)"
FRAMEWORK_PROVIDER_BASE_URL="${PROVIDER_BASE_URL%/}"
if [[ "$FRAMEWORK_PROVIDER_BASE_URL" != */v1 ]]; then FRAMEWORK_PROVIDER_BASE_URL="$FRAMEWORK_PROVIDER_BASE_URL/v1"; fi
SEMANTIC_SOURCE="${SEMANTIC_SOURCE:-$ROOT/api/_semantic_scholar_api_usage.md}"
PROVIDER_ENV="$BASE/provider.env"
SEMANTIC_ENV="$BASE/semantic.env"
OUTER_IMAGE="ai-researcher:runtime-ready"
OUTER_CONTAINER_NAME="ai_researcher_mc_outer_${RUN_ID}"
INNER_CONTAINER_NAME="mc_eval_${RUN_ID}"
TOPIC_INSTANCE_REL="AI-Researcher/benchmark/final/topic2/topic2.json"
TOPIC_METAPROMPT_REL="AI-Researcher/benchmark/process/dataset_candidate/topic2/metaprompt.py"
TOPIC_SUMMARY_REL="docs/topic2_summary.md"
TOPIC_CONTRACT_REL="automation/topic2_contract.md"
TOPIC_BUDGET_REL="automation/topic2_execution_budget.md"
MC_PYTHON="${TOPIC2_PYTHON:-$ROOT/.venvs/mountaincar/bin/python}"
AI_RESEARCHER_MC_GPUS="${AI_RESEARCHER_MC_GPUS:-all}"
AI_RESEARCHER_MC_GPU_POLICY="${AI_RESEARCHER_MC_GPU_POLICY:-require}"

cleanup_containers() { docker ps -a --format '{{.Names}}' | rg "^(${OUTER_CONTAINER_NAME}|${INNER_CONTAINER_NAME})$" | xargs -r docker rm -f >/dev/null 2>&1 || true; }
trap cleanup_containers EXIT

write_state() {
  local status="$1" summary="$2" exit_code="${3:-0}" command="${4:-}"
  python3 - "$STATE_FILE" "$status" "$summary" "$exit_code" "$command" <<'PY'
from datetime import datetime, timezone
from pathlib import Path
import json, sys
payload = {"project_id": "topic2", "phase": "fullrun", "status": sys.argv[2], "summary": sys.argv[3], "updated_at": datetime.now(timezone.utc).astimezone().isoformat(), "exit_code": int(sys.argv[4])}
if sys.argv[5]: payload["e2e_command"] = sys.argv[5]
Path(sys.argv[1]).write_text(json.dumps(payload, ensure_ascii=False) + "\n", encoding="utf-8")
PY
}

real_eval_require_clean_dir "$BASE"
mkdir -p "$WORKSPACE" "$INPUT_ROOT" "$LOG_DIR" "$CODEX_HOME_DIR"
[[ -d "$TOPIC_ROOT" ]] || { echo "missing topic root: $TOPIC_ROOT" >&2; exit 21; }
[[ -f "$CONTRACT_FILE" ]] || { echo "missing contract file: $CONTRACT_FILE" >&2; exit 22; }
[[ -d "$SRC" ]] || { echo "missing framework source: $SRC" >&2; exit 23; }
write_state "starting" "Preparing AI-Researcher MountainCar fullrun workspace"

python3 "$ROOT/automation/scripts/generate_topic2_native_inputs.py" \
  --output-root "$INPUT_ROOT" --dataset-root "$TOPIC_ROOT" --contract-file "$CONTRACT_FILE" \
  --provider-base-url "$FRAMEWORK_PROVIDER_BASE_URL" --primary-model "$FRAMEWORK_MODEL_RAW" >/dev/null

real_eval_rsync_repo "$SRC" "$REPO"
real_eval_purge_cross_topic_residue "$REPO" "topic2"
rm -rf "$REPO/research_agent/terminal_tmp" "$REPO/research_agent/workplace_paper" \
  "$REPO/research_agent/workplace" "$REPO/research_agent/logs" "$REPO/benchmark/final/reasoning"
find "$REPO" -type d -name __pycache__ -prune -exec rm -rf {} +
[ -f "$ROOT/real_eval_contract_tools.py" ] && cp "$ROOT/real_eval_contract_tools.py" "$REPO/real_eval_contract_tools.py"
real_eval_assert_no_cross_topic_residue "$REPO" "topic2" || { write_state "blocked" "Cross-topic residue" 27; exit 27; }
real_eval_provider_env_from_codex_toml "$PROVIDER_CONFIG" "$PROVIDER_ENV"
real_eval_semantic_env_from_usage_md "$SEMANTIC_SOURCE" "$SEMANTIC_ENV"
cp "$PROVIDER_CONFIG" "$CODEX_HOME_DIR/config.toml"; chmod 755 "$CODEX_HOME_DIR"; chmod 644 "$CODEX_HOME_DIR/config.toml"

cp -r "$TOPIC_ROOT/src/." "$WORKSPACE/src/"
cp "$TOPIC_ROOT/protected/evaluate.py" "$WORKSPACE/evaluate.py"; chmod 444 "$WORKSPACE/evaluate.py"
mkdir -p "$WORKSPACE/checkpoints"
mkdir -p "$REPO/benchmark/final/topic2" "$REPO/benchmark/process/dataset_candidate/topic2" "$WORKSPACE/docs" "$WORKSPACE/automation"
cp "$INPUT_ROOT/$TOPIC_INSTANCE_REL" "$REPO/benchmark/final/topic2/topic2.json"
cp "$INPUT_ROOT/$TOPIC_METAPROMPT_REL" "$REPO/benchmark/process/dataset_candidate/topic2/metaprompt.py"
cp "$INPUT_ROOT/$TOPIC_SUMMARY_REL" "$WORKSPACE/docs/topic2_summary.md"
cp "$INPUT_ROOT/$TOPIC_CONTRACT_REL" "$WORKSPACE/automation/topic2_contract.md"
cp "$INPUT_ROOT/$TOPIC_BUDGET_REL" "$WORKSPACE/automation/topic2_execution_budget.md"
mkdir -p "$WORKSPACE/automation/scripts"
cp "$INPUT_ROOT/automation/scripts/run_topic2_host_score.py" "$WORKSPACE/automation/scripts/"

# setup_dataset patch
python3 - "$REPO/research_agent/inno/environment/utils.py" <<'PY'
from pathlib import Path; import sys, os
p = Path(sys.argv[1]); s = p.read_text(encoding="utf-8")
old = '''source_path = f"../benchmark/process/dataset_candidate/{category}"'''
new = '''repo_root = Path(__file__).resolve().parents[3]
    source_path = repo_root / "benchmark" / "process" / "dataset_candidate" / category'''
if old not in s: raise SystemExit("setup_dataset old not found")
s = s.replace(old, new)
mc_hook = '''if category == "topic2":
            src_dir = os.path.join(local_workplace, "src")
            os.makedirs(src_dir, exist_ok=True)
            shutil.copytree("/workspace/src", src_dir, dirs_exist_ok=True)
            shutil.copy2("/workspace/evaluate.py", os.path.join(local_workplace, "evaluate.py"))
            print(f"copy MountainCar starter code to {local_workplace} success")
            return'''
s = s.replace("shutil.copytree(source_path, dataset_candidate_path)", mc_hook + "\n        shutil.copytree(source_path, dataset_candidate_path)")
if "from pathlib import Path" not in s: s = "from pathlib import Path\n" + s
p.write_text(s, encoding="utf-8")
PY

# tool registration, PaperMemory, entrypoint patches
python3 - "$REPO/research_agent/inno/tools/__init__.py" "$REPO/research_agent/constant.py" "$REPO/research_agent/run_infer_idea.py" <<'PY'
from pathlib import Path; import sys, re
tools = Path(sys.argv[1]); t = tools.read_text(encoding="utf-8")
t = t.replace("import_tools_recursively(current_dir, 'inno.tools')", '''for mn in ("terminal_tools","inner","inno_tools.planning_tools","inno_tools.web_tools"): importlib.import_module(f"research_agent.inno.tools.{mn}")''')
tools.write_text(t, encoding="utf-8")
const = Path(sys.argv[2]); t = const.read_text(encoding="utf-8")
if "PLATFORM =" not in t: const.write_text(t + "\nPLATFORM = 'linux/amd64'\n", encoding="utf-8")
ep = Path(sys.argv[3]); t = ep.read_text(encoding="utf-8")
t = t.replace("def main(args):", 'def main(args, references=""):')
t = t.replace("def main(args, references):", 'def main(args, references=""):')
t = t.replace('github_result = self.git_search({"metadata": metadata})', 'github_result = "" if category == "topic2" else self.git_search({"metadata": metadata})')
ep.write_text(t, encoding="utf-8")
PY


# Patch BrowserEnv to skip browser initialization (no playwright browser available)
python3 - "$REPO/research_agent/inno/environment/browser_env.py" <<'PY'
from pathlib import Path; import sys
p = Path(sys.argv[1])
s = p.read_text(encoding="utf-8")
# Patch __init__ to skip self.init_browser() call
old = '''        self.init_browser()
        
        atexit.register(self.close)'''
new = '''        self.browser_ready = False
        self.browser = None
        debug_print(True, "BrowserEnv: browser initialization skipped (topic2 mode)", title = "Browser Env", log_path=self.log_path)
        
        atexit.register(self.close)'''
if old not in s: raise SystemExit("BrowserEnv init_browser call not found")
s = s.replace(old, new)
# Patch init_browser to be a no-op
old2 = '''    @tenacity.retry(
        wait=tenacity.wait_fixed(1),
        stop=tenacity.stop_after_attempt(5) | stop_if_should_exit(),
        retry=tenacity.retry_if_exception_type(BrowserInitException),
    )
    def init_browser(self):
        debug_print(True, "Starting browser env...", title = "Browser Env", log_path=self.log_path)
        try:
            self.process = multiprocessing.Process(target=self.browser_process)
            self.process.start()
        except Exception as e:
            debug_print(True, f'Failed to start browser process: {e}', title = "Browser Env", log_path=self.log_path)
            raise

        if not self.check_alive():
            self.close()
            raise BrowserInitException('Failed to start browser environment.')'''
new2 = '''    def init_browser(self):
        """Browser initialization skipped for topic2."""
        self.browser_ready = False
        debug_print(True, "BrowserEnv: browser initialization skipped (topic2 mode)", title = "Browser Env", log_path=self.log_path)'''
if old2 not in s: raise SystemExit("BrowserEnv init_browser not found")
s = s.replace(old2, new2)
p.write_text(s, encoding="utf-8")
PY

# Patch run_infer_idea.py to handle BrowserEnv failure gracefully
python3 - "$REPO/research_agent/run_infer_idea.py" <<'PY'
from pathlib import Path; import sys
p = Path(sys.argv[1])
s = p.read_text(encoding="utf-8")
old = '''    web_env = BrowserEnv(browsergym_eval_env = None, local_root=env_config.local_root, workplace_name=env_config.workplace_name)'''
new = '''    try:
        web_env = BrowserEnv(browsergym_eval_env = None, local_root=env_config.local_root, workplace_name=env_config.workplace_name)
    except Exception:
        print("BrowserEnv initialization skipped (browser not available)")
        web_env = None'''
if old not in s: raise SystemExit("BrowserEnv init pattern not found")
s = s.replace(old, new)
p.write_text(s, encoding="utf-8")
PY

# tree command patch
python3 - "$REPO/research_agent/inno/tools/terminal_tools.py" <<'PY'
from pathlib import Path; import sys
p = Path(sys.argv[1]); s = p.read_text(encoding="utf-8")
s = s.replace('command = f"tree {directory}"', 'command = f"find {directory} -type f -o -type d 2>/dev/null | head -200"')
p.write_text(s, encoding="utf-8")
PY

# Make logger tolerant to malformed tool-call argument JSON emitted by the DeepSeek relay.
python3 - "$REPO/research_agent/inno/logger.py" <<'PY'
from pathlib import Path; import sys
p = Path(sys.argv[1]); s = p.read_text(encoding="utf-8")
old = '''    def _warp_args(self, args_dict: str):
        args_dict = json.loads(args_dict)
        args_str = ''
        for k, v in args_dict.items():
            args_str += f"{repr(k)}={repr(v)}, "
        return args_str[:-2]'''
new = '''    def _warp_args(self, args_dict: str):
        try:
            parsed = json.loads(args_dict)
        except Exception:
            return str(args_dict)
        args_str = ''
        for k, v in parsed.items():
            args_str += f"{repr(k)}={repr(v)}, "
        return args_str[:-2] if args_str else str(args_dict)'''
if old not in s:
    raise SystemExit("AI-Researcher logger _warp_args pattern not found")
s = s.replace(old, new)
p.write_text(s, encoding="utf-8")
PY

# Patch RequestsMarkdownBrowser PaperMemory platform so topic2 import does not
# try to download the default sentence-transformers embedding model.
python3 - "$REPO/research_agent/inno/environment/markdown_browser/requests_markdown_browser.py" <<'PY'
from pathlib import Path; import sys
p = Path(sys.argv[1]); s = p.read_text(encoding="utf-8")
needle = "        platform = 'default'\n"
if needle not in s:
    raise SystemExit("RequestsMarkdownBrowser platform insertion point not found")
s = s.replace(needle, "        platform = 'OpenAI'\n", 1)
p.write_text(s, encoding="utf-8")
PY

# docker_env.py patch: mount starter code, use JAX executor
python3 - "$REPO/research_agent/inno/environment/docker_env.py" <<'PY'
from pathlib import Path; import sys, os
p = Path(sys.argv[1]); s = p.read_text(encoding="utf-8")
old = '''        gpu_cmd = ["--gpus", GPUS] if GPUS else []
        docker_command = [
            "docker", "run", "-d", "--platform", PLATFORM, "--userns=host",] + gpu_cmd + ["--name", self.container_name,'''
new = '''        gpu_cmd = ["--gpus", GPUS] if GPUS else []
        extra_mounts = []
        host_repo = os.getenv('RESEARCHCLAWEVAL_AI_RESEARCHER_HOST_REPO', '')
        local_workplace = self.local_workplace
        if host_repo and local_workplace.startswith('/workspace/AI-Researcher/'):
            local_workplace = os.path.join(host_repo, local_workplace.removeprefix('/workspace/AI-Researcher/'))
        host_starter = os.getenv('RESEARCHCLAWEVAL_TOPIC_HOST_STARTER_ROOT', '')
        if host_starter:
            extra_mounts.extend(['-v', f'{host_starter}/src:/workspace/src:ro'])
        docker_command = [
            "docker", "run", "-d", "--platform", PLATFORM, "--userns=host",] + gpu_cmd + ["--name", self.container_name,'''
if old not in s: raise SystemExit("docker_command pattern not found")
s = s.replace(old, new)
s = s.replace('] + gpu_cmd + ["--name",', '] + extra_mounts + gpu_cmd + ["--name",')
s = s.replace("assert port_info and (port_info[0] == port_info[1])", "assert port_info")
s = s.replace("hostname = 'localhost'", "hostname = os.getenv('RESEARCHCLAWEVAL_DOCKER_HOST', 'localhost')")
p.write_text(s, encoding="utf-8")
PY

RUNTIME_COMMAND=$(cat <<EOF
set -euo pipefail
echo "AI_RESEARCHER_NATIVE_INFER_IDEA"
cd /workspace/AI-Researcher/research_agent
PORT=$(python3 - <<'INNERPY'
import socket; s=socket.socket(); s.bind(('127.0.0.1',0)); print(s.getsockname()[1]); s.close()
INNERPY
)
timeout "${AI_RESEARCHER_MC_TIMEOUT_SECONDS:-7200}s" python run_infer_idea.py --instance_path ../benchmark/final/topic2/topic2.json \
  --container_name ${INNER_CONTAINER_NAME} --model $AI_RESEARCHER_COMPLETION_MODEL \
  --workplace_name workplace --cache_path cache_${RUN_ID} --port "\$PORT" \
  --max_iter_times 0 --category topic2
EOF
)

python3 - "$MANIFEST_FILE" "$SRC" "$REPO" "$TOPIC_ROOT" "$CONTRACT_FILE" "$OUTER_IMAGE" "$RUNTIME_COMMAND" "$FRAMEWORK_MODEL_RAW" "$FRAMEWORK_PROVIDER_BASE_URL" <<'PY'
from pathlib import Path; import json, sys
payload = {"framework": "AI-Researcher", "slug": "01_ai_researcher_topic2_fullrun", "source_root": sys.argv[2], "workspace_repo": sys.argv[3], "topic_root": sys.argv[4], "contract_file": sys.argv[5], "runtime_image": sys.argv[6], "runtime_command": sys.argv[7], "entry_instance": "benchmark/final/topic2/topic2.json", "entry_metaprompt": "benchmark/process/dataset_candidate/topic2/metaprompt.py", "execution_mode": "framework_native", "native_standard_version": "1.0", "framework_orchestration": True, "native_entrypoint": "research_agent/run_infer_idea.py", "kimi_injection": "COMPLETION_MODEL/CHEEP_MODEL with OPENAI_BASE_URL from injected provider", "native_log_marker": "AI_RESEARCHER_NATIVE_INFER_IDEA", "executor_kind": "framework_cli", "evaluation_model": sys.argv[8], "provider_base_url": sys.argv[9], "result_fields": ["score","reward_std","score_source","score_artifact","checkpoint_count"]}
Path(sys.argv[1]).write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
PY

{ echo "[$(date -Is)] framework=AI-Researcher slug=01_ai_researcher_topic2_fullrun"; echo "topic_root=$TOPIC_ROOT"; echo "contract_file=$CONTRACT_FILE"; echo "runtime_image=$OUTER_IMAGE"; echo "native_entrypoint=research_agent/run_infer_idea.py"; echo "native_log_marker=AI_RESEARCHER_NATIVE_INFER_IDEA"; echo "e2e_command=python run_infer_idea.py --category topic2"; } | tee "$LOG_FILE"

write_state "running" "Launching AI-Researcher MountainCar native execution" "0" "python run_infer_idea.py --category topic2"

AI_RESEARCHER_MC_NESTED_GPUS="$AI_RESEARCHER_MC_GPUS"
if [[ "$AI_RESEARCHER_MC_GPU_POLICY" == "off" ]]; then AI_RESEARCHER_MC_NESTED_GPUS=""; fi

run_rc=0; set +e
if [[ "$AI_RESEARCHER_MC_GPU_POLICY" == "require" ]]; then
  echo "GPU policy=require: probing ai-researcher-exec:mountaincar-jax with --gpus ${AI_RESEARCHER_MC_GPUS}" | tee -a "$LOG_FILE"
  docker run --rm --gpus "$AI_RESEARCHER_MC_GPUS" ai-researcher-exec:mountaincar-jax \
    bash -lc 'nvidia-smi -L && python -c "import jax; ds=jax.devices(); print(ds); assert any(d.platform==\"gpu\" for d in ds), \"JAX cannot see any CUDA device\""' 2>&1 | tee -a "$LOG_FILE"
  gpu_probe_rc=${PIPESTATUS[0]}
  if [[ "$gpu_probe_rc" -ne 0 ]]; then
    write_state "blocked" "GPU policy=require but ai-researcher-exec:mountaincar-jax could not see a GPU" "$gpu_probe_rc" "python run_infer_idea.py --category topic2"
    exit "$gpu_probe_rc"
  fi
elif [[ "$AI_RESEARCHER_MC_GPU_POLICY" == "auto" ]]; then
  echo "GPU policy=auto: nested executors will use --gpus ${AI_RESEARCHER_MC_GPUS} when available" | tee -a "$LOG_FILE"
else
  echo "GPU policy=off: nested executors will run on CPU" | tee -a "$LOG_FILE"
fi
docker run --rm --init --name "$OUTER_CONTAINER_NAME" \
  --add-host=host.docker.internal:host-gateway --ipc=host --ulimit memlock=-1 --ulimit stack=67108864 \
  -v /var/run/docker.sock:/var/run/docker.sock -v "$WORKSPACE":/workspace -v "$CODEX_HOME_DIR":/codex-home \
  -v "$TOPIC_ROOT":/data/topic2:ro -v "$CONTRACT_FILE":/input/contract.md:ro \
  --env-file "$PROVIDER_ENV" --env-file "$SEMANTIC_ENV" \
  -e HOME=/codex-home -e CODEX_HOME=/codex-home \
  -e COMPLETION_MODEL=$AI_RESEARCHER_COMPLETION_MODEL -e CHEEP_MODEL=$AI_RESEARCHER_CHEAP_MODEL \
  -e BASE_IMAGES=ai-researcher-exec:mountaincar-jax -e GPUS="$AI_RESEARCHER_MC_NESTED_GPUS" -e PYTHONPATH=/workspace/AI-Researcher \
  -e AI_RESEARCHER_MC_GPUS="$AI_RESEARCHER_MC_GPUS" -e AI_RESEARCHER_MC_GPU_POLICY="$AI_RESEARCHER_MC_GPU_POLICY" \
  -e RESEARCHCLAWEVAL_AI_RESEARCHER_HOST_REPO="$REPO" -e RESEARCHCLAWEVAL_DOCKER_HOST=host.docker.internal \
  -e RESEARCHCLAWEVAL_TOPIC_HOST_STARTER_ROOT="$WORKSPACE" -e RESEARCHCLAWEVAL_TOPIC_DATASET_ROOT=/data/topic2 \
  -w /workspace/AI-Researcher "$OUTER_IMAGE" bash -lc "$RUNTIME_COMMAND" 2>&1 | tee -a "$LOG_FILE"
run_rc=${PIPESTATUS[0]}; set -e

if [[ "$run_rc" -ne 0 ]]; then write_state "failed" "AI-Researcher MountainCar exited non-zero; see log" "$run_rc" "python run_infer_idea.py --category topic2"; exit "$run_rc"; fi

python3 - "$WORKSPACE" "${TOPIC2_MODEL:-$FRAMEWORK_MODEL_RAW}" "$FRAMEWORK_PROVIDER_BASE_URL" <<'PY'
from pathlib import Path; import json, sys
w = Path(sys.argv[1]); m = sys.argv[2]; u = sys.argv[3].rstrip("/")
req = ["research_idea.json","experiment_trace.json","final_report.md","evaluate.py"]
miss = [n for n in req if not (w/n).is_file() or not (w/n).stat().st_size]
if miss: raise SystemExit("missing artifacts: "+", ".join(miss))
if not (w/"src"/"config.yaml").is_file(): raise SystemExit("missing src/config.yaml")
ck = sorted((w/"checkpoints").glob("*.pkl")) if (w/"checkpoints").is_dir() else []
if len(ck) != 5: raise SystemExit(f"expected 5 checkpoints, found {len(ck)}")
tr = json.loads((w/"experiment_trace.json").read_text(encoding="utf-8"))
if tr.get("framework_native_execution") is not True: raise SystemExit("trace must prove native execution")
PY

if ! "$MC_PYTHON" "$ROOT/automation/scripts/run_topic2_host_score.py" --workspace "$WORKSPACE" --output-score "$WORKSPACE/score.json" --dataset-root "$TOPIC_ROOT" --python "$MC_PYTHON" --config-fname src/config.yaml >"$LOG_DIR/official_score.log" 2>&1; then
  write_state "failed" "Official scorer failed" 43 "python run_infer_idea.py --category topic2"; exit 43
fi

python3 - "$MANIFEST_FILE" "$WORKSPACE" "$LOG_FILE" <<'PY'
from pathlib import Path; import json, sys
mp = Path(sys.argv[1]); ws = Path(sys.argv[2]); pl = json.loads(mp.read_text(encoding="utf-8"))
pl.update({"final_report": str(ws/"final_report.md"), "score_artifact": str(ws/"score.json") if (ws/"score.json").exists() else None, "workspace_trace_root": str(ws/"AI-Researcher"/"research_agent"/"workplace"), "log": sys.argv[3]})
mp.write_text(json.dumps(pl, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
PY

write_state "finished" "AI-Researcher MountainCar workflow produced framework-native score evidence." "0" "python run_infer_idea.py --category topic2"