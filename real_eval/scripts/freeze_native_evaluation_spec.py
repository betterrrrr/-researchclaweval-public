#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from validate_native_evaluation_spec import (
    ROOT,
    freeze_payload,
    load_json,
    repo_path,
    validate_spec,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Freeze the files and runtime image digests for a native evaluation campaign."
    )
    parser.add_argument("--spec", required=True, type=Path)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    root = args.root.expanduser()
    spec_path = args.spec.expanduser()
    if not spec_path.is_absolute():
        spec_path = root / spec_path
    spec = load_json(spec_path)
    report = validate_spec(spec_path, root=root, stage="freeze")
    if not report.ok:
        print(json.dumps(report.as_dict(), ensure_ascii=False, indent=2))
        return 2
    configured_output = repo_path(root, spec.get("campaign", {}).get("freeze_manifest"))
    output = args.output.expanduser() if args.output else configured_output
    if output is not None and not output.is_absolute():
        output = root / output
    if output is None:
        raise SystemExit("spec campaign.freeze_manifest is required when --output is omitted")
    payload = freeze_payload(root, spec_path, spec)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
