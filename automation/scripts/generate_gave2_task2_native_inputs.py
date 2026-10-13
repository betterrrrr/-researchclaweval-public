#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

SCORE_FORMULA = "0.3*(0.3*Sen+0.3*Spec+0.4*Acc)+0.4*DSC+0.3*(0.5*Cor+0.5*(1-INF))"
DATASET_ROOT = "data/gave2/task2"
VISIBLE_SOURCE = "GAVE2_preliminary"
CONTRACT_FILE = "automation/gave2_task2_contract.md"

SHARED_SUMMARY = f"""# GAVE2 Task 2 Summary

## Goal
Optimize GAVE2 Task 2 official score for cross-modal retinal artery-vein segmentation.

## Official task framing
- Input per case:
  - 1 CFP image
  - 1 early-phase FFA image (`FFA_A`)
  - 1 late-phase / arteriovenous-filling FFA image (`FFA_AV`)
- Prediction target on CFP:
  - artery mask
  - vein mask
  - overlap mask

## Official split contract
- 50 train
- 50 preliminary leaderboard
- 50 final blind evaluation

## Local repository status
- Standardized local path: `{DATASET_ROOT}`
- Current visible local copy comes from `{VISIBLE_SOURCE}`
- Visible files confirmed locally:
  - `training/`: 50 CFP + 50 masks + 50 FFA_A + 50 FFA_AV + 50 av + 50 biomarker
  - `validation/`: 50 CFP + 50 masks + 50 FFA_A + 50 FFA_AV
- Therefore this repo currently materializes the train split plus the preliminary visible split.
- The blind final split is part of the challenge contract but is not present as visible files in this checkout.

## Optimization target
- Task 2 is the core task.
- Overall challenge weighting: Task 2 contributes 0.4 to the total score.
- Primary objective: maximize Task 2 official score, not generic novelty.

## Shared references
- Metric spec: `docs/gave2_metric_spec.md`
- Submission spec: `docs/gave2_submission_spec.md`
- Data layout: `docs/gave2_data_layout.md`
"""

METRIC_SPEC = f"""# GAVE2 Task 2 Metric Spec

## Official formula
`Score_task2 = {SCORE_FORMULA}`

## Components
- `Sen`: sensitivity
- `Spec`: specificity
- `Acc`: accuracy
- `DSC`: Dice similarity coefficient
- `Cor`: artery-vein correctness / consistency term from challenge evaluation
- `INF`: incorrectness / infeasible-topology penalty term from challenge evaluation

## Weighting breakdown
- Classification-quality block:
  - `0.3 * (0.3*Sen + 0.3*Spec + 0.4*Acc)`
- Segmentation-quality block:
  - `0.4 * DSC`
- Structure / AV-consistency block:
  - `0.3 * (0.5*Cor + 0.5*(1-INF))`

## Practical implications
- Optimizing Dice alone is insufficient.
- Thin-vessel continuity, crossings, and artery/vein identity matter.
- A model with high local mask overlap can still lose score through AV confusion or topology breaks.

## Local implementation note
Any local evaluator should at minimum log these six components separately before aggregating the final score.
"""

SUBMISSION_SPEC = f"""# GAVE2 Task 2 Submission Spec

## Required output per case
For each CFP case, generate:
- artery mask
- vein mask
- overlap mask

## Packaging target
Produce a submission-ready folder that can be transformed into the official upload package without extra manual relabeling.

## Naming and structure policy used in this repo
Until the official organizer packaging script is added, keep outputs under a deterministic structure such as:

```text
submission/
  case_id/
    artery.png
    vein.png
    overlap.png
```

or an equivalent flat structure documented by the framework run.

## Hard requirements
- every required case must have a prediction
- outputs must be reproducible from a single inference command
- any post-processing used for submission must be scripted
- do not mix training labels into leaderboard/final prediction folders

## Validation checklist before upload
- all required case IDs present
- output image sizes match CFP target canvas
- binary / label encoding is consistent across all cases
- no empty submission folder
- final run records checkpoint path, inference command, and output root

## Challenge-score alignment
A valid submission is not enough. The preferred packaging preserves artery / vein separation and overlap consistency because the official score is `{SCORE_FORMULA}`.
"""

