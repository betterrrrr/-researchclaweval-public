#!/usr/bin/env bash
set -euo pipefail

ROOT="${RESEARCHCLAWEVAL_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
source "$ROOT/real_eval/scripts/lib_real_eval.sh"
RUN_ID="${REAL_EVAL_RUN_ID:-$(date +%Y%m%d-%H%M%S)}"
BASE="${REAL_EVAL_RUN_ROOT:-$ROOT/real_eval/runs/$RUN_ID/01_ai_researcher}"
SRC="$ROOT/AI-Researcher"
REPO="$BASE/repo"
LOG_DIR="$BASE/logs"
DATASET_ROOT="${BABYLM_DATASET_ROOT:-$ROOT/BabyLM-2026-Strict-Small}"
CONTRACT_FILE="${BABYLM_CONTRACT_FILE:-$ROOT/BabyLM-10M_七框架任务包装与分发指南.md}"
PROVIDER_CONFIG="${PROVIDER_CONFIG:-$ROOT/api/codex_gpt54_shubiaobiao.toml}"
SEMANTIC_SOURCE="${SEMANTIC_SOURCE:-$ROOT/api/_semantic_scholar_api_usage.md}"
AI_RESEARCHER_MODEL="${REAL_EVAL_FRAMEWORK_MODEL:-${REAL_EVAL_MODEL:-deepseek-v4-flash}}"
PORT="${AI_RESEARCHER_PORT:-12372}"
CONTAINER_NAME="ai_researcher_babylm_${RUN_ID}"
OUTER_CONTAINER_NAME="ai_researcher_outer_${RUN_ID}"
PROVIDER_ENV="$BASE/provider.env"
SEMANTIC_ENV="$BASE/semantic.env"
GITHUB_ENV="$BASE/github.env"

cleanup_inner_container() {
  docker ps -a --format '{{.Names}}' | rg "^(${OUTER_CONTAINER_NAME}|${CONTAINER_NAME})" | xargs -r docker rm -f >/dev/null 2>&1 || true
}

# Preemptive cleanup: remove any stale AI-Researcher containers from previous runs
docker ps -a --format '{{.Names}}' | rg '^ai_researcher_babylm_' | xargs -r docker rm -f >/dev/null 2>&1 || true

trap cleanup_inner_container EXIT

real_eval_require_clean_dir "$BASE"
mkdir -p "$BASE" "$LOG_DIR"
real_eval_rsync_repo "$SRC" "$REPO"
real_eval_provider_env_from_codex_toml "$PROVIDER_CONFIG" "$PROVIDER_ENV"
real_eval_semantic_env_from_usage_md "$SEMANTIC_SOURCE" "$SEMANTIC_ENV"
cp "$ROOT/api/github.env" "$GITHUB_ENV" 2>/dev/null || echo "GITHUB_AI_TOKEN=" > "$GITHUB_ENV"

mkdir -p "$REPO/benchmark/final/babylm"
mkdir -p "$REPO/benchmark/process/dataset_candidate/babylm"
cat > "$REPO/benchmark/process/dataset_candidate/babylm/metaprompt.py" <<'PY'
TASK = "BabyLM 2026 Strict-Small real language-model training and evaluation."
DATASET = """
Use the real BabyLM 2026 Strict-Small dataset. In the execution container it is
available under all of these paths after setup:
- /data/BabyLM-2026-Strict-Small
- /workplace_<run_id>/dataset_candidate/BabyLM-2026-Strict-Small
- /workplace_<run_id>/project/data/BabyLM-2026-Strict-Small
- /workplace_<run_id>/project/dataset_candidate/BabyLM-2026-Strict-Small
"""
BASELINE = """
Restore a HuggingFace-compatible small neural language-model baseline first.
The baseline must train on the real BabyLM Strict-Small text files and save a
checkpoint, training log, and evaluation JSON.
"""
COMPARISON = "Compare the baseline with one constrained improvement under the same BabyLM data and epoch limits."
EVALUATION = "Run BabyLM-compatible language-model evaluation and save machine-readable metrics."
REF = "Do not use proxy scripts, sklearn toy datasets, old experiment outputs, or placeholder results."
PY
python3 - "$REPO/research_agent/inno/environment/utils.py" <<'PY'
from pathlib import Path
import sys

