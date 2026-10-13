#!/usr/bin/env bash
set -euo pipefail

ROOT="${RESEARCHCLAWEVAL_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
source "$ROOT/real_eval/scripts/lib_real_eval.sh"
RUN_ID="${REAL_EVAL_RUN_ID:-$(date +%Y%m%d-%H%M%S)}"
BASE="${REAL_EVAL_RUN_ROOT:-$ROOT/real_eval/runs/$RUN_ID/01_ai_researcher_resume}"
LOG_DIR="$BASE/logs"
SOURCE_RUN_ID="${AI_RESEARCHER_RESUME_SOURCE_RUN_ID:-systemd-six-repair2-20260603-203759}"
SOURCE_BASE="$ROOT/real_eval/runs/$SOURCE_RUN_ID/01_ai_researcher_real_babylm"
SOURCE_REPO="$SOURCE_BASE/repo"
SOURCE_CODE_REPO="${AI_RESEARCHER_RESUME_SOURCE_CODE_REPO:-$ROOT/AI-Researcher}"
SOURCE_WORKPLACE="${AI_RESEARCHER_RESUME_SOURCE_WORKPLACE:-/workspace/AI-Researcher/research_agent/workplace_paper/task_babylm_10m_idea_gpt-5.4/workplace_${SOURCE_RUN_ID}/workplace_${SOURCE_RUN_ID}}"
REPO="$BASE/repo"
PAPER_ROOT="$REPO/research_agent/paper_agent/babylm/babylm_10m"
PROVIDER_CONFIG="${PROVIDER_CONFIG:-$ROOT/api/codex_gpt54_shubiaobiao.toml}"
SEMANTIC_SOURCE="${SEMANTIC_SOURCE:-$ROOT/api/_semantic_scholar_api_usage.md}"
PROVIDER_ENV="$BASE/provider.env"
SEMANTIC_ENV="$BASE/semantic.env"
CONTAINER_NAME="ai_researcher_resume_${RUN_ID}"

require_dir() {
  local path="$1"
  local label="$2"
  if [[ ! -d "$path" ]]; then
    echo "AI-Researcher writing contract missing directory [$label]: $path" >&2
    exit 30
  fi
}

require_file() {
  local path="$1"
  local label="$2"
  if [[ ! -f "$path" ]]; then
    echo "AI-Researcher writing contract missing file [$label]: $path" >&2
    exit 31
  fi
}

require_find() {
  local dir="$1"
  local label="$2"
  shift 2
  if ! find "$dir" "$@" 2>/dev/null | rg . >/dev/null; then
    echo "AI-Researcher writing contract missing evidence [$label] under: $dir" >&2
    exit 32
  fi
}

materialize_related_work_notes() {
  local papers_dir="$PAPER_ROOT/workplace/papers"
  mkdir -p "$papers_dir"
  python3 - "$CACHE_DST" "$PAPER_ROOT/workplace" "$papers_dir" "$RUN_ID" <<'PY'
import json
import os
import pathlib
import sys

cache_dir = pathlib.Path(sys.argv[1])
workplace = pathlib.Path(sys.argv[2])
papers_dir = pathlib.Path(sys.argv[3])
run_id = sys.argv[4]
papers_dir.mkdir(parents=True, exist_ok=True)

def read_text(path: pathlib.Path, limit: int = 18000) -> str:
    text = path.read_text(encoding="utf-8", errors="replace")
    return text[:limit]

def read_json_or_text(path: pathlib.Path):
    text = read_text(path, limit=30000)
    try:
        return json.loads(text)
    except Exception:
        return {"text_excerpt": text}

def write_note(filename: str, payload: dict) -> None:
    (papers_dir / filename).write_text(
        json.dumps(payload, ensure_ascii=True, indent=2),
        encoding="utf-8",
    )

write_note("babylm_task_context.json", {
    "source_type": "task_contract",
    "run_id": run_id,
    "purpose": "Related-work context for the AI-Researcher paper writer. This is not an experiment result.",
    "content": {
        "task": "BabyLM-10M real language-model training experiment",
        "dataset_context": "BabyLM constrained-data language modeling using the mounted BabyLM data contract.",
        "required_evidence": [
            "real training checkpoints under workplace/project/outputs",
            "evaluation JSON files under workplace/project/outputs",
            "generated model/training/testing/data_processing code under workplace/project"
        ],
    },
})

agent_files = [
    "paper_survey_agent.json",
    "paper_survey_agent_iter_select.json",
    "paper_survey_agent_iter_1.json",
    "paper_survey_agent_iter_2.json",
    "paper_survey_agent_iter_3.json",
    "paper_survey_agent_iter_4.json",
    "code_survey_agent.json",
    "prepare_agent.json",
]
written = 1
for filename in agent_files:
    path = cache_dir / filename
    if path.is_file():
        write_note(f"agent_cache_{filename}", {
            "source_type": "ai_researcher_agent_cache",
            "source_file": str(path),
            "purpose": "Real AI-Researcher cache artifact used as related-work context only.",
            "content": read_json_or_text(path),
        })
        written += 1

readme_paths = [
    "transformers/README.md",
    "nanoGPT/README.md",
    "minGPT/README.md",
    "litgpt/README.md",
    "OLMo/README.md",
    "HuggingFaceTransformerTasks/README.md",
    "huggingface-transformers-examples/README.md",
]
for rel in readme_paths:
    path = workplace / rel
    if path.is_file():
        safe_name = rel.replace("/", "__").replace(".", "_")
        write_note(f"source_readme_{safe_name}.json", {
            "source_type": "source_repository_readme",
            "source_file": str(path),
            "purpose": "Repository README excerpt collected during the real AI-Researcher run; used as related-work context only.",
            "content_excerpt": read_text(path),
        })
        written += 1

if written < 2:
    raise SystemExit("No real related-work context could be materialized from cache or source READMEs")
PY
}

