# Repository Layout

This repository should be treated as the evaluation control plane, not as a dump of every local checkout, dataset, paper, and run artifact.

## Intended Source Layout

- `real_eval/`: benchmark lane for formal topic x framework x mode evaluation. This owns registries, configs, wrappers, validators, serial runners, and benchmark tests.
- `automation/`: headless automation lane for repair loops, runtime state, systemd dispatch, and project-level smoke/e2e orchestration.
- `framework_evaluator/`: shared evaluator code that can be reused by `real_eval/` and `automation/`.
- `tasks/`: task and topic input definitions that are part of the benchmark contract.
- `docs/`: maintainer documentation, topic specs, evaluation model notes, and migration plans.
- `Report/`: human-facing reports and investigation notes. This may later be renamed to `reports/`, but keep the current path until references are migrated.
- `external/`: optional local workspace for ignored external assets. It is not required by current scripts yet.

## Local External Assets

The following directories currently live at repository root for compatibility with existing scripts, but they are local assets rather than root source modules:

- Framework checkouts: `AI-Researcher/`, `AI-Scientist-v2/`, `Auto-claude-code-research-in-sleep/`, `AutoResearchClaw/`, `DeepScientist/`, `dr-claw/`, `EvoScientist/`.
- Datasets: `BabyLM-2026-Strict-Small/`, `GAVE2_preliminary/`, `data/`.
- Paper collections: `collected_paper_pdfs_20260603/`, `collected_paper_pdfs_20260603_by_topic/`, `论文收集/`.
- Historical workspaces and bundles: `babylm_agent_workspaces_*/`, `archive/`, `p6_home/`, `p6_runtime_home/`, `codex_runs/`.

Long term, these should move under `external/` or outside the repository checkout, with compatibility provided by registry paths or environment variables. Do not move them in one large step while scripts still assume root-relative locations.

The registry records path override variables for this migration:

- Framework-specific roots use each framework's `source_env` in `real_eval/registry/frameworks.json`.
- Dataset-specific roots use each topic's `dataset_env` in `real_eval/registry/topics.json`.
- `RESEARCHCLAWEVAL_FRAMEWORKS_ROOT` can point to a directory containing all seven framework checkout directories.
- `RESEARCHCLAWEVAL_DATASETS_ROOT` can point to a directory containing dataset directories such as `BabyLM-2026-Strict-Small/` and `GAVE2_preliminary/`.

To inspect resolved paths without running any evaluation:

```bash
python3 real_eval/scripts/registry_paths.py
```

The GAVE2 common helpers and full-run wrappers already consume this path metadata for dataset roots and framework source roots. Current default paths still resolve to the repository root layout, so existing experiments do not need new environment variables.

Example future external layout run configuration:

```bash
export RESEARCHCLAWEVAL_FRAMEWORKS_ROOT="$PWD/external/frameworks"
export RESEARCHCLAWEVAL_DATASETS_ROOT="$PWD/external/datasets"
python3 real_eval/scripts/registry_paths.py
```

## Generated Runtime State

These paths are generated and should stay ignored:

- `real_eval/runs/`
- `real_eval/run_checks/`
- `real_eval/systemd_runs/`
- `automation/runs/`
- `automation/state/*.json`
- `automation/state/projects/*.json`
- `automation/env/`

`real_eval/runs/` is currently the largest local footprint. Keep summaries and status files when they are useful for reports, but avoid treating full run directories as source.

## Migration Order

1. Keep current runtime paths working.
2. Document root-level external assets and keep them ignored.
3. Add registry or environment-variable support for alternate framework and dataset roots.
4. Migrate one asset class at a time into `external/` or outside the repo.
5. Remove compatibility root paths only after tests and dry-runs pass.

This order avoids breaking long-running experiments and keeps each change reviewable.
