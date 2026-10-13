#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

SOURCE_REPO_ROOT = Path(__file__).resolve().parents[2]
PROVIDER_CONFIG_RELATIVE = Path("api/codex_gpt54_shubiaobiao.toml")
SEMANTIC_SOURCE_RELATIVE = Path("api/_semantic_scholar_api_usage.md")


@dataclass(frozen=True)
class RunIsolation:
    project_id: str
    topic_slug: str
    attempt: int
    source_repo_root: Path
    topic_contract_file: Path | None
    authoritative_automation_dir: Path
    authoritative_state_dir: Path
    authoritative_runs_dir: Path
    tmp_root: Path
    repo_dir: Path
    home_dir: Path
    codex_home_dir: Path
    cache_dir: Path
    state_dir: Path
    logs_dir: Path
    scratch_dir: Path
    manifest_path: Path


def _slugify_topic(topic_label: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", topic_label.lower()).strip("-")
    return slug or "topic"


def allocate_run_isolation(
    *,
    repo_root: Path,
    automation_dir: Path,
    project: dict[str, str],
    attempt: int,
    topic_label: str,
    base_tmp_root: Path,
    topic_contract_file: Path | None = None,
) -> RunIsolation:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S-%f")
    token = f"{stamp}-{uuid4().hex[:8]}-attempt-{attempt:03d}"
    topic_slug = _slugify_topic(topic_label)
    tmp_root = base_tmp_root / topic_slug / project["id"] / token
    return RunIsolation(
        project_id=project["id"],
        topic_slug=topic_slug,
        attempt=attempt,
        source_repo_root=repo_root,
        topic_contract_file=topic_contract_file,
        authoritative_automation_dir=automation_dir,
        authoritative_state_dir=automation_dir / "state",
        authoritative_runs_dir=automation_dir / "runs",
        tmp_root=tmp_root,
        repo_dir=tmp_root / "repo",
        home_dir=tmp_root / "home",
        codex_home_dir=tmp_root / "codex-home",
        cache_dir=tmp_root / "cache",
        state_dir=tmp_root / "state",
        logs_dir=tmp_root / "logs",
        scratch_dir=tmp_root / "scratch",
        manifest_path=tmp_root / "run_manifest.json",
    )


def write_run_manifest(isolation: RunIsolation, payload: dict[str, object]) -> Path:
    isolation.manifest_path.parent.mkdir(parents=True, exist_ok=True)
    isolation.manifest_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return isolation.manifest_path


def repo_relative_path(host_path: Path, repo_root: Path) -> Path:
    try:
        return host_path.relative_to(repo_root)
    except ValueError:
        pass

    repo_name = repo_root.name
    if repo_root.parent.name == ".worktrees" and repo_root.parent.parent.name:
        repo_name = repo_root.parent.parent.name
    parts = host_path.parts
    if repo_name in parts:
        anchor = parts.index(repo_name)
        if anchor + 1 < len(parts):
            return Path(*parts[anchor + 1 :])
        return Path()
    raise ValueError(f"{host_path!s} is not mappable into repo root {repo_root!s}")


def _framework_override(host_path: Path) -> Path | None:
    framework_name = host_path.parent.name if host_path.name == "project4.env" else host_path.name
    specific_name = re.sub(r"[^A-Za-z0-9]+", "_", framework_name).upper()
    specific = os.environ.get(f"RESEARCHCLAWEVAL_{specific_name}_ROOT")
    if specific:
        root = Path(specific).expanduser()
        return root / host_path.name if host_path.name == "project4.env" else root
    frameworks_root = os.environ.get("RESEARCHCLAWEVAL_FRAMEWORKS_ROOT")
    if frameworks_root:
        root = Path(frameworks_root).expanduser() / framework_name
        return root / host_path.name if host_path.name == "project4.env" else root
    return None


def authoritative_host_path(host_path: str, repo_root: Path) -> Path:
    candidate = Path(host_path)
    try:
        if candidate.exists():
            return candidate
    except OSError:
        pass

    override = _framework_override(candidate)
    if override is not None:
        return override

    relative = repo_relative_path(candidate, repo_root)
    search_roots = [repo_root]
    if repo_root.parent.name == ".worktrees":
        search_roots.append(repo_root.parent.parent)

    for root in search_roots:
        resolved = root / relative
        if resolved.exists():
            return resolved
    return search_roots[0] / relative


def _normalize_topic_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.lower())


