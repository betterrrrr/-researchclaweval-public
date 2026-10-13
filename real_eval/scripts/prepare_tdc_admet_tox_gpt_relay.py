#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

try:
    import tomllib as toml_parser
except ModuleNotFoundError:
    import toml as toml_parser


def fail(message: str) -> None:
    raise SystemExit(message)


def checked_env_value(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip() or "\n" in value or "\r" in value:
        fail(f"provider {field} is missing or invalid")
    return value.strip()


def write_env(path: Path, values: dict[str, str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(f"{key}={value}\n" for key, value in values.items()), encoding="utf-8")
    path.chmod(0o600)


def main() -> int:
    parser = argparse.ArgumentParser(description="Prepare an isolated Topic 5 GPT relay.")
    parser.add_argument("--provider-config", type=Path, required=True)
    parser.add_argument("--client-base-url", required=True)
    parser.add_argument("--client-key", required=True)
    parser.add_argument("--upstream-env", type=Path, required=True)
    parser.add_argument("--client-env", type=Path, required=True)
    parser.add_argument("--codex-config", type=Path, required=True)
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--evaluation-variant")
    args = parser.parse_args()

    provider_path = args.provider_config.resolve()
    payload = toml_parser.loads(provider_path.read_text(encoding="utf-8"))
    model = checked_env_value(payload.get("model"), "model")
    variant = (
        checked_env_value(args.evaluation_variant, "evaluation_variant")
        if args.evaluation_variant
        else ("ds" if model.startswith("deepseek") else "gpt")
    )
    provider_name = checked_env_value(payload.get("model_provider"), "model_provider")
    providers = payload.get("model_providers")
    if not isinstance(providers, dict) or not isinstance(providers.get(provider_name), dict):
        fail(f"provider section model_providers.{provider_name} is missing")
    provider = providers[provider_name]
    upstream_base_url = checked_env_value(provider.get("base_url"), "base_url").rstrip("/")
    upstream_key = checked_env_value(
        provider.get("experimental_bearer_token"), "experimental_bearer_token"
    )
    wire_api = checked_env_value(provider.get("wire_api"), "wire_api").lower()
    if wire_api not in {"chat", "responses"}:
        fail(f"unsupported upstream wire_api: {wire_api}")
    client_base_url = args.client_base_url.rstrip("/")
    client_key = checked_env_value(args.client_key, "client_key")

    write_env(
        args.upstream_env,
        {
            "KIMI_API_KEY": upstream_key,
            "KIMI_UPSTREAM_BASE_URL": upstream_base_url,
            "KIMI_RELAY_PORT": "8787",
            "KIMI_UPSTREAM_TIMEOUT_SECONDS": "900",
            "RELAY_CLIENT_API_KEY": client_key,
            "RELAY_UPSTREAM_WIRE_API": wire_api,
            "RELAY_UPSTREAM_RETRY_COUNT": "6",
            "RELAY_LOG_LEVEL": "INFO",
        },
    )
    write_env(
        args.client_env,
        {
            "OPENAI_API_KEY": client_key,
            "CODEX_API_KEY": client_key,
            "OPENAI_BASE_URL": client_base_url,
            "API_BASE_URL": client_base_url,
            "OPENAI_MODEL": model,
            "CUSTOM_OPENAI_API_KEY": client_key,
            "CUSTOM_OPENAI_BASE_URL": client_base_url,
            "OPENROUTER_API_KEY": client_key,
            "OPENROUTER_BASE_URL": client_base_url,
            "OPENROUTER_MODEL": model,
                    },
    )
    model_reasoning_effort = payload.get("model_reasoning_effort", "medium")
    codex_config = "\n".join(
        [
            f"model = {json.dumps(model)}",
            'model_provider = "tdc_isolated_relay"',
            f"model_reasoning_effort = {json.dumps(model_reasoning_effort)}",
            'model_verbosity = "low"',
            'web_search = "disabled"',
            "project_root_markers = []",
            "",
            "[model_providers.tdc_isolated_relay]",
            f'name = "TDC {variant.upper()} isolated relay"',
            f"base_url = {json.dumps(client_base_url)}",
            'wire_api = "responses"',
            f"experimental_bearer_token = {json.dumps(client_key)}",
            "",
        ]
    )
    args.codex_config.parent.mkdir(parents=True, exist_ok=True)
    args.codex_config.write_text(codex_config, encoding="utf-8")
    args.codex_config.chmod(0o600)

    evidence = {
        "evaluation_variant": variant,
        "model": model,
        "client_base_url": client_base_url,
        "relay_upstream_wire_api": wire_api,
        "upstream_origin": upstream_base_url,
        "source_provider_config": str(provider_path),
        "public_network_visible_to_framework": False,
        "relay_client_key_recorded": False,
    }
    args.evidence.parent.mkdir(parents=True, exist_ok=True)
    args.evidence.write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
