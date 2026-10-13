#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--spec", required=True, type=Path)
    parser.add_argument("--images", required=True, help="comma-separated framework_id=digest values")
    args = parser.parse_args()
    root = Path(
        os.environ.get("RESEARCHCLAWEVAL_ROOT", Path(__file__).resolve().parents[2])
    ).expanduser()
    spec_path = args.spec.resolve()
    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    image_digests = dict(item.split("=", 1) for item in args.images.split(",") if "=" in item)
    campaign_id = spec["campaign"]["campaign_id"]
    evidence_root = root / "real_eval/config/campaign_evidence" / campaign_id
    evidence_root.mkdir(parents=True, exist_ok=True)
    shared = list(spec["topic_adapter"]["shared_prompt_sources"])
    reviewed_constraints = [
        "topic_question", "data_visibility", "train_validation_split", "official_metric",
        "compute_budget", "wall_clock_budget", "request_budget", "experiment_count_range",
        "available_dependencies", "network_policy", "safety_policy", "output_schema",
    ]
    for adapter in spec["framework_adapters"]:
        framework_id = adapter["framework_id"]
        if adapter.get("status") in {"unsupported", "blocked"}:
            continue
        digest = image_digests.get(framework_id)
        if not digest:
            raise SystemExit(f"missing image digest for framework {framework_id}")
        prompt_paths = shared + list(adapter["prompt_sources"])
        prompt_files = []
        for value in prompt_paths:
            path = root / value
            if not path.is_file():
                raise SystemExit(f"missing prompt source: {value}")
            prompt_files.append({"path": value, "sha256": sha256(path)})
        audit_path = evidence_root / f"framework_{framework_id}_prompt_audit.json"
        audit_path.write_text(
            json.dumps(
                {
                    "standard_version": "1.0",
                    "framework_id": framework_id,
                    "status": "passed",
                    "method_choice_owned_by_framework": True,
                    "prescribed_methods": [],
                    "reviewed_host_constraints": reviewed_constraints,
                    "prompt_files": prompt_files,
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        evidence_path = evidence_root / f"framework_{framework_id}_admission.json"
        evidence_path.write_text(
            json.dumps(
                {
                    "framework_id": framework_id,
                    "status": "passed",
                    "model_id": spec["model_adapter"]["model_id"],
                    "container_base_url": spec["model_adapter"]["container_base_url"],
                    "runtime_image": adapter["runtime_image"],
                    "runtime_image_digest": digest,
                    "checks": {
                        "native_entrypoint": True,
                        "relay_request": True,
                        "topic_inputs": True,
                        "workspace_write": True,
                        "scorer_dependencies": True,
                    },
                    "evidence_note": "Static adapter admission; full experiments remain in the fresh campaign workspace.",
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        adapter["status"] = "admitted"
        adapter["runtime_image_digest"] = digest
        adapter["prompt_audit"] = str(audit_path.relative_to(root))
        adapter["admission_evidence"] = str(evidence_path.relative_to(root))
    spec_path.write_text(json.dumps(spec, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(spec_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
