import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
CONTAINER_PROVIDER = REPO_ROOT / "api/codex_kimi_k27_code_relay_container.toml"
HOST_PROVIDER = REPO_ROOT / "api/codex_kimi_k27_code_relay_host.toml"


def test_provider_env_parser_accepts_codex_nested_model_provider_config(tmp_path: Path) -> None:
    provider_toml = tmp_path / "config.toml"
    provider_env = tmp_path / "provider.env"
    provider_toml.write_text(
        '\n'.join(
            [
                'model = "gpt-5.5"',
                'model_provider = "gac"',
                "",
                "[model_providers.gac]",
                'base_url = "https://proxy.example.test"',
                'experimental_bearer_token = "test-token"',
                "",
            ]
        ),
        encoding="utf-8",
    )

    script = f"""
set -euo pipefail
source "{REPO_ROOT}/real_eval/scripts/lib_real_eval.sh"
real_eval_provider_env_from_codex_toml "{provider_toml}" "{provider_env}"
"""
    subprocess.run(["bash", "-lc", script], check=True)

    parsed = provider_env.read_text(encoding="utf-8")
    assert "OPENAI_API_KEY=test-token\n" in parsed
    assert "OPENAI_BASE_URL=https://proxy.example.test/v1\n" in parsed
    assert "OPENAI_MODEL=gpt-5.5\n" in parsed


def test_semantic_env_parser_allows_empty_optional_usage_file(tmp_path: Path) -> None:
    usage_md = tmp_path / "_semantic_scholar_api_usage.md"
    semantic_env = tmp_path / "semantic.env"
    usage_md.write_text("", encoding="utf-8")

    script = f"""
set -euo pipefail
source "{REPO_ROOT}/real_eval/scripts/lib_real_eval.sh"
real_eval_semantic_env_from_usage_md "{usage_md}" "{semantic_env}"
"""
    subprocess.run(["bash", "-lc", script], check=True)

    assert semantic_env.read_text(encoding="utf-8") == ""


def test_provider_env_parser_accepts_kimi_relay_host_config(tmp_path: Path) -> None:
    provider_toml = tmp_path / "kimi_relay_host.toml"
    provider_env = tmp_path / "provider.env"
    provider_toml.write_text(
        "\n".join(
            [
                'model = "kimi-k2.6"',
                'model_provider = "kimi_relay"',
                "",
                "[model_providers.kimi_relay]",
                'name = "kimi_relay"',
                'base_url = "http://127.0.0.1:8787/v1"',
                'wire_api = "responses"',
                'experimental_bearer_token = "local-relay-token"',
                "",
            ]
        ),
        encoding="utf-8",
    )

    script = f"""
set -euo pipefail
source "{REPO_ROOT}/real_eval/scripts/lib_real_eval.sh"
real_eval_provider_env_from_codex_toml "{provider_toml}" "{provider_env}"
"""
    subprocess.run(["bash", "-lc", script], check=True)

    parsed = provider_env.read_text(encoding="utf-8")
    assert "OPENAI_API_KEY=local-relay-token\n" in parsed
    assert "OPENAI_BASE_URL=http://127.0.0.1:8787/v1\n" in parsed
    assert "OPENAI_MODEL=kimi-k2.6\n" in parsed


def test_provider_env_parser_accepts_kimi_relay_container_config(tmp_path: Path) -> None:
    provider_toml = tmp_path / "kimi_relay_container.toml"
    provider_env = tmp_path / "provider.env"
    provider_toml.write_text(
        "\n".join(
            [
                'model = "kimi-k2.6"',
                'model_provider = "kimi_relay"',
                "",
                "[model_providers.kimi_relay]",
                'name = "kimi_relay"',
                'base_url = "http://host.docker.internal:8787/v1"',
                'wire_api = "responses"',
                'experimental_bearer_token = "local-relay-token"',
                "",
            ]
        ),
        encoding="utf-8",
    )

    script = f"""
set -euo pipefail
source "{REPO_ROOT}/real_eval/scripts/lib_real_eval.sh"
real_eval_provider_env_from_codex_toml "{provider_toml}" "{provider_env}"
"""
    subprocess.run(["bash", "-lc", script], check=True)

    parsed = provider_env.read_text(encoding="utf-8")
    assert "OPENAI_BASE_URL=http://host.docker.internal:8787/v1\n" in parsed
    assert "CUSTOM_OPENAI_BASE_URL=http://host.docker.internal:8787/v1\n" in parsed
    assert "OPENROUTER_MODEL=kimi-k2.6\n" in parsed


def test_direct_kimi_provider_configs_use_responses_wire_api() -> None:
    container_text = CONTAINER_PROVIDER.read_text(encoding="utf-8")
    host_text = HOST_PROVIDER.read_text(encoding="utf-8")

    assert 'wire_api = "responses"' in container_text
    assert 'wire_api = "responses"' in host_text


def test_provider_env_parser_accepts_direct_chat_completions_config(tmp_path: Path) -> None:
    provider_toml = tmp_path / "deepseek.toml"
    provider_env = tmp_path / "provider.env"
    provider_toml.write_text(
        "\n".join(
            [
                'model = "deepseek-v4-flash"',
                'model_provider = "bianxie"',
                "",
                "[model_providers.bianxie]",
                'base_url = "https://api.bianxie.ai/v1"',
                'wire_api = "chat"',
                'experimental_bearer_token = "test-token"',
                "",
            ]
        ),
        encoding="utf-8",
    )

    script = f'''\nset -euo pipefail\nsource "{REPO_ROOT}/real_eval/scripts/lib_real_eval.sh"\nreal_eval_provider_env_from_codex_toml "{provider_toml}" "{provider_env}"\n'''
    subprocess.run(["bash", "-lc", script], check=True)

    parsed = provider_env.read_text(encoding="utf-8")
    assert "OPENAI_API_KEY=test-token\n" in parsed
    assert "OPENAI_BASE_URL=https://api.bianxie.ai/v1\n" in parsed
    assert "OPENAI_MODEL=deepseek-v4-flash\n" in parsed
