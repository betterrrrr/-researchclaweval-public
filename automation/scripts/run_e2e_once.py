#!/usr/bin/env python3
import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from run_isolation import (
    authoritative_topic_runtime_mounts,
    ensure_authoritative_mount_targets,
    prepare_attempt_runtime,
    render_project_command_for_run,
)
from topic_runtime import load_topic_config, render_topic_command

REPO_ROOT = Path(os.environ.get("RESEARCHCLAWEVAL_ROOT", str(Path(__file__).resolve().parents[2]))).expanduser()
AUTOMATION_DIR = Path(os.environ.get("RESEARCHCLAWEVAL_AUTOMATION_DIR", str(REPO_ROOT / "automation")))
PROJECTS_FILE = AUTOMATION_DIR / "projects.yaml"
STATE_DIR = AUTOMATION_DIR / "state/projects"
RUNS_DIR = AUTOMATION_DIR / "runs"
ORCHESTRATOR = REPO_ROOT / "automation/scripts/orchestrator.py"
VALIDATOR = REPO_ROOT / "automation/scripts/validate_project_alignment.py"
TMP_RUNS_DIR = Path(os.environ.get("RESEARCHCLAWEVAL_TMP_RUNS_DIR", "/tmp/researchclaweval-runs"))
TOPIC = load_topic_config(REPO_ROOT, AUTOMATION_DIR)
TOPIC_LABEL = TOPIC.label
TOPIC_DATASET_ROOT = str(TOPIC.dataset_root)
TOPIC_CONTRACT_FILE = str(TOPIC.contract_file)


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat()


def load_projects() -> dict:
    return json.loads(PROJECTS_FILE.read_text(encoding="utf-8"))


def project_by_id(project_id: str) -> dict:
    for project in load_projects()["projects"]:
        if project["id"] == project_id:
            return project
    raise KeyError(f"unknown project id: {project_id}")


def state_path(project_id: str) -> Path:
    return STATE_DIR / f"{project_id}.json"


def write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def render_project_command(command: str) -> str:
    return render_topic_command(command, TOPIC)


