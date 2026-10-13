#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_TOPIC_ROOT = ROOT / "data" / "topic2"
SCORE_SOURCE = "official_evaluate_py"


def read_json(path: Path) -> object | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_evaluator_integrity(workspace: Path, topic_root: Path) -> bool:
    """The workspace evaluate.py must byte-match the frozen protected copy."""
    protected = topic_root / "protected" / "evaluate.py"
    workspace_copy = workspace / "evaluate.py"
    if not protected.is_file():
        raise RuntimeError(f"missing protected evaluator: {protected}")
    if not workspace_copy.is_file():
        raise RuntimeError(f"workspace is missing evaluate.py: {workspace_copy}")
    if sha256_file(protected) != sha256_file(workspace_copy):
        raise RuntimeError("evaluate.py was modified in the workspace; integrity check failed")
    return True


def parse_metrics(stdout: str) -> tuple[float, float]:
    """Parse the final JSON line {"Reward Mean": ..., "Reward Std": ...}."""
    match = re.search(r'\{\s*"Reward Mean"\s*:\s*(-?[0-9.]+(?:[eE][+-]?[0-9]+)?)\s*,\s*"Reward Std"\s*:\s*(-?[0-9.]+(?:[eE][+-]?[0-9]+)?)\s*\}', stdout)
    if not match:
        raise RuntimeError("evaluate.py did not emit a parseable Reward Mean/Std JSON object")
    reward_mean = float(match.group(1))
    reward_std = float(match.group(2))
    return reward_mean, reward_std


def run_evaluator(workspace: Path, python: str, config_fname: str) -> tuple[float, float]:
    evaluator = workspace / "evaluate.py"
    if not evaluator.is_file():
        raise RuntimeError(f"missing evaluator in workspace: {evaluator}")
    completed = subprocess.run(
        [python, "evaluate.py", "--config_fname", config_fname],
        cwd=workspace,
        text=True,
        capture_output=True,
        env=os.environ.copy(),
    )
    if completed.returncode != 0:
        raise RuntimeError(
            f"evaluate.py failed (rc={completed.returncode}): {completed.stderr[-2000:]}"
        )
    return parse_metrics(completed.stdout)


def write_score(output_score: Path, reward_mean: float, reward_std: float, checkpoint_count: int) -> None:
    normalized = {
        "score": reward_mean,
        "reward_std": reward_std,
        "score_source": SCORE_SOURCE,
        "checkpoint_count": checkpoint_count,
    }
    output_score.parent.mkdir(parents=True, exist_ok=True)
    output_score.write_text(
        json.dumps(normalized, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def count_checkpoints(workspace: Path, config_fname: str) -> int:
    stem = Path(config_fname).stem
    return len(list((workspace / "checkpoints").glob(f"{stem}*.pkl")))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--output-score", type=Path, required=True)
    parser.add_argument("--dataset-root", type=Path, default=DEFAULT_TOPIC_ROOT)
    parser.add_argument("--python", default=sys.executable)
    parser.add_argument("--config-fname", default="src/config.yaml")
    args = parser.parse_args(argv)

    if args.output_score.exists():
        raise RuntimeError(
            "refusing to overwrite a framework-visible score.json; the host scorer must be the sole score owner"
        )

    workspace = args.workspace.resolve()
    topic_root = args.dataset_root.resolve()

    verify_evaluator_integrity(workspace, topic_root)

    checkpoint_count = count_checkpoints(workspace, args.config_fname)
    if checkpoint_count != 5:
        raise RuntimeError(
            f"expected exactly 5 checkpoints, found {checkpoint_count}"
        )

    reward_mean, reward_std = run_evaluator(workspace, args.python, args.config_fname)

    write_score(args.output_score, reward_mean, reward_std, checkpoint_count)
    print(json.dumps({"score": reward_mean, "reward_std": reward_std, "score_source": SCORE_SOURCE}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
