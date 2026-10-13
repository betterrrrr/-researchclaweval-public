#!/usr/bin/env bash
set -euo pipefail

ROOT="${RESEARCHCLAWEVAL_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
CONFIG="${REAL_EVAL_FRAMEWORK_CONFIG:-$ROOT/real_eval/config/seven_psydefdetect_deepseek_fullrun_frameworks.json}"
PROVIDER_CONFIG="${PROVIDER_CONFIG:-$ROOT/api/codex_deepseek_v4_flash_bianxie_relay_container.toml}"
MODEL="${PSYDEFDETECT_EVAL_MODEL:-deepseek-v4-flash}"
RELAY_PORT="${DEEPSEEK_RELAY_PORT:-8788}"
BASE_URL="$(sed -n 's/^[[:space:]]*base_url[[:space:]]*=[[:space:]]*"\(.*\)"[[:space:]]*$/\1/p' "$PROVIDER_CONFIG" | head -1)"
RELAY_API_KEY="$(sed -n 's/^[[:space:]]*experimental_bearer_token[[:space:]]*=[[:space:]]*"\(.*\)"[[:space:]]*$/\1/p' "$PROVIDER_CONFIG" | head -1)"
EXPECTED_BASE_URL="http://host.docker.internal:${RELAY_PORT}/v1"

[[ -f "$CONFIG" && -f "$PROVIDER_CONFIG" ]] || { echo "missing DeepSeek framework/provider config" >&2; exit 2; }
[[ "$MODEL" == "deepseek-v4-flash" ]] || { echo "DeepSeek evaluation model must be deepseek-v4-flash, got: $MODEL" >&2; exit 3; }
[[ "$BASE_URL" == "$EXPECTED_BASE_URL" ]] || { echo "DeepSeek relay must use Docker-bridge URL $EXPECTED_BASE_URL" >&2; exit 4; }
[[ -n "$RELAY_API_KEY" ]] || { echo "DeepSeek relay API key is missing" >&2; exit 5; }
export RELAY_API_KEY BASE_URL MODEL

mapfile -t images < <(python3 - "$CONFIG" <<'PY'
import json
import sys

payload = json.load(open(sys.argv[1], encoding="utf-8"))
seen = set()
for item in payload["frameworks"]:
    if item.get("expected_status") in {
        "unsupported_native_entrypoint",
        "blocked_benchmark_authorization",
    }:
        continue
    for image in item.get("required_images", []):
        if image not in seen:
            seen.add(image)
            print(image)
PY
)

for image in "${images[@]}"; do
  docker run --rm \
    --add-host=host.docker.internal:host-gateway \
    -e RELAY_API_KEY \
    -e BASE_URL \
    -e MODEL \
    --entrypoint python3 \
    "$image" -c '
import json
import os
import urllib.request

body = json.dumps({
    "model": os.environ["MODEL"],
    "input": "Reply with exactly RELAY_OK.",
    "max_output_tokens": 16,
}).encode("utf-8")
request = urllib.request.Request(
    os.environ["BASE_URL"].rstrip("/") + "/responses",
    data=body,
    headers={
        "Authorization": "Bearer " + os.environ["RELAY_API_KEY"],
        "Content-Type": "application/json",
    },
    method="POST",
)
with urllib.request.urlopen(request, timeout=90) as response:
    payload = json.load(response)
if not isinstance(payload, dict) or not payload.get("id"):
    raise SystemExit("relay response missing response id")
' >/dev/null
  printf 'DEEPSEEK_RELAY_IMAGE_OK image=%s model=%s base_url=%s\n' "$image" "$MODEL" "$BASE_URL"
done
