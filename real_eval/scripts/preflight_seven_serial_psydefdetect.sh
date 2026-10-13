#!/usr/bin/env bash
set -euo pipefail

ROOT="${RESEARCHCLAWEVAL_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
source "$ROOT/real_eval/scripts/lib_real_eval.sh"
BASE_RUN_ROOT="${REAL_EVAL_RUN_ROOT:-$ROOT/real_eval/runs/preflight-psydefdetect}"
DEFAULT_CONFIG="${REAL_EVAL_DEFAULT_CONFIG:-$ROOT/real_eval/config/seven_psydefdetect_smoke_frameworks.json}"
TOPIC_MODE="${REAL_EVAL_MODE:-smoke}"
CONFIG="${REAL_EVAL_FRAMEWORK_CONFIG:-$DEFAULT_CONFIG}"
DATASET_ROOT="${PSYDEFDETECT_DATASET_ROOT:-$(real_eval_resolve_topic_dataset "$ROOT" psydefdetect)}"
CONTRACT_FILE="${PSYDEFDETECT_CONTRACT_FILE:-$ROOT/automation/psydefdetect_contract.md}"
PROVIDER_CONFIG="${PROVIDER_CONFIG:-$ROOT/api/codex_gpt54_shubiaobiao.toml}"
EVAL_MODEL="${PSYDEFDETECT_EVAL_MODEL:-$(sed -n 's/^[[:space:]]*model[[:space:]]*=[[:space:]]*"\(.*\)"[[:space:]]*$/\1/p' "$PROVIDER_CONFIG" | head -1)}"

mkdir -p "$BASE_RUN_ROOT"

if [[ ! -f "$CONFIG" ]]; then
  echo "missing config: $CONFIG" >&2
  exit 2
fi
if [[ ! -d "$DATASET_ROOT" ]]; then
  echo "missing dataset root: $DATASET_ROOT" >&2
  exit 3
fi
if [[ ! -f "$CONTRACT_FILE" ]]; then
  echo "missing contract file: $CONTRACT_FILE" >&2
  exit 4
fi
if [[ ! -f "$PROVIDER_CONFIG" ]]; then
  echo "missing provider config: $PROVIDER_CONFIG" >&2
  exit 5
fi

python3 - "$ROOT" "$CONFIG" "$DATASET_ROOT" "$CONTRACT_FILE" "$TOPIC_MODE" "$PROVIDER_CONFIG" "$EVAL_MODEL" <<'PY'
from pathlib import Path
import json
import sys

root = Path(sys.argv[1])
config = Path(sys.argv[2])
dataset_root = Path(sys.argv[3])
contract_file = Path(sys.argv[4])
mode = sys.argv[5]
provider_config = Path(sys.argv[6])
effective_model = sys.argv[7]
data = json.loads(config.read_text(encoding="utf-8"))
errors = []

declared_variant = data.get("evaluation_variant")
configured_model = data.get("model")
if effective_model == "gpt-5.6-luna":
    variant = "gpt56luna"
elif effective_model.startswith("kimi-"):
    variant = "kimi"
elif effective_model.startswith("gpt-"):
    variant = "gpt"
elif effective_model == "deepseek-v4-flash":
    variant = "deepseek"
else:
    variant = declared_variant
if declared_variant not in {None, variant}:
    errors.append("evaluation_variant_model_mismatch")
if variant == "gpt56luna":
    if provider_config != root / "api/codex_gpt56_luna_bianxie.toml":
        errors.append("gpt56luna_provider_config")
    if configured_model != "gpt-5.6-luna" or effective_model != "gpt-5.6-luna":
        errors.append("gpt56luna_model")
    provider_text = provider_config.read_text(encoding="utf-8", errors="ignore")
    if 'wire_api = "responses"' not in provider_text:
        errors.append("gpt56luna_wire_api")
elif variant == "gpt":
    if provider_config != root / "api/codex_gpt54_shubiaobiao.toml":
        errors.append("gpt_provider_config")
    if configured_model != "gpt-5.4" or effective_model != "gpt-5.4":
        errors.append("gpt_model")
elif variant == "kimi":
    if provider_config not in {
        root / "api/codex_kimi_k27_code_relay_container.toml",
        root / "api/codex_kimi_k27_code_relay_host.toml",
    }:
        errors.append("kimi_provider_config")
    if configured_model != "kimi-k2.6" or effective_model != "kimi-k2.6":
        errors.append("kimi_model")
    provider_text = provider_config.read_text(encoding="utf-8", errors="ignore")
    if (
        'base_url = "http://host.docker.internal:8787/v1"' not in provider_text
        and 'base_url = "http://127.0.0.1:8787/v1"' not in provider_text
    ):
        errors.append("kimi_relay_base_url")
