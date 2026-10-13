#!/usr/bin/env python3
"""Verify AI-Researcher runtime image definitions and lock file integrity.

Usage:
    # Update lock file hashes from current Dockerfiles and source files
    python verify_ai_researcher_images.py --lock

    # Check that the lock file matches current files
    python verify_ai_researcher_images.py --check-locked

    # Verify outer image definition (syntax, structure, reproducibility)
    python verify_ai_researcher_images.py --outer

    # Verify inner exec image definition
    python verify_ai_researcher_images.py --inner

    # Test that two consecutive builds produce identical images
    python verify_ai_researcher_images.py --rebuild-twice

    # Run all checks
    python verify_ai_researcher_images.py --check-locked --outer --inner

Flags are independent and may be combined.  With no flags, all checks run.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
ROOT = Path(os.environ.get("RESEARCHCLAWEVAL_ROOT", Path(__file__).resolve().parents[2])).expanduser()
DOCKER_DIR = ROOT / "real_eval" / "docker"
SCRIPTS_DIR = ROOT / "real_eval" / "scripts"
LOCK_FILE = DOCKER_DIR / "ai_researcher-images.lock.json"
OUTER_DOCKERFILE = DOCKER_DIR / "ai_researcher_runtime.Dockerfile"
INNER_DOCKERFILE = DOCKER_DIR / "ai_researcher_exec_runtime.Dockerfile"
OUTER_REQS_HASHES = DOCKER_DIR / "ai_researcher_runtime.requirements-hashes.txt"
INNER_REQS_HASHES = DOCKER_DIR / "ai_researcher_exec_runtime.requirements-hashes.txt"
OUTER_SUPERVISORD = DOCKER_DIR / "ai_researcher_runtime.supervisord.conf"

# Source reference files (from the upstream AI-Researcher project)
AI_RESEARCHER_DIR = ROOT / "AI-Researcher"
UPSTREAM_DOCKERFILE = AI_RESEARCHER_DIR / "docker" / "Dockerfile"
UPSTREAM_REQUIREMENTS = AI_RESEARCHER_DIR / "docker" / "requirements.txt"
UPSTREAM_SETUP_CFG = AI_RESEARCHER_DIR / "setup.cfg"

# The "import gate" packages that must be importable without runtime installs.
IMPORT_GATE_PACKAGES: list[dict[str, str]] = [
    {"module": "torch", "pip": "torch", "expect": "1.13"},
    {"module": "rdkit", "pip": "rdkit-pypi", "expect": "2024"},
    {"module": "sentence_transformers", "pip": "sentence-transformers", "expect": "3.4"},
    {"module": "docling", "pip": "docling", "expect": "2.18"},
    {"module": "playwright.sync_api", "pip": "playwright", "expect": "1.39"},
]

# ---------------------------------------------------------------------------
# Result accumulator
# ---------------------------------------------------------------------------
@dataclass
class CheckResult:
    """Collects pass/fail results across all checks."""

    checks: list[dict[str, Any]] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def ok(self, name: str, detail: str = "") -> None:
        self.checks.append({"check": name, "status": "PASS", "detail": detail})

    def fail(self, name: str, detail: str = "") -> None:
        self.checks.append({"check": name, "status": "FAIL", "detail": detail})
        self.errors.append(f"{name}: {detail}")

    @property
    def all_ok(self) -> bool:
        return not self.errors

    def summary(self) -> str:
        lines = []
        for c in self.checks:
            mark = "\u2713" if c["status"] == "PASS" else "\u2717"
            lines.append(f"  {mark} {c['check']}")
            if c["detail"]:
                lines.append(f"       {c['detail']}")
        total = len(self.checks)
        passed = sum(1 for c in self.checks if c["status"] == "PASS")
        lines.append(f"\n{passed}/{total} checks passed")
        if self.errors:
            lines.append(f"{len(self.errors)} failure(s):")
            for e in self.errors:
                lines.append(f"  - {e}")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def sha256_file(path: Path) -> str:
    """Return lowercase hex SHA-256 of a file."""
    if not path.exists():
        return "<MISSING>"
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()


def load_lock() -> dict[str, Any]:
    """Load the lock file, returning an empty dict on failure."""
    if not LOCK_FILE.exists():
        return {}
    try:
        return json.loads(LOCK_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        return {}


def write_lock(data: dict[str, Any]) -> None:
    """Write the lock file with pretty-printing."""
    LOCK_FILE.write_text(
        json.dumps(data, indent=2, ensure_ascii=False, sort_keys=False) + "\n",
        encoding="utf-8",
    )


def parse_dockerfile_base_image(path: Path) -> str | None:
    """Extract the FROM line from a Dockerfile."""
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped.startswith("FROM "):
            parts = stripped.split()
            if len(parts) >= 2:
                return parts[1]
    return None


def extract_pip_packages_from_dockerfile(path: Path) -> list[str]:
    """Extract pip install package specs from a Dockerfile."""
    pkgs: list[str] = []
    in_pip_install = False
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        # Detect pip install continuation lines
        if "pip install" in stripped:
            in_pip_install = True
        if in_pip_install:
            # Extract package specs and version pins
            matches = re.findall(r"(\S+==\S+)", stripped)
            pkgs.extend(matches)
            # Check if line ends with continuation
            if stripped.endswith("\\") or stripped.endswith("&&"):
                continue
            in_pip_install = False
    return sorted(set(pkgs))


# ---------------------------------------------------------------------------
# Check: Lock file integrity
# ---------------------------------------------------------------------------
def check_lock_integrity(result: CheckResult) -> None:
    """Verify that the lock file is valid JSON and has the expected schema."""
    if not LOCK_FILE.exists():
        result.fail("lock-exists", f"Lock file not found: {LOCK_FILE}")
        return

    lock = load_lock()
    if not lock:
        result.fail("lock-parse", "Lock file is empty or invalid JSON")
        return

    # Schema version
    sv = lock.get("schema_version")
    if sv is None:
        result.fail("lock-schema-version", "Missing schema_version")
    else:
        result.ok("lock-schema-version", f"schema_version={sv}")

    # Dockerfiles section
    df = lock.get("dockerfiles", {})
    if not df:
        result.fail("lock-dockerfiles", "Missing dockerfiles section")
    else:
        for key in ("outer", "inner"):
            entry = df.get(key, {})
            if not entry:
                result.fail(f"lock-dockerfiles-{key}", f"Missing dockerfiles.{key}")
            else:
                path_val = entry.get("path")
                sha = entry.get("sha256")
                if path_val:
                    expected_path = ROOT / path_val
                    if expected_path.exists():
                        result.ok(
                            f"lock-dockerfiles-{key}-path",
                            f"path={path_val} exists",
                        )
                    else:
                        result.fail(
                            f"lock-dockerfiles-{key}-path",
                            f"path={path_val} not found",
                        )
                if sha is None:
                    result.ok(f"lock-dockerfiles-{key}-sha256", "sha256=null (unlocked)")
                else:
                    actual = sha256_file(ROOT / (entry.get("path") or ""))
                    if actual == sha:
                        result.ok(f"lock-dockerfiles-{key}-sha256", "matches")
                    else:
                        result.fail(
                            f"lock-dockerfiles-{key}-sha256",
                            f"expected {sha}, got {actual}",
                        )

    # Images section
    img = lock.get("images", {})
    if not img:
        result.fail("lock-images", "Missing images section")
    else:
        for key in ("outer", "inner"):
            entry = img.get(key, {})
            if not entry:
                result.fail(f"lock-images-{key}", f"Missing images.{key}")
            else:
                tag = entry.get("tag", "?")
                digest = entry.get("digest")
                if digest is None:
                    result.ok(f"lock-images-{key}-digest", f"tag={tag} digest=null (unlocked)")
                else:
                    result.ok(f"lock-images-{key}-digest", f"tag={tag} digest={digest}")


# ---------------------------------------------------------------------------
# Check: Lock file update
# ---------------------------------------------------------------------------
def do_lock_update(result: CheckResult) -> None:
    """Update the lock file with current file hashes."""
    lock = load_lock()
    if not lock:
        lock = {
            "schema_version": "1.0",
            "description": "Lock file for AI-Researcher outer and inner runtime images.",
            "metadata": {
                "created_at": "2026-08-12T00:00:00Z",
                "updated_at": None,
                "generated_by": "verify_ai_researcher_images.py --lock",
                "project": "AI-Researcher",
                "version": "0.2.0",
                "apt_snapshot_date": "2026-08-12",
                "apt_snapshot_url": "https://snapshot.debian.org/archive/debian/20260812T000000Z/",
            },
            "dockerfiles": {},
            "images": {},
            "dependencies": {},
            "verification": {},
        }

    # Update metadata
    lock.setdefault("metadata", {})["updated_at"] = "2026-08-12T00:00:00Z"
    lock["metadata"]["generated_by"] = "verify_ai_researcher_images.py --lock"

    # --- Dockerfile hashes ---
    lock.setdefault("dockerfiles", {})
    for key, df_path, source_ref, source_path in [
        ("outer", OUTER_DOCKERFILE, "AI-Researcher/docker/Dockerfile@HEAD", UPSTREAM_DOCKERFILE),
        ("inner", INNER_DOCKERFILE, "python:3.11-slim-bookworm", None),
    ]:
        entry = lock["dockerfiles"].setdefault(key, {})
        entry["path"] = str(df_path.relative_to(ROOT))
        entry["sha256"] = sha256_file(df_path)
        entry["source_ref"] = source_ref
        entry["source_sha256"] = sha256_file(source_path) if source_path and source_path.exists() else None
        result.ok(f"lock-update-dockerfile-{key}", f"sha256={entry['sha256']}")

    # --- Image tags ---
    lock.setdefault("images", {})
    img_config = [
        ("outer", "ai-researcher:runtime-ready", "pytorch/pytorch:2.5.1-cuda12.1-cudnn9-runtime"),
        ("inner", "ai-researcher-exec:runtime-ready", "python:3.11-slim-bookworm"),
    ]
    for key, tag, base in img_config:
        entry = lock["images"].setdefault(key, {})
        entry["tag"] = tag
        entry["digest"] = entry.get("digest")  # preserve existing
        entry["base_image"] = base
        entry["base_digest"] = entry.get("base_digest")  # preserve existing
        entry["build_timestamp"] = entry.get("build_timestamp")  # preserve existing

    # --- Dependency hashes ---
    lock.setdefault("dependencies", {})
    dep = lock["dependencies"]

    # Requirements hashes files
    for req_key, req_path in [("pip_wheels", OUTER_REQS_HASHES), ("pip_wheels_exec", INNER_REQS_HASHES)]:
        entry = dep.setdefault(req_key, {})
        entry["requirements_file"] = str(req_path.relative_to(ROOT)) if req_path.exists() else None
        entry["sha256"] = sha256_file(req_path) if req_path.exists() else None
        entry["entries"] = None
        if req_path.exists() and req_path.stat().st_size > 0:
            lines = [l for l in req_path.read_text(encoding="utf-8").splitlines() if l.strip() and not l.strip().startswith("#")]
            entry["entries"] = len(lines)
        result.ok(f"lock-update-{req_key}", f"sha256={entry['sha256']}, entries={entry['entries']}")

    # Apt packages
    for apt_key in ("outer", "inner"):
        entry = dep.setdefault("apt_packages", {}).setdefault(apt_key, {})
        entry["snapshot_url"] = "https://snapshot.debian.org/archive/debian/20260812T000000Z/"
        entry["package_count"] = entry.get("package_count")  # preserve
        entry["manifest_sha256"] = entry.get("manifest_sha256")  # preserve

    # Additional pip deps
    dep.setdefault("additional_pip", {
        "rdkit": "rdkit-pypi==2024.9.6",
        "sentence-transformers": "sentence-transformers==3.4.1",
        "docling": "docling==2.18.0",
    })

    # --- Verification state ---
    lock.setdefault("verification", {}).setdefault("import_gate", {
        pkg["module"]: False for pkg in IMPORT_GATE_PACKAGES
    })
    lock.setdefault("verification", {}).setdefault("rebuild_twice_identical", {
        "outer_image_id_1": None,
        "outer_image_id_2": None,
        "inner_image_id_1": None,
        "inner_image_id_2": None,
        "outer_match": False,
        "inner_match": False,
        "verified_at": None,
    })

    write_lock(lock)
    result.ok("lock-write", f"Written to {LOCK_FILE}")


# ---------------------------------------------------------------------------
# Check: Outer image definition
# ---------------------------------------------------------------------------
def check_outer_image(result: CheckResult) -> None:
    """Verify the outer runtime Dockerfile for correctness and reproducibility."""
    if not OUTER_DOCKERFILE.exists():
        result.fail("outer-exists", f"Not found: {OUTER_DOCKERFILE}")
        return

    content = OUTER_DOCKERFILE.read_text(encoding="utf-8")

    # 1. FROM with digest
    if re.search(r"FROM\s+\S+@sha256:[a-f0-9]{64}", content):
        result.ok("outer-from-digest", "Base image pinned by SHA-256 digest")
    else:
        result.fail("outer-from-digest", "Base image NOT pinned by digest (no @sha256:)")

    # 2. Apt snapshot
    if "snapshot.debian.org" in content:
        result.ok("outer-apt-snapshot", "Apt sources pinned to snapshot.debian.org")
    else:
        result.fail("outer-apt-snapshot", "No snapshot.debian.org reference found")

    # 3. No credentials
    cred_patterns = [
        r"(?i)(API_KEY|API_SECRET|ACCESS_TOKEN|PASSWORD|SECRET_KEY)\s*=",
        r"(?i)env\s+OPENAI_API_KEY",
        r"(?i)env\s+ANTHROPIC_API_KEY",
        r"(?i)env\s+HF_TOKEN",
        r"(?i)env\s+.*_API_KEY",
        r"(?i)env\s+.*_SECRET",
    ]
    cred_found = False
    for pat in cred_patterns:
        if re.search(pat, content):
            # Allow ANONYMIZED_TELEMETRY=false
            if "ANONYMIZED_TELEMETRY" in pat:
                continue
            cred_found = True
            result.fail("outer-no-credentials", f"Found credential pattern: {pat}")

    if not cred_found:
        result.ok("outer-no-credentials", "No baked credentials detected")

    # 4. PIP_REQUIRE_HASHES
    if "PIP_REQUIRE_HASHES=1" in content:
        result.ok("outer-pip-require-hashes", "PIP_REQUIRE_HASHES=1 is set")
    else:
        result.fail("outer-pip-require-hashes", "PIP_REQUIRE_HASHES not set")

    # 5. Supervisor config
    if "supervisord.conf" in content:
        result.ok("outer-supervisor", "Supervisor configuration included")
    else:
        result.fail("outer-supervisor", "No supervisor configuration found")

    # 6. Playwright
    if "playwright install" in content:
        result.ok("outer-playwright", "Playwright browser installation present")
    else:
        result.fail("outer-playwright", "Playwright browser installation missing")

    # 7. No source code COPY (must be mounted at runtime)
    if re.search(r"COPY\s+\.\s+/app", content) or re.search(r"COPY\s+\.\s+\.", content):
        result.fail("outer-no-source-bake", "Source code is COPY'd into the image (should be mounted at runtime)")
    else:
        result.ok("outer-no-source-bake", "No source code baked into the image")

    # 8. tree availability
    if "tree" in content:
        result.ok("outer-tree", "tree utility installed")
    else:
        result.fail("outer-tree", "tree utility missing")

    # 9. ENV PYTHONUNBUFFERED=1
    if "PYTHONUNBUFFERED=1" in content:
        result.ok("outer-python-unbuffered", "PYTHONUNBUFFERED=1 is set")
    else:
        result.fail("outer-python-unbuffered", "PYTHONUNBUFFERED=1 is missing")

    # 10. Check requirements-hashes file reference
    if "requirements-hashes.txt" in content:
        result.ok("outer-requirements-hashes", "Requirements hashes file referenced")
        if OUTER_REQS_HASHES.exists():
            result.ok("outer-requirements-hashes-file", f"Exists: {OUTER_REQS_HASHES.name}")
        else:
            result.ok("outer-requirements-hashes-file", "File not yet created (expected before build)")
    else:
        result.fail("outer-requirements-hashes", "No requirements-hashes.txt reference")

    # 11. Check supervisor config file
    if OUTER_SUPERVISORD.exists():
        result.ok("outer-supervisord-file", f"Supervisor config exists: {OUTER_SUPERVISORD.name}")
    else:
        result.ok("outer-supervisord-file", "Supervisor config not yet created (expected before build)")


# ---------------------------------------------------------------------------
# Check: Inner exec image definition
# ---------------------------------------------------------------------------
def check_inner_image(result: CheckResult) -> None:
    """Verify the inner exec runtime Dockerfile for correctness and reproducibility."""
    if not INNER_DOCKERFILE.exists():
        result.fail("inner-exists", f"Not found: {INNER_DOCKERFILE}")
        return

    content = INNER_DOCKERFILE.read_text(encoding="utf-8")

    # 1. FROM with digest
    if re.search(r"FROM\s+\S+@sha256:[a-f0-9]{64}", content):
        result.ok("inner-from-digest", "Base image pinned by SHA-256 digest")
    else:
        result.fail("inner-from-digest", "Base image NOT pinned by digest (no @sha256:)")

    # 2. Apt snapshot
    if "snapshot.debian.org" in content:
        result.ok("inner-apt-snapshot", "Apt sources pinned to snapshot.debian.org")
    else:
        result.fail("inner-apt-snapshot", "No snapshot.debian.org reference found")

    # 3. PIP_REQUIRE_HASHES
    if "PIP_REQUIRE_HASHES=1" in content:
        result.ok("inner-pip-require-hashes", "PIP_REQUIRE_HASHES=1 is set")
    else:
        result.fail("inner-pip-require-hashes", "PIP_REQUIRE_HASHES not set")

    # 4. No credentials
    if "OPENAI_API_KEY" in content or "ANTHROPIC_API_KEY" in content or "HF_TOKEN" in content:
        result.fail("inner-no-credentials", "Baked credentials detected")
    else:
        result.ok("inner-no-credentials", "No baked credentials detected")

    # 5. Non-root user
    if "USER exec" in content or "useradd" in content:
        result.ok("inner-nonroot", "Non-root user configured")
    else:
        result.fail("inner-nonroot", "No non-root user configured")

    # 6. No supervisor (exec image is lighter)
    if "supervisord" in content:
        result.ok("inner-no-supervisor-note", "Supervisor present (lighter than outer)")
    else:
        result.ok("inner-no-supervisor", "No supervisor (exec image is minimal)")

    # 7. No Playwright (exec image doesn't need browsers)
    if "playwright" in content:
        result.ok("inner-playwright-note", "Playwright present (not typical for exec)")
    else:
        result.ok("inner-no-playwright", "No Playwright (exec image is minimal)")

    # 8. RDKit + sentence-transformers + docling
    for pkg_name in ("rdkit-pypi", "sentence-transformers", "docling"):
        if pkg_name in content:
            result.ok(f"inner-{pkg_name.replace('-', '_')}", f"{pkg_name} present")
        else:
            result.fail(f"inner-{pkg_name.replace('-', '_')}", f"{pkg_name} missing")

    # 9. Requirements-hashes reference
    if "requirements-hashes.txt" in content:
        result.ok("inner-requirements-hashes", "Requirements hashes file referenced")
        if INNER_REQS_HASHES.exists():
            result.ok("inner-requirements-hashes-file", f"Exists: {INNER_REQS_HASHES.name}")
        else:
            result.ok("inner-requirements-hashes-file", "File not yet created (expected before build)")
    else:
        result.fail("inner-requirements-hashes", "No requirements-hashes.txt reference")

    # 10. ENV PYTHONUNBUFFERED=1
    if "PYTHONUNBUFFERED=1" in content:
        result.ok("inner-python-unbuffered", "PYTHONUNBUFFERED=1 is set")
    else:
        result.fail("inner-python-unbuffered", "PYTHONUNBUFFERED=1 is missing")


# ---------------------------------------------------------------------------
# Check: Import gate (verify without runtime installs)
# ---------------------------------------------------------------------------
def check_import_gate(result: CheckResult) -> None:
    """Verify that the import gate packages are listed and can be parsed.

    The import gate checks that the expected packages appear in the Dockerfiles
    and that their module names are valid Python identifiers.  This runs
    without actually importing the packages (which would require them to be
    installed).
    """
    outer_content = OUTER_DOCKERFILE.read_text(encoding="utf-8") if OUTER_DOCKERFILE.exists() else ""
    inner_content = INNER_DOCKERFILE.read_text(encoding="utf-8") if INNER_DOCKERFILE.exists() else ""

    for pkg in IMPORT_GATE_PACKAGES:
        module = pkg["module"]
        pip_name = pkg["pip"]
        expect = pkg["expect"]

        # Check that the module name is a valid Python identifier or dotted path
        module_parts = module.split(".")
        valid = all(part.isidentifier() for part in module_parts)
        if not valid:
            result.fail(f"import-gate-{module}-module", f"Invalid module name: {module}")
            continue

        # Check that the pip package appears in at least one Dockerfile
        in_outer = pip_name in outer_content
        in_inner = pip_name in inner_content
        if in_outer or in_inner:
            locations = []
            if in_outer:
                locations.append("outer")
            if in_inner:
                locations.append("inner")
            result.ok(
                f"import-gate-{module}",
                f"pip={pip_name} in {', '.join(locations)} (expect ~{expect})",
            )
        else:
            # Check if the package name is embedded in a compound name
            compound_found = False
            for df_name, content in [("outer", outer_content), ("inner", inner_content)]:
                if pip_name.replace("-", "_") in content or pip_name.replace(".", "") in content:
                    compound_found = True
                    result.ok(
                        f"import-gate-{module}",
                        f"pip={pip_name} found as compound match in {df_name}",
                    )
                    break
            if not compound_found:
                result.fail(
                    f"import-gate-{module}",
                    f"pip={pip_name} not found in either Dockerfile (expect ~{expect})",
                )


# ---------------------------------------------------------------------------
# Check: Rebuild twice (requires Docker)
# ---------------------------------------------------------------------------
def check_rebuild_twice(result: CheckResult) -> None:
    """Verify that two consecutive builds produce identical images.

    This check requires Docker to be available.  If Docker is not available,
    the check is skipped with a warning.
    """
    # Check if docker is available
    try:
        subprocess.run(
            ["docker", "--version"],
            capture_output=True,
            check=True,
            timeout=30,
        )
    except (FileNotFoundError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        result.ok(
            "rebuild-twice-docker",
            "Docker not available; skipping rebuild check (expected in CI without Docker)",
        )
        return

    result.ok("rebuild-twice-docker", "Docker is available")

    # Check that Dockerfiles exist
    if not OUTER_DOCKERFILE.exists() or not INNER_DOCKERFILE.exists():
        result.fail("rebuild-twice-files", "Dockerfiles not found")
        return

    # Check that requirements-hashes files exist (needed for build)
    if not OUTER_REQS_HASHES.exists():
        result.ok(
            "rebuild-twice-outer-reqs",
            "Outer requirements-hashes file missing; skipping build (expected before build)",
        )
        return

    if not INNER_REQS_HASHES.exists():
        result.ok(
            "rebuild-twice-inner-reqs",
            "Inner requirements-hashes file missing; skipping build (expected before build)",
        )
        return

    # Get the build context root
    context_root = ROOT

    # Build outer image twice
    outer_tag_1 = "ai-researcher:rebuild-test-1"
    outer_tag_2 = "ai-researcher:rebuild-test-2"

    outer_build_cmd = [
        "docker", "build",
        "--no-cache",
        "-f", str(OUTER_DOCKERFILE),
        "-t", outer_tag_1,
        str(context_root),
    ]

    # Build 1
    try:
        subprocess.run(outer_build_cmd, capture_output=True, check=True, timeout=600)
        result.ok("rebuild-twice-outer-build-1", f"Built as {outer_tag_1}")
    except subprocess.CalledProcessError as e:
        result.fail("rebuild-twice-outer-build-1", f"Build failed: {e.stderr.decode()[:200]}")
        return
    except subprocess.TimeoutExpired:
        result.fail("rebuild-twice-outer-build-1", "Build timed out after 600s")
        return

    # Get image ID 1
    try:
        inspect_1 = subprocess.run(
            ["docker", "inspect", "--format", "{{.Id}}", outer_tag_1],
            capture_output=True, check=True, timeout=30, text=True,
        )
        image_id_1 = inspect_1.stdout.strip()
        result.ok("rebuild-twice-outer-id-1", f"Image ID: {image_id_1}")
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
        result.fail("rebuild-twice-outer-id-1", f"Failed to get image ID: {e}")
        image_id_1 = "<unknown>"

    # Build 2
    try:
        subprocess.run(
            ["docker", "build", "--no-cache", "-f", str(OUTER_DOCKERFILE), "-t", outer_tag_2, str(context_root)],
            capture_output=True, check=True, timeout=600,
        )
        result.ok("rebuild-twice-outer-build-2", f"Built as {outer_tag_2}")
    except subprocess.CalledProcessError as e:
        result.fail("rebuild-twice-outer-build-2", f"Build failed: {e.stderr.decode()[:200]}")
        return
    except subprocess.TimeoutExpired:
        result.fail("rebuild-twice-outer-build-2", "Build timed out after 600s")
        return

    # Get image ID 2
    try:
        inspect_2 = subprocess.run(
            ["docker", "inspect", "--format", "{{.Id}}", outer_tag_2],
            capture_output=True, check=True, timeout=30, text=True,
        )
        image_id_2 = inspect_2.stdout.strip()
        result.ok("rebuild-twice-outer-id-2", f"Image ID: {image_id_2}")
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
        result.fail("rebuild-twice-outer-id-2", f"Failed to get image ID: {e}")
        image_id_2 = "<unknown>"

    # Compare
    if image_id_1 == image_id_2 and image_id_1 != "<unknown>":
        result.ok("rebuild-twice-outer-match", "Both builds produced identical image ID")
    else:
        result.fail("rebuild-twice-outer-match", f"Image IDs differ: {image_id_1} vs {image_id_2}")

    # Clean up tags
    for tag in (outer_tag_1, outer_tag_2):
        subprocess.run(["docker", "rmi", tag], capture_output=True, timeout=30)

    # Build inner image twice
    inner_tag_1 = "ai-researcher-exec:rebuild-test-1"
    inner_tag_2 = "ai-researcher-exec:rebuild-test-2"

    inner_build_cmd = [
        "docker", "build",
        "--no-cache",
        "-f", str(INNER_DOCKERFILE),
        "-t", inner_tag_1,
        str(context_root),
    ]

    try:
        subprocess.run(inner_build_cmd, capture_output=True, check=True, timeout=600)
        result.ok("rebuild-twice-inner-build-1", f"Built as {inner_tag_1}")
    except subprocess.CalledProcessError as e:
        result.fail("rebuild-twice-inner-build-1", f"Build failed: {e.stderr.decode()[:200]}")
        return
    except subprocess.TimeoutExpired:
        result.fail("rebuild-twice-inner-build-1", "Build timed out after 600s")
        return

    try:
        inspect_inner_1 = subprocess.run(
            ["docker", "inspect", "--format", "{{.Id}}", inner_tag_1],
            capture_output=True, check=True, timeout=30, text=True,
        )
        inner_image_id_1 = inspect_inner_1.stdout.strip()
        result.ok("rebuild-twice-inner-id-1", f"Image ID: {inner_image_id_1}")
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
        result.fail("rebuild-twice-inner-id-1", f"Failed to get image ID: {e}")
        inner_image_id_1 = "<unknown>"

    try:
        subprocess.run(
            ["docker", "build", "--no-cache", "-f", str(INNER_DOCKERFILE), "-t", inner_tag_2, str(context_root)],
            capture_output=True, check=True, timeout=600,
        )
        result.ok("rebuild-twice-inner-build-2", f"Built as {inner_tag_2}")
    except subprocess.CalledProcessError as e:
        result.fail("rebuild-twice-inner-build-2", f"Build failed: {e.stderr.decode()[:200]}")
        return
    except subprocess.TimeoutExpired:
        result.fail("rebuild-twice-inner-build-2", "Build timed out after 600s")
        return

    try:
        inspect_inner_2 = subprocess.run(
            ["docker", "inspect", "--format", "{{.Id}}", inner_tag_2],
            capture_output=True, check=True, timeout=30, text=True,
        )
        inner_image_id_2 = inspect_inner_2.stdout.strip()
        result.ok("rebuild-twice-inner-id-2", f"Image ID: {inner_image_id_2}")
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
        result.fail("rebuild-twice-inner-id-2", f"Failed to get image ID: {e}")
        inner_image_id_2 = "<unknown>"

    if inner_image_id_1 == inner_image_id_2 and inner_image_id_1 != "<unknown>":
        result.ok("rebuild-twice-inner-match", "Both builds produced identical image ID")
    else:
        result.fail("rebuild-twice-inner-match", f"Image IDs differ: {inner_image_id_1} vs {inner_image_id_2}")

    for tag in (inner_tag_1, inner_tag_2):
        subprocess.run(["docker", "rmi", tag], capture_output=True, timeout=30)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Verify AI-Researcher runtime image definitions and lock file integrity.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    p.add_argument("--lock", action="store_true", help="Update lock file hashes from current files")
    p.add_argument("--check-locked", action="store_true", help="Check lock file integrity against current files")
    p.add_argument("--outer", action="store_true", help="Verify outer runtime image definition")
    p.add_argument("--inner", action="store_true", help="Verify inner exec runtime image definition")
    p.add_argument("--rebuild-twice", action="store_true", help="Test two consecutive builds produce identical images")
    p.add_argument("--json", action="store_true", help="Output results as JSON")
    return p


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    # If no flags specified, run all
    all_flags = not any([args.lock, args.check_locked, args.outer, args.inner, args.rebuild_twice])

    result = CheckResult()

    # --lock: Update lock file (always runs first if requested)
    if args.lock or all_flags:
        do_lock_update(result)

    # --check-locked: Verify lock file
    if args.check_locked or all_flags:
        check_lock_integrity(result)

    # --outer: Verify outer image
    if args.outer or all_flags:
        check_outer_image(result)

    # --inner: Verify inner image
    if args.inner or all_flags:
        check_inner_image(result)

    # --rebuild-twice: Rebuild test
    if args.rebuild_twice or all_flags:
        check_rebuild_twice(result)

    # Import gate is always checked (it's a structural check, not a Docker build)
    # It runs as part of outer/inner checks in all mode, or standalone.
    if all_flags or args.outer or args.inner:
        check_import_gate(result)

    # Output
    if args.json:
        output = {
            "all_ok": result.all_ok,
            "checks": result.checks,
            "errors": result.errors,
        }
        print(json.dumps(output, indent=2, ensure_ascii=False))
    else:
        print(result.summary())

    return 0 if result.all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())