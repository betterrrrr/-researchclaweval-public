#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

TOPIC_ID = "arc_wbe_2026"
TOPIC_LABEL = "ARC-WBE-2026"
RESULT_FIELDS = ["score", "score_source", "score_artifact", "submission_artifact"]
REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DATASET_ROOT = REPO_ROOT / "data" / "arc_white_box_estimation_2026"
DEFAULT_CONTRACT_FILE = REPO_ROOT / "automation" / "arc_wbe_2026_contract.md"


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content.rstrip() + "\n", encoding="utf-8")


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def render_shared_summary(dataset_root: Path, contract_file: Path) -> str:
    return f"""# ARC WBE 2026 Summary

## Topic
- Topic id: `{TOPIC_ID}`
- Topic label: `{TOPIC_LABEL}`
- Dataset root: `{dataset_root}`
- Contract file: `{contract_file}`

## Goal
Produce official-comparable ARC White-Box Estimation Challenge 2026 results.

## Task description
- The goal is to estimate the per-layer hidden activations of a 32-layer Transformer MLP from its weight matrices
- Input: the 32 weight matrices of a 32-layer MLP, each layer is a (256, 256) matrix (ReLU activation)
- Output: predicted activations for every layer — a matrix of shape (32, 256)
- The estimator's `predict(mlp)` method must return a **numpy array of shape (32, 256)** (the predicted per-layer activations), NOT a scalar score or a 1-D vector
- The official scorer compares the predicted activations to the ground-truth activations using MSE and other metrics
- Do NOT predict a scalar performance metric (loss, accuracy, MSE, etc.) — the scorer computes the metric from the activation predictions

## Required normalized result fields
- `score`
- `score_source`
- `score_artifact`
- `submission_artifact`

## Expected deliverables
- root-level `research_idea.json`, `estimator.py`, `submission.json`, `experiment_trace.json`, and `final_report.md`
- host-produced official local score evidence after the native framework exits
- manifest and state references
- logs and preserved workspace traces

## Estimator interface requirements
- `estimator.py` must be self-contained: the official scorer imports it, instantiates the estimator class, and calls `predict(mlp)` without calling `fit` first
- Embed all trained model parameters as Python literal values (lists, floats, arrays in `np.array([...])`) directly in `estimator.py` source code
- Do NOT reference external JSON, pickle, NPY, or any other data files at import time or predict time
- The estimator class `__init__` must load these embedded parameters so the instance is immediately ready for prediction
- `predict(mlp)` must accept the official scorer's `MLP` object (which has a `.weights` attribute) and return a `(32, 256)` prediction matrix
- Do not require any external files, pickled state, or `fit()` call at scoring time

## Phase-one scope
- keep topic-specific inputs explicit for each framework
- preserve tool-use traces for later analysis
- do not require tool-call scoring in phase one
"""


def render_ai_scientist_topic(dataset_root: Path, contract_file: Path) -> str:
    return f"""# Title
ARC-WBE-2026: White-Box Estimation Benchmark Execution

# TL;DR
Build a reproducible ARC White-Box Estimation Challenge 2026 workflow that produces official-format outputs, records benchmark evidence, and optimizes the benchmark score where local scoring exists.

# Dataset
- standardized local dataset root: {dataset_root}

# Contract
- topic label: {TOPIC_LABEL}
- contract file: {contract_file}

# Concrete Goal
Implement and evaluate an ARC-WBE-2026 run path that:
1. consumes the challenge contract directly,
2. writes and locks `research_idea.json` before the first experiment,
3. emits a runnable `estimator.py` when possible so the official local scorer can be replayed,
4. records reproducible commands and artifact locations,
5. writes a concise final report.

# Scientific Independence
The framework owns the hypothesis, method choice, experiment design, comparison, and final selection. No algorithm family, feature representation, architecture, hyperparameters, baseline, or experiment sequence is prescribed.

# Required Result Fields
- score
- score_source
- score_artifact
- submission_artifact
"""