p = Path(sys.argv[1])
s = p.read_text()
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

    source_path = f"../benchmark/process/dataset_candidate/{category}"
    if not os.path.exists(source_path):
        raise Exception(f"source path {source_path} not exists")

    if category == "babylm":
        real_dataset = os.getenv("RESEARCHCLAWEVAL_TOPIC_DATASET_ROOT")
        if not real_dataset or not os.path.isdir(real_dataset):
            raise Exception(f"BabyLM dataset root not available: {real_dataset}")
        try:
            os.makedirs(dataset_candidate_path, exist_ok=True)
            if os.path.isfile(os.path.join(source_path, "metaprompt.py")):
                shutil.copy2(os.path.join(source_path, "metaprompt.py"), os.path.join(dataset_candidate_path, "metaprompt.py"))
            copied_dataset = os.path.join(dataset_candidate_path, "BabyLM-2026-Strict-Small")
            shutil.copytree(real_dataset, copied_dataset)
            project_dir = os.path.join(local_workplace, "project")
            for rel in ("data/BabyLM-2026-Strict-Small", "dataset_candidate/BabyLM-2026-Strict-Small"):
                target = os.path.join(project_dir, rel)
                os.makedirs(os.path.dirname(target), exist_ok=True)
                if not os.path.exists(target):
                    shutil.copytree(real_dataset, target)
            root_visible = os.path.join(local_workplace, "BabyLM-2026-Strict-Small")
            if not os.path.exists(root_visible):
                shutil.copytree(real_dataset, root_visible)
            print(f"copy BabyLM dataset {real_dataset} to {dataset_candidate_path} success")
            return
        except Exception as e:
            raise Exception(f"copy BabyLM dataset to {dataset_candidate_path} failed: {str(e)}")

    try:
        shutil.copytree(source_path, dataset_candidate_path)
        print(f"copy {source_path} to {dataset_candidate_path} success")
    except Exception as e:
        raise Exception(f"copy {source_path} to {dataset_candidate_path} failed: {str(e)}")
'''
if old not in s:
    raise SystemExit("setup_dataset block not found")
p.write_text(s.replace(old, new))
PY
python3 - "$REPO/research_agent/inno/environment/docker_env.py" <<'PY'
from pathlib import Path
import sys

p = Path(sys.argv[1])
s = p.read_text()
# Fix docker_workplace for "." workplace_name
s = s.replace(
    '        self.docker_workplace = f"/{config.workplace_name}"',
    '        self.docker_workplace = "/workspace" if config.workplace_name == "." else f"/{config.workplace_name}"',
    1,
)
old = '''        docker_command = [
            "docker", "run", "-d", "--platform", PLATFORM, "--userns=host",] + gpu_cmd + ["--name", self.container_name, 
            "--user", "root", "-v", f"{self.local_workplace}:{self.docker_workplace}",
            "-w", f"{self.docker_workplace}", "-p", f"{self.communication_port}:8000", 
            "--restart", "unless-stopped", BASE_IMAGES
        ]'''
new = '''        extra_mounts = []
        host_repo = os.getenv("RESEARCHCLAWEVAL_AI_RESEARCHER_HOST_REPO", "")
        local_workplace = self.local_workplace
        if host_repo and local_workplace.startswith("/workspace/AI-Researcher/"):
            local_workplace = os.path.join(host_repo, local_workplace.removeprefix("/workspace/AI-Researcher/"))
        host_dataset = os.getenv("RESEARCHCLAWEVAL_TOPIC_HOST_DATASET_ROOT", "")
        if host_dataset:
            extra_mounts.extend(["-v", f"{host_dataset}:/data/BabyLM-2026-Strict-Small:ro"])
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
p.write_text(s.replace(old, new))
s2 = p.read_text()
s2 = s2.replace(
    "hostname = 'localhost'",
    "hostname = os.getenv('RESEARCHCLAWEVAL_DOCKER_HOST', 'localhost')",
    1,
)
s2 = s2.replace(
    "assert port_info and (port_info[0] == port_info[1])",
    "assert port_info",
    1,
)
s2 = s2.replace(
    "        if self.wait_for_container_ready(timeout=60):",
    "        if result.returncode == 0:\n"
    "            _r = subprocess.run([\"docker\", \"inspect\", \"--format\", \"{{.State.Status}}\", self.container_name], capture_output=True, text=True)\n"
    "            if _r.stdout.strip() != \"running\":\n"
    "                subprocess.run([\"docker\", \"start\", self.container_name])\n"
    "        if self.wait_for_container_ready(timeout=300):",
    1,
)
p.write_text(s2)
PY
python3 - "$REPO/research_agent/inno/tools/arxiv_source.py" <<'PY'
from pathlib import Path
import sys

