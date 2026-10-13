#!/usr/bin/env python3
"""Verify that the ARIS framework trace truthfully records the injected relay.

Reads OPENAI_MODEL / OPENAI_BASE_URL from the environment and compares them
against framework_internal_model / framework_internal_api_base_url in the
framework-authored experiment_trace.json (relative to the workspace root given
as argv[1], defaulting to the current directory).
"""
from __future__ import annotations

import json
import os
import sys


def main() -> int:
    workspace = sys.argv[1] if len(sys.argv) > 1 else os.getcwd()
    trace_path = os.path.join(workspace, "experiment_trace.json")
    expected_model = os.environ.get("OPENAI_MODEL")
    expected_base_url = os.environ.get("OPENAI_BASE_URL")
    if not expected_model or not expected_base_url:
        print("check_aris_trace_fields: OPENAI_MODEL / OPENAI_BASE_URL are missing")
        return 1
    try:
        with open(trace_path, encoding="utf-8") as handle:
            trace = json.load(handle)
    except Exception as exc:
        print(f"check_aris_trace_fields: cannot read trace: {exc}")
        return 1
    problems = []
    if trace.get("framework_internal_model") != expected_model:
        problems.append(
            f"framework_internal_model={trace.get('framework_internal_model')!r} "
            f"expected {expected_model!r}"
        )
    if trace.get("framework_internal_api_base_url") != expected_base_url:
        problems.append(
            f"framework_internal_api_base_url={trace.get('framework_internal_api_base_url')!r} "
            f"expected {expected_base_url!r}"
        )
    if trace.get("framework_native_execution") is not True:
        problems.append("framework_native_execution is not true")
    if trace.get("consumed_topic_input") is not True:
        problems.append("consumed_topic_input is not true")
    if problems:
        print("check_aris_trace_fields: mismatch:")
        for problem in problems:
            print(f"- {problem}")
        return 1
    print("check_aris_trace_fields: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