def render_framework_brief(dataset_root: Path, contract_file: Path) -> str:
    return f"""# {TOPIC_LABEL}

## Objective
Execute the ARC White-Box Estimation Challenge 2026 topic directly instead of falling back to another benchmark.

## Inputs
- dataset root: {dataset_root}
- contract file: {contract_file}
- the mounted dataset contains real parquet records with `mlp_id`, `mlp_name`, `mlp_seed`, and `weights`; target labels for the scored records are **not** visible to the framework
- a small **labelled** visible-validation subset is mounted alongside at `visible-validation/` (10 of the 100 MLPs, with `weights`, `all_layer_means`, and `final_means`). Use it to self-evaluate your estimator with the official metric. It is disjoint from the scoring set by `mlp_id`.

## Success Criteria
- write and lock `research_idea.json` before the first experiment
- run 2-4 materially different framework-native experiments chosen by the framework, then finalize
- produce root-level `research_idea.json`, `estimator.py`, `submission.json`, `experiment_trace.json`, and `final_report.md`
- make `estimator.py` directly runnable by the supplied official scorer; expose an estimator object with a `predict(mlp)` method that returns a (32,256) NumPy array of predicted per-layer activations
- the estimator's `predict(mlp)` must accept the official scorer's `MLP` object (which has a `.weights` attribute of shape (32, 256, 256)) and return a numpy array of shape (32,256) — the predicted activations for every layer
- do NOT predict a scalar score or class label; the scorer computes the metric from the activation predictions
- do not fabricate, synthesize, zero-fill, broadcast, or use placeholder predictions; if a real estimator cannot be produced, stop with a concrete blocker and do not write a score
- record `framework_native_execution`, `consumed_topic_input`, `workspace_trace_root`, `experiments`, `selected_experiment_id`, `framework_internal_model`, `framework_internal_api_base_url`, `idea_artifact`, and `idea_locked_before_experiments` in `experiment_trace.json`
- record each experiment's self-evaluation under `framework_visible_validation` as **numeric fields** (`n_mlps`, `adjusted_final_layer_score`, `final_layer_mse`, `all_layers_mse`). A qualitative sentence is not a substitute: without numbers the trace cannot support `b0`/`bT`/`AUP`/`UR`, and those dimensions fall back to the judge's ordinal path.
- use the injected OpenAI-compatible API environment and record the model/base URL in the trace
- preserve logs, manifests, and workspace traces
- write `final_report.md`

## Method Ownership
The framework owns the hypothesis, algorithm family, feature representation, architecture, hyperparameters, experiment sequence, comparison, and selected method.

## Normalized Result Fields
- score
- score_source
- score_artifact
- submission_artifact
"""


def render_autoresearchclaw_topic() -> str:
     return """ARC-WBE-2026: White-Box Estimation of Transformer MLP Activations

Execute the ARC White-Box Estimation Challenge 2026 contract in
/workspace/automation/arc_wbe_2026_contract.md using the prepared dataset at
/data/arc_wbe_2026. The parquet records contain real weights only; target labels
are host-only. The parquet file has columns: mlp_id (int32), mlp_name (string),
mlp_seed (int64), weights (float32[32,256,256]). Load it with pyarrow.parquet.
Before the first experiment the framework Stage 8 synthesis writes and locks
research_idea.json. Design and run 2-4 bounded, materially different experiments
under the supplied execution budget, then select one result. The framework owns
the hypothesis, method choice, experiment design, comparison, and final
selection; no algorithm family, feature representation, architecture,
hyperparameters, baseline, or experiment sequence is prescribed. Deliver
root-level estimator.py, submission.json,
experiment_trace.json, and final_report.md. Do NOT create and do NOT overwrite
root-level research_idea.json or research_idea_lock_event.json: the framework
idea-lock step owns those two files and overwriting them invalidates the run.
Record the injected model and API
base URL in the trace. The host creates score.json after the native run exits.
The dataset has a fixed validation split. Never compute val and test metrics on the same data.
"""


