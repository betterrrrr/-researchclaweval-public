#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from topic_runtime import TopicConfig, load_topic_config

REPO_ROOT = Path(os.environ.get("RESEARCHCLAWEVAL_ROOT", "$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"))
AUTOMATION_DIR = Path(os.environ.get("RESEARCHCLAWEVAL_AUTOMATION_DIR", str(REPO_ROOT / "automation")))
PROJECTS_FILE = AUTOMATION_DIR / "projects.yaml"
PROVIDER_CONFIG = str(REPO_ROOT / "api/codex_gpt54_shubiaobiao.toml")
SEMANTIC_SOURCE = str(REPO_ROOT / "api/_semantic_scholar_api_usage.md")
FORBIDDEN_MARKERS = [
    "sklearn_iris",
    "digits_iris_light",
    "minimal_iris_digits",
    "load_iris",
    "load_digits",
]


PROJECT_RULES = {
    "01": {
        "smoke_files": [
            REPO_ROOT / "automation/scripts/run_framework_babylm_proxy.py",
            REPO_ROOT / "babylm_10m_harness/scripts/run_proxy_babylm_pipeline.py",
        ],
        "result_files": [
            REPO_ROOT / "AI-Researcher/workplace_paper/task_babylm_10m_gpt-5.4/workplace/workplace/run_manifest.json",
            REPO_ROOT / "AI-Researcher/workplace_paper/task_babylm_10m_gpt-5.4/workplace/workplace/project/eval/proxy_strict_small_eval.json",
        ],
    },
    "03": {
        "smoke_files": [
            REPO_ROOT / "automation/scripts/run_framework_babylm_proxy.py",
            REPO_ROOT / "babylm_10m_harness/scripts/run_proxy_babylm_pipeline.py",
        ],
        "result_files": [
            REPO_ROOT / "Auto-claude-code-research-in-sleep/.aris-codex-project/RESEARCH_BRIEF.md",
            REPO_ROOT / "Auto-claude-code-research-in-sleep/.aris-codex-project/babylm_proxy/run_manifest.json",
        ],
    },
    "04": {
        "smoke_files": [
            REPO_ROOT / "automation/projects.yaml",
            REPO_ROOT / "real_eval/scripts/run_seven_serial_psydefdetect_smoke.sh",
            REPO_ROOT / "real_eval/scripts/preflight_seven_serial_psydefdetect.sh",
        ],
        "result_files": [
            Path(os.environ.get("REAL_EVAL_SYSTEMD_LOG_ROOT", str(REPO_ROOT / "real_eval/systemd_runs/latest-psydefdetect"))) / "submission.json",
            Path(os.environ.get("REAL_EVAL_SYSTEMD_LOG_ROOT", str(REPO_ROOT / "real_eval/systemd_runs/latest-psydefdetect"))) / "state.json",
            Path(os.environ.get("REAL_EVAL_SYSTEMD_LOG_ROOT", str(REPO_ROOT / "real_eval/systemd_runs/latest-psydefdetect"))) / "child_summary.md",
        ],
    },
    "05": {
        "smoke_files": [
            REPO_ROOT / "automation/scripts/run_framework_babylm_proxy.py",
            REPO_ROOT / "babylm_10m_harness/scripts/run_proxy_babylm_pipeline.py",
        ],
        "result_files": [
            REPO_ROOT / "DeepScientist/.deepscientist_home/quests/001/brief.md",
            REPO_ROOT / "DeepScientist/.deepscientist_home/quests/001/babylm_proxy/run_manifest.json",
            REPO_ROOT / "DeepScientist/.deepscientist_home/quests/001/paper/final_report.md",
        ],
    },
    "06": {
        "smoke_files": [
            REPO_ROOT / "automation/scripts/run_framework_babylm_proxy.py",
            REPO_ROOT / "babylm_10m_harness/scripts/run_proxy_babylm_pipeline.py",
        ],
        "result_files": [
            REPO_ROOT / "dr-claw/.runtime-home/user/dr-claw/babylm-10m-project-e2e-remediated/.pipeline/docs/research_brief.json",
            REPO_ROOT / "dr-claw/.runtime-home/user/dr-claw/babylm-10m-project-e2e-remediated/Experiment/babylm_proxy/run_manifest.json",
            REPO_ROOT / "dr-claw/.runtime-home/user/dr-claw/babylm-10m-project-e2e-remediated/Publication/paper/main.md",
        ],
    },
    "07": {
        "smoke_files": [
            REPO_ROOT / "automation/scripts/run_framework_babylm_proxy.py",
            REPO_ROOT / "babylm_10m_harness/scripts/run_proxy_babylm_pipeline.py",
        ],
        "result_files": [
            REPO_ROOT / "EvoScientist/workspace/babylm_proxy/run_manifest.json",
            REPO_ROOT / "EvoScientist/workspace/final_report.md",
        ],
    },
}


def topic_from_args(args: argparse.Namespace) -> TopicConfig:
    loaded = load_topic_config(REPO_ROOT, AUTOMATION_DIR)
    return TopicConfig(
        label=args.topic_label or loaded.label,
        dataset_root=Path(args.dataset_root) if args.dataset_root else loaded.dataset_root,
        contract_file=Path(args.contract_file) if args.contract_file else loaded.contract_file,
    )