DATA_LAYOUT = f"""# GAVE2 Data Layout

## Canonical standardized path
`{DATASET_ROOT}`

This path is the normalized dataset root used by the new GAVE2 Task 2 input pack.
In this checkout it points to the visible dataset source `{VISIBLE_SOURCE}`.

## Visible local tree
```text
training/
  images/      # 50 CFP images
  masks/       # 50 field-of-view masks
  FFA_A/       # 50 early-phase FFA images
  FFA_AV/      # 50 late-phase / AV-filling FFA images
  av/          # 50 artery-vein labels
  biomarker/   # 50 biomarker txt files

validation/
  images/      # 50 CFP images
  masks/       # 50 field-of-view masks
  FFA_A/       # 50 early-phase FFA images
  FFA_AV/      # 50 late-phase / AV-filling FFA images
```

## Case ID convention
- Current visible cases use `g_001` ... `g_100` style IDs.
- Training split: `g_001` ... `g_050`
- Preliminary visible split: `g_051` ... `g_100`

## Mapping assumptions used in the input pack
- CFP image basename is the primary case key.
- `images/`, `FFA_A/`, and `FFA_AV/` are matched by identical case ID stem.
- Training supervision for artery / vein / overlap is expected from `training/av/`.
- `training/masks/` is treated as field-of-view / valid-region support unless the baseline repo documents otherwise.

## Caveat
The challenge contract includes a blind final split of 50 cases, but those files are not visible in this repository snapshot. The input pack therefore references the official 150-case task contract while documenting that the visible local tree currently exposes 100 cases.
"""

CONTRACT = f"""# GAVE2 Task 2 Runtime Contract

## Topic
- Topic label: `GAVE2-Task2`
- Dataset root: `{DATASET_ROOT}`
- Visible source root: `{VISIBLE_SOURCE}`
- Contract file: `{CONTRACT_FILE}`

## Objective
Optimize the official GAVE2 Task 2 score for CFP + early-phase FFA + late-phase FFA multimodal artery-vein segmentation.

## Shared bottom files
- `docs/gave2_task2_summary.md`
- `docs/gave2_metric_spec.md`
- `docs/gave2_submission_spec.md`
- `docs/gave2_data_layout.md`

## Framework-native entry files
- `DeepScientist/DEEPSCIENTIST_BRIEF.md`
- `Auto-claude-code-research-in-sleep/RESEARCH_BRIEF.md`
- `AI-Researcher/benchmark/final/medical_image_analysis/gave2_task2_multimodal_av_segmentation.json`
- `AI-Scientist-v2/ai_scientist/ideas/gave2_task2_topic.md`
- `AutoResearchClaw/config.arc.yaml`
- `AutoResearchClaw/topic.txt`
- `dr-claw/research_brief.json`
- `dr-claw/tasks.json`
- `EvoScientist/EVOSCIENTIST_BRIEF.md`
- `EvoScientist/gave2_task2_start_message.txt`

## Scope guard
- do not collapse back to BabyLM proxy harnesses
- do not rewrite this task into single-modality Task 1 only
- do not prioritize paper polish over submission-ready masks
- keep all framework inputs aligned to the same official score and split contract
"""

DEEPSCIENTIST_BRIEF = f"""# Project
GAVE2 Task 2: Cross-Modal FFA-Guided Retinal Artery-Vein Segmentation

# Research Goal
Develop a submission-oriented method for GAVE2 Task 2.
Use CFP together with paired early-phase and late-phase FFA to improve retinal artery-vein segmentation performance on CFP.
Optimize the official challenge score rather than generic paper novelty.

# Problem Definition
Input for each case:
- 1 color fundus photograph (CFP)
- 1 early-phase FFA image
- 1 late-phase / arteriovenous-filling FFA image

Prediction target:
- artery mask
- vein mask
- overlap mask
on the CFP image

# Dataset
- Total cases: 150
- Train: 50
- Preliminary leaderboard split: 50
- Final blind split: 50
- Standardized local dataset root: {DATASET_ROOT}
- Visible local copy in this repo: {VISIBLE_SOURCE}

# Official Metric
Score_task2 = {SCORE_FORMULA}

# Success Criterion
Primary success:
- maximize official Task 2 score
Secondary success:
- stable local validation
- reproducible inference pipeline
- submission-ready predictions

# Constraints
- Publicly available data and public pretrained models are allowed
- Do not drift to Task 1-only single-modality design
- Do not drift to paper-writing-first behavior
- Prioritize challenge submission quality, robustness, and reproducibility
- Every case must have a prediction

# Required Deliverables
- best model checkpoint
- train script
- inference script
- local evaluation script
- submission folder
- concise method summary
- ablation summary

# Suggested Work Plan
1. audit data and modality alignment
2. build a strong CFP-only baseline
3. add early/late FFA fusion
4. improve topology preservation
5. align local validation with official metric
6. generate submission outputs

# Baseline Links
- ./baseline_repo
- ./starter_code

# Paper / Reference Sources
- ./docs/gave2_task2_summary.md
- ./docs/gave2_metric_spec.md
- ./docs/gave2_submission_spec.md
- ./docs/gave2_data_layout.md
- ./refs/gave2_original_description.pdf

# Local Paths
- dataset root: ./data/gave2/task2
- workspace root: ./workspace
- outputs root: ./outputs/deepscientist_gave2_task2

# Anti-Drift Notes
Do not broaden the objective into a generic multimodal ophthalmology project.
Do not spend the main budget on literature-only surveying.
The task is to produce a high-scoring, reproducible challenge submission.
"""

