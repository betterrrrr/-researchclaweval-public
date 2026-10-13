#!/usr/bin/env bash
set -euo pipefail

ROOT="${RESEARCHCLAWEVAL_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
IMAGE="${KIMI_RELAY_IMAGE:-researchclaweval/codex-kimi-relay:test}"
CONTAINER="${KIMI_RELAY_CONTAINER:-researchclaweval-codex-kimi-relay}"
PORT="${KIMI_RELAY_PORT:-8787}"
BIND_HOST="${KIMI_RELAY_BIND_HOST:-0.0.0.0}"
UPSTREAM="${KIMI_UPSTREAM_BASE_URL:-https://api.bianxie.ai/v1}"
HEALTH_URL="http://127.0.0.1:${PORT}/healthz"

if [[ -z "${KIMI_API_KEY:-}" ]]; then
  echo "KIMI_API_KEY is required" >&2
  exit 12
fi

declare -a relay_source_args=()
if [[ "${KIMI_RELAY_SKIP_BUILD:-0}" != "1" ]]; then
  docker build -t "$IMAGE" "$ROOT/real_eval/codex_relay"
else
  relay_source_args+=(-v "$ROOT/real_eval/codex_relay/relay.py:/app/relay.py:ro")
fi
docker rm -f "$CONTAINER" >/dev/null 2>&1 || true
docker run -d \
  --name "$CONTAINER" \
  --add-host=host.docker.internal:host-gateway \
  -p "${BIND_HOST}:${PORT}:8787" \
  -e KIMI_API_KEY \
  -e "KIMI_UPSTREAM_BASE_URL=$UPSTREAM" \
  -e "KIMI_RELAY_PORT=8787" \
  "${relay_source_args[@]}" \
  "$IMAGE" >/dev/null

for ((attempt = 1; attempt <= 30; attempt++)); do
  if curl -fsS "$HEALTH_URL" >/dev/null 2>&1; then
    printf 'container=%s\n' "$CONTAINER"
    printf 'health=%s\n' "$HEALTH_URL"
    exit 0
  fi
  sleep 1
done

echo "Relay container did not become healthy at $HEALTH_URL" >&2
echo "Recent relay container logs:" >&2
docker logs --tail 80 "$CONTAINER" >&2 || echo "Unable to read logs for $CONTAINER" >&2
exit 13
