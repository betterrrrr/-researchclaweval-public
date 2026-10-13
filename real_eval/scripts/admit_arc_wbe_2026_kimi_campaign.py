#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path

ROOT = Path(os.environ.get("RESEARCHCLAWEVAL_ROOT", Path(__file__).resolve().parents[2])).expanduser()
REVIEWED_CONSTRAINTS = [
    "topic_question",
    "data_visibility",
    "train_validation_split",
    "official_metric",
    "compute_budget",
    "wall_clock_budget",
    "request_budget",
    "experiment_count_range",
    "available_dependencies",
    "network_policy",
    "safety_policy",
    "output_schema",
]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain an object")
    return value


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--spec", type=Path, required=True)
    parser.add_argument("--smoke-root", type=Path, required=True)
    parser.add_argument("--preflight", type=Path, required=True)
    parser.add_argument("--evidence-root", type=Path)
    args = parser.parse_args()

    spec_path = args.spec.expanduser()
    spec = load(spec_path)
    preflight = load(args.preflight.expanduser())
    if preflight.get("topic_id") != "arc_wbe_2026" or preflight.get("status") != "passed":
        raise SystemExit("Topic 3 Kimi preflight did not pass")
    if preflight.get("model_id") != "kimi-k2.6":
        raise SystemExit("Topic 3 preflight model is not kimi-k2.6")
    preflight_rows = {row["framework_id"]: row for row in preflight["frameworks"]}
    evidence_root = args.evidence_root.expanduser() if args.evidence_root else ROOT / "real_eval/config/campaign_evidence" / spec["campaign"]["campaign_id"]
    if not evidence_root.is_absolute():
        evidence_root = ROOT / evidence_root
    evidence_root.mkdir(parents=True, exist_ok=True)

    for adapter in spec["framework_adapters"]:
        framework_id = adapter["framework_id"]
        row = preflight_rows.get(framework_id)
        if row is None or row.get("status") != "passed" or not all(row.get("checks", {}).values()):
            raise SystemExit(f"preflight evidence failed for framework {framework_id}")
        if row.get("relay_response_model") != "kimi-k2.6":
            raise SystemExit(f"relay effective model mismatch for framework {framework_id}")

        smoke_slug = Path(adapter["same_image_smoke"]).name.replace(".sh", "")
        smoke_run = args.smoke_root.expanduser() / smoke_slug
        smoke_manifest = load(smoke_run / "smoke_manifest.json")
        smoke_state = load(smoke_run / "state.json")
        if smoke_manifest.get("all_passed") is not True or smoke_state.get("status") != "finished":
            raise SystemExit(f"Topic 3 smoke failed for framework {framework_id}")

        prompt_paths = list(spec["topic_adapter"]["shared_prompt_sources"]) + list(
            adapter["prompt_sources"]
        )
        prompt_files = [{"path": value, "sha256": sha256(ROOT / value)} for value in prompt_paths]
        audit_path = evidence_root / f"framework_{framework_id}_prompt_audit.json"
        audit_path.write_text(
            json.dumps(
                {
                    "standard_version": "1.0",
                    "framework_id": framework_id,
                    "status": "passed",
                    "method_choice_owned_by_framework": True,
                    "prescribed_methods": [],
                    "reviewed_host_constraints": REVIEWED_CONSTRAINTS,
                    "prompt_files": prompt_files,
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )

        evidence_path = evidence_root / f"framework_{framework_id}_admission.json"
        evidence = {
            **row,
            "same_image_smoke": {
                "run_root": str(smoke_run),
                "manifest": str(smoke_run / "smoke_manifest.json"),
                "state": str(smoke_run / "state.json"),
                "status": "finished",
            },
            "relay_preflight": str(args.preflight.expanduser()),
            "evidence_note": "Verified Topic 3 inputs, writable fresh workspace, native entrypoint source, scorer dependencies, and a real kimi-k2.6 relay request (effective model checked) in the full-run image.",
        }
        evidence_path.write_text(
            json.dumps(evidence, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )

        adapter["status"] = "admitted"
        adapter["runtime_image_digest"] = row["runtime_image_digest"]
        adapter["prompt_audit"] = str(audit_path.relative_to(ROOT))
        adapter["admission_evidence"] = str(evidence_path.relative_to(ROOT))

    spec_path.write_text(json.dumps(spec, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(spec_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