ARIS_BRIEF = f"""# Problem
GAVE2 Task 2 asks for cross-modal retinal artery-vein segmentation.
Each case contains a CFP image plus paired early-phase and late-phase FFA images.
The target is artery / vein / overlap segmentation on the CFP image.

# Primary Objective
Maximize the official GAVE2 Task 2 score on the challenge leaderboard.

# Scope
In scope:
- multimodal segmentation for Task 2
- training, validation, inference, ablation
- submission packaging
- concise technical report

Out of scope:
- Task 1-only benchmarking as the main goal
- Task 3 biomarker quantification as the main goal
- full paper-writing workflow unless needed as a byproduct

# Official Dataset
- 150 total paired cases
- 50 train
- 50 preliminary leaderboard cases
- 50 final blind cases
- standardized local dataset root: {DATASET_ROOT}

# Modalities
- CFP
- FFA early phase
- FFA late / arteriovenous filling phase

# Output
For each CFP image, produce:
- artery mask
- vein mask
- overlap mask

# Official Metric
Score_task2 = {SCORE_FORMULA}

# Hard Constraints
- optimize for challenge score
- public data allowed
- every case must have a valid output
- preserve topology as well as pixel accuracy
- keep the pipeline reproducible
- keep method complexity proportional to dataset size

# Expected Deliverables
- code in runnable state
- trained checkpoints
- local validation results
- final submission folder
- short method note
- error analysis with 5-10 representative cases

# Available Assets
- dataset: ./data/gave2/task2
- baseline repo: ./baseline_repo
- metric spec: ./docs/gave2_metric_spec.md
- submission spec: ./docs/gave2_submission_spec.md
- data layout: ./docs/gave2_data_layout.md
- original challenge pdf: ./refs/gave2_original_description.pdf

# Recommended ARIS Workflow
1. plan a narrow attack on Task 2
2. inspect data consistency and alignment
3. implement a strong CFP-only baseline
4. add multimodal fusion and compare variants
5. run adversarial review on failure modes
6. refine based on topology and classification errors
7. prepare submission artifacts

# Failure Modes To Watch
- modality misalignment
- overfitting due to only 50 training cases
- artery/vein confusion at crossings
- broken vessel topology
- strong local Dice but weak official composite score

# Final Standard
A run is only considered complete if it produces submission-ready predictions and a reproducible inference command.
"""

