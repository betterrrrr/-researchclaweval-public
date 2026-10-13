#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Admit GAVE2 Task 2 DeepSeek campaign")
    parser.add_argument("--spec", type=Path, required=True, help="Path to campaign spec JSON")
    parser.add_argument("--preflight", type=Path, required=True, help="Path to preflight result JSON")
    parser.add_argument("--smoke-root", type=Path, required=True, help="Root directory containing smoke run results")
    parser.add_argument("--output", type=Path, required=True, help="Output path for admitted spec")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    spec = load_json(args.spec)
    preflight = load_json(args.preflight)

    if preflight.get("status") != "passed":
        print(f"Preflight status is '{preflight.get('status')}', expected 'passed'")
        return 1

    evidence_root = args.spec.parent / "campaign_evidence" / spec["campaign"]["campaign_id"]
    evidence_root.mkdir(parents=True, exist_ok=True)

    for adapter in spec["framework_adapters"]:
        fw_id = adapter["framework_id"]
        fw_name = next(
            (fw["name"] for fw in preflight.get("frameworks", []) if fw["framework_id"] == fw_id),
            f"framework_{fw_id}",
        )

        fw_preflight = next(
            (fw for fw in preflight.get("frameworks", []) if fw["framework_id"] == fw_id),
            {},
        )
        if not fw_preflight.get("all_passed", False):
            print(f"Framework {fw_id} ({fw_name}) preflight not passed, skipping admission")
            continue

        smoke_state_path = args.smoke_root / fw_id / "state.json"
        if smoke_state_path.exists():
            smoke_state = load_json(smoke_state_path)
            smoke_passed = smoke_state.get("status") == "finished" and smoke_state.get("summary", "").startswith("all_passed")
        else:
            smoke_passed = False

        prompt_hashes = {}
        for source in adapter.get("prompt_sources", []):
            source_path = REPO_ROOT / source
            if source_path.exists():
                prompt_hashes[str(source_path)] = sha256_file(source_path)

        prompt_audit = {
            "spec_version": "1.0",
            "campaign_id": spec["campaign"]["campaign_id"],
            "framework_id": fw_id,
            "framework_name": fw_name,
            "status": "passed" if smoke_passed else "pending",
            "method_choice_owned_by_framework": True,
            "prescribed_methods": [],
            "reviewed_host_constraints": list(spec.get("ideation_policy", {}).get("allowed_host_constraints", [])),
            "method_prescription_forbidden": spec.get("ideation_policy", {}).get("host_method_prescription_forbidden", True),
            "prompt_file_hashes": prompt_hashes,
            "reviewed_at": None,
            "reviewed_by": "admission_script",
        }
        prompt_audit_path = evidence_root / f"framework_{fw_id}_prompt_audit.json"
        write_json(prompt_audit_path, prompt_audit)

        admission = {
            "framework_id": fw_id,
            "framework_name": fw_name,
            "campaign_id": spec["campaign"]["campaign_id"],
            "preflight_checks": fw_preflight.get("checks", {}),
            "preflight_all_passed": fw_preflight.get("all_passed", False),
            "smoke_evidence": {
                "state_file": str(smoke_state_path) if smoke_state_path.exists() else None,
                "all_passed": smoke_passed,
            },
            "relay_preflight": str(spec["model_adapter"]["relay_preflight"]),
            "runtime_image": fw_preflight.get("runtime_image", adapter.get("runtime_image", "")),
            "runtime_image_digest": fw_preflight.get("runtime_image_digest", ""),
            "admitted_at": None,
        }
        admission_path = evidence_root / f"framework_{fw_id}_admission.json"
        write_json(admission_path, admission)

        adapter["status"] = "admitted"
        adapter["runtime_image_digest"] = fw_preflight.get("runtime_image_digest", "")
        adapter["prompt_audit"] = str(prompt_audit_path.relative_to(REPO_ROOT))
        adapter["admission_evidence"] = str(admission_path.relative_to(REPO_ROOT))

        print(f"Framework {fw_id} ({fw_name}): admitted")

    write_json(args.output, spec)
    print(f"Wrote admitted spec: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())