#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

TOPIC_ID = "topic2"
TOPIC_LABEL = "Topic 2"
UPSTREAM_COMMIT = "9d40c1b5035202018cd7091fb4e83a9c68b377c0"
RESULT_FIELDS = ["score", "reward_std", "score_source", "score_artifact"]
REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_TOPIC_ROOT = REPO_ROOT / "data" / "topic2"
DEFAULT_CONTRACT_FILE = REPO_ROOT / "automation" / "topic2_contract.md"


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content.rstrip() + "\n", encoding="utf-8")


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def render_shared_summary(topic_root: Path, contract_file: Path) -> str:
    return f"""# Topic 2 Summary

## Topic
- Topic id: {TOPIC_ID}
- Topic label: {TOPIC_LABEL}
- Topic root: {topic_root}
- Contract file: {contract_file}
- Upstream: facebookresearch/MLGym @ {UPSTREAM_COMMIT}

## Goal
Improve the official Average Reward of the MountainCarContinuous-v0
reinforcement-learning task as much as possible under the available resource
budget.

## Task description
- A runnable PPO Actor-Critic baseline and a frozen evaluation protocol are
  provided.
- You may inspect and modify the permitted training code (src/train.py,
  src/policy.py, src/networks.py, src/helpers.py, src/config.yaml) and add
  new research code under src/.
- You must run real training experiments and deliver exactly five valid
  trained checkpoints under checkpoints/.
- The frozen evaluator (evaluate.py) is read-only. It evaluates 256 parallel
  environments across 5 seeds, each rollout capped at 200 frames, and
  requires exactly 5 checkpoints.

## CRITICAL: Checkpoint Location Requirement
Checkpoints MUST be saved directly to:
  checkpoints/config-42-0.pkl
  checkpoints/config-42-1.pkl
  checkpoints/config-42-2.pkl
  checkpoints/config-42-3.pkl
  checkpoints/config-42-4.pkl
Do NOT put checkpoints in subdirectories (exp1_checkpoints/, etc.).

## Required normalized result fields
- score (Reward Mean, higher is better)
- reward_std
- score_source
- score_artifact

## Expected deliverables
- root-level research_idea.json, experiment_trace.json, and final_report.md
- exactly five checkpoints under checkpoints/ plus config.yaml and src/
- host-produced official score evidence after the native framework exits
- logs and preserved workspace traces

## Checkpoint / config contract
- The evaluator globs checkpoints/<config_stem>*.pkl and asserts exactly 5.
- Keep the Model class name in networks.py unchanged.
- config.yaml + networks.py + checkpoints must stay mutually compatible.
"""


def render_framework_brief(topic_root: Path, contract_file: Path) -> str:
    return f"""# {TOPIC_LABEL}

## Objective
Improve the official Average Reward of the MountainCarContinuous-v0
reinforcement-learning task by running real training experiments.

## Inputs
- starter code (modifiable): src/train.py, src/policy.py, src/networks.py,
  src/helpers.py, src/config.yaml, src/__init__.py
- frozen evaluator (read-only): evaluate.py
- contract file: {contract_file}
- topic root (read-only): {topic_root}

## CRITICAL: Checkpoint Location Requirement
The frozen evaluator (evaluate.py) looks for checkpoints ONLY at:
  /workspace/checkpoints/config-42-0.pkl
  /workspace/checkpoints/config-42-1.pkl
  /workspace/checkpoints/config-42-2.pkl
  /workspace/checkpoints/config-42-3.pkl
  /workspace/checkpoints/config-42-4.pkl

Do NOT save checkpoints in subdirectories like exp1_checkpoints/,
baseline_checkpoints/, or any other folder. Save them directly to
/workspace/checkpoints/ with the exact filenames above.

## CRITICAL: Config/Model Consistency
The frozen evaluator rebuilds the model from src/config.yaml and
src/networks.py, then loads each checkpoint. If you modify networks.py
(e.g., add new layers, change initialization, add new parameters), you MUST
also update config.yaml to include ALL new parameters with their correct
values. The evaluator will fail if the checkpoint has parameters that the
model definition does not expect, or vice versa.
- Keep the Model class name unchanged ("Model").
- If you add new __init__ parameters, add them to config.yaml network_config.
- If you change layer names or counts, ensure consistency with checkpoints.
- Always test: load a checkpoint with the current config before finalizing.

## Success Criteria
- write and lock research_idea.json before the first experiment
- run 2-4 materially different framework-native experiments chosen by the
  framework, then finalize
- produce exactly five valid checkpoints under checkpoints/ plus config.yaml
  and src/
- produce root-level research_idea.json, experiment_trace.json, and
  final_report.md
- do not modify evaluate.py or the Model class name
- record framework_native_execution, consumed_topic_input, workspace_trace_root,
  experiments, selected_experiment_id, framework_internal_model,
  framework_internal_api_base_url, idea_artifact, and
  idea_locked_before_experiments in experiment_trace.json
- use the injected OpenAI-compatible API environment and record the model/base
  URL in the trace
- preserve logs, manifests, and workspace traces
- write final_report.md

## Method Ownership
The framework owns the hypothesis, algorithm family, feature representation,
architecture, hyperparameters, experiment sequence, comparison, and selected
method. No method is prescribed.

## Normalized Result Fields
- score
- reward_std
- score_source
- score_artifact
"""


