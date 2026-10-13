#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path


def secret_values(paths: list[Path]) -> list[str]:
    values: set[str] = set()
    for path in paths:
        for line in path.read_text(encoding="utf-8").splitlines():
            key, separator, value = line.partition("=")
            normalized = key.upper()
            if (
                separator
                and len(value) >= 8
                and any(marker in normalized for marker in ("KEY", "TOKEN", "SECRET", "PASSWORD"))
            ):
                values.add(value)
    return sorted(values, key=len, reverse=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="Redact env-file secrets from a text stream.")
    parser.add_argument("--env-file", action="append", type=Path, required=True)
    args = parser.parse_args()
    secrets = secret_values(args.env_file)
    for line in sys.stdin:
        for secret in secrets:
            line = line.replace(secret, "[REDACTED]")
        sys.stdout.write(line)
        sys.stdout.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
