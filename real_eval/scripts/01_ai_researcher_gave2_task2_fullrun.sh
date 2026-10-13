#!/usr/bin/env bash
set -euo pipefail
ROOT="${RESEARCHCLAWEVAL_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
source "$ROOT/real_eval/scripts/lib_real_eval.sh"
FRAMEWORK_MODEL_RAW="${REAL_EVAL_FRAMEWORK_MODEL:-${REAL_EVAL_MODEL:-gpt-5.4}}"
AI_RESEARCHER_COMPLETION_MODEL="${AI_RESEARCHER_COMPLETION_MODEL:-openai/${FRAMEWORK_MODEL_RAW}}"
AI_RESEARCHER_CHEAP_MODEL="${AI_RESEARCHER_CHEAP_MODEL:-$AI_RESEARCHER_COMPLETION_MODEL}"
export FRAMEWORK_NAME="AI-Researcher"
export FRAMEWORK_SLUG="01_ai_researcher_gave2_task2_fullrun"
export FRAMEWORK_SRC="$(real_eval_resolve_framework_source "$ROOT" 01)"
export FRAMEWORK_ENTRY_PATHS=$(cat <<'EOF'
AI-Researcher/benchmark/final/medical_image_analysis/gave2_task2_multimodal_av_segmentation.json
docs/gave2_task2_summary.md
docs/gave2_metric_spec.md
docs/gave2_submission_spec.md
docs/gave2_data_layout.md
automation/gave2_task2_contract.md
EOF
)
export FRAMEWORK_RUNTIME_KIND="docker"
export FRAMEWORK_RUNTIME_IMAGE="ai-researcher:runtime-ready"
export FRAMEWORK_DISABLE_GPU="1"
export FRAMEWORK_DOCKER_ARGS=$(cat <<EOF
-v
/var/run/docker.sock:/var/run/docker.sock
-e
COMPLETION_MODEL=$AI_RESEARCHER_COMPLETION_MODEL
-e
CHEEP_MODEL=$AI_RESEARCHER_CHEAP_MODEL
-e
BASE_IMAGES=ai-researcher-exec:runtime-ready
-e
GPUS=all
-e
PYTHONPATH=/workspace
-e
RESEARCHCLAWEVAL_AI_RESEARCHER_HOST_REPO
EOF
)
export FRAMEWORK_RUNTIME_COMMAND=$(cat <<EOF
set -euo pipefail
mkdir -p benchmark/process/dataset_candidate/medical_image_analysis
python - <<'PY'
from pathlib import Path
import sys

p = Path('research_agent/inno/environment/docker_env.py')
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
if old not in s:
    raise SystemExit('docker_command block not found')
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
cd research_agent
PORT=$(python - <<'PY'
import socket
s = socket.socket()
s.bind(('127.0.0.1', 0))
print(s.getsockname()[1])
s.close()
PY
)
python - <<'PY'
import json
from pathlib import Path
instance_path = Path('../benchmark/final/medical_image_analysis/gave2_task2_multimodal_av_segmentation.json')
data = json.loads(instance_path.read_text(encoding='utf-8'))
instance_id = data.get('instance_id')
if not instance_id:
    raise SystemExit(f'missing instance_id in {instance_path}')
print(f'[ai-researcher] benchmark instance_id={instance_id}')
PY
python run_infer_idea.py \
  --instance_path ../benchmark/final/medical_image_analysis/gave2_task2_multimodal_av_segmentation.json \
  --container_name gave2_task2_eval_\${REAL_EVAL_RUN_ID} \
  --model "$AI_RESEARCHER_COMPLETION_MODEL" \
  --workplace_name workplace \
  --cache_path cache_\${REAL_EVAL_RUN_ID} \
  --port "\$PORT" \
  --max_iter_times 0 \
  --category medical_image_analysis
EOF
)
exec "$ROOT"/real_eval/scripts/gave2_framework_fullrun.sh