def render_ai_scientist_topic(topic_root: Path, contract_file: Path) -> str:
    return f"""# Title
Topic 2: Reinforcement-Learning Reward Optimization

# TL;DR
Build a reproducible MountainCarContinuous-v0 workflow that improves the
official Average Reward, records benchmark evidence, and delivers five valid
trained checkpoints.

# Inputs
- starter code root: {topic_root}
- frozen evaluator: evaluate.py (read-only)

# Contract
- topic label: {TOPIC_LABEL}
- contract file: {contract_file}

# Concrete Goal
1. write and lock research_idea.json before the first experiment,
2. run 2-4 materially different experiments and select one result,
3. deliver exactly five checkpoints under checkpoints/ plus config.yaml and
   src/,
4. write experiment_trace.json and final_report.md.

# CRITICAL: Checkpoint Location
Checkpoints MUST be saved directly to /workspace/checkpoints/ as:
  config-42-0.pkl, config-42-1.pkl, config-42-2.pkl, config-42-3.pkl, config-42-4.pkl
Do NOT use subdirectories. The evaluator looks for checkpoints ONLY at checkpoints/&lt;config_stem&gt;*.pkl.

# Scientific Independence
The framework owns the hypothesis, method choice, experiment design,
comparison, and final selection. No algorithm family, feature representation,
architecture, hyperparameters, baseline, or experiment sequence is prescribed.

# Required Result Fields
- score
- reward_std
- score_source
- score_artifact
"""


def render_ai_researcher_metaprompt(topic_root: Path, contract_file: Path) -> str:
    return f'''TASK = "Topic 2 reinforcement-learning benchmark execution."
DATASET = """
Use the frozen starter code at /workspace/src/ (train.py, policy.py, networks.py, helpers.py, config.yaml, __init__.py) and the read-only evaluator at /workspace/evaluate.py. The starter code provides a runnable PPO Actor-Critic baseline for MountainCarContinuous-v0. You may modify the code, add new code under src/, and run training experiments. The environment has JAX, gymnax, flax, optax, and tensorflow_probability installed.
CRITICAL: You MUST use the provided PPO baseline (src/train.py, src/policy.py, src/networks.py). Do NOT switch to a different algorithm (e.g., QD, CMA-ES, evolutionary strategies). Do NOT train on a different environment (e.g., CartPole). The task is MountainCarContinuous-v0 only.
"""
BASELINE = "A runnable PPO Actor-Critic baseline is provided in src/."
COMPARISON = "Compare only official Reward Mean evidence generated from the same frozen evaluate.py."
EVALUATION = "Write and lock research_idea.json before the first experiment. Run 2-4 bounded framework-native experiments selected by the framework. Use the injected OPENAI_BASE_URL, OPENAI_API_KEY, and OPENAI_MODEL for all internal calls. Deliver exactly five checkpoints under checkpoints/, config.yaml, src/, experiment_trace.json (including model/base URL and idea-lock evidence), and final_report.md. The host creates score.json after native exit by running the frozen evaluate.py. CRITICAL: Checkpoints MUST be saved directly to /workspace/checkpoints/ as config-42-0.pkl ... config-42-4.pkl. Do NOT put them in subdirectories."
REF = "Do not use unrelated benchmarks, toy environments, placeholder results, synthetic checkpoints, fallback scores, or outputs from previous topics. Do not modify evaluate.py or the Model class name. The contract file is: {contract_file}"
METHOD_OWNERSHIP = "The framework owns the hypothesis, algorithm family, feature representation, architecture, hyperparameters, experiment sequence, comparison, and selected method."
'''


