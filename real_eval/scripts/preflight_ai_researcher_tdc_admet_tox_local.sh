#!/usr/bin/env bash
set -euo pipefail

ROOT="${RESEARCHCLAWEVAL_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
source "$ROOT/real_eval/scripts/lib_real_eval.sh"
BASE="${REAL_EVAL_RUN_ROOT:?REAL_EVAL_RUN_ROOT is required}"
RUN_ID="${REAL_EVAL_RUN_ID:?REAL_EVAL_RUN_ID is required}"
DATASET_ROOT="${TDC_ADMET_TOX_DATASET_ROOT:-$(real_eval_resolve_topic_dataset "$ROOT" tdc_admet_tox)}"
FRAMEWORK_SRC="$(real_eval_resolve_framework_source "$ROOT" 01)"
IMAGE="ai-researcher:runtime-ready"
ENTRYPOINT_PATH="research_agent/run_infer_idea.py"
WORKSPACE="$BASE/workspace"
LOG_DIR="$BASE/logs"
LOG_FILE="$LOG_DIR/local_preflight.log"
STATE_FILE="$BASE/state.json"
MANIFEST_FILE="$BASE/local_preflight_manifest.json"
TEMPLATE_ARTIFACTS_BEFORE="$BASE/template_forbidden_artifacts.before"

check_template_clean() {
  if [[ -f "$TEMPLATE_ARTIFACTS_BEFORE" ]]; then
    real_eval_assert_no_new_forbidden_artifacts "$FRAMEWORK_SRC" "$TEMPLATE_ARTIFACTS_BEFORE"
  fi
}
trap check_template_clean EXIT

real_eval_require_clean_dir "$BASE"
mkdir -p "$WORKSPACE" "$LOG_DIR"
real_eval_snapshot_forbidden_artifacts "$FRAMEWORK_SRC" "$TEMPLATE_ARTIFACTS_BEFORE"
real_eval_rsync_repo "$FRAMEWORK_SRC" "$WORKSPACE"
real_eval_purge_cross_topic_residue "$WORKSPACE" tdc_admet_tox
chmod -R a+rwX "$WORKSPACE"
(
  cd "$WORKSPACE"
  python3 "$ROOT/real_eval/adapters/tdc_admet_tox/patch_ai_researcher.py"
)

{
  echo "[$(date -Is)] topic=tdc_admet_tox framework=AI-Researcher"
  echo "execution_kind=local_preflight_no_llm"
  echo "network=none"
  echo "workspace=$WORKSPACE"
  echo "dataset_root=$DATASET_ROOT"
  echo "native_entrypoint=$ENTRYPOINT_PATH"
  echo "runtime_image=$IMAGE"
} | tee "$LOG_FILE"

set +e
docker run --rm \
  --name "ai-researcher-tdc-local-preflight-$RUN_ID" \
  --network none \
  --cpus 4 \
  --memory 16g \
  --pids-limit 2048 \
  -e HOME=/workspace \
  -v "$WORKSPACE":/workspace \
  -v "$DATASET_ROOT":/data/tdc_admet_tox:ro \
  -w /workspace \
  --entrypoint python3 \
  "$IMAGE" \
  -c '
import csv
import json
from pathlib import Path
from research_agent.inno.tools import (
    execute_command,
    gen_code_tree_structure,
    plan_dataset,
    plan_testing,
    plan_training,
    read_file,
    run_python,
)
import research_agent.inno.agents.inno_agent.judge_agent
import research_agent.inno.agents.inno_agent.ml_agent
import research_agent.inno.agents.inno_agent.plan_agent
import research_agent.run_infer_idea

workspace = Path("/workspace")
dataset = Path("/data/tdc_admet_tox")
expected_files = {"train.csv", "validation.csv", "test.csv", "dataset_manifest.json"}
required_tools = (
    execute_command,
    gen_code_tree_structure,
    plan_dataset,
    plan_testing,
    plan_training,
    read_file,
    run_python,
)

def header(name):
    with (dataset / name).open("r", encoding="utf-8", newline="") as handle:
        return next(csv.reader(handle))

def endpoints(name):
    with (dataset / name).open("r", encoding="utf-8", newline="") as handle:
        return {row["endpoint"] for row in csv.DictReader(handle)}

checks = {
    "native_entrypoint": (workspace / "research_agent/run_infer_idea.py").is_file(),
    "native_imports": all(callable(tool) for tool in required_tools),
    "public_files": {path.name for path in dataset.iterdir() if path.is_file()} == expected_files,
    "labeled_schema": header("train.csv") == ["sample_id", "endpoint", "smiles", "label"]
        and header("validation.csv") == ["sample_id", "endpoint", "smiles", "label"],
    "test_schema_unlabeled": header("test.csv") == ["sample_id", "endpoint", "smiles"],
    "endpoints": all(
        endpoints(name) == {"AMES", "hERG", "DILI"}
        for name in ("train.csv", "validation.csv", "test.csv")
    ),
    "workspace_writable": workspace.is_dir(),
}
payload = {
    "task_id": "tdc_admet_tox",
    "framework": "AI-Researcher",
    "execution_kind": "local_preflight_no_llm",
    "network": "none",
    "checks": checks,
    "all_passed": all(checks.values()),
}
(workspace / "tdc_admet_tox_local_preflight.json").write_text(
    json.dumps(payload, ensure_ascii=True, indent=2) + "\n", encoding="utf-8"
)
print(json.dumps(payload, ensure_ascii=True, sort_keys=True))
raise SystemExit(0 if payload["all_passed"] else 1)
' 2>&1 | tee -a "$LOG_FILE"
run_rc=${PIPESTATUS[0]}
set -e

python3 - "$MANIFEST_FILE" "$STATE_FILE" "$WORKSPACE" "$run_rc" <<'PY'
from datetime import datetime, timezone
from pathlib import Path
import json
import sys

manifest_path = Path(sys.argv[1])
state_path = Path(sys.argv[2])
workspace = Path(sys.argv[3])
run_rc = int(sys.argv[4])
evidence_path = workspace / "tdc_admet_tox_local_preflight.json"
try:
    evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
except Exception:
    evidence = None
passed = run_rc == 0 and isinstance(evidence, dict) and evidence.get("all_passed") is True
manifest = {
    "task_id": "tdc_admet_tox",
    "framework": "AI-Researcher",
    "phase": "local_preflight",
    "network": "none",
    "llm_invoked": False,
    "evidence": evidence,
    "all_passed": passed,
}
manifest_path.write_text(json.dumps(manifest, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")
state = {
    "project_id": "tdc_admet_tox",
    "phase": "local_preflight",
    "status": "preflight_passed" if passed else "preflight_failed",
    "summary": (
        "AI-Researcher local no-network preflight passed; formal Codex smoke remains pending"
        if passed
        else "AI-Researcher local no-network preflight failed"
    ),
    "updated_at": datetime.now(timezone.utc).astimezone().isoformat(),
    "exit_code": run_rc,
}
state_path.write_text(json.dumps(state, ensure_ascii=True) + "\n", encoding="utf-8")
raise SystemExit(0 if passed else 1)
PY