def render_ai_researcher_metaprompt(dataset_root: Path, contract_file: Path) -> str:
    return f'''TASK = "ARC White-Box Estimation Challenge 2026 benchmark execution."
DATASET = """
Use the real ARC-WBE-2026 dataset mounted by ResearchClawEval.
The dataset is available at:
- /data/arc_wbe_2026
- /workplace/project/data/arc_wbe_2026
- /workplace/dataset_candidate/arc_wbe_2026
- {dataset_root}
"""
BASELINE = "No host-prescribed baseline. The framework must choose and justify its own methods."
COMPARISON = "Compare only official-format outputs or score evidence generated from the same ARC-WBE-2026 contract."
EVALUATION = "Write and lock research_idea.json before the first experiment. Run 2-4 bounded framework-native experiments selected by the framework. Use the injected OPENAI_BASE_URL, OPENAI_API_KEY, and OPENAI_MODEL for all internal calls. Promote the selected result to root-level research_idea.json, estimator.py, submission.json, experiment_trace.json (including model/base URL and idea-lock evidence), and final_report.md. The host creates score.json after native exit."
REF = "Do not use unrelated benchmarks, toy datasets, placeholder results, synthetic submissions, zero/broadcast predictions, fallback scores, or outputs from previous topics. The mounted parquet contains real weights-only records; do not fabricate labels. The contract file is: {contract_file}"
METHOD_OWNERSHIP = "The framework owns the hypothesis, algorithm family, feature representation, architecture, hyperparameters, experiment sequence, comparison, and selected method."
DATA_INSPECTION_RULES = """
When inspecting ARC-WBE-2026 parquet or dataset rows, Do not print raw weights, all_layer_means, final_means, or other large tensor/array payloads.
Inspect schema, column names, dtypes, shapes, and concise scalar summaries only.
If you need examples, print only field names, array shapes, lengths, and a tiny bounded preview; never dump full arrays or full row dictionaries to stdout.
"""
'''


def build_ai_researcher_payload(dataset_root: Path, contract_file: Path) -> dict[str, object]:
    return {
        "instance_id": TOPIC_ID,
        "target": "ARC White-Box Estimation Challenge 2026",
        "title": "ARC-WBE-2026: White-Box Estimation Benchmark Execution",
        "authors": ["Project-local custom benchmark"],
        "year": 2026,
        "url": "http://arxiv.org/abs/2606.18001v1",
        "abstract": "A local benchmark configuration for ARC-WBE-2026 with explicit benchmark-native inputs and normalized score reporting fields.",
        "venue": "Local Benchmark",
        "topic": "benchmark_execution",
        "field": "benchmarking",
        "source_papers": [],
        "dataset_root": str(dataset_root),
        "contract_file": str(contract_file),
        "result_fields": RESULT_FIELDS,
        "task1": "Before the first experiment, write and lock research_idea.json. Consume the ARC-WBE-2026 contract, run 2-4 materially different framework-chosen experiments, and preserve a runnable estimator.py, submission artifact, trace, logs, and concise final report.",
        "task2": "Own the hypothesis, method choice, experiment design, comparison, and final selection. Record estimator entrypoints and submission artifact paths; the host creates score.json after native exit.",
    }


def build_dr_claw_brief(dataset_root: Path, contract_file: Path) -> dict[str, object]:
    return {
        "project_name": TOPIC_ID,
        "project_type": "benchmark_task",
        "objective": "Produce official-comparable ARC-WBE-2026 outputs with normalized score reporting.",
        "dataset": {
            "name": TOPIC_LABEL,
            "root": str(dataset_root),
        },
        "contract_file": str(contract_file),
        "result_fields": RESULT_FIELDS,
        "deliverables": [
            "research_idea.json",
            "submission_artifact",
            "experiment_trace.json",
            "final_report.md",
            "logs",
            "workspace_traces",
        ],
    }


def build_dr_claw_tasks() -> dict[str, object]:
    return {
        "method_policy": {
            "framework_owns_method_choice": True,
            "prescribed_methods": [],
        },
        "tasks": [
            {
                "id": "native_research_workflow",
                "title": "Complete the ARC-WBE-2026 native research workflow",
                "goal": "Write the pre-experiment idea, choose and run 2-4 materially different experiments, compare them, select one result, and deliver the required framework-authored artifacts.",
            }
        ],
    }