def build_ai_researcher_payload(topic_root: Path, contract_file: Path) -> dict[str, object]:
    return {
        "instance_id": TOPIC_ID,
        "target": "Topic 2 reinforcement-learning task",
        "title": "Topic 2: Reinforcement-Learning Reward Optimization",
        "authors": ["Project-local custom benchmark"],
        "year": 2026,
        "url": "https://github.com/facebookresearch/MLGym",
        "abstract": "A local benchmark configuration for Topic 2 with frozen starter code, a protected evaluator, and normalized reward score reporting.",
        "venue": "Local Benchmark",
        "topic": "benchmark_execution",
        "field": "reinforcement_learning",
        "source_papers": [],
        "dataset_root": str(topic_root),
        "contract_file": str(contract_file),
        "result_fields": RESULT_FIELDS,
        "task1": "Before the first experiment, write and lock research_idea.json. Run 2-4 materially different framework-chosen experiments, train real checkpoints, and deliver exactly five checkpoints plus config.yaml and src/.",
        "task2": "Own the hypothesis, method choice, experiment design, comparison, and final selection. The host creates score.json after native exit by running the frozen evaluate.py.",
    }


def build_dr_claw_brief(topic_root: Path, contract_file: Path) -> dict[str, object]:
    return {
        "project_name": TOPIC_ID,
        "project_type": "benchmark_task",
        "objective": "Improve the official Average Reward of MountainCarContinuous-v0.",
        "dataset": {
            "name": TOPIC_LABEL,
            "root": str(topic_root),
        },
        "contract_file": str(contract_file),
        "result_fields": RESULT_FIELDS,
        "deliverables": [
            "research_idea.json",
            "experiment_trace.json",
            "final_report.md",
            "checkpoints",
            "config.yaml",
            "src",
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
                "title": "Complete the Topic 2 native research workflow",
                "goal": "Write the pre-experiment idea, choose and run 2-4 materially different experiments, train real checkpoints, select one result, and deliver the required framework-authored artifacts.",
            }
        ],
    }


def build_autoresearchclaw_config(
    repo_root: Path,
    topic_root: Path,
    contract_file: Path,
    provider_base_url: str,
    primary_model: str,
    gpu_required: bool = True,
) -> str:
    _is_kimi = primary_model.startswith("kimi-")
    if _is_kimi:
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
  acp:
    agent: "codex"
    cwd: "/workspace"
    base_url: "{provider_base_url}"
    api_key_env: "OPENAI_API_KEY"
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
  dataset_root: "{topic_root}"
  contract_file: "{workspace_contract_file}"