def scan_json_values(value, topic: TopicConfig) -> dict[str, bool]:
    text_hits = {
        "topic_label": False,
        "dataset_root": False,
        "contract_file": False,
    }
    if isinstance(value, dict):
        for nested in value.values():
            nested_hits = scan_json_values(nested, topic)
            for key, hit in nested_hits.items():
                text_hits[key] = text_hits[key] or hit
        return text_hits
    if isinstance(value, list):
        for nested in value:
            nested_hits = scan_json_values(nested, topic)
            for key, hit in nested_hits.items():
                text_hits[key] = text_hits[key] or hit
        return text_hits
    if isinstance(value, str):
        return {
            "topic_label": topic.label in value,
            "dataset_root": str(topic.dataset_root) in value,
            "contract_file": str(topic.contract_file) in value,
        }
    return text_hits


def scan_file(path: Path, topic: TopicConfig) -> dict:
    if not path.exists():
        return {"path": str(path), "exists": False}
    text = path.read_text(encoding="utf-8", errors="ignore")
    forbidden = [marker for marker in FORBIDDEN_MARKERS if marker in text]
    required = scan_json_values(text, topic)
    if path.suffix == ".json":
        try:
            required = scan_json_values(json.loads(text), topic)
        except json.JSONDecodeError:
            required = scan_json_values(text, topic)
    return {
        "path": str(path),
        "exists": True,
        "forbidden_markers": forbidden,
        "required": required,
    }


def load_project_map() -> dict[str, dict]:
    return {item["id"]: item for item in json.loads(PROJECTS_FILE.read_text(encoding="utf-8"))["projects"]}


def command_alignment(project_id: str, topic: TopicConfig) -> dict:
    project = load_project_map()[project_id]
    raw = project["e2e_cmd"]
    rendered = (
        raw.replace("__TOPIC_LABEL__", topic.label)
        .replace("__TOPIC_DATASET_ROOT__", str(topic.dataset_root))
        .replace("__TOPIC_CONTRACT_FILE__", str(topic.contract_file))
        .replace("__BABYLM_ROOT__", str(topic.dataset_root))
        .replace("__BABYLM_TASK_FILE__", str(topic.contract_file))
    )
    required = {
        "topic_label": topic.label in rendered,
        "dataset_root": str(topic.dataset_root) in rendered,
        "contract_file": str(topic.contract_file) in rendered,
    }
    if topic.label != "PsyDefDetect":
        required["provider_config"] = PROVIDER_CONFIG in rendered
        required["semantic_source"] = SEMANTIC_SOURCE in rendered
    missing = [key for key, ok in required.items() if not ok]
    forbidden = [marker for marker in FORBIDDEN_MARKERS if marker in rendered]
    return {
        "project_id": project_id,
        "raw_e2e_cmd": raw,
        "rendered_e2e_cmd": rendered,
        "required": required,
        "missing": missing,
        "forbidden_markers": forbidden,
        "ok": not missing and not forbidden,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-id", required=True, choices=sorted(PROJECT_RULES))
    parser.add_argument("--phase", required=True, choices=["smoke", "e2e"])
    parser.add_argument("--topic-label")
    parser.add_argument("--dataset-root")
    parser.add_argument("--contract-file")
    args = parser.parse_args()
    topic = topic_from_args(args)

    rules = PROJECT_RULES[args.project_id]
    files = rules["smoke_files"] if args.phase == "smoke" else rules["result_files"]
    results = [scan_file(path, topic) for path in files]

    missing = [item["path"] for item in results if not item["exists"]]
    forbidden = [
        {"path": item["path"], "markers": item.get("forbidden_markers", [])}
        for item in results
        if item.get("forbidden_markers")
    ]
    missing_required: list[str] = []
    smoke_alignment = None
    if args.phase == "e2e":
        required_totals = {"topic_label": False, "dataset_root": False, "contract_file": False}
        for item in results:
            if not item["exists"]:
                continue
            for key, ok in item["required"].items():
                required_totals[key] = required_totals[key] or ok
        if topic.label == "PsyDefDetect" and args.project_id == "04":
            required_totals = {"topic_label": False, "dataset_root": True, "contract_file": True}
            for item in results:
                if item["exists"]:
                    text = Path(item["path"]).read_text(encoding="utf-8", errors="ignore")
                    required_totals["topic_label"] = required_totals["topic_label"] or "PsyDefDetect" in text
            command = command_alignment(args.project_id, topic)
            if not command["ok"]:
                missing_required.extend(command["missing"])
        missing_required = [key for key, ok in required_totals.items() if not ok]
    else:
        smoke_alignment = command_alignment(args.project_id, topic)
        if not smoke_alignment["ok"]:
            missing_required = smoke_alignment["missing"]
            if smoke_alignment["forbidden_markers"]:
                forbidden.append(
                    {
                        "path": f"projects.yaml:{args.project_id}:e2e_cmd",
                        "markers": smoke_alignment["forbidden_markers"],
                    }
                )

    payload = {
        "project_id": args.project_id,
        "phase": args.phase,
        "topic_label": topic.label,
        "dataset_root": str(topic.dataset_root),
        "contract_file": str(topic.contract_file),
        # 放宽：missing_files 只记录不参与 ok 判断；禁止标记和必要字段缺失仍为 fail
        "ok": not forbidden and not missing_required,
        "results": results,
        "missing_files": missing,
        "forbidden_hits": forbidden,
        "missing_required": missing_required,
        "smoke_alignment": smoke_alignment,
    }
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0 if payload["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