elif variant == "deepseek":
    deepseek_provider_base_urls = {
        root / "api/codex_deepseek_v4_flash_bianxie_relay_container.toml": "http://host.docker.internal:8788/v1",
        root / "api/codex_deepseek_v4_flash_bianxie_recovery_container.toml": "http://host.docker.internal:8789/v1",
        root / "api/codex_deepseek_v4_flash_bianxie_required_auto_container.toml": "http://host.docker.internal:8790/v1",
    }
    deepseek_provider_base_urls[root / "api/codex_deepseek_v4_flash_bianxie_relay_host.toml"] = "http://172.17.0.1:8788/v1"
    if provider_config not in deepseek_provider_base_urls:
        errors.append("deepseek_provider_config")
    if configured_model != "deepseek-v4-flash" or effective_model != "deepseek-v4-flash":
        errors.append("deepseek_model")
    provider_text = provider_config.read_text(encoding="utf-8", errors="ignore")
    expected_base_url = deepseek_provider_base_urls.get(provider_config)
    if expected_base_url and f'base_url = "{expected_base_url}"' not in provider_text:
        errors.append("deepseek_relay_base_url")
    if 'wire_api = "responses"' not in provider_text:
        errors.append("deepseek_wire_api")

dataset_files = [p for p in dataset_root.rglob("*") if p.is_file()]
recognized_suffixes = {".json", ".jsonl", ".csv", ".tsv", ".txt", ".parquet"}
recognized_files = [p for p in dataset_files if p.suffix.lower() in recognized_suffixes]
dataset_ok = bool(recognized_files)
contract_text = contract_file.read_text(encoding="utf-8", errors="ignore")
contract_ok = "PsyDefDetect" in contract_text and "macro-F1" in contract_text

helper_text = "\n".join(
    [
        (root / "real_eval/scripts/psydefdetect_framework_smoke.sh").read_text(encoding="utf-8", errors="ignore"),
        (root / "real_eval/scripts/psydefdetect_framework_fullrun.sh").read_text(encoding="utf-8", errors="ignore"),
    ]
)
has_snapshot_guard = "real_eval_snapshot_forbidden_artifacts" in helper_text
has_after_guard = "real_eval_assert_no_new_forbidden_artifacts" in helper_text

for item in data["frameworks"]:
    wrapper = root / item["wrapper"]
    wrapper_ok = wrapper.exists()
    wrapper_text = wrapper.read_text(encoding="utf-8", errors="ignore") if wrapper_ok else ""
    missing_paths = [rel_path for rel_path in item.get("required_paths", []) if not (root / rel_path).exists()]
    wrong_topic = any(marker in wrapper_text.lower() for marker in ["gave2", "arc_wbe_2026", "babylm"])
    row = {
        "id": item["id"],
        "name": item["name"],
        "mode": mode,
        "wrapper": item["wrapper"],
        "wrapper_ok": wrapper_ok,
        "dataset_ok": dataset_ok,
        "contract_ok": contract_ok,
        "template_snapshot_guard": has_snapshot_guard,
        "template_after_guard": has_after_guard,
        "wrong_topic": wrong_topic,
        "missing_paths": missing_paths,
        "recognized_dataset_file_count": len(recognized_files),
    }
    if mode == "fullrun":
        expected_status = item.get("expected_status")
        native_entrypoint = item.get("native_entrypoint")
        provider_injection = item.get("provider_injection")
        expected_terminal = expected_status in {
            "unsupported_native_entrypoint",
            "blocked_benchmark_authorization",
        }
        native_metadata_ok = bool(
            expected_terminal
            or (
                isinstance(native_entrypoint, str)
                and native_entrypoint.strip()
                and isinstance(provider_injection, str)
                and provider_injection.strip()
            )
        )
        generic_codex = (
            "codex exec" in wrapper_text
            and 'FRAMEWORK_EXECUTOR_KIND="framework_skill_executor"' not in wrapper_text
            and 'FRAMEWORK_EXECUTOR_KIND="official_framework_skill"' not in wrapper_text
        )
        wrapper_native_declarations = bool(
            expected_terminal
            or (
                "FRAMEWORK_NATIVE_ENTRYPOINT=" in wrapper_text
                and "FRAMEWORK_NATIVE_LOG_MARKER=" in wrapper_text
                and "FRAMEWORK_EXECUTOR_KIND=" in wrapper_text
                and "FRAMEWORK_PROVIDER_INJECTION=" in wrapper_text
            )
        )
        kimi_injection_ok = bool(
            variant != "kimi"
            or expected_terminal
            or (
                isinstance(provider_injection, str)
                and "kimi-k2.6 relay" in provider_injection.lower()
            )
        )
        row.update({
            "evaluation_variant": variant,
            "effective_model": effective_model,
            "native_entrypoint": native_entrypoint,
            "provider_injection": provider_injection,
            "native_metadata_ok": native_metadata_ok,
            "wrapper_native_declarations": wrapper_native_declarations,
            "generic_codex_wrapper": generic_codex,
            "expected_status": expected_status,
            "kimi_injection_ok": kimi_injection_ok,
        })
        if not native_metadata_ok or not wrapper_native_declarations or generic_codex or not kimi_injection_ok:
            errors.append(item["id"])
    print(json.dumps(row, ensure_ascii=False))
    if (
        not wrapper_ok
        or missing_paths
        or wrong_topic
        or not dataset_ok
        or not contract_ok
        or not has_snapshot_guard
        or not has_after_guard
    ):
        errors.append(item["id"])

if errors:
    raise SystemExit(10)
PY