def build_autoresearchclaw_config(
    repo_root: Path,
    dataset_root: Path,
    contract_file: Path,
    provider_base_url: str,
    primary_model: str,
) -> str:
    _is_kimi = primary_model.startswith("kimi-")
    _is_direct_api = _is_kimi or "deepseek" in primary_model.lower()
    if _is_direct_api:
        llm_block = f"""llm:
  provider: "openai-compatible"
  primary_model: "{primary_model}"
  fallback_models: []
  base_url: "{provider_base_url}"
  api_key_env: "OPENAI_API_KEY"
"""
    else:
        llm_block = f"""llm:
  provider: "acp"
  primary_model: "{primary_model}"
  fallback_models: []
  base_url: "{provider_base_url}"
  api_key_env: "OPENAI_API_KEY"
  acp:
    agent: "codex"
    cwd: "/workspace"
"""
    try:
        contract_relative_path = contract_file.relative_to(repo_root)
    except ValueError as error:
        raise ValueError(
            f"contract file is outside supplied repo root: {contract_file}"
        ) from error
    workspace_contract_file = f"/workspace/{contract_relative_path}"
    return f"""project:
  name: "{TOPIC_ID}"
  mode: "full-auto"
  output_dir: "./outputs/{TOPIC_ID}"

research:
  topic: "{TOPIC_LABEL}"
  daily_paper_count: 0
  quality_threshold: 0.0

runtime:
  timezone: "Asia/Shanghai"
  max_parallel_tasks: 1
  retry_limit: 3

notifications:
  channel: "none"

knowledge_base:
  root: "./knowledge_base"

assets:
  dataset_root: "{dataset_root}"
  contract_file: "{workspace_contract_file}"

{llm_block}
# The evaluation container has no public-network dependency.  Keep the
# framework's research pipeline native while preventing long retry loops in
# the optional literature augmentation path.
web_search:
  enabled: false
  enable_scholar: false
  enable_crawling: false
  enable_pdf_extraction: false
  max_web_results: 0
  max_scholar_results: 0
  max_crawl_urls: 0

prompts:
  extra_prompts:
    hypothesis_gen: >-
      This is the ARC-WBE-2026 weights-only contract. Before any
      experiment or generated experiment code, write and lock a substantive
      root-level research_idea.json. Keep the idea method-free: the framework
      must choose the hypothesis and method from the visible weights.
    experiment_design: >-
      Stay inside ARC-WBE-2026 only. Use the mounted weights-only parquet at
      /data/arc_wbe_2026 and do not create generic torchvision, MNIST, CIFAR,
      classification, or unrelated Hugging Face benchmark loaders. Design 2-4
      materially different experiments chosen by the framework, with no host
      prescribed algorithm family, representation, architecture,
      hyperparameters, or sequence.
    code_generation: >-
      Generate only the ARC-WBE-2026 deliverables. Read the contract and
      weights-only schema, keep labels hidden, and write root-level
      estimator.py, submission.json,
      experiment_trace.json, and final_report.md. Do NOT create and do NOT
      overwrite root-level research_idea.json or research_idea_lock_event.json:
      the framework Stage 8 idea-lock step owns those two files, and
      overwriting them invalidates the run. The estimator must consume
      each input mlp.weights and return a finite nonzero (32,256) array with
      direct input dependence; never use scalar, zero, broadcast, placeholder,
      synthetic, or fallback predictions. Record the injected model and base
      URL and keep the framework-native trace complete.

evaluation:
  result_fields:
    - "score"
    - "score_source"
    - "score_artifact"
    - "submission_artifact"

experiment:
  # Beast Mode (framework-native OpenCode code generation).  The framework
  # default is 600s per attempt with 1 retry, which ARC-WBE code generation
  # exceeds: both attempts hit the limit and the pipeline fell back to
  # CodeAgent.  Give the framework's own mechanism enough time to finish.
  opencode:
    enabled: true
    auto: true
    timeout_sec: 3600
    max_retries: 2
  mode: "sandbox"
  time_budget_sec: 28800
  max_iterations: 3
  code_agent:
    enabled: true
    architecture_planning: true
    sequential_generation: true
    hard_validation: true
    hard_validation_max_repairs: 4
    exec_fix_max_iterations: 3
    exec_fix_timeout_sec: 600
  sandbox:
    python_path: "/usr/bin/python3"
    gpu_required: false
    allowed_imports: [math, json, pathlib, numpy, pandas, scipy, sklearn, torch, pyarrow, datasets]
"""


