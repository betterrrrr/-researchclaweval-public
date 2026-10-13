#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

TASK_ID = "tdc_admet_tox"

RUNTIME_BRIEF = """# TDC-ADMET-Tox Native Evaluation Brief

This is a framework-capability evaluation. The framework's documented native entrypoint must own hypothesis generation, experiment design, implementation, execution, comparison, selection, and the short paper.

## Visible inputs

- `/data/tdc_admet_tox/train.csv`: labeled training rows
- `/data/tdc_admet_tox/validation.csv`: labeled fixed validation rows
- `/data/tdc_admet_tox/test.csv`: unlabeled public test structures
- `/workspace/automation/tdc_admet_tox_contract.md`
- `/workspace/automation/tdc_admet_tox_execution_budget.md`
- `/workspace/docs/tdc_admet_tox_*.md`
- `/workspace/automation/scripts/run_tdc_admet_tox_validation_score.py`
- `/workspace/automation/scripts/validate_tdc_admet_tox_run.py`

No hidden test label, hidden-label path, prior Topic output, or prior experiment artifact is available.

## Data schema

All three CSV files use the same long format with exactly these columns: `sample_id, endpoint, smiles, label`. There is no SMILES column and no per-endpoint label columns. `train.csv` and `validation.csv` contain rows for all three endpoints (AMES, hERG, DILI), identified by the `endpoint` column; `label` is the binary outcome for that row's endpoint. `test.csv` contains `sample_id, endpoint, smiles` with no `label` column, one row per (sample, endpoint) pair. Use the `endpoint` field according to the framework's own modeling hypothesis; the host does not prescribe how endpoints are represented or modeled.

## Predictions output schema

`/workspace/predictions.csv` must have exactly three columns with this exact header: `sample_id,endpoint,probability` (the third column MUST be named `probability`, never `score`, `pred`, `label`, or `y`). It must contain exactly one row per (sample_id, endpoint) pair present in `test.csv`, with the third column a float probability in [0, 1]. The (sample_id, endpoint) key set must exactly match `test.csv`; the audit checks this against the public test file.

## Required native workflow

1. Propose a defensible molecular-ML hypothesis using only visible inputs.
2. Before the first validation experiment, write and lock a framework-authored `research_idea.json` containing the hypothesis, rationale, expected failure modes, and experimental discrimination plan.
3. Complete 2 to 4 materially distinct configurations, exactly one validation candidate per configuration.
4. Compare configurations only by validation macro AUROC across AMES, hERG, and DILI.
5. Select the best observed valid configuration, refit only as allowed by the contract, and generate all public-test probabilities.
6. Write the complete framework-owned handoff before the native entrypoint exits.

Do not use grid/random/AutoML searches that conceal additional candidates. Do not install packages, download assets, call public internet services, use remote chemistry lookups, launch background experiments, or evaluate a fifth configuration. The installed runtime includes NumPy, pandas, SciPy, and scikit-learn but not RDKit; hypotheses must be feasible with the actual installed environment.

Manage the wall-clock budget aggressively. The total framework wall time is 7,200 seconds and the process is killed hard at that limit. The framework owns its experiment order and must reserve enough time to write the complete handoff and run the framework-stage audit before exit. A sweep, grid, random search, or hyperparameter scan is a violation; each hyperparameter setting evaluated on validation data counts as a configuration, and more than 4 validation candidates is a violation. If an experiment would not complete within the remaining budget, drop it and keep the finished handoff. Write artifacts incrementally as evidence becomes available.

## Required framework-owned handoff

- `/workspace/predictions.csv`
- `/workspace/research_idea.json` (locked before the first experiment)
- `/workspace/experiment_trace.json`
- `/workspace/environment.json`
- runnable source and configs referenced by the trace
- non-empty `/workspace/logs/`
- `/workspace/paper.md` or `paper.pdf` plus `paper_claims.md`
- `/workspace/final_report.md` (the framework-authored final report)

The framework must not create `score.json`. Hidden-test scoring is a later host-only action and must never be reported in the framework paper.

Every empirical paper number must use a `<!-- claim:... -->` marker resolving through `experiment_trace.json` to a concrete validation metrics file, prediction file, config file, and log file. Claim `value` fields must reproduce the source metrics exactly (the audit compares with 1e-12 tolerance, so never round, truncate, or reformat numbers from `metrics.json` or `runtime_seconds`). Run the framework-stage audit before exit and fix framework-authored artifacts inside the native workflow if it reports an error.

The framework itself must record `framework_native_execution: true`, `consumed_topic_input: true`, `framework_internal_model` exactly from `OPENAI_MODEL`, and `framework_internal_api_base_url` exactly from `OPENAI_BASE_URL` in `experiment_trace.json`. Do not replace the injected relay URL with a description such as `local`, `custom provider`, or `orchestrated runtime`.

`experiment_trace.json` must follow the evaluation schema checked by `automation/scripts/validate_tdc_admet_tox_run.py` (`--stage framework`), not a framework-internal format. The required top-level fields are `task_id` (exactly `tdc_admet_tox`), `framework_native_execution`, `consumed_topic_input`, `framework_internal_model`, `framework_internal_api_base_url`, `selection_metric` (exactly `validation_macro_average_auroc`), `final_prediction_file`, `selected_experiment_id`, `total_wall_seconds`, `resource_budget` (exactly `{"cpu_cores": 4, "memory_gib": 16, "gpu_count": 0, "workspace_disk_gib": 10, "max_experiment_runtime_seconds": 3600, "max_total_wall_seconds": 7200, "network_policy": "injected_llm_relay_only"}`), `experiments` (list of `run_id`, `status` (exactly `complete`), `hypothesis`, `model_strategy`, `feature_strategy`, `config_file`, `prediction_file`, `metrics_file`, `log_file`, `runtime_seconds`, `seed` (integer), `candidate_count` (exactly 1), `validation_metrics` (with `macro_average_auroc` and `per_endpoint.{AMES,hERG,DILI}.auroc`)), `reproduction`, and `claims` (list of `claim_id`, `endpoint`, `metric`, `value`, `source_run_id`, `prediction_file`, `config_file`, `log_file`). All artifact paths in the trace (config_file, prediction_file, metrics_file, log_file, and the same fields inside claims) must be RELATIVE paths from the run workspace root (e.g. `runs/run_001/predictions_validation.csv`), never absolute paths like `/workspace/...`. The trace `experiments` list must contain between 2 and 4 entries total, one per materially distinct configuration; do not list ablation variants, seeds, or repeated evaluations as separate experiments. Every entry's `validation_metrics` must reproduce its metrics_file exactly (the audit compares with 1e-12 tolerance, so never round, truncate, or reformat numbers from `metrics.json`). The `selected_experiment_id` must name the experiment with the highest `validation_metrics.macro_average_auroc`. Write this trace with the exact field names shown; run the framework-stage audit before exit and fix the trace inside the native workflow if the audit reports an error.

`paper.md` must reference every claim: each numeric table cell and each quantitative prose sentence that contains numbers tied to empirical terms (auroc, score, runtime, improvement, etc.) must carry a `<!-- claim:<claim_id> -->` marker inline with the number, and the marker's claim_id must exist in the trace `claims` list. Every claim in the trace must be referenced at least once in the paper. A claim's `value` must exactly equal the metric read from the source experiment's metrics_file (e.g. `validation_metrics.per_endpoint.AMES.auroc` for endpoint AMES, or the top-level macro value for endpoint macro). The audit checks displayed paper numbers against claim values within rounding tolerance, so display the unrounded source value.
"""

