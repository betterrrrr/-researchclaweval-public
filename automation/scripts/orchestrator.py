#!/usr/bin/env python3
import argparse
import json
import os
import re
import shlex
import shutil
import signal
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from run_isolation import (
    authoritative_topic_runtime_mounts,
    ensure_authoritative_mount_targets,
    prepare_attempt_runtime,
    render_project_command_for_run,
)
from topic_runtime import load_topic_config, render_topic_command, write_runtime_topic_markdown

REPO_ROOT = Path(os.environ.get("RESEARCHCLAWEVAL_ROOT", str(Path(__file__).resolve().parents[2]))).expanduser()
AUTOMATION_DIR = Path(os.environ.get("RESEARCHCLAWEVAL_AUTOMATION_DIR", str(REPO_ROOT / "automation")))
PROJECTS_FILE = AUTOMATION_DIR / "projects.yaml"
TODO_FILE = AUTOMATION_DIR / "todo_runtime.md"
RUNTIME_STATE_FILE = AUTOMATION_DIR / "state/runtime_state.json"
PROJECT_STATE_DIR = AUTOMATION_DIR / "state/projects"
RUNS_DIR = AUTOMATION_DIR / "runs"
CODEX_HOME_DIR = AUTOMATION_DIR / "env/codex_home"
SEMANTIC_ENV_FILE = AUTOMATION_DIR / "env/semantic_scholar.env"
TOPIC = load_topic_config(REPO_ROOT, AUTOMATION_DIR)
TOPIC_LABEL = TOPIC.label
TOPIC_DATASET_ROOT = TOPIC.dataset_root
TOPIC_CONTRACT_FILE = TOPIC.contract_file
CODEX_CONFIG_SOURCE = REPO_ROOT / "api/codex_gpt54_shubiaobiao.toml"
SEMANTIC_SOURCE = REPO_ROOT / "api/_semantic_scholar_api_usage.md"
CODEX_BIN = REPO_ROOT / "codex_runs/bin/codex-wrapper"
E2E_RUNNER = REPO_ROOT / "automation/scripts/run_e2e_once.py"
ORCHESTRATOR_SCRIPT = REPO_ROOT / "automation/scripts/orchestrator.py"
TMP_RUNS_DIR = Path(os.environ.get("RESEARCHCLAWEVAL_TMP_RUNS_DIR", "/tmp/researchclaweval-runs"))
CODEX_TIMEOUT_SECONDS = int(os.environ.get("RESEARCHCLAWEVAL_CODEX_TIMEOUT", "0"))
CODEX_STATE_POLL_SECONDS = float(os.environ.get("RESEARCHCLAWEVAL_CODEX_STATE_POLL_SECONDS", "2"))

TODO_RE = re.compile(r"^- \[([ xX])\] (\d{2}) (.+)$")


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat()


def load_json(path: Path, default):
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def load_projects() -> dict:
    return json.loads(PROJECTS_FILE.read_text(encoding="utf-8"))


def load_project_map() -> dict:
    return {item["id"]: item for item in load_projects()["projects"]}


def project_state_path(project_id: str) -> Path:
    return PROJECT_STATE_DIR / f"{project_id}.json"


def run_dir(project_id: str, attempt: int) -> Path:
    return RUNS_DIR / project_id / f"attempt-{attempt:03d}"


def ensure_materialized_env() -> None:
    CODEX_HOME_DIR.mkdir(parents=True, exist_ok=True)
    write_runtime_topic_markdown(AUTOMATION_DIR / "runtime_topic.md", TOPIC)
    config_text = CODEX_CONFIG_SOURCE.read_text(encoding="utf-8")
    config_text = re.sub(
        r'^model_reasoning_effort\s*=\s*"[^"]+"',
        'model_reasoning_effort = "medium"',
        config_text,
        flags=re.MULTILINE,
    )
    (CODEX_HOME_DIR / "config.toml").write_text(config_text, encoding="utf-8")

    md = SEMANTIC_SOURCE.read_text(encoding="utf-8")
    key_match = re.search(r"Authorization: Bearer ([^\s`|]+)", md)
    base_match = re.search(r"Base URL \| `([^`]+)` \|\n\| API Key \|", md)
    auth_mode = "bearer"
    values = {
        "SEMANTIC_SCHOLAR_AUTH_MODE": auth_mode,
    }
    if key_match:
        values["SEMANTIC_SCHOLAR_API_KEY"] = key_match.group(1)
    if "https://ai4scholar.net" in md:
        values["SEMANTIC_SCHOLAR_API_BASE_URL"] = "https://ai4scholar.net"
    elif base_match:
        values["SEMANTIC_SCHOLAR_API_BASE_URL"] = base_match.group(1)
    content = "".join(f"{k}={v}\n" for k, v in values.items())
    SEMANTIC_ENV_FILE.write_text(content, encoding="utf-8")


