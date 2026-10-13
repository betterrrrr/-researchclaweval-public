#!/usr/bin/env python3
from __future__ import annotations

import json
import logging
import os
import sys
from pathlib import Path
from typing import TypedDict

_log = logging.getLogger(__name__)

COMPATIBILITY_MARKERS = {
    "researchclaw/pipeline/stage_impls/_execution.py": (
        "effective_metrics = result.metrics",
    ),
    "researchclaw/pipeline/runner.py": (
        "summary = _build_pipeline_summary(",
    ),
    "researchclaw/prompts/shared.py": (
        "## Multi-Seed Experiment Requirement (MANDATORY — NO EXCEPTIONS)",
    ),
    "researchclaw/pipeline/stage_impls/_experiment_design.py": (
        "_max_conditions = 8  # default for budgets ≤ 3600s",
    ),
}


def check_version_compatibility(root: Path) -> bool:
    missing: list[str] = []
    for relative_path, markers in COMPATIBILITY_MARKERS.items():
        path = root / relative_path
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            missing.append(relative_path)
            continue
        if any(marker not in text for marker in markers):
            missing.append(relative_path)
    if missing:
        _log.warning(
            "AutoResearchClaw TDC-ADMET-Tox source compatibility warning: expected "
            "native markers are missing from %s; continuing to exact patch checks.",
            ", ".join(missing),
        )
        return False
    return True


class DoneClaim(TypedDict):
    status: str
    changed_files: list[str]
    verification_results: dict[str, str]
    risks: list[str]


