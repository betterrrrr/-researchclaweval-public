#!/usr/bin/env python3
"""Project the BabyLM contract and full input pack into a run workspace.

Emits AI-Researcher instance JSON, method-free metaprompt, execution budget,
shared summary, framework-specific inputs, and input manifest.
The model is parameterized (not hardcoded).
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

TOPIC_ID = "babylm"
TOPIC_LABEL = "BabyLM-2026-Strict-Small"
RESULT_FIELDS = ["score", "score_source", "score_artifact", "submission_artifact"]
REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DATASET_ROOT = REPO_ROOT / "BabyLM-2026-Strict-Small"
DEFAULT_CONTRACT_FILE = REPO_ROOT / "automation" / "babylm_method_free_contract.md"


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content.rstrip() + "\n", encoding="utf-8")


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def render_shared_summary(dataset_root: Path, contract_file: Path, primary_model: str) -> str:
    return f"""# {TOPIC_LABEL} Summary

## Topic
- Topic id: `{TOPIC_ID}`
- Topic label: `{TOPIC_LABEL}`
- Dataset root: `{dataset_root}`
- Contract file: `{contract_file}`
- Model: `{primary_model}`

## Goal
Train language models on the BabyLM Strict-Small dataset and report word-level validation perplexity.

## Task description
- The dataset contains 6 text domains: bnc_spoken, childes, gutenberg, open_subtitles, simple_wiki, switchboard
- Each domain is a `.train.txt` file with one sentence per line, already tokenized
- The dataset contains **only** `.train.txt` files — there is **no** separate validation set
- The framework must split the training data into train/validation sets itself (e.g., held-out 10% of tokens or lines per domain)
- The primary metric is **word-level validation perplexity**. Use the same tokenizer and preprocessing across all experiments
- Character-level or subword-level perplexity is not accepted as the primary metric
- When loading text files, do **not** silently swallow file-reading exceptions (no bare `except: pass` around file I/O), and always check that the loaded data is non-empty

## Required normalized result fields
- `score`
- `score_source`
- `score_artifact`
- `submission_artifact`

## Expected deliverables
- root-level `research_idea.json`, `experiment_trace.json`, and `final_report.md`
- host-produced official score evidence after the native framework exits
- manifest and state references
- logs and preserved workspace traces

## Method ownership
The framework owns the hypothesis, algorithm family, feature representation, architecture, hyperparameters, experiment sequence, comparison, and selected method.

## Phase-one scope
- keep topic-specific inputs explicit for each framework
- preserve tool-use traces for later analysis
- do not require tool-call scoring in phase one
"""


def render_ai_scientist_topic(dataset_root: Path, contract_file: Path, primary_model: str) -> str:
    return f"""# Title
{TOPIC_LABEL}: Word-Level Language Modeling Benchmark

# TL;DR
Build a reproducible BabyLM Strict-Small word-level language modeling workflow that produces official-format outputs, records benchmark evidence, and minimizes validation perplexity.

# Dataset
- standardized local dataset root: {dataset_root}
- 6 text domains: bnc_spoken, childes, gutenberg, open_subtitles, simple_wiki, switchboard

# Contract
- topic label: {TOPIC_LABEL}
- contract file: {contract_file}
- model: {primary_model}

# Concrete Goal
Implement and evaluate a BabyLM word-level language modeling run path that:
1. consumes the challenge contract directly,
2. writes and locks `research_idea.json` before the first experiment,
3. trains and evaluates on the real dataset only,
4. records word-level validation perplexity for each experiment,
5. writes a concise final report.

# Scientific Independence
The framework owns the hypothesis, method choice, experiment design, comparison, and final selection. No algorithm family, feature representation, architecture, hyperparameters, baseline, or experiment sequence is prescribed.

# Required Result Fields
- score
- score_source
- score_artifact
- submission_artifact
"""


def render_framework_brief(dataset_root: Path, contract_file: Path, primary_model: str) -> str:
    return f"""# {TOPIC_LABEL}

## Objective
Execute the BabyLM Strict-Small word-level language modeling topic directly instead of falling back to another benchmark.

## Inputs
- dataset root: {dataset_root}
- contract file: {contract_file}
- model: {primary_model}
- the mounted dataset contains 6 `.train.txt` domain files (one sentence per line, already tokenized)
- **no separate validation set** — the framework must split the train data into train/validation sets itself
- total size: approximately 10 million words across all domains