p = Path(sys.argv[1])
s = p.read_text()
s = s.replace(
'''PLACEHOLDER_PAPER_TEXT = """\\
This local note is a fallback paper summary for AI-Researcher when the original paper source is unavailable.

Key machine learning concepts relevant to the current task:

1. Feature scaling / standardization
For a feature x, standardized value z is:
z = (x - mu) / sigma
where mu is the training-set mean and sigma is the training-set standard deviation.

2. Principal component analysis (PCA)
PCA projects data to top eigenvectors of the covariance matrix.
For centered data matrix X, covariance is:
Sigma = (1 / n) X^T X
The k-dimensional projection is:
Z = X W_k
where columns of W_k are the top-k eigenvectors.

3. Mutual information feature selection
Mutual information between feature X and label Y is:
I(X;Y) = sum_x sum_y p(x,y) log( p(x,y) / (p(x) p(y)) )
Higher mutual information suggests stronger predictive relevance.

4. Logistic regression
For binary classification:
p(y=1|x) = sigma(w^T x + b)
where sigma(t) = 1 / (1 + exp(-t)).
The multiclass version uses softmax and cross-entropy loss.

5. Linear SVM
Decision score:
f(x) = w^T x + b
Standard hinge-loss objective:
min_{w,b} 0.5 ||w||^2 + C sum_i max(0, 1 - y_i (w^T x_i + b))

6. Hyperparameter tuning
A lightweight workflow can compare baseline and improved pipelines with cross-validation over small grids for:
- C
- PCA dimension
- feature-selection percentile
- classifier choice

7. Minimal experiment framing
Use train/validation or cross-validation on sklearn builtin datasets.
Record baseline metrics, improved metrics, one figure, and a short analysis table.
"""''',
'''PLACEHOLDER_PAPER_TEXT = """\\
This local reference note is used when a paper source tarball cannot be fetched.
It is not an experiment result and must not be counted as training evidence.

BabyLM-relevant context:

1. Task setting
The active task is BabyLM 2026 Strict-Small language-model training under the
10M-word budget. The real dataset is mounted by ResearchClawEval and must be
used for training and evaluation.

2. Baseline implementation direction
Use a HuggingFace-compatible causal language-model or masked language-model
training pipeline. Training must save checkpoints, logs, evaluation JSON, and a
final report derived from the new run.

3. Evaluation direction
Use the BabyLM task contract and available evaluation pipeline references. If
official external evaluation code is unavailable during setup, record that as a
setup limitation and still run a transparent local validation metric such as
held-out language-model loss/perplexity from the real BabyLM split.

4. Prohibited shortcuts
Do not use sklearn toy datasets, iris, digits, proxy BabyLM scripts, old run
outputs, n-gram-only scoring, or placeholder experiment results.
"""'''
)
insert = r'''

def _semantic_scholar_headers():
    api_key = (
        os.getenv("SEMANTIC_SCHOLAR_API_KEY")
        or os.getenv("S2_API_KEY")
        or os.getenv("AI4SCHOLAR_API_KEY")
    )
    if not api_key:
        return {}
    auth_mode = os.getenv("SEMANTIC_SCHOLAR_AUTH_MODE", "x-api-key").strip().lower()
    if auth_mode == "bearer":
        return {"Authorization": f"Bearer {api_key}"}
    return {"X-API-KEY": api_key}


def _semantic_scholar_search(title: str):
    base_url = os.getenv("SEMANTIC_SCHOLAR_API_BASE_URL", "https://api.semanticscholar.org").rstrip("/")
    headers = _semantic_scholar_headers()
    if not headers:
        return None
    try:
        session = requests.Session()
        session.trust_env = False
        resp = session.get(
            f"{base_url}/graph/v1/paper/search",
            headers=headers,
            params={
                "query": title,
                "limit": 1,
                "fields": "title,authors,venue,year,abstract,citationCount,url",
            },
            timeout=30,
        )
        if resp.status_code == 429:
            return {"status": "rate_limited", "title": title}
        resp.raise_for_status()
        data = resp.json()
        items = data.get("data") or []
        if not items:
            return None
        return items[0]
    except Exception as exc:
        return {"status": "unavailable", "title": title, "error": str(exc)}


def _write_semantic_reference_note(local_root: str, workplace_name: str, title: str, metadata):
    paper_tex_dir = os.path.join(local_root, workplace_name, "papers")
    os.makedirs(paper_tex_dir, exist_ok=True)
    filename = f"{_safe_paper_stem(title)}.tex"
    filepath = os.path.join(paper_tex_dir, filename)
    lines = [
        f"Title: {title}",
        "",
        "Source: Semantic Scholar metadata fallback for AI-Researcher literature context.",
        "This file is a reference note only, not an experiment result.",
        "",
    ]
    if isinstance(metadata, dict):
        lines.extend([
            f"Matched title: {metadata.get('title', title)}",
            f"Venue: {metadata.get('venue', '')}",
            f"Year: {metadata.get('year', '')}",
            f"Citation count: {metadata.get('citationCount', '')}",
            f"URL: {metadata.get('url', '')}",
            "",
            "Abstract:",
            str(metadata.get("abstract") or metadata.get("error") or metadata.get("status") or "No abstract available."),
        ])
    lines.extend(["", PLACEHOLDER_PAPER_TEXT])
    with open(filepath, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    return filepath
'''
if "def _semantic_scholar_headers()" not in s:
    s = s.replace("def _safe_paper_stem(title: str) -> str:", insert + "\n\ndef _safe_paper_stem(title: str) -> str:", 1)
