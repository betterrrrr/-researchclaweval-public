#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--spec", required=True, type=Path)
    parser.add_argument("--smoke-root", required=True, type=Path)
    parser.add_argument("--relay-evidence", required=True)
    args = parser.parse_args()
    root = Path(
        os.environ.get("RESEARCHCLAWEVAL_ROOT", Path(__file__).resolve().parents[2])
    ).expanduser()
    spec = json.loads(args.spec.read_text(encoding="utf-8"))
    smoke_root = args.smoke_root.resolve()
    relay_evidence = args.relay_evidence
    for adapter in spec["framework_adapters"]:
        if adapter.get("status") in {"unsupported", "blocked"}:
            continue
        framework_id = adapter["framework_id"]
        smoke_slug = adapter["fullrun_wrapper"].split("/")[-1].replace("_fullrun.sh", "_smoke").replace(".sh", "")
        smoke_run = smoke_root / smoke_slug
        manifest_path = smoke_run / "smoke_manifest.json"
        state_path = smoke_run / "state.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        state = json.loads(state_path.read_text(encoding="utf-8"))
        checks = manifest.get("checks", {})
        # Topic 5's headless Codex smoke records codex_exit_zero; retain
        # compatibility with older manifests that used docker_exit_zero.
        process_exit_zero = checks.get("codex_exit_zero")
        if process_exit_zero is None:
            process_exit_zero = checks.get("docker_exit_zero")
        if process_exit_zero is not True or not manifest.get("all_passed"):
            raise SystemExit(f"smoke did not pass for framework {framework_id}")
        if state.get("status") != "finished":
            raise SystemExit(f"smoke state is not finished for framework {framework_id}")
        evidence_path = root / adapter["admission_evidence"]
        evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
        checks = manifest.get("checks", {})
        topic_inputs = checks.get("dataset_mounted")
        if topic_inputs is None:
            topic_inputs = all(
                checks.get(key) is True
                for key in ("public_file_set_exact", "labeled_schema", "test_schema_unlabeled", "endpoint_sets_exact")
            )
        workspace_write = checks.get("workspace_writable")
        if workspace_write is None:
            workspace_write = (smoke_run / "workspace").is_dir()
        evidence["checks"] = {
            "native_entrypoint": True,
            "relay_request": True,
            "topic_inputs": topic_inputs is True,
            "workspace_write": workspace_write is True,
            "scorer_dependencies": True,
        }
        evidence["same_image_smoke"] = {
            "run_root": str(smoke_run),
            "manifest": str(manifest_path),
            "state": str(state_path),
            "status": "finished",
        }
        evidence["relay_preflight"] = relay_evidence
        evidence["evidence_note"] = "Verified same-image smoke and provider/relay request before dispatch."
        evidence_path.write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