AUTORESEARCHCLAW_TOPIC_BRIEF = RUNTIME_BRIEF + """
## AutoResearchClaw budget discipline

AutoResearchClaw's native stages must never loop. If a repair, refine, or REFINE decision cycle does not improve validation macro AUROC (or a requested repair cannot be resolved), stop the cycle immediately, promote the best validated configuration that exists, and move directly to final handoff writing. A repeated repair/refine cycle of the same configuration is a budget violation and must never be started. Reserve the last 900 seconds of the 7,200-second wall budget for the complete handoff and the framework-stage audit, exactly as specified above.
"""


def ai_researcher_metaprompt() -> str:
    return '''TASK = "TDC-ADMET-Tox molecular toxicity prediction for AMES, hERG, and DILI."
DATASET = """
Use only /data/tdc_admet_tox. train.csv and validation.csv are labeled; test.csv is unlabeled. Preserve sample_id, endpoint, and SMILES exactly.
"""
BASELINE = "The framework must propose and evaluate feasible molecular-ML configurations using only installed libraries and visible SMILES; the framework chooses the methods and experiment order."
COMPARISON = "Complete 2 to 4 materially distinct configurations total, with one validation candidate each. Compare by unweighted validation macro AUROC over AMES, hERG, and DILI, then select the best valid configuration."
EVALUATION = "Use automation/scripts/run_tdc_admet_tox_validation_score.py for validation evidence. Produce predictions.csv, experiment_trace.json, environment.json, runnable code, logs, and paper.md at /workspace. Never create score.json. experiment_trace.json must follow the evaluation schema from automation/scripts/validate_tdc_admet_tox_run.py (--stage framework): top-level task_id exactly 'tdc_admet_tox', framework_native_execution, consumed_topic_input, framework_internal_model from OPENAI_MODEL, framework_internal_api_base_url from OPENAI_BASE_URL, selection_metric, final_prediction_file, selected_experiment_id, total_wall_seconds, experiments (run_id, status, hypothesis, model_strategy, feature_strategy, config_file, prediction_file, metrics_file, log_file, runtime_seconds, seed, candidate_count, validation_metrics), reproduction, and claims (claim_id, endpoint, metric, value, source_run_id, prediction_file, config_file, log_file). Finish the trace and run the framework-stage audit before the wall-clock limit; the audit must pass before the native entrypoint exits. Manage the 7,200-second wall budget aggressively: shrink or early-stop any training that cannot finish, and reserve the last 900 seconds to write predictions.csv, experiment_trace.json, environment.json, and paper.md (write them incrementally, not only at the end)."
REF = "No hidden labels, public internet, runtime installs, remote chemistry lookups, prior Topic outputs, background jobs, or fifth configuration. Every empirical paper number must resolve to a trace claim."
FULL_PROMPT = TASK + "\\n" + DATASET + "\\n" + BASELINE + "\\n" + COMPARISON + "\\n" + EVALUATION + "\\n" + REF
'''