s = s.replace(
'''    # 发送请求并解析结果
    response = requests.get(query_url, timeout=20)
    response.raise_for_status()
    response = feedparser.parse(response.text)''',
'''    # 发送请求并解析结果. arXiv 429 must not abort the real BabyLM run.
    try:
        response = requests.get(query_url, timeout=20)
        if response.status_code == 429 and os.getenv("AI_RESEARCHER_DISABLE_ARXIV_SOURCE_DOWNLOAD_ON_429", "1") == "1":
            print(f"arXiv rate limited query for {query}; falling back to Semantic Scholar/local note.")
            return []
        response.raise_for_status()
    except requests.exceptions.RequestException as exc:
        if os.getenv("AI_RESEARCHER_DISABLE_ARXIV_SOURCE_DOWNLOAD_ON_429", "1") == "1":
            print(f"arXiv query unavailable for {query}: {exc}; falling back to Semantic Scholar/local note.")
            return []
        raise
    response = feedparser.parse(response.text)''',
1)
s = s.replace(
'''        if len(papers) == 0:
            placeholder = _write_placeholder_paper(local_root, workplace_name, title)
            ret_msg.append(
                f"Cannot find the paper '{title}' in arxiv. "
                f"A local placeholder note was created at /{workplace_name}/papers/{os.path.basename(placeholder)}"
            )
            continue''',
'''        if len(papers) == 0:
            metadata = _semantic_scholar_search(title)
            reference_note = _write_semantic_reference_note(local_root, workplace_name, title, metadata)
            ret_msg.append(
                f"Cannot fetch arXiv source for '{title}'. "
                f"Semantic Scholar/local reference note was created at /{workplace_name}/papers/{os.path.basename(reference_note)}"
            )
            time.sleep(1.1)
            continue''',
1)
s = s.replace(
'''            placeholder = _write_placeholder_paper(local_root, workplace_name, title)
            ret_msg.append(
                download_info["message"]
                + f"\\nA local placeholder note was created at /{workplace_name}/papers/{os.path.basename(placeholder)}"
            )''',
'''            metadata = _semantic_scholar_search(title)
            reference_note = _write_semantic_reference_note(local_root, workplace_name, title, metadata)
            ret_msg.append(
                download_info["message"]
                + f"\\nSemantic Scholar/local reference note was created at /{workplace_name}/papers/{os.path.basename(reference_note)}"
            )
            time.sleep(1.1)''',
1)
p.write_text(s)
PY
cat > "$REPO/benchmark/final/babylm/babylm_10m.json" <<EOF
{
  "target": "BabyLM-10M real language-model training experiment",
  "instance_id": "babylm_10m",
  "authors": ["ResearchClawEval"],
  "year": 2026,
  "url": "https://babylm.github.io/",
  "abstract": "Run a real BabyLM-10M experiment using the mounted dataset and task contract. The project must train a language model, save checkpoints, evaluate the result, and write a paper-style report based on actual training evidence.",
  "venue": "ResearchClawEval",
  "topic": "language-modeling",
  "field": "babylm",
  "source_papers": [
    {
      "reference": "BabyLM Challenge materials",
      "usage": "Use the BabyLM task constraints and strict-small dataset budget."
    },
    {
      "reference": "HuggingFace Transformers language modeling examples",
      "usage": "Use a real neural language-model training implementation with checkpoints and evaluation."
    }
  ],
  "task1": "Read the BabyLM task contract at /input/contract.md and use the dataset mounted at /data/BabyLM-2026-Strict-Small. Implement and run a real language-model training experiment, not a proxy or n-gram counter. Save training logs, loss curves, checkpoints, evaluation JSON, and a concise report. Do not use iris, digits, sklearn toy datasets, proxy scripts, or any previous experiment results.",
  "task2": "Starting from the BabyLM contract and dataset, propose one real training idea for a small language model, implement it in the project workspace, train it on the BabyLM-10M data, evaluate it, and write the paper. Do not reuse old results and do not create placeholder outputs."
}
EOF