def load_topic_registry(repo_root: Path) -> list[dict[str, object]]:
    registry_path = repo_root / "real_eval" / "registry" / "topics.json"
    if not registry_path.exists():
        return []
    payload = json.loads(registry_path.read_text(encoding="utf-8"))
    topics = payload.get("topics", [])
    return [topic for topic in topics if isinstance(topic, dict)]


def resolve_current_topic(
    repo_root: Path,
    topic_label: str,
    topic_contract_file: Path | None,
) -> dict[str, object] | None:
    topics = load_topic_registry(repo_root)
    if not topics:
        return None

    if topic_contract_file is not None:
        contract_name = topic_contract_file.name
        for topic in topics:
            if Path(str(topic.get("contract_file", ""))).name == contract_name:
                return topic

    normalized_label = _normalize_topic_key(topic_label)
    for topic in topics:
        keys = {
            _normalize_topic_key(str(topic.get("id", ""))),
            _normalize_topic_key(str(topic.get("label", ""))),
            _normalize_topic_key(Path(str(topic.get("contract_file", ""))).stem),
        }
        if normalized_label in keys:
            return topic
    return None


def topic_manifest_paths(repo_dir: Path, topic: dict[str, object]) -> set[Path]:
    manifest_path = repo_dir / "automation" / f"{topic['id']}_manifest.json"
    if not manifest_path.exists():
        return set()

    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    files = payload.get("files", [])
    if isinstance(files, dict):
        entries = files.keys()
    elif isinstance(files, list):
        entries = files
    else:
        entries = []
    return {repo_dir / Path(str(entry)) for entry in entries}


def topic_scope_removals(isolation: RunIsolation) -> set[Path]:
    current_topic = resolve_current_topic(
        isolation.source_repo_root,
        isolation.topic_slug,
        isolation.topic_contract_file,
    )
    if current_topic is None:
        return set()

    removals: set[Path] = set()
    for topic in load_topic_registry(isolation.source_repo_root):
        if topic.get("id") == current_topic.get("id"):
            continue

        contract_file = topic.get("contract_file")
        if contract_file:
            removals.add(isolation.repo_dir / Path(str(contract_file)))

        for summary_file in topic.get("summary_files", []):
            removals.add(isolation.repo_dir / Path(str(summary_file)))

        dataset_root = topic.get("dataset_root")
        if dataset_root:
            dataset_path = Path(str(dataset_root))
            if not dataset_path.is_absolute():
                removals.add(isolation.repo_dir / dataset_path)

        removals.add(isolation.repo_dir / "automation" / f"{topic['id']}_manifest.json")
        removals.update(topic_manifest_paths(isolation.repo_dir, topic))

    return removals


def project_snapshot_root(project: dict[str, str], isolation: RunIsolation) -> Path:
    project_dir = Path(project["project_dir"])
    relative_project_dir = repo_relative_path(project_dir, isolation.source_repo_root)
    return isolation.repo_dir / relative_project_dir


def snapshot_path_for_host_file(host_path: str, isolation: RunIsolation) -> Path:
    return isolation.repo_dir / repo_relative_path(Path(host_path), isolation.source_repo_root)


