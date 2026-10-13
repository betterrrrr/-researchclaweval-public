#!/usr/bin/env python3
"""Host-owned BabyLM score extraction; handles multiple experiment_trace.json formats."""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path


def extract_perplexity(exp: dict) -> float | None:
    """Extract perplexity from an experiment dict, handling multiple schemas."""
    if not isinstance(exp, dict):
        return None
    # Direct keys
    for key in ("validation_perplexity", "perplexity", "best_validation_perplexity", "best_val_ppl"):
        value = exp.get(key)
        if isinstance(value, (int, float)) and math.isfinite(value) and value > 0:
            return float(value)
    # Nested in metrics dict
    metrics = exp.get("metrics")
    if isinstance(metrics, dict):
        for key in ("perplexity", "validation_perplexity"):
            value = metrics.get(key)
            if isinstance(value, (int, float)) and math.isfinite(value) and value > 0:
                return float(value)
    # Nested in results list (AI-Scientist-v2 format)
    results = exp.get("results")
    if isinstance(results, list):
        for r in results:
            if isinstance(r, dict):
                result_metrics = r.get("metrics")
                if isinstance(result_metrics, dict):
                    for key in ("perplexity", "validation_perplexity"):
                        value = result_metrics.get(key)
                        if isinstance(value, (int, float)) and math.isfinite(value) and value > 0:
                            return float(value)
    # Validation loss -> exp(validation_loss)
    for key in ("validation_loss", "loss", "avg_nll"):
        value = exp.get(key)
        if isinstance(value, (int, float)) and math.isfinite(value) and value > 0:
            return math.exp(float(value))
    return None


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--run-root", type=Path, required=True)
    p.add_argument("--output-score", type=Path, required=True)
    args = p.parse_args()
    trace = args.run_root / "workspace/experiment_trace.json"
    if not trace.is_file():
        raise SystemExit("missing framework experiment_trace.json")
    payload = json.loads(trace.read_text(encoding="utf-8"))
    values = []
    # Check top-level experiments list
    for exp in payload.get("experiments", []):
        ppl = extract_perplexity(exp)
        if ppl is not None:
            values.append(ppl)
    # Check results list (AI-Scientist-v2 format: experiments at top level, results inside)
    for result in payload.get("results", []):
        ppl = extract_perplexity(result)
        if ppl is not None:
            values.append(ppl)
    # Check best_validation_perplexity at top level
    top_ppl = payload.get("best_validation_perplexity")
    if isinstance(top_ppl, (int, float)) and math.isfinite(top_ppl) and top_ppl > 0:
        values.append(float(top_ppl))
    if not values:
        raise SystemExit("trace contains no finite validation metric")
    score = {
        "task_id": "babylm",
        "metric": "validation_perplexity",
        "perplexity": min(values),
        "direction": "minimize",
        "source": "framework_experiment_trace",
        "all_values": sorted(values),
    }
    args.output_score.parent.mkdir(parents=True, exist_ok=True)
    args.output_score.write_text(json.dumps(score, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(score))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())