cat > "$REPO/research_agent/prepare_babylm_paper_agent.py" <<'PY'
from pathlib import Path
import argparse
import os
import shutil


def copytree_or_replace(src: Path, dst: Path) -> None:
    if dst.exists() or dst.is_symlink():
        if dst.is_symlink() or dst.is_file():
            dst.unlink()
        else:
            shutil.rmtree(dst)
    shutil.copytree(src, dst)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--model", default="gpt-5.4")
    parser.add_argument("--instance-id", default="babylm_10m")
    args = parser.parse_args()

    cwd = Path.cwd()
    model = args.model.replace("/", "__")
    cache_src = cwd / f"cache_{args.instance_id}_idea_{model}" / "agents"
    workplace_src = (
        cwd
        / "workplace_paper"
        / f"task_{args.instance_id}_idea_{model}"
        / f"workplace_{args.run_id}"
        / f"workplace_{args.run_id}"
    )
    if not cache_src.is_dir():
        raise FileNotFoundError(f"AI-Researcher agent cache not found: {cache_src}")
    if not workplace_src.is_dir():
        raise FileNotFoundError(f"AI-Researcher workplace not found: {workplace_src}")

    paper_root = cwd / "paper_agent" / "babylm" / args.instance_id
    paper_root.mkdir(parents=True, exist_ok=True)
    cache_dst = paper_root / f"cache_{args.instance_id}_idea_{model}" / "agents"
    cache_dst.parent.mkdir(parents=True, exist_ok=True)
    copytree_or_replace(cache_src, cache_dst)
    copytree_or_replace(workplace_src, paper_root / "workplace")

    benchmark_src = cwd.parent / "benchmark" / "final" / "babylm" / f"{args.instance_id}.json"
    benchmark_dst = cwd / "benchmark" / "final" / "babylm" / f"{args.instance_id}.json"
    benchmark_dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(benchmark_src, benchmark_dst)

    templates_src = cwd.parent / "paper_agent" / "tiny_cls" / "writing_templates"
    templates_dst = cwd / "babylm" / "writing_templates"
    if templates_src.is_dir() and not templates_dst.is_dir():
        copytree_or_replace(templates_src, templates_dst)

    target_dataset = paper_root / "workplace" / "project" / "data" / "BabyLM-2026-Strict-Small"
    if not target_dataset.is_dir():
        raise FileNotFoundError(f"Prepared paper-agent workplace still cannot see BabyLM dataset: {target_dataset}")

    print("Prepared AI-Researcher paper_agent path:")
    print(f"  paper_root={paper_root}")
    print(f"  cache_agents={cache_dst}")
    print(f"  workplace={paper_root / 'workplace'}")
    print(f"  dataset={target_dataset}")


if __name__ == "__main__":
    main()
PY

cat > "$BASE/state.json" <<EOF
{"project_id":"01","name":"AI-Researcher","run_id":"$RUN_ID","status":"starting","repo":"$REPO"}
EOF