def parse_todo() -> list[dict]:
    items = []
    for line in TODO_FILE.read_text(encoding="utf-8").splitlines():
        match = TODO_RE.match(line.strip())
        if not match:
            continue
        items.append(
            {
                "checked": match.group(1).lower() == "x",
                "id": match.group(2),
                "name": match.group(3),
            }
        )
    return items


def mark_todo_complete(project_id: str) -> None:
    lines = TODO_FILE.read_text(encoding="utf-8").splitlines()
    updated = []
    for line in lines:
        match = TODO_RE.match(line.strip())
        if match and match.group(2) == project_id:
            updated.append(f"- [x] {match.group(2)} {match.group(3)}")
        else:
            updated.append(line)
    TODO_FILE.write_text("\n".join(updated) + "\n", encoding="utf-8")


def current_project() -> dict | None:
    projects = load_project_map()
    for item in parse_todo():
        if item["checked"]:
            continue
        project = projects.get(item["id"])
        if project and project.get("enabled", True):
            return project
    return None


def next_attempt(project_id: str) -> int:
    base = RUNS_DIR / project_id
    if not base.exists():
        return 1
    attempts = []
    for path in base.iterdir():
        match = re.fullmatch(r"attempt-(\d{3})", path.name)
        if match:
            attempts.append(int(match.group(1)))
    return max(attempts, default=0) + 1


def load_jsonl_items(path: Path) -> list[dict]:
    if not path.exists():
        return []
    items = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            items.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return items


def normalize_command_text(text: str) -> str:
    return (
        text.replace('\\"', '"')
        .replace("\\\\n", "\\n")
        .replace("/bin/bash -lc ", "")
        .strip()
    )


def render_project_command(command: str) -> str:
    return render_topic_command(command, TOPIC)


