# Repository Boundary

This document defines what belongs in `ResearchClawEval` and what does not.

## Purpose

`ResearchClawEval` is a multi-framework evaluation and adaptation repository.

It is responsible for:

- shared task contracts
- shared automation and orchestration
- framework-specific evaluation adapters
- validators and reproducibility wrappers
- community-facing integration assets for `BabyLM` and `GAVE2`

It is not responsible for storing every local run artifact generated inside each framework checkout.

## Working Model

The repository has two layers:

1. Root control layer
   - `automation/`
   - `framework_evaluator/`
   - `real_eval/`
   - `docs/`
2. Framework adaptation layer
   - local framework directories with patches, configs, Dockerfiles, prompts, run scripts, and tests required by this project

The framework directories are used here as evaluation forks, not as archival stores for transient runtime outputs.

## Must Commit

Commit files that define or protect the evaluation workflow:

- orchestration code
- project registries and task configs
- validators
- wrapper scripts
- framework-specific Dockerfiles
- framework-specific run scripts
- task/topic briefs for `BabyLM` and `GAVE2`
- framework patches required for the evaluation
- tests that cover those patches
- `.gitignore` rules that enforce the boundary
- maintainer docs that explain the integration

Examples:

- `automation/projects.yaml`
- `automation/scripts/run_framework_babylm_proxy.py`
- `real_eval/scripts/*.sh`
- `AI-Scientist-v2/bfts_config.min_e2e.yaml`
- `AI-Researcher/run_tiny_cls_local_e2e.py`
- `AutoResearchClaw/config.project4.yaml`
- `dr-claw/scripts/run_minimal_e2e.mjs`

## Must Ignore

Ignore files that only capture local runtime state or one-off execution output:

- `.codex-*`
- `.claude/`
- `.aris*`
- `.runtime-home/`
- `.deepscientist_home/`
- `runs/`
- `logs/`
- `results/`
- `review-stage/`
- `idea-stage/`
- `workspaces/`
- `workplace_paper/`
- generated PDFs
- LaTeX build byproducts like `.aux`, `.bbl`, `.blg`, `.out`, `.log`
- sqlite databases
- pid files
- shell snapshots
- local `env` and secrets

These files may be required during execution, and validators may inspect them after a run, but they still do not belong in Git.

## Framework-Level Guidance

### AI-Researcher

Keep:

- benchmark definitions used by this project
- dataset candidate prompts and helpers
- evaluation Dockerfiles
- paper-writing templates and integration code
- local evaluation entrypoints

Ignore:

- generated workplaces
- generated target sections
- generated LaTeX binaries and reports

### AI-Scientist-v2

Keep:

- `BabyLM` and `GAVE2` topic files
- evaluation configs
- runtime Dockerfile
- evaluation scripts
- regression tests
- code changes required for the evaluation fork

Ignore:

- local `runs/`
- local `experiments/`
- local scratch docs unrelated to the maintained evaluation topics

### Auto-claude-code-research-in-sleep

Keep:

- runtime Dockerfile
- maintained minimal pipeline scripts
- integration patches in `tools/`

Ignore:

- generated paper directories
- generated manifests
- generated review outputs
- local project workspaces

### AutoResearchClaw

Keep:

- `project4` configs
- runtime Dockerfile
- integration scripts
- tests covering the transport/runtime changes

Ignore:

- local Codex state
- local agent briefs and one-off topic scratch files unless promoted into maintained task docs

### DeepScientist

Keep:

- runtime Dockerfile
- maintained task briefs used by the evaluation
- source changes required for integration

Ignore:

- local runtime homes
- local fixture builders for obsolete toy workflows unless they become part of a maintained test path

### EvoScientist

Keep:

- evaluation Dockerfiles
- maintained `GAVE2` and `BabyLM` prompts/briefs
- source changes required for integration

Ignore:

- local verification workspaces
- local logs
- framework analysis notes that are not part of the maintained interface

### dr-claw

Keep:

- runtime Dockerfile
- maintained evaluation scripts
- config/code required to support the evaluation path

Ignore:

- `.runtime-home/`
- generated per-project runtime trees
- local project `research_brief.json` state unless intentionally promoted into a reusable template or spec

## Review Rule

Before committing a new file, ask:

1. Is this file required to reproduce the evaluation setup?
2. Would another contributor need this file before running the framework?
3. Is this file a stable adapter, config, or test rather than a local execution trace?

If the answer is `no` to all three, it probably should not be committed.

## Community Goal

Because this repository is intended to become a community project, the bias should be:

- keep stable integration assets
- drop local execution residue
- make the evaluation path legible to outsiders

The repository should explain how to run the frameworks, not preserve every run they ever produced.