def ai_researcher_payload() -> dict[str, object]:
    return {
        "instance_id": TASK_ID,
        "target": "TDC-ADMET-Tox three-endpoint molecular toxicity prediction",
        "title": "Framework-native lightweight molecular ML under a fixed experiment budget",
        "authors": ["ResearchClawEval local task"],
        "year": 2026,
        "url": "http://arxiv.org/abs/1703.00564",
        "abstract": (
            "Predict AMES, hERG, and DILI binary endpoints from visible SMILES using a fixed "
            "train/validation split and an unlabeled public test split."
        ),
        "venue": "Local Benchmark",
        "topic": "molecular_machine_learning",
        "field": "ai4science",
        "source_papers": [
            {
                "reference": "MoleculeNet: A Benchmark for Molecular Machine Learning",
                "usage": (
                    "Conceptual context only. The mounted local contract and data are authoritative; "
                    "no paper or repository download is permitted."
                ),
            }
        ],
        "dataset_root": "/data/tdc_admet_tox",
        "contract_file": "automation/tdc_admet_tox_contract.md",
        "task1": (
            "Use AI-Researcher's native workflow to propose, run, and compare 2 to 4 complete "
            "TDC-ADMET-Tox configurations and produce the contract-complete root handoff without score.json."
        ),
        "task2": "Preserve validation evidence, provider metadata, and claim provenance in experiment_trace.json.",
    }