{llm_block}
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
      This is the Topic 2 reinforcement-learning contract.
      Before any experiment or generated experiment code, write and lock a
      substantive root-level research_idea.json. Keep the idea method-free:
      the framework must choose the hypothesis and method.
    experiment_design: >-
      Stay inside Topic 2 only. Use the frozen starter code at
      /workspace/src and the read-only evaluator. Design 2-4 materially
      different experiments chosen by the framework, with no host prescribed
      algorithm family, representation, architecture, hyperparameters, or
      sequence. CRITICAL: Save checkpoints DIRECTLY to /workspace/checkpoints/
      as config-42-0.pkl through config-42-4.pkl. Do NOT use subdirectories.
    code_generation: >-
      Generate only the Topic 2 deliverables. Read the contract
      and starter code, train real checkpoints, and write root-level
      research_idea.json, experiment_trace.json, and final_report.md. Deliver
      exactly five checkpoints under checkpoints/ plus config.yaml and src/.
      CRITICAL: Save checkpoints DIRECTLY to /workspace/checkpoints/ as
      config-42-0.pkl through config-42-4.pkl. Do NOT use subdirectories.
      Do not modify evaluate.py or the Model class name. Record the injected
      model and base URL. The generated experiment entrypoint must be a
      runnable main.py with an `if __name__ == "__main__":` block that trains
      the model and reports at least one numeric metric through the injected
      experiment_harness (get_harness().report_metric(...) and finalize());
      do not generate model-definition-only main.py files.

evaluation:
  result_fields:
    - "score"
    - "reward_std"
    - "score_source"
    - "score_artifact"

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
    gpu_required: {str(gpu_required).lower()}
    allowed_imports: [math, json, pathlib, numpy, jax, gymnax, flax, optax, tqdm, tensorflow_probability, dotmap, yaml, pickle]
"""


def render_autoresearchclaw_topic() -> str:
    return """Topic 2: reinforcement-learning reward optimization

