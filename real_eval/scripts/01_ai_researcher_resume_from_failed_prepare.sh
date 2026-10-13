#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 3 ]]; then
  echo "usage: $0 <source_framework_dir> <resume_root> <resume_run_id>" >&2
  exit 2
fi

SOURCE_DIR="$1"
RESUME_ROOT="$2"
RESUME_RUN_ID="$3"
ROOT="${RESEARCHCLAWEVAL_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
WORKSPACE="$SOURCE_DIR/workspace"
RESEARCH_AGENT_DIR="$WORKSPACE/research_agent"
LOG_DIR="$RESUME_ROOT/logs"
LOG_FILE="$LOG_DIR/e2e.log"
STATE_FILE="$RESUME_ROOT/state.json"
PROMPT_LOG="$LOG_DIR/resume_wrapper.log"

mkdir -p "$RESUME_ROOT" "$LOG_DIR"

write_state() {
  local status="$1"
  local summary="$2"
  local exit_code="${3:-0}"
  python3 - "$STATE_FILE" "$RESUME_RUN_ID" "$status" "$summary" "$WORKSPACE" "$LOG_FILE" "$exit_code" <<'PY'
from pathlib import Path
import json
import sys
state = {
    "run_id": sys.argv[2],
    "framework": "AI-Researcher",
    "slug": "01_ai_researcher_resume_from_failed_prepare",
    "status": sys.argv[3],
    "summary": sys.argv[4],
    "workspace": sys.argv[5],
    "log": sys.argv[6],
    "exit_code": int(sys.argv[7]),
}
Path(sys.argv[1]).write_text(json.dumps(state, ensure_ascii=False) + "\n", encoding="utf-8")
PY
}

if [[ ! -d "$SOURCE_DIR" ]]; then
  write_state "blocked" "Missing source framework dir: $SOURCE_DIR" 21
  exit 21
fi
if [[ ! -d "$RESEARCH_AGENT_DIR" ]]; then
  write_state "blocked" "Missing research_agent workspace: $RESEARCH_AGENT_DIR" 22
  exit 22
fi
if [[ ! -f "$SOURCE_DIR/provider.env" ]]; then
  write_state "blocked" "Missing provider.env: $SOURCE_DIR/provider.env" 23
  exit 23
fi
if [[ ! -f "$SOURCE_DIR/semantic.env" ]]; then
  write_state "blocked" "Missing semantic.env: $SOURCE_DIR/semantic.env" 24
  exit 24
fi

write_state "starting" "Preparing AI-Researcher resume-from-failed-prepare run"

set -a
source "$SOURCE_DIR/provider.env"
source "$SOURCE_DIR/semantic.env"
set +a

export COMPLETION_MODEL="openai/gpt-5.4"
export AI_RESEARCHER_CHEAP_MODEL="${AI_RESEARCHER_CHEAP_MODEL:-openai/claude-sonnet-4-6}"
export CHEEP_MODEL="$AI_RESEARCHER_CHEAP_MODEL"
export PYTHONUNBUFFERED=1
export PYTHONPATH="$WORKSPACE"
export RESEARCHCLAWEVAL_HOST_WORKSPACE="$WORKSPACE"
export RESEARCHCLAWEVAL_TOPIC_HOST_DATASET_ROOT="${ROOT}/data/gave2/task2"
export RESEARCHCLAWEVAL_TOPIC_HOST_CONTRACT_FILE="${ROOT}/automation/gave2_task2_contract.md"
export REAL_EVAL_RUN_ID="$RESUME_RUN_ID"

OLD_TASK_DIR="$RESEARCH_AGENT_DIR/workplace_paper/task_gave2_task2_multimodal_av_segmentation_idea_gpt-5.4"
NEW_TASK_DIR="$RESEARCH_AGENT_DIR/workplace_paper/task_gave2_task2_multimodal_av_segmentation_idea_openai__gpt-5.4"
OLD_CACHE_DIR="$RESEARCH_AGENT_DIR/cache_gave2_task2_multimodal_av_segmentation_idea_gpt-5.4"
NEW_CACHE_DIR="$RESEARCH_AGENT_DIR/cache_gave2_task2_multimodal_av_segmentation_idea_openai__gpt-5.4"

if [[ ! -e "$OLD_TASK_DIR" ]]; then
  write_state "blocked" "Missing old task dir for resume: $OLD_TASK_DIR" 25
  exit 25
fi
if [[ ! -e "$OLD_CACHE_DIR" ]]; then
  write_state "blocked" "Missing old cache dir for resume: $OLD_CACHE_DIR" 26
  exit 26
fi
if [[ -e "$NEW_TASK_DIR" && ! -L "$NEW_TASK_DIR" ]]; then
  write_state "blocked" "Refusing to overwrite existing non-symlink task dir: $NEW_TASK_DIR" 27
  exit 27
fi
if [[ -e "$NEW_CACHE_DIR" && ! -L "$NEW_CACHE_DIR" ]]; then
  write_state "blocked" "Refusing to overwrite existing non-symlink cache dir: $NEW_CACHE_DIR" 28
  exit 28
fi

mkdir -p "$RESEARCH_AGENT_DIR/workplace_paper"
ln -sfn "$(basename "$OLD_TASK_DIR")" "$NEW_TASK_DIR"
ln -sfn "$(basename "$OLD_CACHE_DIR")" "$NEW_CACHE_DIR"