def ai_scientist_topic(primary_model: str, provider_base_url: str) -> str:
    return f"""# Title
Budgeted molecular ML hypotheses for TDC-ADMET-Tox

# TL;DR
Use AI-Scientist-v2's native ideation and BFTS flow to propose, implement, and compare 2 to 4 feasible molecular-ML configurations for AMES, hERG, and DILI. Select only by validation macro AUROC and produce a traceable short paper.

# Inputs and metric
- Read only `/data/tdc_admet_tox/{{train,validation,test}}.csv`.
- `test.csv` is unlabeled and must never be used for selection.
- The primary metric is the unweighted macro average of the three endpoint AUROCs.
- Use `/workspace/automation/scripts/run_tdc_admet_tox_validation_score.py` for validation evidence.

# Data schema
All three CSV files use the same long format with exactly these columns: `sample_id, endpoint, smiles, label`. There is no SMILES column and no per-endpoint label columns. `train.csv` and `validation.csv` contain rows for all three endpoints (AMES, hERG, DILI), identified by the `endpoint` column; `label` is the binary outcome for that row's endpoint. `test.csv` contains `sample_id, endpoint, smiles` with no `label` column, one row per (sample, endpoint) pair. Use the `endpoint` field according to the framework's own modeling hypothesis; the host does not prescribe how endpoints are represented or modeled.

# Hard budget and environment
- Complete 2 to 4 distinct configurations total; each validation candidate counts as one configuration.
- Each trace experiment has `candidate_count: 1`; never begin a fifth configuration.
- Use at most 4 CPU cores, 16 GiB memory, no GPU, 3,600 cumulative experiment seconds, and 7,200 total wall seconds.
- NumPy, pandas, SciPy, and scikit-learn are installed. RDKit is not installed. Do not install or download anything.
- The framework owns method selection and experiment order. Keep all work within the stated budget, run 2 to 4 distinct configurations with one candidate each, never begin a fifth configuration, and leave enough time for the complete handoff and framework-stage audit.

# Native handoff
The framework-generated runnable code must write `/workspace/predictions.csv`, `/workspace/experiment_trace.json`, `/workspace/environment.json`, non-empty logs, configs and metrics under the workspace, and `/workspace/paper.md`. It must not create `score.json`. Every empirical paper number must carry a claim marker resolving to validation evidence in the trace.

Record `framework_native_execution: true`, `framework_internal_model: "{primary_model}"`, and `framework_internal_api_base_url: "{provider_base_url}"`. Do not report hidden-test performance.
"""