def run_validation(project_id: str) -> tuple[bool, str]:
    proc = subprocess.run(
        [sys.executable, str(VALIDATOR), "--project-id", project_id, "--phase", "e2e"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        env={
            **os.environ,
            "RESEARCHCLAWEVAL_TOPIC_LABEL": TOPIC_LABEL,
            "RESEARCHCLAWEVAL_TOPIC_DATASET_ROOT": TOPIC_DATASET_ROOT,
            "RESEARCHCLAWEVAL_TOPIC_CONTRACT_FILE": TOPIC_CONTRACT_FILE,
        },
    )
    output = (proc.stdout or "") + (proc.stderr or "")
    return proc.returncode == 0, output.strip()


def dispatch_followup(project_id: str, attempt: int, source_unit: str) -> None:
    followup_unit = f"researchclaweval-followup-{project_id}-attempt-{attempt:03d}-{int(datetime.now(timezone.utc).timestamp())}"
    cmd = [
        "systemd-run",
        "--user",
        "--collect",
        "--unit",
        followup_unit,
        "--same-dir",
        "--setenv",
        f"RESEARCHCLAWEVAL_FOLLOWUP_SOURCE_UNIT={source_unit}",
        "--setenv",
        f"RESEARCHCLAWEVAL_ROOT={REPO_ROOT}",
        "--setenv",
        f"RESEARCHCLAWEVAL_AUTOMATION_DIR={AUTOMATION_DIR}",
        "--setenv",
        f"RESEARCHCLAWEVAL_TOPIC_LABEL={TOPIC_LABEL}",
        "--setenv",
        f"RESEARCHCLAWEVAL_TOPIC_DATASET_ROOT={TOPIC_DATASET_ROOT}",
        "--setenv",
        f"RESEARCHCLAWEVAL_TOPIC_CONTRACT_FILE={TOPIC_CONTRACT_FILE}",
        "--setenv",
        f"RESEARCHCLAWEVAL_BABYLM_ROOT={TOPIC_DATASET_ROOT}",
        "--setenv",
        f"RESEARCHCLAWEVAL_BABYLM_TASK_FILE={TOPIC_CONTRACT_FILE}",
        sys.executable,
        str(ORCHESTRATOR),
        "step",
        "--trigger",
        "e2e-followup",
    ]
    subprocess.run(cmd, cwd=REPO_ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-id", required=True)
    parser.add_argument("--attempt", type=int, required=True)
    args = parser.parse_args()

    project = project_by_id(args.project_id)
    run_dir = RUNS_DIR / args.project_id / f"attempt-{args.attempt:03d}"
    isolation, manifest = prepare_attempt_runtime(
        repo_root=REPO_ROOT,
        automation_dir=AUTOMATION_DIR,
        project=project,
        attempt=args.attempt,
        topic_label=TOPIC_LABEL,
        base_tmp_root=TMP_RUNS_DIR,
        repo_attempt_dir=run_dir,
        topic_contract_file=TOPIC.contract_file,
    )
    ensure_authoritative_mount_targets(isolation, TOPIC)

    unit_name = os.environ.get("RESEARCHCLAWEVAL_UNIT_NAME", "")
    started = now_iso()
    log_path = run_dir / "e2e.log"
    metadata_path = run_dir / "e2e.status.json"
    rendered_command = render_project_command_for_run(
        render_project_command(project["e2e_cmd"]),
        project,
        isolation,
        {"__HOST_TOPIC_RUNTIME_MOUNTS__": authoritative_topic_runtime_mounts(REPO_ROOT, TOPIC)},
    )

    current = {
        "project_id": args.project_id,
        "project_name": project["name"],
        "phase": "e2e",
        "status": "e2e_running",
        "attempt": args.attempt,
        "unit": unit_name,
        "started_at": started,
        "command": project["e2e_cmd"],
        "resolved_command": rendered_command,
        "run_dir": str(run_dir),
        "topic_label": TOPIC_LABEL,
        "topic_dataset_root": TOPIC_DATASET_ROOT,
        "topic_contract_file": TOPIC_CONTRACT_FILE,
        "isolated_run_root": str(isolation.tmp_root),
        "snapshot_repo_root": manifest["snapshot_repo"],
        "repo_attempt_dir": str(run_dir),
    }
    write_json(state_path(args.project_id), current)
    write_json(metadata_path, current)

    with log_path.open("wb") as log_fp:
        proc = subprocess.run(
            ["bash", "-lc", rendered_command],
            cwd=isolation.repo_dir,
            stdout=log_fp,
            stderr=subprocess.STDOUT,
            env={
                **os.environ,
                "HOME": str(isolation.home_dir),
                "CODEX_HOME": str(isolation.codex_home_dir),
                "XDG_CACHE_HOME": str(isolation.cache_dir),
                "XDG_STATE_HOME": str(isolation.state_dir),
                "TMPDIR": str(isolation.scratch_dir),
                "RESEARCHCLAWEVAL_TOPIC_LABEL": TOPIC_LABEL,
                "RESEARCHCLAWEVAL_TOPIC_DATASET_ROOT": TOPIC_DATASET_ROOT,
                "RESEARCHCLAWEVAL_TOPIC_CONTRACT_FILE": TOPIC_CONTRACT_FILE,
                "RESEARCHCLAWEVAL_BABYLM_ROOT": TOPIC_DATASET_ROOT,
                "RESEARCHCLAWEVAL_BABYLM_TASK_FILE": TOPIC_CONTRACT_FILE,
                "RESEARCHCLAWEVAL_AUTOMATION_DIR": str(AUTOMATION_DIR),
            },
        )

    finished = now_iso()
    validation_ok = False
    validation_output = ""
    if proc.returncode == 0:
        validation_ok, validation_output = run_validation(args.project_id)
    # 框架 exit code 0 即视为成功；验证结果只记录不影响 pass/fail
    result = "passed" if proc.returncode == 0 else "failed"
    adaptation_notes = []
    if proc.returncode == 0 and not validation_ok:
        adaptation_notes.append(
            f"framework exited 0 but validation reported issues: {validation_output[:200]}"
        )
    final_state = {
        **current,
        "status": f"e2e_{result}",
        "finished_at": finished,
        "exit_code": proc.returncode,
        "log_file": str(log_path),
        "framework_completed": proc.returncode == 0,
        "validation_ok": validation_ok,
        "validation_output": validation_output,
        "adaptation_notes": adaptation_notes,
    }
    write_json(state_path(args.project_id), final_state)
    write_json(metadata_path, final_state)
    dispatch_followup(args.project_id, args.attempt, unit_name)
    return 0 if result == "passed" else 1


if __name__ == "__main__":
    sys.exit(main())
