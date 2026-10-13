#!/usr/bin/env bash
set -euo pipefail

ROOT="${RESEARCHCLAWEVAL_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
CONFIG="${REAL_EVAL_FRAMEWORK_CONFIG:-$ROOT/real_eval/config/seven_psydefdetect_kimi_fullrun_frameworks.json}"
PROVIDER_CONFIG="${PROVIDER_CONFIG:-$ROOT/api/codex_kimi_k27_code_relay_container.toml}"
MODEL="${PSYDEFDETECT_EVAL_MODEL:-kimi-k2.6}"
BASE_URL="$(sed -n 's/^[[:space:]]*base_url[[:space:]]*=[[:space:]]*"\(.*\)"[[:space:]]*$/\1/p' "$PROVIDER_CONFIG" | head -1)"
RELAY_API_KEY="$(sed -n 's/^[[:space:]]*experimental_bearer_token[[:space:]]*=[[:space:]]*"\(.*\)"[[:space:]]*$/\1/p' "$PROVIDER_CONFIG" | head -1)"

[[ -f "$CONFIG" && -f "$PROVIDER_CONFIG" ]] || { echo "missing Kimi framework/provider config" >&2; exit 2; }
[[ "$MODEL" == "kimi-k2.6" ]] || { echo "Kimi evaluation model must be kimi-k2.6, got: $MODEL" >&2; exit 3; }
[[ "$BASE_URL" == "http://host.docker.internal:8787/v1" ]] || { echo "Kimi relay must use Docker-bridge URL http://host.docker.internal:8787/v1" >&2; exit 4; }
[[ -n "$RELAY_API_KEY" ]] || { echo "Kimi relay API key is missing" >&2; exit 5; }
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
  printf 'KIMI_RELAY_IMAGE_OK image=%s model=%s base_url=%s\n' "$image" "$MODEL" "$BASE_URL"
done