def generate_native_inputs(
    repo_root: Path,
    output_root: Path,
    dataset_root: Path,
    contract_file: Path,
    provider_base_url: str = "https://api.openai.com/v1",
    primary_model: str = "gpt-5.4",
) -> dict[str, object]:
    output_root.mkdir(parents=True, exist_ok=True)

    shared_summary = render_shared_summary(dataset_root, contract_file)
    authoritative_contract = (
        contract_file.read_text(encoding="utf-8")
        if contract_file.exists()
        else f"# ARC WBE 2026 Contract Pointer\n\nSource contract file: `{contract_file}`\n"
    )
    ai_scientist_topic = render_ai_scientist_topic(dataset_root, contract_file)
    framework_brief = render_framework_brief(dataset_root, contract_file)

    text_files = {
        "docs/arc_wbe_2026_summary.md": shared_summary,
        "automation/arc_wbe_2026_contract.md": authoritative_contract,
        "automation/arc_wbe_2026_execution_budget.md": (
            (REPO_ROOT / "automation" / "arc_wbe_2026_execution_budget.md").read_text(
                encoding="utf-8"
            )
        ),
        "automation/scripts/run_arc_wbe_2026_local_score.py": (
            (REPO_ROOT / "automation" / "scripts" / "run_arc_wbe_2026_local_score.py").read_text(
                encoding="utf-8"
            )
        ),
        "automation/scripts/arc_wbe_2026_official_adapter.py": (
            (REPO_ROOT / "automation" / "scripts" / "arc_wbe_2026_official_adapter.py").read_text(
                encoding="utf-8"
            )
        ),
        "automation/scripts/prepare_arc_wbe_2026_dataset.py": (
            (REPO_ROOT / "automation" / "scripts" / "prepare_arc_wbe_2026_dataset.py").read_text(
                encoding="utf-8"
            )
        ),
        "AI-Researcher/benchmark/process/dataset_candidate/arc_wbe_2026/metaprompt.py": render_ai_researcher_metaprompt(
            dataset_root, contract_file
        ),
        "AI-Scientist-v2/ai_scientist/ideas/arc_wbe_2026_topic.md": ai_scientist_topic,
        "AI-Scientist-v2/ai_scientist/ideas/my_research_topic.md": ai_scientist_topic,
        "Auto-claude-code-research-in-sleep/ARC_WBE_2026_BRIEF.md": framework_brief,
        "Auto-claude-code-research-in-sleep/.aris-codex-project/ARC_WBE_2026_BRIEF.md": framework_brief,
        "AutoResearchClaw/topic.txt": render_autoresearchclaw_topic(),
        "AutoResearchClaw/config.arc.yaml": build_autoresearchclaw_config(
            repo_root,
            dataset_root,
            contract_file,
            provider_base_url,
            primary_model,
        ),
        "DeepScientist/DEEPSCIENTIST_BRIEF.md": framework_brief,
        "EvoScientist/EVOSCIENTIST_BRIEF.md": framework_brief,
        "EvoScientist/arc_wbe_2026_start_message.txt": "Start ARC-WBE-2026. Read @EVOSCIENTIST_BRIEF.md, @docs/arc_wbe_2026_summary.md, and @automation/arc_wbe_2026_execution_budget.md first. IMPORTANT: This is a white-box estimation task: predict the per-layer hidden activation matrix of shape (32, 256) from the MLP weights.\n",
    }
    json_files = {
        "AI-Researcher/benchmark/final/arc_wbe_2026/arc_wbe_2026.json": build_ai_researcher_payload(
            dataset_root,
            contract_file,
        ),
        "dr-claw/research_brief.json": build_dr_claw_brief(dataset_root, contract_file),
        "dr-claw/tasks.json": build_dr_claw_tasks(),
    }

    manifest_files: dict[str, dict[str, str]] = {}
    for rel_path, content in text_files.items():
        write_text(output_root / rel_path, content)
        manifest_files[rel_path] = {"kind": "text"}
    for rel_path, payload in json_files.items():
        write_json(output_root / rel_path, payload)
        manifest_files[rel_path] = {"kind": "json"}

    manifest = {
        "topic": {
            "id": TOPIC_ID,
            "label": TOPIC_LABEL,
            "dataset_root": str(dataset_root),
            "contract_file": str(contract_file),
        },
        "result_fields": RESULT_FIELDS,
        "files": manifest_files,
    }
    write_json(output_root / "arc_wbe_2026_manifest.json", manifest)
    return manifest


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate ARC-WBE-2026 native framework inputs.")
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--dataset-root", type=Path, default=DEFAULT_DATASET_ROOT)
    parser.add_argument("--contract-file", type=Path, default=DEFAULT_CONTRACT_FILE)
    parser.add_argument("--provider-base-url", default="https://api.openai.com/v1")
    parser.add_argument("--primary-model", default="gpt-5.4")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    generate_native_inputs(
        repo_root=REPO_ROOT,
        output_root=args.output_root,
        dataset_root=args.dataset_root,
        contract_file=args.contract_file,
        provider_base_url=args.provider_base_url,
        primary_model=args.primary_model,
    )
    print(
        json.dumps(
            {
                "topic": TOPIC_ID,
                "output_root": str(args.output_root),
                "manifest": str(args.output_root / "arc_wbe_2026_manifest.json"),
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