## Success Criteria
- write and lock `research_idea.json` before the first experiment
- run 2-4 materially different framework-native experiments chosen by the framework, then finalize
- produce root-level `research_idea.json`, `experiment_trace.json`, and `final_report.md`
- record word-level `validation_perplexity` for each experiment in the trace; use the same tokenizer and preprocessing across all experiments
- do not fabricate, zero-fill, or use placeholder perplexity values; if a real model cannot be produced, stop with a concrete blocker and do not write a score
- record `framework_native_execution`, `consumed_topic_input`, `workspace_trace_root`, `experiments` (array of experiment objects, each with `experiment_id`, `name`, `validation_perplexity`), `selected_experiment_id`, `framework_internal_model`, `framework_internal_api_base_url`, `idea_artifact`, and `idea_locked_before_experiments` in `experiment_trace.json`
- the trace JSON must be **strict JSON** (no `NaN`, `Infinity`, or `-Infinity`; convert them to `null`)
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
    return """BabyLM-2026-Strict-Small: Word-Level Language Modeling

Execute the BabyLM Strict-Small method-free contract in
/workspace/automation/babylm_method_free_contract.md using the prepared dataset at
/data/BabyLM-2026-Strict-Small. The dataset contains only .train.txt files
(one sentence per line, already tokenized) — there is no separate validation
set, so the framework must split the train data into train/validation sets.
Before the first experiment, write and lock research_idea.json. Design and run
2-4 bounded, materially different experiments under the supplied execution
budget, then select one result. The framework owns the hypothesis, method
choice, experiment design, comparison, and final selection; no algorithm
family, feature representation, architecture, hyperparameters, baseline, or
experiment sequence is prescribed. The primary metric is word-level validation
perplexity; use the same tokenizer and preprocessing across all experiments.
Deliver root-level research_idea.json, experiment_trace.json, and
final_report.md. The trace JSON must be strict valid JSON (no NaN, Infinity,
or -Infinity; convert to null). Record the injected model and API base URL in
the trace. The host creates score.json after the native run exits.
"""


def render_ai_researcher_metaprompt(dataset_root: Path, contract_file: Path, primary_model: str) -> str:
    """Method-free metaprompt: no algorithm family, architecture, or framework
    libraries are prescribed. Only real dataset, word-level perplexity policy,
    execution budget, 2-4 experiments, and output schema."""
    return f'''TASK = "BabyLM Strict-Small word-level language modeling benchmark execution."
DATASET = """
Use the real BabyLM-2026-Strict-Small dataset mounted by ResearchClawEval.
The dataset is available at:
- /data/BabyLM-2026-Strict-Small
- /workplace/project/data/BabyLM-2026-Strict-Small
- /workplace/dataset_candidate/BabyLM-2026-Strict-Small
- {dataset_root}
"""
BASELINE = "No host-prescribed baseline. The framework must choose and justify its own methods."
COMPARISON = "Compare only word-level validation perplexity across experiments on the same BabyLM dataset and split."
EVALUATION = "Write and lock research_idea.json before the first experiment. Run 2-4 bounded framework-native experiments selected by the framework. Use the injected OPENAI_BASE_URL, OPENAI_API_KEY, and OPENAI_MODEL for all internal calls. Promote the selected result to root-level research_idea.json, experiment_trace.json (including model/base URL, idea-lock evidence, and word-level validation_perplexity per experiment), and final_report.md. The host creates score.json after native exit."
REF = "Do not use unrelated benchmarks, toy datasets, placeholder results, synthetic scores, or outputs from previous topics. The mounted text files contain real natural language data; do not fabricate perplexity values. The contract file is: {contract_file}"
METHOD_OWNERSHIP = "The framework owns the hypothesis, algorithm family, feature representation, architecture, hyperparameters, experiment sequence, comparison, and selected method."
DATA_INSPECTION_RULES = """
When inspecting BabyLM text files, inspect the first few lines, vocabulary size, total word count, and domain distribution only.
Print concise scalar summaries; never dump full files or large text blocks to stdout.
"""
'''


def build_ai_researcher_payload(dataset_root: Path, contract_file: Path, primary_model: str) -> dict[str, object]:
    return {
        "instance_id": TOPIC_ID,
        "target": "BabyLM 2026 Strict-Small",
        "title": "BabyLM-2026-Strict-Small: Word-Level Language Modeling Benchmark",
        "authors": ["Project-local custom benchmark"],
        "year": 2026,
        "url": "",
        "abstract": "A local benchmark configuration for BabyLM-2026-Strict-Small with explicit benchmark-native inputs and normalized score reporting fields.",
        "venue": "Local Benchmark",
        "topic": "benchmark_execution",
        "field": "language_modeling",
        "source_papers": [],
        "dataset_root": str(dataset_root),
        "contract_file": str(contract_file),
        "model": primary_model,
        "result_fields": RESULT_FIELDS,
        "task1": "Before the first experiment, write and lock research_idea.json. Consume the BabyLM method-free contract, run 2-4 materially different framework-chosen experiments, and preserve a experiment trace, logs, and concise final report. Record word-level validation_perplexity for each experiment.",
        "task2": "Own the hypothesis, method choice, experiment design, comparison, and final selection. Record experiment entrypoints; the host creates score.json after native exit.",
    }


