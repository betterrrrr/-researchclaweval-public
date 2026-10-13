#!/usr/bin/env bash
set -euo pipefail

ROOT="${RESEARCHCLAWEVAL_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
CONFIG="${REAL_EVAL_FRAMEWORK_CONFIG:?REAL_EVAL_FRAMEWORK_CONFIG is required}"
PROVIDER_CONFIG="${PROVIDER_CONFIG:-$ROOT/api/codex_kimi_k27_code_relay_container.toml}"
MODEL="${ARC_WBE_2026_MODEL:-kimi-k2.6}"
DATASET_ROOT="${ARC_WBE_2026_DATASET_ROOT:-$ROOT/data/arc_white_box_estimation_2026/baked/mini}"
CONTRACT_FILE="${ARC_WBE_2026_CONTRACT_FILE:-$ROOT/automation/arc_wbe_2026_contract.md}"
ADMISSION_ROOT="${REAL_EVAL_ADMISSION_ROOT:?REAL_EVAL_ADMISSION_ROOT is required}"
OUTPUT="${REAL_EVAL_ADMISSION_OUTPUT:-$ADMISSION_ROOT/kimi_preflight.json}"
WHEST_PYTHON="${ARC_WBE_2026_WHEST_PYTHON:-/tmp/whest-starterkit/.venv/bin/python}"
BASE_URL="$(sed -n 's/^[[:space:]]*base_url[[:space:]]*=[[:space:]]*"\(.*\)"[[:space:]]*$/\1/p' "$PROVIDER_CONFIG" | head -1)"
API_KEY="$(sed -n 's/^[[:space:]]*experimental_bearer_token[[:space:]]*=[[:space:]]*"\(.*\)"[[:space:]]*$/\1/p' "$PROVIDER_CONFIG" | head -1)"

[[ "$MODEL" == "kimi-k2.6" ]] || { echo "unexpected model: $MODEL" >&2; exit 2; }
[[ "$BASE_URL" == "http://host.docker.internal:8787/v1" ]] || { echo "unexpected relay base URL: $BASE_URL" >&2; exit 3; }
[[ -n "$API_KEY" && -f "$CONFIG" && -d "$DATASET_ROOT" && -f "$CONTRACT_FILE" ]] || { echo "missing Topic 3 admission input" >&2; exit 4; }
[[ -x "$WHEST_PYTHON" ]] || { echo "missing ARC scorer Python: $WHEST_PYTHON" >&2; exit 5; }
"$WHEST_PYTHON" -c 'import pyarrow' >/dev/null 2>&1 || { echo "ARC scorer dependency pyarrow is unavailable" >&2; exit 6; }

mkdir -p "$ADMISSION_ROOT/frameworks"
PROJECTED_DATASET="$ADMISSION_ROOT/arc_wbe_2026_weights_only"
"$WHEST_PYTHON" "$ROOT/automation/scripts/generate_arc_wbe_2026_weights_only_dataset.py" \
  --source-root "$DATASET_ROOT" \
  --output-root "$PROJECTED_DATASET"

ROWS_FILE="$ADMISSION_ROOT/framework_rows.jsonl"
python3 - "$CONFIG" <<'PY' > "$ROWS_FILE"
import json
import sys

config = json.load(open(sys.argv[1], encoding="utf-8"))
for row in config["frameworks"]:
    print(json.dumps({
        "id": row["id"],
        "runtime_image": row["required_images"][0],
        "source_dir": row["source_dir"],
        "native_probe_paths": row["native_probe_paths"],
    }))
PY

while IFS= read -r row; do
  framework_id="$(python3 -c 'import json,sys; print(json.loads(sys.argv[1])["id"])' "$row")"
  image="$(python3 -c 'import json,sys; print(json.loads(sys.argv[1])["runtime_image"])' "$row")"
  source_dir="$(python3 -c 'import json,sys; print(json.loads(sys.argv[1])["source_dir"])' "$row")"
  probe_paths="$(python3 -c 'import json,sys; print(json.dumps(json.loads(sys.argv[1])["native_probe_paths"]))' "$row")"
  workspace_probe="$ADMISSION_ROOT/frameworks/$framework_id"
  mkdir -p "$workspace_probe"
  probe_output="$ADMISSION_ROOT/framework_${framework_id}_probe.json"
  docker run --rm \
    --add-host=host.docker.internal:host-gateway \
    --user 0:0 \
    --entrypoint python3 \
    -e OPENAI_API_KEY="$API_KEY" \
    -v "$ROOT/$source_dir":/framework-source:ro \
    -v "$PROJECTED_DATASET":/data/arc_wbe_2026:ro \
    -v "$CONTRACT_FILE":/input/arc_wbe_2026_contract.md:ro \
    -v "$ROOT/automation/scripts/run_arc_wbe_2026_local_score.py":/input/run_arc_wbe_2026_local_score.py:ro \
    -v "$ROOT/automation/scripts/arc_wbe_2026_official_adapter.py":/input/arc_wbe_2026_official_adapter.py:ro \
    -v "$ROOT/automation/scripts/prepare_arc_wbe_2026_dataset.py":/input/prepare_arc_wbe_2026_dataset.py:ro \
    -v "$ROOT/real_eval/scripts/arc_wbe_2026_kimi_admission_probe.py":/input/admission_probe.py:ro \
    -v "$workspace_probe":/workspace-admission \
    "$image" /input/admission_probe.py \
      --framework-id "$framework_id" \
      --base-url "$BASE_URL" \
      --model "$MODEL" \
      --native-probe-paths-json "$probe_paths" > "$probe_output"
  digest="$(docker image inspect "$image" --format '{{index .RepoDigests 0}}' 2>/dev/null || true)"
  if [[ "$digest" == *@sha256:* ]]; then
    digest="sha256:${digest##*@sha256:}"
  else
    digest="$(docker image inspect "$image" --format 'sha256:{{.Id}}' | sed 's/^sha256:sha256:/sha256:/')"
  fi
  python3 - "$probe_output" "$image" "$digest" <<'PY'
from pathlib import Path
import json
import sys

path = Path(sys.argv[1])
payload = json.loads(path.read_text(encoding="utf-8"))
payload["runtime_image"] = sys.argv[2]
payload["runtime_image_digest"] = sys.argv[3]
path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
PY
done < "$ROWS_FILE"

python3 - "$ADMISSION_ROOT" "$OUTPUT" <<'PY'
from datetime import datetime, timezone
from pathlib import Path
import json
import sys

root = Path(sys.argv[1])
rows = [json.loads((root / f"framework_{index:02d}_probe.json").read_text(encoding="utf-8")) for index in range(1, 8)]
payload = {
    "topic_id": "arc_wbe_2026",
    "model_id": "kimi-k2.6",
    "status": "passed" if all(row.get("status") == "passed" for row in rows) else "failed",
    "created_at": datetime.now(timezone.utc).astimezone().isoformat(),
    "frameworks": rows,
}
Path(sys.argv[2]).write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
if payload["status"] != "passed":
    raise SystemExit(2)
PY

printf 'ARC_WBE_2026_KIMI_ADMISSION=%s\n' "$OUTPUT"
