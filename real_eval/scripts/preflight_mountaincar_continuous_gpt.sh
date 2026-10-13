#!/usr/bin/env bash
set -euo pipefail

ROOT="${RESEARCHCLAWEVAL_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
CONFIG="${REAL_EVAL_FRAMEWORK_CONFIG:?REAL_EVAL_FRAMEWORK_CONFIG is required}"
PROVIDER_CONFIG="${PROVIDER_CONFIG:-$ROOT/api/codex_gpt54_shubiaobiao.toml}"
MODEL="${MOUNTAINCAR_CONTINUOUS_MODEL:-gpt-5.4}"
TOPIC_ROOT="${MOUNTAINCAR_CONTINUOUS_DATASET_ROOT:-$ROOT/data/mountaincar_continuous}"
CONTRACT_FILE="${MOUNTAINCAR_CONTINUOUS_CONTRACT_FILE:-$ROOT/automation/mountaincar_continuous_contract.md}"
ADMISSION_ROOT="${REAL_EVAL_ADMISSION_ROOT:?REAL_EVAL_ADMISSION_ROOT is required}"
OUTPUT="${REAL_EVAL_ADMISSION_OUTPUT:-$ADMISSION_ROOT/gpt_preflight.json}"
MC_PYTHON="${MOUNTAINCAR_CONTINUOUS_PYTHON:-$ROOT/.venvs/mountaincar/bin/python}"
BASE_URL="$(sed -n 's/^[[:space:]]*base_url[[:space:]]*=[[:space:]]*"\(.*\)"[[:space:]]*$/\1/p' "$PROVIDER_CONFIG" | head -1)"
API_KEY="$(sed -n 's/^[[:space:]]*experimental_bearer_token[[:space:]]*=[[:space:]]*"\(.*\)"[[:space:]]*$/\1/p' "$PROVIDER_CONFIG" | head -1)"

[[ "$MODEL" == "gpt-5.4" ]] || { echo "unexpected model: $MODEL" >&2; exit 2; }
[[ -n "$BASE_URL" && -n "$API_KEY" && -f "$CONFIG" && -d "$TOPIC_ROOT" && -f "$CONTRACT_FILE" ]] || { echo "missing MountainCar admission input" >&2; exit 4; }
[[ -f "$TOPIC_ROOT/protected/evaluate.py" ]] || { echo "missing protected evaluator" >&2; exit 5; }
[[ -d "$TOPIC_ROOT/src" ]] || { echo "missing starter code" >&2; exit 6; }
[[ -x "$MC_PYTHON" ]] || { echo "missing MountainCar JAX python: $MC_PYTHON" >&2; exit 7; }
"$MC_PYTHON" -c 'import jax, gymnax, flax, optax, tensorflow_probability, dotmap' >/dev/null 2>&1 || { echo "MountainCar scorer dependency (jax/gymnax/flax/optax/tfp) unavailable" >&2; exit 8; }

mkdir -p "$ADMISSION_ROOT/frameworks"

# Emit framework rows (runtime image, source dir, native probe paths, image digest)
ROWS_FILE="$ADMISSION_ROOT/framework_rows.jsonl"
python3 - "$CONFIG" <<'PY' > "$ROWS_FILE"
import json, sys
config = json.load(open(sys.argv[1], encoding="utf-8"))
for row in config["frameworks"]:
    print(json.dumps({
        "id": row["id"],
        "runtime_image": row["required_images"][0],
        "source_dir": row["source_dir"],
        "native_probe_paths": row.get("native_probe_paths", []),
    }))
PY

while IFS= read -r row; do
  framework_id="$(python3 -c 'import json,sys; print(json.loads(sys.argv[1])["id"])' "$row")"
  image="$(python3 -c 'import json,sys; print(json.loads(sys.argv[1])["runtime_image"])' "$row")"
  source_dir="$(python3 -c 'import json,sys; print(json.loads(sys.argv[1])["source_dir"])' "$row")"
  probe_paths="$(python3 -c 'import json,sys; print(json.dumps(json.loads(sys.argv[1])["native_probe_paths"]))' "$row")"
  probe_output="$ADMISSION_ROOT/framework_${framework_id}_probe.json"

  # Native probe path existence check (host-side; does not require image JAX)
  python3 - "$ROOT/$source_dir" "$probe_paths" "$framework_id" "$image" "$BASE_URL" "$MODEL" "$probe_output" <<'PY'
from pathlib import Path
import json, sys
source = Path(sys.argv[1])
probe_paths = json.loads(sys.argv[2])
framework_id = sys.argv[3]
image = sys.argv[4]
base_url = sys.argv[5]
model = sys.argv[6]
out = Path(sys.argv[7])
missing = [p for p in probe_paths if not (source / p).exists()]
payload = {
    "framework_id": framework_id,
    "model_id": model,
    "container_base_url": base_url,
    "runtime_image": image,
    "native_entrypoint_probe": not missing,
    "missing_probe_paths": missing,
    "status": "passed" if not missing else "failed",
}
out.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
PY
  digest="$(docker image inspect "$image" --format '{{index .RepoDigests 0}}' 2>/dev/null || true)"
  if [[ "$digest" == *@sha256:* ]]; then
    digest="sha256:${digest##*@sha256:}"
  else
    digest="$(docker image inspect "$image" --format 'sha256:{{.Id}}' 2>/dev/null | sed 's/^sha256:sha256:/sha256:/' || true)"
  fi
  python3 - "$probe_output" "$image" "$digest" <<'PY'
from pathlib import Path
import json, sys
p = Path(sys.argv[1])
payload = json.loads(p.read_text(encoding="utf-8"))
payload["runtime_image"] = sys.argv[2]
payload["runtime_image_digest"] = sys.argv[3] or None
p.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
PY
done < "$ROWS_FILE"

python3 - "$ADMISSION_ROOT" "$OUTPUT" <<'PY'
from datetime import datetime, timezone
from pathlib import Path
import json, sys
root = Path(sys.argv[1])
rows = []
for index in range(1, 8):
    p = root / f"framework_{index:02d}_probe.json"
    if p.is_file():
        rows.append(json.loads(p.read_text(encoding="utf-8")))
payload = {
    "topic_id": "mountaincar_continuous",
    "model_id": "gpt-5.4",
    "status": "passed" if rows and all(r.get("status") == "passed" for r in rows) else "failed",
    "created_at": datetime.now(timezone.utc).astimezone().isoformat(),
    "frameworks": rows,
}
Path(sys.argv[2]).write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
if payload["status"] != "passed":
    raise SystemExit(2)
PY

printf 'MOUNTAINCAR_CONTINUOUS_GPT_ADMISSION=%s\n' "$OUTPUT"