set +e
docker run --rm --name "$OUTER_CONTAINER_NAME" --ipc=host --ulimit memlock=-1 --ulimit stack=67108864 \
  --add-host host.docker.internal:host-gateway \
  -e COMPLETION_MODEL=openai/$AI_RESEARCHER_MODEL \
  -e CHEEP_MODEL=openai/$AI_RESEARCHER_MODEL \
  -e BASE_IMAGES=${AI_RESEARCHER_EXEC_RUNTIME_IMAGE:-ai-researcher-exec:blackwell-25.11} \
  -e GPUS=all \
  -e PYTHONPATH=/workspace/AI-Researcher:/workspace/AI-Researcher/research_agent/inno/tools \
  -e RESEARCHCLAWEVAL_TOPIC_LABEL=BabyLM-10M \
  -e RESEARCHCLAWEVAL_TOPIC_DATASET_ROOT=/data/BabyLM-2026-Strict-Small \
  -e RESEARCHCLAWEVAL_TOPIC_HOST_DATASET_ROOT="$DATASET_ROOT" \
  -e RESEARCHCLAWEVAL_DOCKER_HOST=host.docker.internal \
  -e RESEARCHCLAWEVAL_TOPIC_CONTRACT_FILE=/input/contract.md \
  -e RESEARCHCLAWEVAL_TOPIC_HOST_CONTRACT_FILE="$CONTRACT_FILE" \
  -e RESEARCHCLAWEVAL_AI_RESEARCHER_HOST_REPO="$REPO" \
	  --env-file "$ROOT/AI-Researcher/.env.project01" \
	  --env-file "$PROVIDER_ENV" \
	  --env-file "$SEMANTIC_ENV" \
	  --env-file "$GITHUB_ENV" \
	  -v "$REPO":/workspace/AI-Researcher \
  -v "$DATASET_ROOT":/data/BabyLM-2026-Strict-Small:ro \
  -v "$CONTRACT_FILE":/input/contract.md:ro \
  -v "$PROVIDER_CONFIG":/input/provider.toml:ro \
  -v "$SEMANTIC_SOURCE":/input/semantic_scholar.md:ro \
  -v /var/run/docker.sock:/var/run/docker.sock \
  -w /workspace/AI-Researcher/research_agent \
  ai-researcher:runtime-ready \
	  bash -lc "PLAYWRIGHT_BROWSERS_PATH=/ms-playwright python -m playwright install chromium 2>&1 ; apt-get update -qq && apt-get install -y -qq libatk1.0-0 libatk-bridge2.0-0 libcups2 libdrm2 libxkbcommon0 libatspi2.0-0 libxcomposite1 libxdamage1 libxfixes3 libxrandr2 libgbm1 libpango-1.0-0 2>&1 || true ; python -u run_infer_idea.py --instance_path ../benchmark/final/babylm/babylm_10m.json --container_name $CONTAINER_NAME --model openai/$AI_RESEARCHER_MODEL --workplace_name workplace_$RUN_ID --cache_path cache_$RUN_ID --port $PORT --max_iter_times 0 --category babylm 2>&1 ; echo EXIT_CODE=\$? ; python prepare_babylm_paper_agent.py --run-id $RUN_ID --model openai/$AI_RESEARCHER_MODEL --instance-id babylm_10m && python ../paper_agent/writing.py --research_field babylm --instance_id babylm_10m" \
	  2>&1 | tee "$LOG_DIR/e2e.log"
rc=${PIPESTATUS[0]}
set -e
cleanup_inner_container
if [[ "$rc" -ne 0 ]]; then
  real_eval_write_state "$BASE/state.json" "{\"project_id\":\"01\",\"name\":\"AI-Researcher\",\"run_id\":\"$RUN_ID\",\"status\":\"failed\",\"repo\":\"$REPO\",\"log\":\"$LOG_DIR/e2e.log\",\"exit_code\":$rc}"
  exit "$rc"
fi

if ! real_eval_has_artifacts "$BASE"; then
  real_eval_write_state "$BASE/state.json" "{\"project_id\":\"01\",\"name\":\"AI-Researcher\",\"run_id\":\"$RUN_ID\",\"status\":\"failed_no_artifacts\",\"repo\":\"$REPO\",\"log\":\"$LOG_DIR/e2e.log\"}"
  exit 13
fi
cat > "$BASE/state.json" <<EOF
{"project_id":"01","name":"AI-Researcher","run_id":"$RUN_ID","status":"finished","repo":"$REPO","log":"$LOG_DIR/e2e.log"}
EOF