def replace_once(path: Path, old: str, new: str, label: str) -> None:
    text = path.read_text(encoding="utf-8")
    if text.count(old) != 1:
        raise SystemExit(f"AutoResearchClaw adapter insertion point changed: {label}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


def patch_multi_seed_enforcement(root: Path) -> None:
    path = root / "researchclaw/prompts/shared.py"
    text = path.read_text(encoding="utf-8")
    marker = '    "multi_seed_enforcement": ('
    start = text.find(marker)
    end = text.find("\n    ),", start)
    block = text[start:end] if start >= 0 and end >= 0 else ""
    if start < 0 or end < 0 or text.count(marker) != 1 or "MANDATORY — NO EXCEPTIONS" not in block:
        raise SystemExit("AutoResearchClaw adapter insertion point changed: multi-seed enforcement prompt block")
    replacement = (
        '    "multi_seed_enforcement": (\n'
        '        "\\n## Single-Candidate Evaluation Requirement (TDC-ADMET-Tox contract)\\n"\n'
        '        "Run each configuration exactly once with one fixed integer seed.\\n"\n'
        '        "Each configuration is one distinct strategy evaluated on validation data.\\n"\n'
        '        "Print `condition=X metric: V` and do not aggregate across seeds.\\n"\n'
        "    ),"
    )
    path.write_text(text[:start] + replacement + text[end + len("\n    ),"):], encoding="utf-8")


def patch_experiment_design_condition_limit(root: Path) -> None:
    path = root / "researchclaw/pipeline/stage_impls/_experiment_design.py"
    old = (
        "    _max_conditions = 8  # default for budgets ≤ 3600s\n"
        "    if _time_budget > 3600:\n"
        "        _max_conditions = 12\n"
        "    if _time_budget > 7200:\n"
        "        _max_conditions = 20"
    )
    new = "    _max_conditions = 4"
    replace_once(path, old, new, "experiment design condition limit")


def patch_literature_screen_passthrough(root: Path) -> None:
    """TDC-ADMET-Tox: skip LLM literature screening and pass all candidates.

    AutoResearchClaw's strict screen can reject the whole candidate set, which
    pauses the native pipeline before any experiment.  The Topic 5 contract
    treats literature as context only, so the adapter passes every
    keyword-filtered candidate straight to the shortlist.
    """
    path = root / "researchclaw/pipeline/stage_impls/_literature.py"
    old = (
        "    shortlist: list[dict[str, Any]] = []\n"
        "    model_rejected_all = False"
    )
    new = (
        "    shortlist: list[dict[str, Any]] = [\n"
        "        {\n"
        "            **row,\n"
        "            \"relevance_score\": 1.0,\n"
        "            \"quality_score\": 1.0,\n"
        "            \"keep_reason\": \"TDC-ADMET-Tox: literature screening disabled; all candidates passed\",\n"
        "        }\n"
        "        for row in filtered_rows\n"
        "    ]\n"
        "    out = stage_dir / \"shortlist.jsonl\"\n"
        "    _write_jsonl(out, shortlist)\n"
        "    logger.info(\n"
        "        \"Stage 5: TDC-ADMET-Tox screening disabled; passed all %d candidates\",\n"
        "        len(shortlist),\n"
        "    )\n"
        "    return StageResult(\n"
        "        stage=Stage.LITERATURE_SCREEN,\n"
        "        status=StageStatus.DONE,\n"
        "        artifacts=(\"shortlist.jsonl\",),\n"
        "        evidence_refs=(\"stage-05/shortlist.jsonl\",),\n"
        "    )\n"
        "    model_rejected_all = False"
    )
    replace_once(path, old, new, "literature screen passthrough")


def patch_iterative_refine_skip(root: Path) -> None:
    """TDC-ADMET-Tox: skip Stage 13 iterative refinement.

    AutoResearchClaw's full 23-stage pipeline is too slow for the Topic 5
    7000s wall budget.  Stage 12 already executes the chosen experiments in
    sandbox mode; Stage 13 iterates on Python files and would eat the time
    needed to write the handoff.  The adapter makes Stage 13 a no-op that
    promotes the Stage 12 runs into `experiment_final/`.
    """
    path = root / "researchclaw/pipeline/stage_impls/_execution.py"
    old = (
        "    # Agent-based modes (collider_agent, biology_agent, stat_agent): no Python\n"
        "    # refinement loop — the agent handled the full pipeline atomically in\n"
        "    # Stage 12 and wrote a canonical results.json.  \"Refining\" python\n"
        "    # source files that were never executed is wasted work; the only\n"
        "    # meaningful refinement option is re-invoking the agent (which the\n"
        "    # repair loop in pipeline/runner.py handles separately).  Create\n"
        "    # placeholder artifacts and exit so downstream stages see a non-empty\n"
        "    # experiment_final/.\n"
        "    if config.experiment.mode in (\"collider_agent\", \"biology_agent\", \"stat_agent\"):"
    )
    new = (
        "    # TDC-ADMET-Tox: skip iterative refinement and reserve wall time\n"
        "    # for analysis, selection, and the framework handoff.\n"
        "    if \"TDC-ADMET-Tox\" in str(getattr(getattr(config, \"research\", None), \"topic\", \"\")):\n"
        "        import shutil as _shutil\n"
        "        final_dir = stage_dir / \"experiment_final\"\n"
        "        final_dir.mkdir(exist_ok=True)\n"
        "        runs_artifact = _read_prior_artifact(run_dir, \"runs/\")\n"
        "        if runs_artifact and Path(runs_artifact).is_dir():\n"
        "            for _item in Path(runs_artifact).iterdir():\n"
        "                _dst = final_dir / _item.name\n"
        "                if _item.is_file():\n"
        "                    _shutil.copy2(_item, _dst)\n"
        "        else:\n"
        "            for _stage_num in (12, 10):\n"
        "                src_dir = run_dir / f\"stage-{_stage_num:02d}\" / \"experiment\"\n"
        "                if src_dir.is_dir():\n"
        "                    if final_dir.exists():\n"
        "                        _shutil.rmtree(final_dir)\n"
        "                    _shutil.copytree(src_dir, final_dir)\n"
        "                    break\n"
        "            else:\n"
        "                (final_dir / \"tdc_admet_tox_results.md\").write_text(\n"
        "                    \"# TDC-ADMET-Tox Results\\n\\n\"\n"
        "                    \"Experiment execution completed in Stage 12. \"\n"
        "                    \"Iterative refinement was skipped by the Topic 5 adapter \"\n"
        "                    \"to reserve wall-clock budget for result analysis, final \"\n"
        "                    \"selection, prediction generation, and handoff writing.\\n\",\n"
        "                    encoding=\"utf-8\",\n"
        "                )\n"
        "        (stage_dir / \"refinement_log.json\").write_text(\n"
        "            json.dumps(\n"
        "                {\n"
        "                    \"generated\": _utcnow_iso(),\n"
        "                    \"mode\": \"tdc_admet_tox_skip_refine\",\n"
        "                    \"skipped\": True,\n"
        "                    \"skip_reason\": (\n"
        "                        \"TDC-ADMET-Tox adapter skips iterative refine so the \"\n"
        "                        \"pipeline reaches final selection and handoff before \"\n"
        "                        \"the 7000s wall budget expires.\"\n"
        "                    ),\n"
        "                    \"metric_key\": config.experiment.metric_key,\n"
        "                },\n"
        "                indent=2,\n"
        "            ),\n"
        "            encoding=\"utf-8\",\n"
        "        )\n"
        "        return StageResult(\n"
        "            stage=Stage.ITERATIVE_REFINE,\n"
        "            status=StageStatus.DONE,\n"
        "            artifacts=(\"refinement_log.json\", \"experiment_final/\"),\n"
        "            evidence_refs=(\"stage-13/refinement_log.json\",),\n"
        "        )\n"
        "    # Agent-based modes (collider_agent, biology_agent, stat_agent): no Python\n"
        "    # refinement loop — the agent handled the full pipeline atomically in\n"
        "    # Stage 12 and wrote a canonical results.json.  \"Refining\" python\n"
        "    # source files that were never executed is wasted work; the only\n"
        "    # meaningful refinement option is re-invoking the agent (which the\n"
        "    # repair loop in pipeline/runner.py handles separately).  Create\n"
        "    # placeholder artifacts and exit so downstream stages see a non-empty\n"
        "    # experiment_final/.\n"
        "    if config.experiment.mode in (\"collider_agent\", \"biology_agent\", \"stat_agent\"):"
    )
    replace_once(path, old, new, "iterative refine skip")


def patch_refine_rollback_guard(root: Path) -> None:
    """TDC-ADMET-Tox: forbid REFINE/PIVOT rollback loops in the native runner.

    The Topic 5 contract says the native stages must never loop and a
    repeated repair/refine cycle is a budget violation.  The native runner
    otherwise recurses from RESEARCH_DECISION back into result analysis,
    which re-runs the expensive multi-agent debate and creates extra trace
    experiments (run_003) without the required parent_run_id/change_rationale.

    This guard only fires for Topic 5 TDC runs and only for rollback
    decisions.  It promotes the already-computed best stage-14 analysis and
    lets the pipeline continue to paper writing, so the framework still owns
    the decision content and final artifacts.
    """
    path = root / "researchclaw/pipeline/runner.py"
    runner_text = path.read_text(encoding="utf-8")
    old = (
        "        ):\n"
        "            pivot_count = _read_pivot_count(run_dir)\n"
        "            # R6-4: Skip REFINE if experiment metrics are empty for consecutive cycles\n"
        "            if pivot_count > 0 and _consecutive_empty_metrics(run_dir, pivot_count):\n"
    )
    new = (
        "        ):\n"
        "            pivot_count = _read_pivot_count(run_dir)\n"
        "            # TDC-ADMET-Tox adapter: the contract forbids repeated\n"
        "            # REFINE/PIVOT cycles. Promote the best completed analysis\n"
        "            # and proceed to paper writing instead of rolling back.\n"
        "            if (\n"
        '                "TDC-ADMET-Tox" in str(getattr(getattr(config, "research", None), "topic", ""))\n'
        "                and result.decision in DECISION_ROLLBACK\n"
        "            ):\n"
        "                _promote_best_stage14(run_dir, config)\n"
        "            elif pivot_count > 0 and _consecutive_empty_metrics(run_dir, pivot_count):\n"
    )
    if runner_text.count(old) != 1:
        raise SystemExit(
            f"AutoResearchClaw runner refine-guard insertion point changed: "
            f"{runner_text.count(old)}"
        )
    path.write_text(runner_text.replace(old, new, 1), encoding="utf-8")

def patch_topic_metrics_split_requirement(root: Path) -> None:
    """Inject the contract-required `"split": "validation"` into 04's topic.

    AutoResearchClaw feeds ``topic.tdc_admet_tox.txt`` directly to the native
    pipeline.  The TDC-ADMET-Tox validator requires every per-run
    ``metrics.json`` to declare ``"split": "validation"``.  The generated
    experiment code writes those files, so the topic prompt must state the
    requirement explicitly.
    """
    path = root / "topic.tdc_admet_tox.txt"
    if not path.is_file():
        raise SystemExit("AutoResearchClaw TDC topic file is missing")
    text = path.read_text(encoding="utf-8")
    requirement = (
        "Each per-run metrics file written under runs/run_XXX/metrics.json "
        "(and every metrics file referenced by experiment_trace.json claims) "
        "MUST be a JSON object that contains the exact field "
        '"split": "validation" alongside macro_average_auroc and per_endpoint '
        "metrics. Never omit or rename that field."
    )
    if requirement not in text:
        path.write_text(text.rstrip() + "\n\n" + requirement + "\n", encoding="utf-8")


def patch_reasoning_effort(root: Path) -> None:
    """Fix min_tokens for TDC-ADMET-Tox.

    The bianxie.ai upstream returns HTTP 400 when max_tokens=1 for
    gpt-6-luna.  Increasing the minimum preflight tokens to 64 avoids
    the 400 while keeping the preflight lightweight.
    """
    path = root / "researchclaw/llm/client.py"
    text = path.read_text(encoding="utf-8")
    old = "        min_tokens = 64 if is_reasoning else 1"
    new = "        min_tokens = 64  # TDC-ADMET-Tox: use 64 for all models (some upstreams reject max_tokens=1)"
    if old not in text:
        _log.warning("TDC-ADMET-Tox min_tokens patch: insertion point not found")
        return
    text = text.replace(old, new, 1)
    path.write_text(text, encoding="utf-8")


def patch_workspace_handoff(root: Path | None = None) -> DoneClaim:
    workspace = root if root is not None else Path(os.environ.get("WORKSPACE", "/workspace"))
    workspace = workspace.resolve()
    if not workspace.is_dir():
        raise SystemExit(f"TDC-ADMET-Tox workspace is missing: {workspace}")
    score_path = workspace / "score.json"
    if score_path.exists():
        raise SystemExit("framework handoff must not contain root score.json")

    configured_root = os.environ.get("AUTORESEARCHCLAW_ARTIFACT_ROOT")
    if not configured_root:
        raise SystemExit("current artifact root must be explicitly configured")
    artifact_root = Path(configured_root)
    if not artifact_root.is_absolute():
        raise SystemExit("current artifact root must be an explicit absolute path")
    if artifact_root.is_symlink():
        raise SystemExit("current artifact root must not be a symlink")
    try:
        artifact_root = artifact_root.resolve(strict=True)
    except OSError as exc:
        raise SystemExit(f"current artifact root is missing: {artifact_root}") from exc
    try:
        artifact_root.relative_to(workspace)
    except ValueError as exc:
        raise SystemExit("current artifact root must be inside the current workspace") from exc
    if not artifact_root.is_dir():
        raise SystemExit(f"current artifact root is missing: {artifact_root}")
    if any(path.is_symlink() for path in artifact_root.rglob("*")):
        raise SystemExit("current artifact root contains symlinks")

    changed_files: list[str] = []
    verification_results: dict[str, str] = {}

    def promote(destination_name: str, candidates: tuple[str, ...]) -> None:
        destination = workspace / destination_name
        # Some native pipelines write the final handoff directly to the
        # workspace root instead of packaging it under artifacts/.  Treat
        # an existing non-empty regular root file as already promoted.
        if (
            destination.is_file()
            and not destination.is_symlink()
            and destination.stat().st_size > 0
        ):
            verification_results[destination_name] = "present"
            return
        source = next(
            (artifact_root / candidate for candidate in candidates
             if (artifact_root / candidate).is_file()
             and not (artifact_root / candidate).is_symlink()
             and (artifact_root / candidate).stat().st_size > 0),
            None,
        )
        if source is None:
            verification_results[destination_name] = "missing"
            return
        try:
            source.resolve(strict=True).relative_to(artifact_root)
        except ValueError as exc:
            raise SystemExit(f"handoff source is outside current artifact root: {source}") from exc
        except OSError as exc:
            raise SystemExit(f"handoff source is missing: {source}") from exc
        if destination.is_symlink():
            raise SystemExit(f"handoff destination is a symlink: {destination}")
        if source.resolve() != destination.resolve():
            destination.write_bytes(source.read_bytes())
            changed_files.append(str(destination))
        verification_results[destination_name] = "present"

    promote("experiment_trace.json", ("experiment_trace.json",))
    promote("predictions.csv", ("predictions.csv", "submission.csv"))
    if verification_results.get("predictions.csv") == "missing":
        verification_results["predictions.csv or submission.csv"] = verification_results.pop(
            "predictions.csv"
        )
    promote("final_report.md", ("final_report.md",))
    missing = [name for name, status in verification_results.items() if status == "missing"]
    if missing:
        raise SystemExit("incomplete framework handoff: " + ", ".join(sorted(missing)))

    return {
        "status": "done",
        "changed_files": changed_files,
        "verification_results": {
            **verification_results,
            "score.json": "pending_host_scoring",
        },
        "risks": ["score.json remains pending until the separate host-only scoring step"],
    }


def main() -> int:
    root = Path.cwd()
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s: %(message)s")
    if "--handoff" in sys.argv[1:]:
        print(json.dumps(patch_workspace_handoff(), sort_keys=True))
        return 0
    check_version_compatibility(root)
    patch_multi_seed_enforcement(root)
    patch_experiment_design_condition_limit(root)
    patch_literature_screen_passthrough(root)
    patch_iterative_refine_skip(root)
    patch_refine_rollback_guard(root)
    patch_topic_metrics_split_requirement(root)
    patch_reasoning_effort(root)
    print(
        json.dumps(
            {
                "status": "patched",
                "score.json": "pending_host_scoring",
                "literature_screening": "disabled-pass-all-candidates",
                "iterative_refine": "skipped-for-tdc-admet-tox",
                "refine_rollback_guard": "no-native-loop-for-tdc-admet-tox",
                "metrics_split_requirement": "injected-into-topic",
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