AI_RESEARCHER_INSTANCE = {
    "instance_id": "gave2_task2_multimodal_av_segmentation",
    "target": "GAVE2 Task 2 multimodal retinal artery-vein segmentation",
    "title": "GAVE2 Task 2: Cross-Modal FFA-Guided Retinal Artery-Vein Segmentation",
    "authors": ["Project-local custom benchmark"],
    "year": 2026,
    "url": "http://arxiv.org/abs/2501.00001v1",
    "abstract": "A local benchmark for GAVE2 Task 2: use paired CFP and early/late-phase FFA to improve retinal artery-vein segmentation on CFP.",
    "venue": "Local Benchmark",
    "venue_source": "Project-local",
    "venue_lookup_time": "2026-06-10T00:00:00",
    "citations": 0,
    "topic": "segmentation",
    "field": "medical_image_analysis",
    "source_papers": [
        {
            "reference": "Phase-Order Distillation for Retinal AV Segmentation",
            "usage": "Use as a reference for multimodal distillation and topology-aware loss design."
        },
        {
            "reference": "U-Net: Convolutional Networks for Biomedical Image Segmentation",
            "usage": "Use as a strong segmentation baseline architecture."
        },
        {
            "reference": "Attention U-Net: Learning Where to Look for the Pancreas",
            "usage": "Use attention gating to improve feature fusion across modalities."
        },
        {
            "reference": "Squeeze-and-Excitation Networks",
            "usage": "Use channel recalibration to emphasize modality-specific features."
        },
        {
            "reference": "Dice Loss for Data Imbalanced Medical Image Segmentation",
            "usage": "Use Dice-based losses for small-vessel segmentation."
        },
    ],
    "task1": "Research topic: On the GAVE2 Task 2 dataset, propose and test one multimodal improvement over a CFP-only artery-vein segmentation baseline using paired early-phase and late-phase FFA. The improvement must come from cross-modal fusion, distillation, or topology-aware design. Build a reproducible training pipeline, run experiments, compare baseline and improved results, save metrics and submission masks, and write a concise technical report. The official composite score must be tracked throughout.",
    "task2": "I have some multimodal retinal segmentation references. Please propose one small but testable improvement for artery-vein segmentation on CFP using paired FFA, implement it quickly, run a minimal experiment, analyze results, and write a concise technical report. Use the official challenge metric."
}

AI_SCIENTIST_TOPIC = f"""# Title
GAVE2 Task 2: Cross-Modal FFA-Guided Retinal Artery-Vein Segmentation in Color Fundus Photography

# Keywords
retinal artery-vein segmentation, multimodal medical imaging, color fundus photography, fluorescein angiography, topology-aware segmentation, ophthalmic image analysis

# TL;DR
Develop a submission-oriented multimodal segmentation method for GAVE2 Task 2. Use CFP plus early-phase and late-phase FFA to improve artery-vein segmentation on CFP, and optimize the official challenge score.

# Abstract
This project targets GAVE2 Task 2, a multimodal retinal artery-vein segmentation task. Each case contains one CFP image and two FFA images acquired at early and late perfusion phases. The model must predict artery, vein, and overlap masks on the CFP image. The main objective is to maximize the official composite score, which combines segmentation quality, artery-vein classification quality, and topology preservation. The project should prioritize challenge performance, reproducibility, and submission readiness rather than broad scientific novelty.

# Concrete Goal
Produce a robust method that:
1. learns from CFP and paired FFA jointly,
2. improves artery-vein discrimination,
3. preserves vascular topology,
4. outputs submission-ready predictions.

# Dataset Summary
- 150 cases total
- 50 train
- 50 preliminary leaderboard
- 50 final blind evaluation
- standardized local dataset root: {DATASET_ROOT}

# Official Metric
Score_task2 = {SCORE_FORMULA}

# Available Resources
- dataset: ./data/gave2/task2
- baseline code: ./baseline_repo
- metric spec: ./docs/gave2_metric_spec.md
- submission spec: ./docs/gave2_submission_spec.md
- data layout: ./docs/gave2_data_layout.md
- challenge description: ./refs/gave2_original_description.pdf

# Constraints
- public data allowed
- every case needs a prediction
- focus on Task 2 only
- do not broaden into a generic ophthalmology survey
- reproducible inference is mandatory

# Expected Outputs
- best method
- training and inference commands
- ablations
- final submission package
- concise report of design choices and failure cases
"""

AUTORESEARCHCLAW_TOPIC = "Solve GAVE2 Task 2 by building a submission-oriented multimodal retinal artery-vein segmentation system using CFP, early-phase FFA, and late-phase FFA. Optimize the official challenge score, preserve vessel topology, generate submission-ready masks for every case, and deliver reproducible training/inference code plus a concise technical report.\n"