materialize_writing_contract() {
  mkdir -p "$PAPER_ROOT/workplace/project/model" \
    "$PAPER_ROOT/workplace/project/training" \
    "$PAPER_ROOT/workplace/project/testing" \
    "$PAPER_ROOT/workplace/project/data_processing" \
    "$PAPER_ROOT/workplace/project/outputs" \
    "$PAPER_ROOT/workplace/papers" \
    "$REPO/research_agent/babylm/target_sections/babylm_10m"

  if [[ -d "$REPO/paper_agent/final_paper" ]]; then
    mkdir -p "$REPO/research_agent/paper_agent/final_paper"
    rsync -a "$REPO/paper_agent/final_paper/" "$REPO/research_agent/paper_agent/final_paper/"
  fi

  materialize_related_work_notes

  require_dir "$PAPER_ROOT/workplace/project/model" "model code"
  require_dir "$PAPER_ROOT/workplace/project/training" "training code"
  require_dir "$PAPER_ROOT/workplace/project/testing" "testing code"
  require_dir "$PAPER_ROOT/workplace/project/data_processing" "data processing code"
  require_dir "$PAPER_ROOT/workplace/project/outputs" "training outputs"
  require_dir "$PAPER_ROOT/workplace/papers" "related-work context"
  require_dir "$CACHE_DST" "agent cache"
  require_file "$CACHE_DST/prepare_agent.json" "prepare agent cache"
  require_file "$CACHE_DST/survey_agent.json" "survey agent cache alias"
  require_file "$REPO/research_agent/benchmark/final/babylm/babylm_10m.json" "research_agent benchmark"
  require_file "$REPO/benchmark/final/babylm/babylm_10m.json" "repo benchmark"
  require_file "$REPO/research_agent/paper_agent/final_paper/iclr2025_conference.tex" "paper template tex"
  require_file "$REPO/research_agent/paper_agent/final_paper/iclr2025_conference.bib" "paper template bib"
  require_find "$PAPER_ROOT/workplace/project/outputs" "real checkpoint" -type f \( -iname '*.pt' -o -iname 'pytorch_model.bin' \)
  require_find "$PAPER_ROOT/workplace/project/outputs" "real evaluation JSON" -type f \( -iname '*eval*.json' -o -iname '*comparison*.json' -o -iname '*experiment*.json' \)
  require_find "$PAPER_ROOT/workplace/papers" "related-work input notes" -type f \( -iname '*.json' -o -iname '*.txt' \)

  python3 - "$BASE/ai_researcher_writing_contract_manifest.json" "$PAPER_ROOT" "$CACHE_DST" "$REPO" "$RUN_ID" <<'PY'
import json
import pathlib
import sys

manifest_path = pathlib.Path(sys.argv[1])
paper_root = pathlib.Path(sys.argv[2])
cache_dst = pathlib.Path(sys.argv[3])
repo = pathlib.Path(sys.argv[4])
run_id = sys.argv[5]

manifest = {
    "run_id": run_id,
    "contract": "AI-Researcher writing-stage workspace contract",
    "paper_root": str(paper_root),
    "required_paths": {
        "project": str(paper_root / "workplace/project"),
        "model": str(paper_root / "workplace/project/model"),
        "training": str(paper_root / "workplace/project/training"),
        "testing": str(paper_root / "workplace/project/testing"),
        "data_processing": str(paper_root / "workplace/project/data_processing"),
        "outputs": str(paper_root / "workplace/project/outputs"),
        "papers": str(paper_root / "workplace/papers"),
        "agent_cache": str(cache_dst),
        "benchmark": str(repo / "research_agent/benchmark/final/babylm/babylm_10m.json"),
        "latex_template": str(repo / "research_agent/paper_agent/final_paper"),
    },
    "evidence_policy": "Directories for framework inputs may be materialized from real cache/source materials; checkpoint and evaluation evidence must already exist and is only verified.",
}
manifest_path.write_text(json.dumps(manifest, ensure_ascii=True, indent=2), encoding="utf-8")
PY
}

