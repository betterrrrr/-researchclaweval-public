from __future__ import annotations

import json
from pathlib import Path

from researchclaweval.registry import load_registry
from researchclaweval.validation import validate_registry

ROOT = Path(__file__).resolve().parents[1]


def test_public_registry_has_expected_coverage() -> None:
    registry = load_registry(ROOT)
    assert len(registry.topics) == 6
    assert len(registry.frameworks) == 7
    assert len(registry.runs) >= 56


def test_registry_and_relations_validate_without_external_assets() -> None:
    registry = load_registry(ROOT)
    assert validate_registry(registry) == []


def test_generic_codex_fullruns_are_not_admitted_as_native() -> None:
    registry = load_registry(ROOT)
    unsupported = [
        row for row in registry.runs if row["admission_status"] == "unsupported_non_native"
    ]
    assert len(unsupported) >= 4
    for row in unsupported:
        assert row["mode"] == "fullrun"
        source = (ROOT / row["wrapper"]).read_text(encoding="utf-8")
        assert "codex exec" in source


def test_adapter_manifests_pin_upstream_and_patch_files_exist() -> None:
    registry = load_registry(ROOT)
    for framework in registry.frameworks.values():
        manifest_path = ROOT / framework["adapter_manifest"]
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        assert manifest["upstream_commit"] == framework["upstream_commit"]
        assert len(manifest["upstream_commit"]) == 40
        for patch in manifest["patches"]:
            patch_path = manifest_path.parent / patch
            assert patch_path.is_file()
            assert "diff --git" in patch_path.read_text(encoding="utf-8")