def authoritative_topic_runtime_mounts(repo_root: Path, topic) -> str:
    container_repo_root = Path(
        os.environ.get("RESEARCHCLAWEVAL_CONTAINER_ROOT", str(repo_root)),
    ).expanduser()
    provider_config = repo_root / PROVIDER_CONFIG_RELATIVE
    semantic_source = repo_root / SEMANTIC_SOURCE_RELATIVE
    dataset_path = Path(str(topic.dataset_root))
    try:
        dataset_container_path = container_repo_root / repo_relative_path(dataset_path, repo_root)
    except ValueError:
        dataset_container_path = dataset_path
    mounts = [
        (
            authoritative_host_path(str(dataset_path), repo_root),
            dataset_container_path,
        ),
        (
            authoritative_host_path(str(provider_config), repo_root),
            container_repo_root / PROVIDER_CONFIG_RELATIVE,
        ),
        (
            authoritative_host_path(str(semantic_source), repo_root),
            container_repo_root / SEMANTIC_SOURCE_RELATIVE,
        ),
    ]
    rendered: list[str] = []
    seen: set[tuple[str, str]] = set()
    for host_path, container_path in mounts:
        pair = (str(host_path), str(container_path))
        if pair in seen:
            continue
        seen.add(pair)
        rendered.append(f"-v {host_path}:{container_path}:ro")
    return " ".join(rendered)


def ensure_authoritative_mount_targets(isolation: RunIsolation, topic) -> None:
    dataset_target = isolation.repo_dir / repo_relative_path(Path(str(topic.dataset_root)), isolation.source_repo_root)
    dataset_target.mkdir(parents=True, exist_ok=True)

    for target in (PROVIDER_CONFIG_RELATIVE, SEMANTIC_SOURCE_RELATIVE):
        snapshot_target = isolation.repo_dir / target
        snapshot_target.parent.mkdir(parents=True, exist_ok=True)
        snapshot_target.touch(exist_ok=True)


def render_project_command_for_run(
    command: str,
    project: dict[str, str],
    isolation: RunIsolation,
    topic_env: dict[str, str],
) -> str:
    replacements = {
        "__HOST_REPO_ROOT__": str(isolation.repo_dir),
        "__HOST_PROJECT_ROOT__": str(project_snapshot_root(project, isolation)),
        "__HOST_AUTOMATION_DIR__": str(isolation.authoritative_automation_dir),
        "__RUN_HOME__": str(isolation.home_dir),
        "__RUN_CODEX_HOME__": str(isolation.codex_home_dir),
        "__RUN_CACHE_DIR__": str(isolation.cache_dir),
    }
    if env_file := project.get("env_file"):
        replacements["__HOST_PROJECT_ENV_FILE__"] = str(authoritative_host_path(env_file, isolation.source_repo_root))

    rendered = command
    for placeholder, value in replacements.items():
        rendered = rendered.replace(placeholder, value)
    for placeholder, value in topic_env.items():
        rendered = rendered.replace(placeholder, value)
    return rendered


def snapshot_rsync_command(isolation: RunIsolation) -> list[str]:
    return [
        "rsync",
        "-a",
        "--no-owner",
        "--no-group",
        "--exclude",
        ".git",
        "--exclude",
        ".worktrees",
        "--exclude",
        "automation/projects.yaml",
        "--exclude",
        "automation/todo_runtime.md",
        "--exclude",
        "automation/runtime_topic.md",
        "--exclude",
        "automation/runs",
        "--exclude",
        "automation/state",
        "--exclude",
        "automation/env/codex_home",
        "--exclude",
        "real_eval/runs",
        "--exclude",
        "**/.codex*",
        "--exclude",
        "**/.runtime-home",
        "--exclude",
        "**/.deepscientist_home",
        "--exclude",
        "**/workplace_paper",
        f"{isolation.source_repo_root}/",
        str(isolation.repo_dir),
    ]


def excluded_snapshot_paths() -> tuple[str, ...]:
    return (
        "automation/projects.yaml",
        "automation/todo_runtime.md",
        "automation/runtime_topic.md",
    )


def is_runtime_residue(relative_path: Path) -> bool:
    parts = relative_path.parts
    if parts[:2] == ("automation", "runs"):
        return True
    if parts[:2] == ("automation", "state"):
        return True
    if parts[:3] == ("automation", "env", "codex_home"):
        return True
    if parts[:2] == ("real_eval", "runs"):
        return True
    if any(part.startswith(".codex") for part in parts):
        return True
    if ".runtime-home" in parts:
        return True
    if ".deepscientist_home" in parts:
        return True
    if "workplace_paper" in parts:
        return True
    return False