cd "$RESEARCH_AGENT_DIR"
mkdir -p benchmark/process/dataset_candidate/medical_image_analysis
python3 - <<'PY'
from pathlib import Path
p = Path('inno/environment/docker_env.py')
s = p.read_text()
old = '''        gpu_cmd = _normalize_gpus_flag(GPUS)
        docker_command = [
            "docker", "run", "-d", "--platform", PLATFORM, "--userns=host",] + gpu_cmd + ["--name", self.container_name, 
            "--user", "root", "-v", f"{self.local_workplace}:{self.docker_workplace}",
            "-w", f"{self.docker_workplace}", "-p", f"{self.communication_port}:8000", 
            "--restart", "unless-stopped", BASE_IMAGES
        ]'''
new = '''        gpu_cmd = _normalize_gpus_flag(GPUS)
        host_workspace = os.getenv("RESEARCHCLAWEVAL_HOST_WORKSPACE", "")
        local_workplace = self.local_workplace
        if host_workspace and local_workplace.startswith("/workspace/"):
            local_workplace = os.path.join(host_workspace, local_workplace.removeprefix("/workspace/"))
        extra_mounts = []
        host_dataset = os.getenv("RESEARCHCLAWEVAL_TOPIC_HOST_DATASET_ROOT", "")
        if host_dataset:
            extra_mounts.extend(["-v", f"{host_dataset}:/data/gave2/task2:ro"])
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
if old in s:
    p.write_text(s.replace(old, new))
PY
cat > benchmark/process/dataset_candidate/medical_image_analysis/metaprompt.py <<'PY'
TASK = "GAVE2 Task 2 multimodal retinal artery-vein segmentation."
DATASET = """
Use the real GAVE2 Task 2 dataset mounted at:
- /data/gave2/task2
- /workspace/data/gave2/task2
The case contains CFP + early-phase FFA + late-phase FFA.
"""
BASELINE = "Restore a real multimodal medical-image segmentation baseline first."
COMPARISON = "Compare a baseline with one real multimodal improvement under the same dataset split."
EVALUATION = "Track the official composite score and save runnable artifacts only."
REF = "Do not use BabyLM, toy data, placeholder results, or previous outputs."
PY

python3 - <<'PY'
import json
from pathlib import Path
instance_path = Path('../benchmark/final/medical_image_analysis/gave2_task2_multimodal_av_segmentation.json')
data = json.loads(instance_path.read_text(encoding='utf-8'))
instance_id = data.get('instance_id')
if not instance_id:
    raise SystemExit(f'missing instance_id in {instance_path}')
print(f'[ai-researcher-resume] benchmark instance_id={instance_id}')
PY

PORT=$(python3 - <<'PY'
import socket
s = socket.socket()
s.bind(('127.0.0.1', 0))
print(s.getsockname()[1])
s.close()
PY
)

{
  echo "[$(date -Is)] source_dir=$SOURCE_DIR"
  echo "[$(date -Is)] resume_root=$RESUME_ROOT"
  echo "[$(date -Is)] workspace=$WORKSPACE"
  echo "[$(date -Is)] old_task_dir=$OLD_TASK_DIR"
  echo "[$(date -Is)] new_task_dir=$NEW_TASK_DIR"
  echo "[$(date -Is)] old_cache_dir=$OLD_CACHE_DIR"
  echo "[$(date -Is)] new_cache_dir=$NEW_CACHE_DIR"
  echo "[$(date -Is)] port=$PORT"
} | tee "$LOG_FILE"

write_state "running" "Resuming from previous failed prepare-agent point"

set +e
docker run --rm -i -t \
  -v /var/run/docker.sock:/var/run/docker.sock \
  -v "$WORKSPACE":/workspace \
  -v "$ROOT/real_eval/scripts":/resume-scripts:ro \
  --env-file "$SOURCE_DIR/provider.env" \
  --env-file "$SOURCE_DIR/semantic.env" \
  -e COMPLETION_MODEL="openai/gpt-5.4" \
  -e AI_RESEARCHER_CHEAP_MODEL="$AI_RESEARCHER_CHEAP_MODEL" \
  -e CHEEP_MODEL="$AI_RESEARCHER_CHEAP_MODEL" \
  -e BASE_IMAGES="ai-researcher-exec:runtime-ready" \
  -e GPUS="all" \
  -e PYTHONPATH="/workspace" \
  -e RESEARCHCLAWEVAL_HOST_WORKSPACE="$WORKSPACE" \
  -e RESEARCHCLAWEVAL_TOPIC_HOST_DATASET_ROOT="${ROOT}/data/gave2/task2" \
  -e RESEARCHCLAWEVAL_TOPIC_HOST_CONTRACT_FILE="${ROOT}/automation/gave2_task2_contract.md" \
  -e REAL_EVAL_RUN_ID="$RESUME_RUN_ID" \
  -w /workspace \
  ai-researcher:runtime-ready \
  bash -lc "cd research_agent && python3 /resume-scripts/01_ai_researcher_resume_select.py /workspace/research_agent python3 -u run_infer_idea.py --instance_path ../benchmark/final/medical_image_analysis/gave2_task2_multimodal_av_segmentation.json --container_name gave2_task2_eval_${RESUME_RUN_ID} --model $AI_RESEARCHER_COMPLETION_MODEL --workplace_name workplace --cache_path cache_${RESUME_RUN_ID} --port ${PORT} --max_iter_times 0 --category medical_image_analysis" 2>&1 | tee -a "$LOG_FILE"
run_rc=${PIPESTATUS[0]}
set -e

if [[ $run_rc -eq 0 ]]; then
  write_state "completed" "Resume run finished" 0
else
  write_state "failed" "Resume run exited non-zero" "$run_rc"
fi
exit "$run_rc"