AUTORESEARCHCLAW_CONFIG = f"""project:
  name: "gave2-task2"
  output_dir: "./outputs/autoresearchclaw_gave2_task2"

research:
  topic: "GAVE2 Task 2 multimodal retinal artery-vein segmentation with CFP + early/late FFA"
  domains:
    - "medical imaging"
    - "retinal image analysis"
    - "segmentation"
    - "multimodal learning"
    - "ophthalmology"
  daily_paper_count: 10
  quality_threshold: 4.0

execution:
  goal: "challenge_submission"
  mode: "end_to_end"

assets:
  dataset_root: "./data/gave2/task2"
  baseline_repo: "./baseline_repo"
  metric_spec: "./docs/gave2_metric_spec.md"
  submission_spec: "./docs/gave2_submission_spec.md"
  data_layout: "./docs/gave2_data_layout.md"
  challenge_pdf: "./refs/gave2_original_description.pdf"

constraints:
  public_data_allowed: true
  submission_oriented: true
  focus_on_task2_only: true
  require_prediction_for_all_cases: true
  require_reproducibility: true

evaluation:
  primary_metric_name: "official_task2_score"
  primary_metric_formula: "{SCORE_FORMULA}"

deliverables:
  - "best_checkpoint"
  - "train_script"
  - "inference_script"
  - "submission_masks"
  - "ablation_summary"
  - "technical_report"

notes:
  - "Do not turn this into a generic literature-first project."
  - "Prioritize robust multimodal segmentation and leaderboard performance."
  - "Keep complexity appropriate for 50 labeled training cases."
"""

DR_CLAW_BRIEF = {
    "project_name": "gave2-task2",
    "project_type": "benchmark_task",
    "objective": "Maximize the official GAVE2 Task 2 score using CFP + early-phase FFA + late-phase FFA for retinal artery-vein segmentation on CFP.",
    "problem_statement": "This project targets multimodal retinal artery-vein segmentation. Each case includes one CFP image and two paired FFA images. The system must predict artery, vein, and overlap masks on the CFP image and package the outputs for challenge submission.",
    "dataset": {
        "name": "GAVE2 Task 2",
        "root": "./data/gave2/task2",
        "total_cases": 150,
        "splits": {"train": 50, "preliminary": 50, "final": 50},
        "modalities": ["cfp", "ffa_early", "ffa_late"],
        "prediction_target": ["artery_mask", "vein_mask", "overlap_mask"],
    },
    "metrics": {
        "primary": "official_task2_score",
        "formula": SCORE_FORMULA,
        "components": ["Sen", "Spec", "Acc", "DSC", "Cor", "INF"],
    },
    "constraints": {
        "public_data_allowed": True,
        "must_predict_every_case": True,
        "focus_on_task2_only": True,
        "submission_oriented": True,
        "reproducibility_required": True,
    },
    "assets": {
        "baseline_repo": "./baseline_repo",
        "metric_spec": "./docs/gave2_metric_spec.md",
        "submission_spec": "./docs/gave2_submission_spec.md",
        "data_layout": "./docs/gave2_data_layout.md",
        "challenge_pdf": "./refs/gave2_original_description.pdf",
    },
    "deliverables": [
        "method_implementation",
        "training_pipeline",
        "inference_pipeline",
        "local_validation_results",
        "submission_package",
        "technical_summary",
    ],
    "anti_drift": [
        "Do not broaden into generic multimodal ophthalmology research.",
        "Do not prioritize paper writing over submission artifacts.",
        "Do not collapse back to a CFP-only baseline as the main solution.",
    ],
}

DR_CLAW_TASKS = {
    "tasks": [
        {"id": "t1_dataset_audit", "title": "Audit dataset structure and modality alignment", "goal": "Verify file layout, naming, case mapping, and image pairing across CFP, early FFA, and late FFA."},
        {"id": "t2_baseline", "title": "Build strong CFP-only baseline", "goal": "Implement or restore a reliable single-modality baseline to quantify the gain from multimodal fusion."},
        {"id": "t3_multimodal_model", "title": "Implement multimodal segmentation variants", "goal": "Add early/late FFA fusion, cross-modal consistency, and feature alignment strategies."},
        {"id": "t4_metric_alignment", "title": "Align local evaluation with official metric", "goal": "Track DSC, Sen, Spec, Acc, Cor, and INF, and compute the official composite score locally."},
        {"id": "t5_error_analysis", "title": "Analyze artery-vein confusion and topology failures", "goal": "Identify recurring failure modes at crossings, thin vessels, low-contrast areas, and discontinuities."},
        {"id": "t6_refinement", "title": "Refine the best multimodal method", "goal": "Improve classification quality and topology while controlling overfitting on the small training split."},
        {"id": "t7_submission_packaging", "title": "Prepare submission-ready outputs", "goal": "Generate valid predictions for all required cases and package them in the required submission structure."},
        {"id": "t8_report", "title": "Write concise technical summary", "goal": "Summarize method, ablations, strengths, limitations, and reproducibility instructions."},
    ]
}

