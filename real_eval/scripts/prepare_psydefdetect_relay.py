#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument('--provider-config', type=Path, required=True)
    p.add_argument('--client-base-url', required=True)
    p.add_argument('--client-key', required=True)
    p.add_argument('--upstream-env', type=Path, required=True)
    p.add_argument('--client-env', type=Path, required=True)
    p.add_argument('--codex-config', type=Path, required=True)
    p.add_argument('--evidence', type=Path, required=True)
    a = p.parse_args()
    text = a.provider_config.read_text(encoding='utf-8')
    model = re.search(r'^model\s*=\s*"([^"]+)"', text, re.M).group(1)
    upstream = re.search(r'^base_url\s*=\s*"([^"]+)"', text, re.M).group(1).rstrip('/')
    token = re.search(r'^experimental_bearer_token\s*=\s*"([^"]+)"', text, re.M).group(1)
    wire_match = re.search(r'^wire_api\s*=\s*"([^"]+)"', text, re.M)
    wire = (wire_match.group(1) if wire_match else 'responses').lower()
    env = {
        'KIMI_API_KEY': token,
        'KIMI_UPSTREAM_BASE_URL': upstream,
        'KIMI_RELAY_PORT': '8787',
        'KIMI_UPSTREAM_TIMEOUT_SECONDS': '300',
        'RELAY_CLIENT_API_KEY': a.client_key,
        'RELAY_UPSTREAM_WIRE_API': wire,
        'RELAY_LOG_LEVEL': 'INFO',
    }
    a.upstream_env.write_text(''.join(f'{k}={v}\n' for k, v in env.items()), encoding='utf-8')
    client = {
        'OPENAI_API_KEY': a.client_key,
        'CODEX_API_KEY': a.client_key,
        'OPENAI_BASE_URL': a.client_base_url.rstrip('/'),
        'API_BASE_URL': a.client_base_url.rstrip('/'),
        'OPENAI_MODEL': model,
    }
    a.client_env.write_text(''.join(f'{k}={v}\n' for k, v in client.items()), encoding='utf-8')
    a.codex_config.write_text(
        '\n'.join([f'model = {json.dumps(model)}', 'model_provider = "isolated_relay"',
                   'web_search = "disabled"', '', '[model_providers.isolated_relay]',
                   f'base_url = {json.dumps(a.client_base_url.rstrip("/"))}',
                   'wire_api = "responses"', f'experimental_bearer_token = {json.dumps(a.client_key)}', '']),
        encoding='utf-8')
    a.evidence.write_text(json.dumps({'model': model, 'client_base_url': a.client_base_url,
        'upstream_origin': upstream, 'relay_upstream_wire_api': wire,
        'public_network_visible_to_framework': False}, indent=2) + '\n', encoding='utf-8')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
