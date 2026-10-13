#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--root", default=os.environ.get("RESEARCHCLAWEVAL_AI_RESEARCHER_ROOT", ""))
    p.add_argument("--output", default="real_eval/config/ai_researcher_source.v1.json")
    args = p.parse_args()

    root = Path(args.root)
    if not root.is_dir():
        print(f"AI-Researcher root not found: {root}", file=__import__("sys").stderr)
        return 1

    required = ["README.md", "research_agent/run_infer_idea.py", "docker/Dockerfile", "docker/requirements.txt"]
    manifest = {}
    for rel in required:
        f = root / rel
        if not f.is_file():
            print(f"Missing required file: {f}", file=__import__("sys").stderr)
            return 1
        manifest[rel] = sha256_file(f)

    out = {
        "source_root": str(root.resolve()),
        "files": manifest,
        "source_sha256": hashlib.sha256("".join(sorted(manifest.values())).encode()).hexdigest(),
    }
    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(out, indent=2) + "\n")
    print(json.dumps(out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())