Execute the Topic 2 contract in
/workspace/automation/topic2_contract.md using the frozen
starter code at /workspace/src and the read-only evaluator at
/workspace/evaluate.py. The task is MountainCarContinuous-v0. You may modify
src/train.py, src/policy.py, src/networks.py, src/helpers.py, and
src/config.yaml, and add new code under src/. Before the first experiment,
write and lock research_idea.json. Design and run 2-4 bounded, materially
different experiments under the supplied execution budget, then select one
result. The framework owns the hypothesis, method choice, experiment design,
comparison, and final selection; no algorithm family, feature representation,
architecture, hyperparameters, baseline, or experiment sequence is prescribed.
Deliver exactly five checkpoints under checkpoints/ plus config.yaml and src/,
and root-level research_idea.json, experiment_trace.json, and final_report.md.
CRITICAL: Save checkpoints DIRECTLY to /workspace/checkpoints/ as
config-42-0.pkl ... config-42-4.pkl. Do NOT use subdirectories.
Record the injected model and API base URL in the trace. The host creates
score.json after the native run exits by running the frozen evaluate.py.
"""


def generate_native_inputs(
    repo_root: Path,
    output_root: Path,
    topic_root: Path,
    contract_file: Path,
    provider_base_url: str = "https://api.openai.com/v1",
    primary_model: str = "gpt-5.4",
    gpu_required: bool = True,
) -> dict[str, object]:
    output_root.mkdir(parents=True, exist_ok=True)

    shared_summary = render_shared_summary(topic_root, contract_file)
    authoritative_contract = (
        contract_file.read_text(encoding="utf-8")
        if contract_file.exists()
        else f"# Topic 2 Contract Pointer\n\nSource contract file: {contract_file}\n"
    )
    framework_brief = render_framework_brief(topic_root, contract_file)
    ai_scientist_topic = render_ai_scientist_topic(topic_root, contract_file)

    text_files = {
        "docs/topic2_summary.md": shared_summary,
        "automation/topic2_contract.md": authoritative_contract,
        "automation/topic2_execution_budget.md": (
            (REPO_ROOT / "automation" / "topic2_execution_budget.md").read_text(encoding="utf-8")
        ),
        "automation/scripts/run_topic2_host_score.py": (
            (REPO_ROOT / "automation" / "scripts" / "run_topic2_host_score.py").read_text(encoding="utf-8")
        ),
        "AI-Researcher/benchmark/process/dataset_candidate/topic2/metaprompt.py": render_ai_researcher_metaprompt(
            topic_root, contract_file
        ),
        "AI-Scientist-v2/ai_scientist/ideas/topic2_topic.md": ai_scientist_topic,
        "AI-Scientist-v2/ai_scientist/ideas/my_research_topic.md": ai_scientist_topic,
        "Auto-claude-code-research-in-sleep/TOPIC2_BRIEF.md": framework_brief,
        "Auto-claude-code-research-in-sleep/.aris-codex-project/TOPIC2_BRIEF.md": framework_brief,
        "AutoResearchClaw/topic.txt": render_autoresearchclaw_topic(),
        "AutoResearchClaw/config.arc.yaml": build_autoresearchclaw_config(
            repo_root, topic_root, contract_file, provider_base_url, primary_model, gpu_required
        ),
        "DeepScientist/DEEPSCIENTIST_BRIEF.md": framework_brief,
        "EvoScientist/EVOSCIENTIST_BRIEF.md": framework_brief,
        "EvoScientist/topic2_start_message.txt": "Start Topic 2. Read @EVOSCIENTIST_BRIEF.md, @docs/topic2_summary.md, and @automation/topic2_execution_budget.md first. IMPORTANT: This is a reinforcement-learning task: improve the Average Reward of MountainCarContinuous-v0 and deliver exactly five checkpoints. CRITICAL: Save checkpoints DIRECTLY to /workspace/checkpoints/ as config-42-0.pkl ... config-42-4.pkl. Do NOT use subdirectories.\n",
    }
    json_files = {
        "AI-Researcher/benchmark/final/topic2/topic2.json": build_ai_researcher_payload(
            topic_root, contract_file
        ),
        "dr-claw/research_brief.json": build_dr_claw_brief(topic_root, contract_file),
        "dr-claw/tasks.json": build_dr_claw_tasks(),
    }

    manifest_files: dict[str, dict[str, str]] = {}
    for rel_path, content in text_files.items():
        write_text(output_root / rel_path, content)
        manifest_files[rel_path] = {"kind": "text"}
    for rel_path, payload in json_files.items():
        write_json(output_root / rel_path, payload)
        manifest_files[rel_path] = {"kind": "json"}

    # Copy starter code + protected evaluator into the generated input root so
    # the wrapper can place them into each fresh workspace.
    starter_dst = output_root / "starter" / "src"
    starter_src = topic_root / "src"
    if starter_src.is_dir():
        shutil.copytree(starter_src, starter_dst, dirs_exist_ok=True)
        for rel in sorted(str(p.relative_to(starter_dst)) for p in starter_dst.rglob("*") if p.is_file()):
            manifest_files[f"starter/src/{rel}"] = {"kind": "text"}
    protected_dst = output_root / "protected"
    protected_dst.mkdir(parents=True, exist_ok=True)
    for name in ("evaluate.py", "evaluate.py.sha256"):
        src = topic_root / "protected" / name
        if src.is_file():
            shutil.copy2(src, protected_dst / name)
            manifest_files[f"protected/{name}"] = {"kind": "text"}

    manifest = {
        "topic": {
            "id": TOPIC_ID,
            "label": TOPIC_LABEL,
            "topic_root": str(topic_root),
            "contract_file": str(contract_file),
        },
        "result_fields": RESULT_FIELDS,
        "files": manifest_files,
    }
    write_json(output_root / "topic2_manifest.json", manifest)
    return manifest


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate Topic 2 native framework inputs.")
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--dataset-root", type=Path, default=DEFAULT_TOPIC_ROOT)
    parser.add_argument("--contract-file", type=Path, default=DEFAULT_CONTRACT_FILE)
    parser.add_argument("--provider-base-url", default="https://api.openai.com/v1")
    parser.add_argument("--primary-model", default="gpt-5.4")
    parser.add_argument("--gpu-required", action="store_true", default=True)
    parser.add_argument("--no-gpu-required", action="store_false", dest="gpu_required")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    generate_native_inputs(
        repo_root=REPO_ROOT,
        output_root=args.output_root,
        topic_root=args.dataset_root,
        contract_file=args.contract_file,
        provider_base_url=args.provider_base_url,
        primary_model=args.primary_model,
        gpu_required=args.gpu_required,
    )
    print(
        json.dumps(
            {
                "topic": TOPIC_ID,
                "output_root": str(args.output_root),
                "manifest": str(args.output_root / "topic2_manifest.json"),
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())