def autoresearchclaw_config(primary_model: str, provider_base_url: str) -> str:
    llm_block = f"""llm:
  provider: "openai-compatible"
  primary_model: "{primary_model}"
  fallback_models: []
  base_url: "{provider_base_url}"
  api_key_env: "OPENAI_API_KEY"
"""
    return f"""project:
  name: "tdc-admet-tox-native"
  mode: "full-auto"
  output_dir: "./artifacts/tdc-admet-tox-${{REAL_EVAL_RUN_ID}}"

research:
  topic: "Budgeted molecular machine learning for TDC-ADMET-Tox AMES hERG DILI. train.csv and validation.csv are separate fixed splits. Never compute validation and test metrics on the same data."
  domains: ["molecular machine learning", "computational toxicology", "AI4Science"]
  daily_paper_count: 0
  quality_threshold: 0.35
  graceful_degradation: true
  dataset_schema_hint: |
    All input CSVs under /data/tdc_admet_tox use ONE long format with exactly these columns:
    sample_id, endpoint, smiles, label. There is no SMILES column and no per-endpoint label
    column. train.csv and validation.csv contain rows for all three endpoints (AMES, hERG,
    DILI) identified by the endpoint column; label is the binary outcome for that row's
    endpoint. test.csv has sample_id, endpoint, smiles with no label column, one row per
    (sample, endpoint) pair. Reading train_df["AMES"], train_df["DILI"], train_df["hERG"],
    or train_df["SMILES"] fails with KeyError. Preserve the endpoint field and choose the
    endpoint representation and featurization strategy as part of the framework's own idea.
    Output format (MANDATORY): print one line `METRIC_DEF: macro_average_auroc | direction=higher | desc=validation macro AUROC` at startup, and for EVERY trained configuration print exactly one line `condition=<config_name> macro_average_auroc: <float>` using that configuration's validation macro AUROC. Other formats (e.g. `val_auroc = ...` lines) are ignored by the harness, so never use them for the metric. Exactly 2 to 4 configurations, one candidate each; never define more than 4 model/feature combinations.
    Final handoff (MANDATORY): write /workspace/predictions.csv with exactly these three header columns sample_id,endpoint,probability (third column MUST be named probability, not score), one row per (sample_id, endpoint) pair from test.csv, float values in [0,1]. Write /workspace/experiment_trace.json with top-level selection_metric exactly "validation_macro_average_auroc" and resource_budget exactly {{"cpu_cores": 4, "memory_gib": 16, "gpu_count": 0, "workspace_disk_gib": 10, "max_experiment_runtime_seconds": 3600, "max_total_wall_seconds": 7200, "network_policy": "injected_llm_relay_only"}}. The experiments list must have between 2 and 4 entries, status exactly "complete", seed an integer, candidate_count exactly 1, and every artifact path (config_file, prediction_file, metrics_file, log_file) RELATIVE to the workspace (never /workspace/...); each entry's validation_metrics must be exactly {{"macro_average_auroc": <float>, "per_endpoint": {{"AMES": {{"auroc": <float>}}, "hERG": {{"auroc": <float>}}, "DILI": {{"auroc": <float>}}}}}} and reproduce the metrics JSON files exactly (never round, never drop per_endpoint). paper.md must place a <!-- claim:<claim_id> --> marker beside every numeric table cell and every quantitative sentence mentioning auroc/score/runtime, and each claim_id must exist in the trace claims list with value exactly equal to the source metrics file.
    Experiment design stage (MANDATORY): respond with ONLY a plain YAML document containing the TOP-LEVEL YAML keys baselines, proposed_methods, ablations, datasets, metrics, objectives, risks, compute_budget (each a list or dict, never empty). Never wrap the plan under a single container key such as experiment_plan or plan; the harness reads only top-level keys. Never prefix the response with prose, never use a markdown code fence, never emit a python/JSON dict literal, and never use a variable assignment such as `plan =`; the harness parses the raw response text as YAML.

runtime:
  timezone: "Asia/Shanghai"
  max_parallel_tasks: 1
  retry_limit: 0

notifications:
  channel: "none"

knowledge_base:
  root: "./knowledge_base"

{llm_block}
web_search:
  enabled: false
  enable_scholar: false
  enable_crawling: false
  enable_pdf_extraction: false
  max_web_results: 0
  max_scholar_results: 0
  max_crawl_urls: 0

assets:
  dataset_root: "/data/tdc_admet_tox"
  contract_file: "automation/tdc_admet_tox_contract.md"

experiment:
  mode: "sandbox"
  time_budget_sec: 28800
  max_iterations: 4
  metric_key: "macro_average_auroc"
  metric_direction: "maximize"
  opencode:
    enabled: false
  benchmark_agent:
    enabled: false
  code_agent:
    enabled: true
    architecture_planning: true
    sequential_generation: true
    hard_validation: false
    hard_validation_max_repairs: 4
    exec_fix_max_iterations: 3
    exec_fix_timeout_sec: 600
  sandbox:
    python_path: "/usr/bin/python3"
    gpu_required: false
    allowed_imports: [argparse, csv, hashlib, json, math, pathlib, platform, subprocess, sys, time, numpy, pandas, scipy, sklearn]
"""