EVOSCIENTIST_BRIEF = f"""# Mission
Complete GAVE2 Task 2 as a submission-oriented multimodal segmentation project.

# Core Objective
Use CFP together with early-phase and late-phase FFA to improve retinal artery-vein segmentation on the CFP image and maximize the official Task 2 score.

# Inputs Per Case
- CFP
- FFA early phase
- FFA late / arteriovenous filling phase

# Required Predictions
- artery mask
- vein mask
- overlap mask

# Dataset Split
- train: 50
- preliminary leaderboard: 50
- final blind evaluation: 50
- standardized local dataset root: {DATASET_ROOT}

# Official Metric
Score_task2 = {SCORE_FORMULA}

# Available Files
- dataset: ./data/gave2/task2
- starting codebase: current workspace root
- metric spec: ./docs/gave2_metric_spec.md
- submission spec: ./docs/gave2_submission_spec.md
- data layout: ./docs/gave2_data_layout.md
- challenge pdf: ./refs/gave2_original_description.pdf

# Operational Priorities
1. correctness of data pairing
2. strong single-modality baseline
3. effective multimodal fusion
4. topology preservation
5. official-score alignment
6. submission readiness

# Constraints
- public data allowed
- every case must have a prediction
- do not drift into open-ended literature exploration
- do not prioritize paper polish over executable artifacts
- focus on Task 2 only

# Deliverables
- best checkpoint
- train command
- inference command
- local score report
- submission package
- concise technical note

# Known Risks
- overfitting due to small training set
- artery/vein confusion near crossings
- weak topology despite good pixel metrics
- modality mismatch or registration inconsistency

# Completion Standard
The project is not complete until it produces valid submission artifacts and reproducible instructions.
"""

EVOSCIENTIST_START = "Start a submission-oriented research workflow for GAVE2 Task 2. Read @EVOSCIENTIST_BRIEF.md, @docs/gave2_metric_spec.md, and @docs/gave2_submission_spec.md first. Use the current workspace root as the starting codebase. Prioritize official score optimization, topology preservation, and reproducible submission artifacts over broad literature exploration.\n"

FILES: dict[str, str] = {
    "docs/gave2_task2_summary.md": SHARED_SUMMARY,
    "docs/gave2_metric_spec.md": METRIC_SPEC,
    "docs/gave2_submission_spec.md": SUBMISSION_SPEC,
    "docs/gave2_data_layout.md": DATA_LAYOUT,
    "automation/gave2_task2_contract.md": CONTRACT,
    "DeepScientist/DEEPSCIENTIST_BRIEF.md": DEEPSCIENTIST_BRIEF,
    "Auto-claude-code-research-in-sleep/RESEARCH_BRIEF.md": ARIS_BRIEF,
    "Auto-claude-code-research-in-sleep/.aris-codex-project/RESEARCH_BRIEF.md": ARIS_BRIEF,
    "AI-Scientist-v2/ai_scientist/ideas/gave2_task2_topic.md": AI_SCIENTIST_TOPIC,
    "AI-Scientist-v2/ai_scientist/ideas/my_research_topic.md": AI_SCIENTIST_TOPIC,
    "AutoResearchClaw/topic.txt": AUTORESEARCHCLAW_TOPIC,
    "AutoResearchClaw/config.arc.yaml": AUTORESEARCHCLAW_CONFIG,
    "EvoScientist/EVOSCIENTIST_BRIEF.md": EVOSCIENTIST_BRIEF,
    "EvoScientist/gave2_task2_start_message.txt": EVOSCIENTIST_START,
}

JSON_FILES: dict[str, object] = {
    "AI-Researcher/benchmark/final/medical_image_analysis/gave2_task2_multimodal_av_segmentation.json": AI_RESEARCHER_INSTANCE,
    "dr-claw/research_brief.json": DR_CLAW_BRIEF,
    "dr-claw/tasks.json": DR_CLAW_TASKS,
}


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content.rstrip() + "\n", encoding="utf-8")


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    written: list[str] = []
    for rel, content in FILES.items():
        write_text(REPO_ROOT / rel, content)
        written.append(rel)
    for rel, payload in JSON_FILES.items():
        write_json(REPO_ROOT / rel, payload)
        written.append(rel)

    manifest = {
        "topic_label": "GAVE2-Task2",
        "dataset_root": str(DATASET_ROOT),
        "visible_source": str(VISIBLE_SOURCE),
        "contract_file": str(CONTRACT_FILE),
        "files": sorted(written),
    }
    write_json(REPO_ROOT / "automation/gave2_task2_manifest.json", manifest)
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
