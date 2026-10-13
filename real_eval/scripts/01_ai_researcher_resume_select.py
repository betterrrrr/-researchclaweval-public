#!/usr/bin/env python3
import os
import pty
import re
import select
import subprocess
import sys
import time


def choose_response(buffer: str, handled: set[str]):
    tool_matches = list(re.finditer(r"The tool '([^']+)' cache file exists", buffer, re.I))
    agent_matches = list(re.finditer(r"The agent '([^']+)' cache file exists", buffer, re.I))

    last_tool = tool_matches[-1] if tool_matches else None
    last_agent = agent_matches[-1] if agent_matches else None

    if last_tool and (not last_agent or last_tool.start() > last_agent.start()):
        tool_name = last_tool.group(1).strip().lower().replace(" ", "_")
        key = f"tool-{tool_name}-{last_tool.start()}"
        if key not in handled:
            return b"\r", key
        return None, None

    if last_agent:
        agent_name = last_agent.group(1).strip().lower().replace(" ", "_")
        if agent_name == "judge_agent":
            current_prompt = buffer[last_agent.start():]
            if "> Resume" in current_prompt:
                return None, None
            key = f"agent-judge-resume-{last_agent.start()}"
            if key not in handled:
                return b"\x1b[B\r", key
            return None, None
        key = f"agent-{agent_name}-yes-{last_agent.start()}"
        if key not in handled:
            return b"\r", key
        return None, None

    return None, None


def main() -> int:
    if len(sys.argv) < 3:
        print("usage: 01_ai_researcher_resume_select.py <cwd> <cmd> [args...]", file=sys.stderr)
        return 2

    cwd = sys.argv[1]
    cmd = sys.argv[2:]

    master_fd, slave_fd = pty.openpty()
    proc = subprocess.Popen(
        cmd,
        cwd=cwd,
        stdin=slave_fd,
        stdout=slave_fd,
        stderr=slave_fd,
        text=False,
        env=os.environ.copy(),
        close_fds=True,
    )
    os.close(slave_fd)

    handled = set()
    buffer = ""
    last_output = time.time()

    try:
        while True:
            if proc.poll() is not None:
                break
            ready, _, _ = select.select([master_fd], [], [], 0.2)
            if master_fd in ready:
                try:
                    data = os.read(master_fd, 65536)
                except OSError:
                    break
                if not data:
                    break
                sys.stdout.buffer.write(data)
                sys.stdout.buffer.flush()
                text = data.decode("utf-8", errors="replace")
                buffer = (buffer + text)[-12000:]
                last_output = time.time()
                response, key = choose_response(buffer, handled)
                if response and key:
                    os.write(master_fd, response)
                    handled.add(key)
                    sys.stdout.write(f"\n[resume-wrapper] auto-selected {key}\n")
                    sys.stdout.flush()
            elif time.time() - last_output > 1.0:
                continue
    finally:
        try:
            os.close(master_fd)
        except OSError:
            pass

    return proc.wait()


if __name__ == "__main__":
    raise SystemExit(main())