cleanup_container() {
  docker ps -a --format '{{.Names}}' | rg "^${CONTAINER_NAME}$" | xargs -r docker rm -f >/dev/null 2>&1 || true
}
trap cleanup_container EXIT

real_eval_require_clean_dir "$BASE"
mkdir -p "$BASE" "$LOG_DIR"
real_eval_provider_env_from_codex_toml "$PROVIDER_CONFIG" "$PROVIDER_ENV"
real_eval_semantic_env_from_usage_md "$SEMANTIC_SOURCE" "$SEMANTIC_ENV"

if [[ ! -d "$SOURCE_CODE_REPO/research_agent" ]]; then
  echo "AI-Researcher clean source repo not found: $SOURCE_CODE_REPO" >&2
  exit 20
fi
real_eval_rsync_repo "$SOURCE_CODE_REPO" "$REPO"
if [[ ! -d "$SOURCE_WORKPLACE/project/model" ]]; then
  echo "Resume source model directory not found: $SOURCE_WORKPLACE/project/model" >&2
  exit 21
fi
if [[ ! -d "$SOURCE_WORKPLACE/project/training" || ! -d "$SOURCE_WORKPLACE/project/testing" ]]; then
  echo "Resume source training/testing directories not found under: $SOURCE_WORKPLACE/project" >&2
  exit 22
fi
if ! find "$SOURCE_WORKPLACE/project/outputs" -type f \( -iname '*.pt' -o -iname 'pytorch_model.bin' \) | rg . >/dev/null; then
  echo "Resume source has no checkpoint files under: $SOURCE_WORKPLACE/project/outputs" >&2
  exit 23
fi
if ! find "$SOURCE_WORKPLACE/project/outputs" -type f \( -iname '*eval*.json' -o -iname '*comparison*.json' -o -iname '*experiment*.json' \) | rg . >/dev/null; then
  echo "Resume source has no evaluation/result JSON under: $SOURCE_WORKPLACE/project/outputs" >&2
  exit 24
fi

mkdir -p "$PAPER_ROOT"
rsync -a --delete "$SOURCE_WORKPLACE/" "$PAPER_ROOT/workplace/"

CACHE_SRC="$SOURCE_REPO/research_agent/cache_babylm_10m_idea_gpt-5.4/agents"
if [[ ! -d "$CACHE_SRC" ]]; then
  CACHE_SRC="/workspace/AI-Researcher/research_agent/cache_babylm_10m_idea_gpt-5.4/agents"
fi
CACHE_DST="$PAPER_ROOT/cache_babylm_10m_idea_gpt-5.4/agents"
if [[ ! -d "$CACHE_SRC" ]]; then
  echo "AI-Researcher agent cache not found: $CACHE_SRC" >&2
  exit 25
fi
mkdir -p "$(dirname "$CACHE_DST")"
rsync -a --delete "$CACHE_SRC/" "$CACHE_DST/"
if [[ ! -f "$CACHE_DST/survey_agent.json" && -f "$CACHE_DST/paper_survey_agent.json" ]]; then
  cp "$CACHE_DST/paper_survey_agent.json" "$CACHE_DST/survey_agent.json"
fi

