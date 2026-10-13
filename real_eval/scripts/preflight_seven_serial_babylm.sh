#!/usr/bin/env bash
set -euo pipefail

ROOT="${RESEARCHCLAWEVAL_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
CONFIG="${REAL_EVAL_FRAMEWORK_CONFIG:-$ROOT/real_eval/config/seven_babylm_frameworks.json}"
DATASET_ROOT="${BABYLM_DATASET_ROOT:-$ROOT/BabyLM-2026-Strict-Small}"
CONTRACT_FILE="${BABYLM_CONTRACT_FILE:-$ROOT/BabyLM-10M_七框架任务包装与分发指南.md}"

if [[ ! -f "$CONFIG" ]]; then
  echo "missing config: $CONFIG" >&2
  exit 2
fi
if [[ ! -d "$DATASET_ROOT" ]]; then
  echo "missing dataset root: $DATASET_ROOT" >&2
  exit 3
fi
if [[ ! -f "$CONTRACT_FILE" ]]; then
  echo "missing contract file: $CONTRACT_FILE" >&2
  exit 4
fi
if ! command -v docker >/dev/null 2>&1; then
  echo "docker not found" >&2
  exit 5
fi
if ! docker info >/dev/null 2>&1; then
  echo "docker daemon not reachable" >&2
  exit 6
fi

python3 - "$ROOT" "$CONFIG" <<'PY'
from pathlib import Path
import json
import subprocess
import sys

root = Path(sys.argv[1])
config = Path(sys.argv[2])
data = json.loads(config.read_text(encoding="utf-8"))
errors = []
rows = []
for item in data["frameworks"]:
    wrapper = root / item["wrapper"]
    wrapper_ok = wrapper.exists()
    wrapper_text = wrapper.read_text(encoding="utf-8", errors="ignore") if wrapper_ok else ""
    missing_paths = []
    for rel_path in item.get("required_paths", []):
        p = root / rel_path
        if not p.exists():
            missing_paths.append(rel_path)
    missing_images = []
    for image in item.get("required_images", []):
        rc = subprocess.run(["docker", "image", "inspect", image], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode
        if rc != 0:
            missing_images.append(image)
    clean_dir_guard = 'real_eval_require_clean_dir "$BASE"' in wrapper_text
    uses_resume_source = (
        "SOURCE_RUN_ID=" in wrapper_text
        or "source_workplace" in wrapper_text
        or "resume_repair" in wrapper.name
        or "_resume_" in wrapper.name
    )
    shared_root_bind = '-v "$ROOT":/repo' in wrapper_text or '-v "$ROOT":/workspace' in wrapper_text
    rows.append({
        "id": item["id"],
        "name": item["name"],
        "wrapper": str(wrapper.relative_to(root)) if wrapper.exists() else item["wrapper"],
        "wrapper_ok": wrapper_ok,
        "clean_dir_guard": clean_dir_guard,
        "uses_resume_source": uses_resume_source,
        "shared_root_bind": shared_root_bind,
        "missing_paths": missing_paths,
        "missing_images": missing_images,
    })
    if (not wrapper_ok) or missing_paths or missing_images or (not clean_dir_guard) or uses_resume_source or shared_root_bind:
        errors.append(item["id"])

for row in rows:
    print(json.dumps(row, ensure_ascii=False))

if errors:
    raise SystemExit(10)
PY
