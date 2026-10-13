#!/usr/bin/env bash
set -euo pipefail

ROOT="${RESEARCHCLAWEVAL_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
FRAMEWORK_CONFIG="${REAL_EVAL_FRAMEWORK_CONFIG:-$ROOT/real_eval/config/seven_babylm_kimi_method_free_20260810_frameworks.json}"
PROVIDER_CONFIG="${PROVIDER_CONFIG:-$ROOT/api/codex_kimi_k27_code_relay_container.toml}"
MODEL="${REAL_EVAL_MODEL:-kimi-k2.6}"
DATASET_ROOT="${BABYLM_DATASET_ROOT:-$ROOT/BabyLM-2026-Strict-Small}"
CONTRACT_FILE="${BABYLM_CONTRACT_FILE:-$ROOT/automation/babylm_method_free_contract.md}"
ADMISSION_ROOT="${REAL_EVAL_ADMISSION_ROOT:-$ROOT/real_eval/admissions/babylm_kimi}"
OUTPUT="${REAL_EVAL_PREFLIGHT_OUTPUT:-$ADMISSION_ROOT/preflight.json}"

echo "[preflight] BabyLM Kimi relay preflight"
echo "  model=$MODEL"
echo "  dataset=$DATASET_ROOT"
echo "  contract=$CONTRACT_FILE"
echo "  output=$OUTPUT"

[[ "$MODEL" == "kimi-k2.6" ]] || { echo "model must be kimi-k2.6" >&2; exit 2; }

BASE_URL=$(sed -n 's/^[[:space:]]*base_url[[:space:]]*=[[:space:]]*"\(.*\)"[[:space:]]*$/\1/p' "$PROVIDER_CONFIG" | head -1)
[[ -n "$BASE_URL" ]] || { echo "cannot extract base_url from $PROVIDER_CONFIG" >&2; exit 3; }
[[ "$BASE_URL" == "http://host.docker.internal:8787/v1" ]] || { echo "base_url must be kimi relay" >&2; exit 4; }

[[ -f "$FRAMEWORK_CONFIG" ]] || { echo "missing framework config: $FRAMEWORK_CONFIG" >&2; exit 5; }
[[ -f "$PROVIDER_CONFIG" ]] || { echo "missing provider config: $PROVIDER_CONFIG" >&2; exit 6; }
[[ -d "$DATASET_ROOT" ]] || { echo "missing dataset root: $DATASET_ROOT" >&2; exit 7; }
[[ -f "$CONTRACT_FILE" ]] || { echo "missing contract file: $CONTRACT_FILE" >&2; exit 8; }

mkdir -p "$ADMISSION_ROOT"

python3 - "$FRAMEWORK_CONFIG" "$ADMISSION_ROOT" <<'PY'
import json, sys
from pathlib import Path
config = json.loads(Path(sys.argv[1]).read_text())
out = Path(sys.argv[2])
for fw in config["frameworks"]:
    row = {
        "id": fw["id"],
        "name": fw["name"],
        "runtime_image": (fw.get("required_images") or [None])[0],
        "source_dir": fw.get("source_dir", ""),
        "native_probe_paths": fw.get("native_probe_paths", []),
    }
    (out / f"{fw['id']}.json").write_text(json.dumps(row) + "\n")
PY

ALL_PASSED=1
for fw_json in "$ADMISSION_ROOT"/0*.json; do
    fw_id=$(python3 -c "import json; print(json.loads(open('$fw_json').read())['id'])")
    fw_name=$(python3 -c "import json; print(json.loads(open('$fw_json').read())['name'])")
    image=$(python3 -c "import json; print(json.loads(open('$fw_json').read())['runtime_image'])")
    source_dir=$(python3 -c "import json; print(json.loads(open('$fw_json').read())['source_dir'])")
    probe_paths=$(python3 -c "import json; print(json.dumps(json.loads(open('$fw_json').read())['native_probe_paths']))")

    echo "[preflight] framework $fw_id ($fw_name): image=$image"

    ws_probe="$ADMISSION_ROOT/ws_probe_$fw_id"
    rm -rf "$ws_probe"
    mkdir -p "$ws_probe"

    probe_output="$ADMISSION_ROOT/probe_${fw_id}.json"
    IMAGE_DIGEST=""

    if docker image inspect "$image" >/dev/null 2>&1; then
        IMAGE_DIGEST=$(docker image inspect "$image" --format '{{.Id}}' 2>/dev/null || echo "")
    fi

    docker run --rm \
        --add-host=host.docker.internal:host-gateway \
        --user 0:0 \
        -v "$ROOT/$source_dir:/framework-source:ro" \
        -v "$DATASET_ROOT:/data/BabyLM-2026-Strict-Small:ro" \
        -v "$CONTRACT_FILE:/input/babylm_method_free_contract.md:ro" \
        -v "$ROOT/real_eval/scripts/babylm_kimi_admission_probe.py:/input/admission_probe.py:ro" \
        -v "$ws_probe:/workspace-admission" \
        -e FRAMEWORK_ID="$fw_id" \
        -e NATIVE_PROBE_PATHS="$probe_paths" \
        -e OPENAI_API_KEY="${OPENAI_API_KEY}" \
        -e OPENAI_BASE_URL="http://host.docker.internal:8787/v1" \
        -e OPENAI_MODEL="$MODEL" \
        --entrypoint python3 \
        "$image" \
        /input/admission_probe.py > "$probe_output" 2>/dev/null || true

    python3 - "$probe_output" "$fw_id" "$IMAGE_DIGEST" "$image" <<'PY'
import json, sys
from pathlib import Path
result = json.loads(Path(sys.argv[1]).read_text())
result["runtime_image"] = sys.argv[4]
result["runtime_image_digest"] = sys.argv[3]
Path(sys.argv[1]).write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
PY

    fw_passed=$(python3 -c "import json; r=json.loads(open('$probe_output').read()); print('true' if r.get('all_passed') else 'false')")
    echo "  result: all_passed=$fw_passed"
    if [[ "$fw_passed" != "true" ]]; then
        ALL_PASSED=0
    fi
done

python3 - "$OUTPUT" "$MODEL" "$ALL_PASSED" "$ADMISSION_ROOT" <<'PY'
import json, sys
from datetime import datetime, timezone
from pathlib import Path
output = Path(sys.argv[1])
frameworks = []
for f in sorted(Path(sys.argv[4]).glob("probe_*.json")):
    data = json.loads(f.read_text())
    frameworks.append(data)
payload = {
    "topic_id": "babylm",
    "model_id": sys.argv[2],
    "status": "passed" if sys.argv[3] == "1" else "failed",
    "created_at": datetime.now(timezone.utc).astimezone().isoformat(),
    "frameworks": frameworks,
}
output.parent.mkdir(parents=True, exist_ok=True)
output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
PY

echo "[preflight] status=$(python3 -c "import json; print(json.loads(open('$OUTPUT').read())['status'])")"
echo "$OUTPUT"