def build_dr_claw_brief(dataset_root: Path, contract_file: Path, primary_model: str) -> dict[str, object]:
    return {
        "project_name": TOPIC_ID,
        "project_type": "benchmark_task",
        "objective": "Produce official-comparable BabyLM word-level language modeling outputs with normalized score reporting.",
        "dataset": {
            "name": TOPIC_LABEL,
            "root": str(dataset_root),
        },
        "contract_file": str(contract_file),
        "model": primary_model,
        "result_fields": RESULT_FIELDS,
        "deliverables": [
            "research_idea.json",
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
                "title": "Complete the BabyLM native research workflow",
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
  quality_threshold: 0.3

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

llm:
  provider: "acp"
  primary_model: "{primary_model}"
  fallback_models: []
  base_url: "{provider_base_url}"
  api_key_env: "OPENAI_API_KEY"
  acp:
    agent: "codex"
    cwd: "/workspace"

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
      This is the BabyLM Strict-Small word-level language modeling contract.
      Before any experiment or generated experiment code, write and lock a
      substantive root-level research_idea.json. Keep the idea method-free:
      the framework must choose the hypothesis and method from the visible
      text data.
    experiment_design: >-
      Stay inside BabyLM-2026-Strict-Small only. Use the mounted text files
      at /data/BabyLM-2026-Strict-Small and do not create generic
      classification, image, or unrelated benchmark loaders. Design 2-4
      materially different experiments chosen by the framework, with no host
      prescribed algorithm family, representation, architecture,
      hyperparameters, or sequence. The primary metric is word-level
      validation perplexity.
    code_generation: >-
      Generate only the BabyLM deliverables. Read the contract and text
      schema, and write root-level research_idea.json, experiment_trace.json,
      and final_report.md. Record word-level validation_perplexity for each
      experiment. Record the injected model and base URL and keep the
      framework-native trace complete.

evaluation:
  result_fields:
    - "score"
    - "score_source"
    - "score_artifact"
    - "submission_artifact"

experiment:
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
    allowed_imports: [math, json, pathlib, collections, numpy, scipy, sklearn]
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

    shared_summary = render_shared_summary(dataset_root, contract_file, primary_model)
    authoritative_contract = (
        contract_file.read_text(encoding="utf-8")
        if contract_file.exists()
        else f"# BabyLM Contract Pointer\n\nSource contract file: `{contract_file}`\n"
    )
    ai_scientist_topic = render_ai_scientist_topic(dataset_root, contract_file, primary_model)
    framework_brief = render_framework_brief(dataset_root, contract_file, primary_model)

    # Read execution budget from repo
    budget_path = REPO_ROOT / "automation" / "babylm_execution_budget.md"
    execution_budget = budget_path.read_text(encoding="utf-8") if budget_path.exists() else ""

    text_files = {
        "docs/babylm_summary.md": shared_summary,
        "automation/babylm_method_free_contract.md": authoritative_contract,
        "automation/babylm_execution_budget.md": execution_budget,
        "automation/scripts/run_babylm_score.py": (
            (REPO_ROOT / "automation" / "scripts" / "run_babylm_score.py").read_text(
                encoding="utf-8"
            )
        ),
        "AI-Researcher/benchmark/process/dataset_candidate/babylm/metaprompt.py": render_ai_researcher_metaprompt(
            dataset_root, contract_file, primary_model
        ),
        "AI-Scientist-v2/ai_scientist/ideas/babylm_topic.md": ai_scientist_topic,
        "AI-Scientist-v2/ai_scientist/ideas/my_research_topic.md": ai_scientist_topic,
        "Auto-claude-code-research-in-sleep/babylm_brief.md": framework_brief,
        "Auto-claude-code-research-in-sleep/.aris-codex-project/babylm_brief.md": framework_brief,
        "AutoResearchClaw/topic.txt": render_autoresearchclaw_topic(),
        "AutoResearchClaw/config.babylm.yaml": build_autoresearchclaw_config(
            repo_root,
            dataset_root,
            contract_file,
            provider_base_url,
            primary_model,
        ),
        "DeepScientist/babylm_brief.md": framework_brief,
        "EvoScientist/babylm_brief.md": framework_brief,
        "EvoScientist/babylm_start_message.txt": f"Start BabyLM-2026-Strict-Small. Read @babylm_brief.md, @docs/babylm_summary.md, and @automation/babylm_execution_budget.md first. IMPORTANT: This is a word-level language modeling task: train on the text files and report word-level validation perplexity.\n",
    }
    json_files = {
        "AI-Researcher/benchmark/final/babylm/babylm.json": build_ai_researcher_payload(
            dataset_root,
            contract_file,
            primary_model,
        ),
        "dr-claw/research_brief.json": build_dr_claw_brief(dataset_root, contract_file, primary_model),
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
            "model": primary_model,
        },
        "result_fields": RESULT_FIELDS,
        "files": manifest_files,
    }
    write_json(output_root / "babylm_manifest.json", manifest)
    return manifest


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate BabyLM native framework inputs.")
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
                "manifest": str(args.output_root / "babylm_manifest.json"),
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())