mkdir -p "$REPO/research_agent/benchmark/final/babylm" "$REPO/benchmark/final/babylm"
cat > "$REPO/research_agent/benchmark/final/babylm/babylm_10m.json" <<'EOF'
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
  "task1": "Run a real BabyLM-10M language-model training experiment. The writing stage must use actual generated code, checkpoints, logs, and evaluation JSON from workplace/project; do not use toy datasets, proxy scripts, or old unrelated samples."
}
EOF
cp "$REPO/research_agent/benchmark/final/babylm/babylm_10m.json" "$REPO/benchmark/final/babylm/babylm_10m.json"

if [[ -d "$REPO/paper_agent/tiny_cls/writing_templates" && ! -d "$REPO/research_agent/paper_agent/babylm/writing_templates" ]]; then
  mkdir -p "$REPO/research_agent/paper_agent/babylm"
  rsync -a "$REPO/paper_agent/tiny_cls/writing_templates/" "$REPO/research_agent/paper_agent/babylm/writing_templates/"
fi

materialize_writing_contract

cat > "$BASE/state.json" <<EOF
{"project_id":"01","name":"AI-Researcher resume","run_id":"$RUN_ID","source_run_id":"$SOURCE_RUN_ID","status":"starting","repo":"$REPO","source_workplace":"$SOURCE_WORKPLACE","contract_manifest":"$BASE/ai_researcher_writing_contract_manifest.json"}
EOF

set +e
docker run --rm --name "$CONTAINER_NAME" --ipc=host --ulimit memlock=-1 --ulimit stack=67108864 \
  --env-file "$PROVIDER_ENV" \
  --env-file "$SEMANTIC_ENV" \
  --env-file "$ROOT/AI-Researcher/.env.project01" \
  -e COMPLETION_MODEL=gpt-5.4 \
  -e CHEEP_MODEL=gpt-5.4 \
  -e AI_RESEARCHER_LLM_MAX_ATTEMPTS="${AI_RESEARCHER_LLM_MAX_ATTEMPTS:-8}" \
  -e PYTHONPATH=/workspace/AI-Researcher \
  -v "$REPO":/workspace/AI-Researcher \
  -w /workspace/AI-Researcher/research_agent \
  ai-researcher:runtime-ready \
  bash -lc 'python ../paper_agent/writing.py --research_field babylm --instance_id babylm_10m' \
  2>&1 | tee "$LOG_DIR/writing_resume.log"
rc=${PIPESTATUS[0]}
set -e
if [[ "$rc" -ne 0 ]]; then
  real_eval_write_state "$BASE/state.json" "{\"project_id\":\"01\",\"name\":\"AI-Researcher resume\",\"run_id\":\"$RUN_ID\",\"source_run_id\":\"$SOURCE_RUN_ID\",\"status\":\"failed\",\"repo\":\"$REPO\",\"source_workplace\":\"$SOURCE_WORKPLACE\",\"contract_manifest\":\"$BASE/ai_researcher_writing_contract_manifest.json\",\"log\":\"$LOG_DIR/writing_resume.log\",\"exit_code\":$rc}"
  exit "$rc"
fi

if ! find "$REPO/research_agent/babylm/target_sections/babylm_10m" -type f \( -iname '*.tex' -o -iname '*.bib' -o -iname '*.pdf' \) 2>/dev/null | rg . >/dev/null; then
  real_eval_write_state "$BASE/state.json" "{\"project_id\":\"01\",\"name\":\"AI-Researcher resume\",\"run_id\":\"$RUN_ID\",\"source_run_id\":\"$SOURCE_RUN_ID\",\"status\":\"failed_no_paper_artifacts\",\"repo\":\"$REPO\",\"source_workplace\":\"$SOURCE_WORKPLACE\",\"contract_manifest\":\"$BASE/ai_researcher_writing_contract_manifest.json\",\"log\":\"$LOG_DIR/writing_resume.log\"}"
  exit 26
fi

cat > "$BASE/state.json" <<EOF
{"project_id":"01","name":"AI-Researcher resume","run_id":"$RUN_ID","source_run_id":"$SOURCE_RUN_ID","status":"finished","repo":"$REPO","source_workplace":"$SOURCE_WORKPLACE","contract_manifest":"$BASE/ai_researcher_writing_contract_manifest.json","log":"$LOG_DIR/writing_resume.log","paper_dir":"$REPO/research_agent/babylm/target_sections/babylm_10m"}
EOF
