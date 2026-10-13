#!/usr/bin/env bash
set -euo pipefail

ROOT="${RESEARCHCLAWEVAL_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
UPSTREAM_PROVIDER_CONFIG="${DEEPSEEK_UPSTREAM_PROVIDER_CONFIG:-$ROOT/api/codex_deepseek_v4_flash_bianxie.toml}"
CLIENT_PROVIDER_CONFIG="${DEEPSEEK_CLIENT_PROVIDER_CONFIG:-$ROOT/api/codex_deepseek_v4_flash_bianxie_relay_container.toml}"
IMAGE="${DEEPSEEK_RELAY_IMAGE:-researchclaweval/codex-kimi-relay:test}"
CONTAINER="${DEEPSEEK_RELAY_CONTAINER:-researchclaweval-codex-deepseek-relay}"
PORT="${DEEPSEEK_RELAY_PORT:-8788}"
BIND_HOST="${DEEPSEEK_RELAY_BIND_HOST:-172.17.0.1}"
[[ -f "$UPSTREAM_PROVIDER_CONFIG" ]] || { echo "DeepSeek upstream provider config is missing" >&2; exit 11; }
[[ -f "$CLIENT_PROVIDER_CONFIG" ]] || { echo "DeepSeek client provider config is missing" >&2; exit 11; }
UPSTREAM="$(sed -n 's/^[[:space:]]*base_url[[:space:]]*=[[:space:]]*"\(.*\)"[[:space:]]*$/\1/p' "$UPSTREAM_PROVIDER_CONFIG" | head -1)"
UPSTREAM_API_KEY="$(sed -n 's/^[[:space:]]*experimental_bearer_token[[:space:]]*=[[:space:]]*"\(.*\)"[[:space:]]*$/\1/p' "$UPSTREAM_PROVIDER_CONFIG" | head -1)"
UPSTREAM_MODEL="$(sed -n 's/^[[:space:]]*model[[:space:]]*=[[:space:]]*"\(.*\)"[[:space:]]*$/\1/p' "$UPSTREAM_PROVIDER_CONFIG" | head -1)"
CLIENT_API_KEY="$(sed -n 's/^[[:space:]]*experimental_bearer_token[[:space:]]*=[[:space:]]*"\(.*\)"[[:space:]]*$/\1/p' "$CLIENT_PROVIDER_CONFIG" | head -1)"
HEALTH_URL="http://${BIND_HOST}:${PORT}/healthz"

[[ "$UPSTREAM" == "https://api.bianxie.ai/v1" ]] || { echo "DeepSeek upstream must be https://api.bianxie.ai/v1" >&2; exit 12; }
[[ "$UPSTREAM_MODEL" == "deepseek-v4-flash" ]] || { echo "DeepSeek upstream model must be deepseek-v4-flash" >&2; exit 13; }
[[ -n "$UPSTREAM_API_KEY" ]] || { echo "DeepSeek upstream API key is missing" >&2; exit 14; }
[[ -n "$CLIENT_API_KEY" ]] || { echo "DeepSeek relay client API key is missing" >&2; exit 14; }

declare -a relay_source_args=()
if [[ "${DEEPSEEK_RELAY_SKIP_BUILD:-0}" != "1" ]]; then
  docker build -t "$IMAGE" "$ROOT/real_eval/codex_relay"
else
  relay_source_args+=(-v "$ROOT/real_eval/codex_relay/relay.py:/app/relay.py:ro")
fi
docker rm -f "$CONTAINER" >/dev/null 2>&1 || true
docker run -d \
  --name "$CONTAINER" \
  --add-host=host.docker.internal:host-gateway \
  -p "${BIND_HOST}:${PORT}:8787" \
  -e "KIMI_API_KEY=$UPSTREAM_API_KEY" \
  -e "KIMI_UPSTREAM_BASE_URL=$UPSTREAM" \
  -e "KIMI_RELAY_PORT=8787" \
  -e "RELAY_CLIENT_API_KEY=$CLIENT_API_KEY" \
  -e "RELAY_UPSTREAM_PROVIDER=bianxie" \
  "${relay_source_args[@]}" \
  "$IMAGE" >/dev/null

for ((attempt = 1; attempt <= 30; attempt++)); do
  if curl -fsS "$HEALTH_URL" >/dev/null 2>&1; then
    printf 'container=%s\n' "$CONTAINER"
    printf 'health=%s\n' "$HEALTH_URL"
    printf 'bind_host=%s\n' "$BIND_HOST"
    printf 'upstream_model=%s\n' "$UPSTREAM_MODEL"
    exit 0
  fi
  sleep 1
done

echo "DeepSeek relay container did not become healthy at $HEALTH_URL" >&2
docker logs --tail 80 "$CONTAINER" >&2 || echo "Unable to read logs for $CONTAINER" >&2
exit 15