def should_copy_snapshot_path(relative_path: Path) -> bool:
    normalized = relative_path.as_posix()
    if normalized in excluded_snapshot_paths():
        return False
    return not is_runtime_residue(relative_path)


def git_snapshot_paths(repo_root: Path) -> list[Path]:
    proc = subprocess.run(
        [
            "git",
            "-C",
            str(repo_root),
            "ls-files",
            "--cached",
            "--others",
            "--exclude-standard",
            "-z",
        ],
        check=True,
        capture_output=True,
    )
    entries = []
    for raw in proc.stdout.split(b"\0"):
        if not raw:
            continue
        path = Path(os.fsdecode(raw))
        if should_copy_snapshot_path(path):
            entries.append(path)
    return entries


def export_clean_repo_snapshot(isolation: RunIsolation) -> None:
    for relative_path in git_snapshot_paths(isolation.source_repo_root):
        source = isolation.source_repo_root / relative_path
        target = isolation.repo_dir / relative_path
        target.parent.mkdir(parents=True, exist_ok=True)
        if source.is_symlink():
            if target.exists() or target.is_symlink():
                target.unlink()
            target.symlink_to(source.resolve())
            continue
        if source.is_file():
            shutil.copy2(source, target)


def can_export_clean_repo_snapshot(repo_root: Path) -> bool:
    probe = subprocess.run(
        ["git", "-C", str(repo_root), "rev-parse", "--verify", "HEAD"],
        check=False,
        capture_output=True,
        text=True,
    )
    return probe.returncode == 0


def materialize_snapshot(isolation: RunIsolation) -> dict[str, object]:
    if isolation.tmp_root.exists():
        shutil.rmtree(isolation.tmp_root)

    for path in (
        isolation.repo_dir,
        isolation.home_dir,
        isolation.codex_home_dir,
        isolation.cache_dir,
        isolation.state_dir,
        isolation.logs_dir,
        isolation.scratch_dir,
    ):
        path.mkdir(parents=True, exist_ok=True)

    if can_export_clean_repo_snapshot(isolation.source_repo_root):
        export_clean_repo_snapshot(isolation)
    else:
        subprocess.run(snapshot_rsync_command(isolation), check=True)

    for path in sorted(topic_scope_removals(isolation), reverse=True):
        if path.is_dir():
            shutil.rmtree(path, ignore_errors=True)
        elif path.exists():
            path.unlink()

    payload = {
        "project_id": isolation.project_id,
        "attempt": isolation.attempt,
        "snapshot_repo": str(isolation.repo_dir),
        "tmp_root": str(isolation.tmp_root),
        "topic_contract_file": str(isolation.topic_contract_file) if isolation.topic_contract_file else None,
        "authoritative_automation_dir": str(isolation.authoritative_automation_dir),
        "authoritative_state_dir": str(isolation.authoritative_state_dir),
        "authoritative_runs_dir": str(isolation.authoritative_runs_dir),
    }
    write_run_manifest(isolation, payload)
    return payload


def prepare_attempt_runtime(
    *,
    repo_root: Path,
    automation_dir: Path,
    project: dict[str, str],
    attempt: int,
    topic_label: str,
    base_tmp_root: Path,
    repo_attempt_dir: Path,
    topic_contract_file: Path | None = None,
) -> tuple[RunIsolation, dict[str, object]]:
    isolation = allocate_run_isolation(
        repo_root=repo_root,
        automation_dir=automation_dir,
        project=project,
        attempt=attempt,
        topic_label=topic_label,
        base_tmp_root=base_tmp_root,
        topic_contract_file=topic_contract_file,
    )
    manifest = materialize_snapshot(isolation)
    repo_attempt_dir.mkdir(parents=True, exist_ok=True)
    manifest["repo_attempt_dir"] = str(repo_attempt_dir)
    (repo_attempt_dir / "run_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return isolation, manifest