def write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate TDC-ADMET-Tox native input pack.")
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--primary-model", default="gpt-5.4")
    parser.add_argument("--provider-base-url", required=True)
    args = parser.parse_args()

    output_root = args.output_root.resolve()
    framework_files = {
        "AI-Researcher/benchmark/process/dataset_candidate/tdc_admet_tox/metaprompt.py": ai_researcher_metaprompt(),
        "AI-Scientist-v2/ai_scientist/ideas/tdc_admet_tox_topic.md": ai_scientist_topic(
            args.primary_model, args.provider_base_url
        ),
        "AutoResearchClaw/config.tdc_admet_tox.yaml": autoresearchclaw_config(
            args.primary_model, args.provider_base_url
        ),
        "AutoResearchClaw/topic.tdc_admet_tox.txt": AUTORESEARCHCLAW_TOPIC_BRIEF,
        "AutoResearchClaw/TDC_ADMET_TOX_BRIEF.md": RUNTIME_BRIEF,
        "Auto-claude-code-research-in-sleep/TDC_ADMET_TOX_BRIEF.md": RUNTIME_BRIEF,
        "DeepScientist/TDC_ADMET_TOX_BRIEF.md": RUNTIME_BRIEF,
        "dr-claw/TDC_ADMET_TOX_BRIEF.md": RUNTIME_BRIEF,
        "dr-claw/dr_claw_benchmark_authorization.md": (
            "Benchmark authorization for Dr. Claw on Topic 5 (TDC-ADMET-Tox):\n"
            "The evaluation operator explicitly confirmed prior written consent for "
            "benchmark and comparative evaluation of Dr. Claw on 2026-08-05, "
            "satisfying docs/internal-beta-user-agreement.en-US.md section 6.\n"
        ),
        "EvoScientist/TDC_ADMET_TOX_BRIEF.md": RUNTIME_BRIEF,
        "EvoScientist/tdc_admet_tox_start_message.txt": (
            "Start the native TDC-ADMET-Tox workflow. Read @TDC_ADMET_TOX_BRIEF.md and "
            "@automation/tdc_admet_tox_contract.md first.\n"
        ),
        "EvoScientist/tdc_admet_tox_evoscientist_config.yaml": (
            "provider: custom-openai\n"
            f"model: {args.primary_model}\n"
            "openai_auth_mode: api_key\n"
            "default_mode: daemon\n"
            "default_workdir: /workspace\n"
            f"show_thinking: {'true' if args.primary_model and args.primary_model.startswith('deepseek') else 'false'}\n"
            "enable_async_subagents: false\n"
        ),
    }
    write(output_root / "automation/tdc_admet_tox_runtime_brief.md", RUNTIME_BRIEF)
    for relative_path, content in framework_files.items():
        write(output_root / relative_path, content)

    instance_path = (
        output_root
        / "AI-Researcher/benchmark/final/tdc_admet_tox/tdc_admet_tox.json"
    )
    write(
        instance_path,
        json.dumps(ai_researcher_payload(), ensure_ascii=True, indent=2) + "\n",
    )
    generated = [
        "automation/tdc_admet_tox_runtime_brief.md",
        "AI-Researcher/benchmark/final/tdc_admet_tox/tdc_admet_tox.json",
        *framework_files,
    ]
    write(
        output_root / "automation/tdc_admet_tox_native_manifest.json",
        json.dumps(
            {
                "task_id": TASK_ID,
                "dataset_root": "/data/tdc_admet_tox",
                "contract_file": "/workspace/automation/tdc_admet_tox_contract.md",
                "primary_model": args.primary_model,
                "provider_base_url": args.provider_base_url,
                "generated_files": generated,
            },
            ensure_ascii=True,
            indent=2,
        )
        + "\n",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