def terminate_process_group(proc: subprocess.Popen) -> None:
    if proc.poll() is not None:
        return
    try:
        os.killpg(proc.pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            return
        time.sleep(0.2)
    try:
        os.killpg(proc.pid, signal.SIGKILL)
    except ProcessLookupError:
        return


def run_codex(
    prompt: str,
    work_dir: Path,
    label: str,
    state_file: Path,
    terminal_statuses: set[str],
    *,
    run_cwd: Path,
    home_dir: Path,
    codex_home_dir: Path,
    cache_dir: Path,
    state_dir: Path,
    scratch_dir: Path,
) -> int:
    run_dir_path = work_dir
    run_dir_path.mkdir(parents=True, exist_ok=True)
    stdout_path = run_dir_path / f"{label}.jsonl"
    last_message_path = run_dir_path / f"{label}_last_message.txt"
    cmd = [
        str(CODEX_BIN),
        "exec",
        "--yolo",
        "--skip-git-repo-check",
        "-C",
        str(run_cwd),
        "--json",
        "-o",
        str(last_message_path),
        prompt,
    ]
    env = dict(os.environ)
    codex_home_dir.mkdir(parents=True, exist_ok=True)
    config_source = CODEX_HOME_DIR / "config.toml"
    if config_source.exists():
        shutil.copy2(config_source, codex_home_dir / "config.toml")
    env["HOME"] = str(home_dir)
    env["CODEX_HOME"] = str(codex_home_dir)
    env["XDG_CACHE_HOME"] = str(cache_dir)
    env["XDG_STATE_HOME"] = str(state_dir)
    env["TMPDIR"] = str(scratch_dir)
    env["RESEARCHCLAWEVAL_AUTOMATION_DIR"] = str(AUTOMATION_DIR)
    with stdout_path.open("wb") as fp:
        proc = subprocess.Popen(
            cmd,
            cwd=run_cwd,
            stdout=fp,
            stderr=subprocess.STDOUT,
            env=env,
            preexec_fn=os.setsid,
        )
        deadline = None if CODEX_TIMEOUT_SECONDS <= 0 else time.monotonic() + CODEX_TIMEOUT_SECONDS
        while True:
            rc = proc.poll()
            if rc is not None:
                return rc

            state = load_json(state_file, {})
            if state.get("status") in terminal_statuses:
                terminate_process_group(proc)
                return 0

            if deadline is not None and time.monotonic() >= deadline:
                terminate_process_group(proc)
                return 124

            time.sleep(CODEX_STATE_POLL_SECONDS)


def write_runtime_state(**kwargs) -> None:
    state = load_json(RUNTIME_STATE_FILE, {})
    state.update(kwargs)
    state["updated_at"] = now_iso()
    write_json(RUNTIME_STATE_FILE, state)


def dispatch_next_step(trigger: str, source_project_id: str) -> None:
    next_project = current_project()
    if next_project is None:
        return
    follow_unit = (
        f"researchclaweval-next-{source_project_id}-to-{next_project['id']}-"
        f"{int(datetime.now(timezone.utc).timestamp())}"
    )
    cmd = [
        "systemd-run",
        "--user",
        "--collect",
        "--unit",
        follow_unit,
        "--same-dir",
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
        sys.executable,
        str(ORCHESTRATOR_SCRIPT),
        "step",
        "--trigger",
        trigger,
    ]
    subprocess.run(cmd, cwd=REPO_ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def initial_prompt(project: dict, state_file: Path, attempt: int, unit_name: str, smoke_command: str) -> str:
    systemd_cmd = build_systemd_command(project, attempt, unit_name)
    return f"""
 你在 {REPO_ROOT} 工作。

只处理项目 {project["id"]} {project["name"]}。
当前自动化目录是：{AUTOMATION_DIR}
只允许读取这个自动化目录下的运行文件，不要读取仓库里其它 `todo` 或其它项目状态。

固定规则：
- 你必须先在当前这轮 headless codex exec 内同步阻塞完成 smoke。
- smoke 阶段还必须检查“当前项目真正的 e2e 输入”是否已经对齐当前 topic contract；如果没有对齐，先做最小必要修改。
- 如果 smoke 通过，必须在同一个 headless 会话里继续提交 systemd --user 的 e2e 任务，然后停止。
- 如果 smoke 失败：
  - 先读报错
  - 做最小必要修复
  - 重试一次 smoke
- 如果 smoke 最终失败，不允许提交任何 systemd --user 命令。
- 必须使用 --yolo 模式运行。
- Provider 来源固定为 {CODEX_CONFIG_SOURCE}
- Semantic Scholar 来源固定为 {SEMANTIC_SOURCE}

请先执行下面这条 smoke 命令：
{smoke_command}

如果 smoke 通过，再原样提交这条 e2e 命令：
{systemd_cmd}

当前 topic contract：
- topic 名称：{TOPIC_LABEL}
- 数据集根目录固定为：{TOPIC_DATASET_ROOT}
- topic contract 文件固定为：{TOPIC_CONTRACT_FILE}

只有在以下前提都满足时，才允许 dispatch e2e：
- 你已经确认后续 e2e 跑的是当前 topic，不是旧 topic
- 你已经让当前项目知道数据集位置或 topic contract 文件位置
- 如需修改，只做最小必要修改

无论结果如何，都把结构化 JSON 写到：
{state_file}

JSON 至少包含：
- project_id
- project_name
- phase=smoke 或 e2e
- status=smoke_failed 或 e2e_submitted
- attempt={attempt}
- smoke_command
- unit={unit_name}
- e2e_command
- submit_command
- topic_label
- topic_dataset_root
- topic_contract_file
- topic_ready=true 或 false
- acceptance_summary
- patched_files
- summary
""".strip()


def build_systemd_command(project: dict, attempt: int, unit_name: str) -> str:
    runner_cmd = [
        "systemd-run",
        "--user",
        "--collect",
        "--unit",
        unit_name,
        "--same-dir",
        "--setenv",
        f"RESEARCHCLAWEVAL_UNIT_NAME={unit_name}",
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
        str(E2E_RUNNER),
        "--project-id",
        project["id"],
        "--attempt",
        str(attempt),
    ]
    return shlex.join(runner_cmd)


def recover_initial_dispatch(project: dict, attempt: int, work_dir: Path, state_file: Path, unit_name: str) -> bool:
    log_path = work_dir / "initial.jsonl"
    items = load_jsonl_items(log_path)
    smoke_ok = False
    codex_platform_error = False
    normalized_smoke_cmd = normalize_command_text(render_project_command(project["smoke_cmd"]))
    for entry in items:
        if entry.get("type") == "item.completed":
            item = entry.get("item", {})
            if item.get("type") == "command_execution" and item.get("exit_code") == 0:
                command_text = normalize_command_text(item.get("command", ""))
                if normalized_smoke_cmd in command_text or command_text in normalized_smoke_cmd:
                    smoke_ok = True
        if entry.get("type") == "error":
            message = entry.get("message", "")
            if "invalid_encrypted_content" in message:
                codex_platform_error = True
    if not smoke_ok or not codex_platform_error:
        return False

    submit_command = build_systemd_command(project, attempt, unit_name)
    proc = subprocess.run(
        ["bash", "-lc", submit_command],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        return False

    write_json(
        state_file,
        {
            "project_id": project["id"],
            "project_name": project["name"],
            "phase": "e2e",
            "status": "e2e_submitted",
            "attempt": attempt,
            "unit": unit_name,
            "smoke_command": render_project_command(project["smoke_cmd"]),
            "e2e_command": render_project_command(project["e2e_cmd"]),
            "submit_command": submit_command,
            "topic_label": TOPIC_LABEL,
            "topic_dataset_root": str(TOPIC_DATASET_ROOT),
            "topic_contract_file": str(TOPIC_CONTRACT_FILE),
            "topic_ready": True,
            "acceptance_summary": "Recovered dispatch after smoke succeeded and the current topic contract remained required.",
            "patched_files": [],
            "summary": "Recovered from codex platform error after successful smoke by dispatching the prepared systemd unit.",
        },
    )
    return True


def reconcile_e2e_state(project_id: str, attempt: int, state_file: Path) -> dict:
    current = load_json(state_file, {})
    metadata_path = run_dir(project_id, attempt) / "e2e.status.json"
    metadata = load_json(metadata_path, {})
    if metadata.get("status") in {"e2e_failed", "e2e_passed"}:
        write_json(state_file, metadata)
        return metadata
    return current


def repair_prompt(project: dict, state_file: Path, attempt: int, unit_name: str, new_unit: str) -> str:
    systemd_cmd = build_systemd_command(project, attempt, new_unit)
    journal_cmd = f"journalctl --user -u {unit_name} -n 200 --no-pager"
    failure_hint = ""
    if project.get("failure_mode") == "block_on_failure":
        failure_hint = "\n- 这是一个合成失败测试用例。不要重新提交 e2e，直接把项目标记为 blocked。\n"
    return f"""
 你在 {REPO_ROOT} 工作。

只处理项目 {project["id"]} {project["name"]} 的 e2e 失败修复。
当前自动化目录是：{AUTOMATION_DIR}
只允许读取这个自动化目录下的运行文件，不要读取仓库里其它 `todo` 或其它项目状态。

固定规则：
- 先查看失败 unit 日志：{journal_cmd}
- 优先修配置和脚本，不随意改外层 docker 入口
- 如果可修复，必须在同一个 headless 会话里提交新的 systemd --user e2e 任务，然后停止
- 如果无法继续，请把项目标成 blocked
- 必须使用 --yolo 模式运行
- 修复后提交出去的 e2e 必须继续保持当前 topic，不允许回退到旧 topic
- 当前 topic 名称：{TOPIC_LABEL}
- 数据集根目录固定为：{TOPIC_DATASET_ROOT}
- topic contract 文件固定为：{TOPIC_CONTRACT_FILE}
{failure_hint}

新的 e2e 提交命令如下：
{systemd_cmd}

最终把结构化 JSON 写到：
{state_file}

JSON 至少包含：
- project_id
- phase=e2e
- status=e2e_resubmitted 或 blocked
- attempt={attempt}
- previous_unit={unit_name}
- unit={new_unit}
- topic_label
- topic_dataset_root
- topic_contract_file
- patched_files
- summary
""".strip()


def systemd_status(unit_name: str) -> dict:
    cmd = [
        "systemctl",
        "--user",
        "show",
        unit_name,
        "--property",
        "ActiveState,SubState,Result,ExecMainStatus,ExecMainCode",
    ]
    proc = subprocess.run(cmd, cwd=REPO_ROOT, capture_output=True, text=True)
    if proc.returncode != 0:
        return {"exists": False, "raw": proc.stdout + proc.stderr}
    data = {"exists": True}
    for line in proc.stdout.splitlines():
        if "=" in line:
            key, value = line.split("=", 1)
            data[key] = value
    return data


def handle_initial_session(project: dict) -> int:
    attempt = next_attempt(project["id"])
    work_dir = run_dir(project["id"], attempt)
    state_file = project_state_path(project["id"])
    unit_name = f"researchclaweval-{project['id']}-e2e-attempt-{attempt:03d}"
    isolation, manifest = prepare_attempt_runtime(
        repo_root=REPO_ROOT,
        automation_dir=AUTOMATION_DIR,
        project=project,
        attempt=attempt,
        topic_label=TOPIC_LABEL,
        base_tmp_root=TMP_RUNS_DIR,
        repo_attempt_dir=work_dir,
        topic_contract_file=TOPIC_CONTRACT_FILE,
    )
    ensure_authoritative_mount_targets(isolation, TOPIC)
    smoke_command = render_project_command_for_run(
        render_project_command(project["smoke_cmd"]),
        project,
        isolation,
        {"__HOST_TOPIC_RUNTIME_MOUNTS__": authoritative_topic_runtime_mounts(REPO_ROOT, TOPIC)},
    )
    write_runtime_state(
        current_project=project["id"],
        last_action="initial_session",
        last_unit=unit_name,
        last_isolated_run_root=str(isolation.tmp_root),
    )
    rc = run_codex(
        initial_prompt(project, state_file, attempt, unit_name, smoke_command),
        work_dir,
        "initial",
        state_file,
        {"smoke_failed", "e2e_submitted", "e2e_running"},
        run_cwd=isolation.repo_dir,
        home_dir=isolation.home_dir,
        codex_home_dir=isolation.codex_home_dir,
        cache_dir=isolation.cache_dir,
        state_dir=isolation.state_dir,
        scratch_dir=isolation.scratch_dir,
    )
    state = load_json(state_file, {})
    if state.get("status") in {"e2e_submitted", "e2e_running"}:
        state = reconcile_e2e_state(project["id"], attempt, state_file)
        return 0
    if recover_initial_dispatch(project, attempt, work_dir, state_file, unit_name):
        reconcile_e2e_state(project["id"], attempt, state_file)
        return 0
    if state.get("status") == "smoke_failed":
        return 1
    if not state and rc != 0:
        write_json(
            state_file,
            {
                "project_id": project["id"],
                "project_name": project["name"],
                "phase": "smoke",
                "status": "smoke_failed",
                "attempt": attempt,
                "summary": f"codex exec exited with {rc}",
                "smoke_command": smoke_command,
                "topic_label": TOPIC_LABEL,
                "topic_dataset_root": str(TOPIC_DATASET_ROOT),
                "topic_contract_file": str(TOPIC_CONTRACT_FILE),
                "topic_ready": False,
                "isolated_run_root": str(isolation.tmp_root),
                "snapshot_repo_root": manifest["snapshot_repo"],
                "repo_attempt_dir": str(work_dir),
            },
        )
    return rc


def handle_e2e_repair(project: dict, state: dict) -> int:
    old_unit = state.get("unit", "")
    if project.get("failure_mode") == "block_on_failure":
        blocked_state = {
            "project_id": project["id"],
            "project_name": project["name"],
            "phase": "e2e",
            "status": "blocked",
            "attempt": state.get("attempt"),
            "previous_unit": old_unit,
            "unit": old_unit,
            "topic_label": TOPIC_LABEL,
            "topic_dataset_root": str(TOPIC_DATASET_ROOT),
            "topic_contract_file": str(TOPIC_CONTRACT_FILE),
            "patched_files": [],
            "summary": "Synthetic failure path requested blocking after failed e2e follow-up.",
            "finished_at": now_iso(),
        }
        write_json(project_state_path(project["id"]), blocked_state)
        write_runtime_state(current_project=project["id"], last_action="blocked", last_unit=old_unit)
        return 0

    attempt = next_attempt(project["id"])
    new_unit = f"researchclaweval-{project['id']}-e2e-attempt-{attempt:03d}"
    work_dir = run_dir(project["id"], attempt)
    isolation, _ = prepare_attempt_runtime(
        repo_root=REPO_ROOT,
        automation_dir=AUTOMATION_DIR,
        project=project,
        attempt=attempt,
        topic_label=TOPIC_LABEL,
        base_tmp_root=TMP_RUNS_DIR,
        repo_attempt_dir=work_dir,
        topic_contract_file=TOPIC_CONTRACT_FILE,
    )
    write_runtime_state(
        current_project=project["id"],
        last_action="repair_e2e",
        last_unit=new_unit,
        last_isolated_run_root=str(isolation.tmp_root),
    )
    rc = run_codex(
        repair_prompt(project, project_state_path(project["id"]), attempt, old_unit, new_unit),
        work_dir,
        "repair_e2e",
        project_state_path(project["id"]),
        {"e2e_resubmitted", "blocked"},
        run_cwd=isolation.repo_dir,
        home_dir=isolation.home_dir,
        codex_home_dir=isolation.codex_home_dir,
        cache_dir=isolation.cache_dir,
        state_dir=isolation.state_dir,
        scratch_dir=isolation.scratch_dir,
    )
    new_state = load_json(project_state_path(project["id"]), {})
    if new_state.get("status") in {"e2e_resubmitted", "blocked"}:
        return 0
    return rc


def step() -> int:
    ensure_materialized_env()
    project = current_project()
    if project is None:
        write_runtime_state(current_project=None, last_action="complete", last_unit=None)
        print("all projects completed")
        return 0

    state = load_json(project_state_path(project["id"]), {})
    status = state.get("status", "")

    if status == "blocked":
        write_runtime_state(current_project=project["id"], last_action="blocked", last_unit=state.get("unit"))
        print(f"{project['id']} is blocked")
        return 1

    if not status or status in {"smoke_failed", "smoke_passed"}:
        return handle_initial_session(project)

    if status in {"e2e_submitted", "e2e_running", "e2e_resubmitted"}:
        unit_name = state.get("unit", "")
        info = systemd_status(unit_name)
        write_runtime_state(current_project=project["id"], last_action="check_e2e", last_unit=unit_name)
        if not info.get("exists"):
            return handle_e2e_repair(project, state)
        active = info.get("ActiveState", "")
        result = info.get("Result", "")
        exit_code = info.get("ExecMainStatus", "")
        if active in {"active", "activating", "reloading"}:
            print(f"{unit_name} still running")
            return 0
        reconciled = reconcile_e2e_state(project["id"], state.get("attempt", 0), project_state_path(project["id"]))
        reconciled_status = reconciled.get("status", "")
        if reconciled_status == "e2e_failed":
            return handle_e2e_repair(project, reconciled)
        if reconciled_status == "e2e_passed":
            reconciled["status"] = "completed"
            reconciled["finished_at"] = now_iso()
            write_json(project_state_path(project["id"]), reconciled)
            mark_todo_complete(project["id"])
            write_runtime_state(current_project=project["id"], last_action="complete_project", last_unit=unit_name)
            dispatch_next_step("advance-next", project["id"])
            print(f"{project['id']} completed")
            return 0
        if result == "success" or exit_code == "0":
            state["status"] = "completed"
            state["finished_at"] = now_iso()
            write_json(project_state_path(project["id"]), state)
            mark_todo_complete(project["id"])
            write_runtime_state(current_project=project["id"], last_action="complete_project", last_unit=unit_name)
            dispatch_next_step("advance-next", project["id"])
            print(f"{project['id']} completed")
            return 0
        return handle_e2e_repair(project, state)

    if status == "e2e_passed":
        state["status"] = "completed"
        state["finished_at"] = now_iso()
        write_json(project_state_path(project["id"]), state)
        mark_todo_complete(project["id"])
        write_runtime_state(current_project=project["id"], last_action="complete_project", last_unit=state.get("unit"))
        dispatch_next_step("advance-next", project["id"])
        print(f"{project['id']} completed")
        return 0

    if status == "completed":
        mark_todo_complete(project["id"])
        return 0

    if status == "e2e_failed":
        return handle_e2e_repair(project, state)

    return handle_initial_session(project)


def status() -> int:
    project = current_project()
    runtime = load_json(RUNTIME_STATE_FILE, {})
    print(json.dumps({"current_project": project, "runtime": runtime}, ensure_ascii=False, indent=2))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="cmd", required=False)
    step_parser = sub.add_parser("step")
    step_parser.add_argument("--trigger", default="manual")
    sub.add_parser("status")
    args = parser.parse_args()

    if args.cmd in (None, "step"):
        return step()
    if args.cmd == "status":
        return status()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
