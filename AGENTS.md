# ResearchClawEval Automation Rules

This repository runs a headless automation loop for research-agent frameworks.

## Scope

- This `AGENTS.md` applies to the repository root and all child directories.
- All paths are relative to the repository root unless otherwise specified.
- Use `RESEARCHCLAWEVAL_ROOT` env var for the repo root path, or auto-detect from the script location.

## Topic Contracts

- Topic `topic2` is MountainCar-Continuous.
  - Contract file: `automation/topic2_contract.md`
  - Dataset env: `TOPIC2_DATASET_ROOT`
  - Canonical runner/script/config names include `topic2`.
- Topic `arc_wbe_2026` is ARC-WBE-2026 / ARC White Box Estimation Challenge.
  - Contract file: `automation/arc_wbe_2026_contract.md`
  - Dataset env: `ARC_WBE_2026_DATASET_ROOT`
  - Canonical runner/script/config names include `arc_wbe_2026`.
- Topic `psydefdetect` is PsyDefDetect.
  - Contract file: `automation/psydefdetect_contract.md`
  - Dataset env: `PSYDEFDETECT_DATASET_ROOT`
  - Canonical runner/script/config names include `psydefdetect`.
- Topic `tdc_admet_tox` is TDC-ADMET-Tox.
  - Contract file: `automation/tdc_admet_tox_contract.md`
  - Public dataset env: `TDC_ADMET_TOX_DATASET_ROOT`
  - Canonical runner/script/config names include `tdc_admet_tox`.
- Topic `babylm` is BabyLM-10M.
  - Contract file: `automation/babylm_contract.md`
  - Dataset env: `BABYLM_DATASET_ROOT`
  - Canonical runner/script/config names include `babylm`.
- Topic `mountaincar_continuous` is MountainCar-Continuous.
  - Contract file: `automation/mountaincar_continuous_contract.md`
  - Dataset env: `MOUNTAINCAR_CONTINUOUS_DATASET_ROOT`
  - Canonical runner/script/config names include `mountaincar_continuous`.
- These topics must be treated as strictly separate runtime contracts.
- When the requested/current topic is one topic, do not run other topic's smoke, preflight, input-pack, fullrun, dataset preparation, or validation paths.
- Do not use a successful run from one topic as evidence for another topic.
- Generated per-run `inputs/` may use framework-native filenames, but their contents must match the active topic contract.

## Native Framework Evaluation Integrity

These rules apply to every Topic and every framework-capability evaluation, regardless of model, wrapper name, or topic-specific scorer.

- Before dispatching any framework run, read that framework's repository README and any linked native-run documentation. Record the relevant README/documentation path and use its documented CLI, runner, skill, required environment, and artifact contract; do not infer the launch procedure from a wrapper name alone.
- The framework must be launched through its documented official CLI, runner, skill, or native orchestration entrypoint. The framework itself must own planning, experiment/configuration design, execution, comparison, selection, analysis, and final artifact delivery.
- A generic outer `codex exec` loop that asks Codex to inspect, imitate, repair, or drive a framework is not a native framework run. It must not be used as the full-run research owner, and its experiments, papers, predictions, traces, or scores must not be accepted as native results.
- Generic `codex exec` is allowed for smoke tests, provider/relay connectivity checks, diagnostics, or lifecycle control only. It must not perform the Topic's actual experiments or final research delivery.
- A framework may use `codex exec` as its native full-run executor only when the framework's documented official CLI/skill/runner explicitly delegates the complete workflow to that executor. The framework entrypoint must still own planning, experiment design, execution, comparison, selection, analysis, and final artifact delivery, and runtime evidence must prove that ownership.
- Before accepting a native result, record and verify the actual launch command, the source/documentation defining the native entrypoint, the process/container that executed it, and logs/traces showing that the framework—not the host loop—performed the work.
- If a framework cannot run through its native entrypoint under these rules, mark that Topic/framework/model version `unsupported` or `blocked`. Do not downgrade it to a generic `codex exec` workflow, count its artifacts as native, or include it in a native ranking.
- Retain every run that went through a framework's native full-run flow as evaluation data, regardless of whether it succeeded, failed, timed out, or failed validation. Do not delete, overwrite, clean, truncate, backfill, or reuse its run directory. A repair or retry must use a new run id and a fresh physical run workspace.

Use separate outcome dimensions for every Topic:

- `research_completed`: the native framework completed the Topic contract's required experiments or configurations, compared or selected a final approach, and delivered the framework-authored final report, paper, or other contract-defined final artifact.
- `scored`: the native framework's predictions or other evaluable output were passed to the official Topic scorer and produced the corresponding score artifact.
- `contract_complete`: all Topic-required inputs, outputs, traces, reports, and score artifacts passed that Topic's contract validator.
- `engineering_complete`: the outer wrapper exited normally and wrote a terminal state without lifecycle or cleanup errors.

## Scientific Ideation Independence

- The framework must own the research question refinement, hypothesis, method choice, experiment rationale, comparison, and final selection. The host may define the task question, visible data, split, official metric, compute/time/request budget, experiment-count range, available dependencies, network/safety policy, and output schema only.
- The host and framework prompt must not prescribe an algorithm family, feature representation, model architecture, hyperparameters, experiment sequence, baseline to reproduce, or selected method.
- The framework must write and lock a framework-authored `research_idea.json` before the first experiment.
- Evaluate idea quality separately from the official task score.

## Execution Model

- `smoke` runs are blocking.
- `fullrun` is submitted through Docker and is non-blocking.
- Do not invent new outer `docker run` entrypoints if a validated minimal command already exists.
- Prefer fixing project config or helper scripts before changing the outer command.

## Workspace Mount And Output Isolation

- Fixed framework workspaces under `real_eval/workspaces/<topic_id>/<framework>/` are template sources only. Do not mount a fixed framework workspace into a container as the writable runtime `/workspace`.
- Every evaluation must create and use a fresh physical run workspace under `real_eval/runs/<run_id>/<framework_slug>/workspace`.
- Before launching a framework container, copy the fixed framework workspace into that run workspace, then mount only the run workspace as the container's writable workspace.
- Dataset roots and topic contract files may be mounted into containers only as read-only inputs.
- Framework outputs, logs, reports, submission packages, score artifacts, and run results must be written under the current `REAL_EVAL_RUN_ROOT` or its `workspace/` subtree.
- Do not write evaluation outputs, archives, caches, or generated artifacts into the repository root, fixed framework workspaces, or another framework's run workspace.

## Change Priority

- Prefer the smallest fix that restores the intended automation flow.
- Fix order:
  1. Project config and prompt/render inputs
  2. Helper scripts and validation logic
  3. Outer orchestration command shape
- Do not broaden the runtime contract for one project unless the same change is truly required by the shared automation model.

## Isolation

- Work on only the target project, attempt, and state file for the current automation action.
- Do not opportunistically rewrite unrelated project state, logs, or commands while fixing one project.
- Preserve the configured topic contract. Do not reroute a failing project to an older task, different dataset, or easier command path just to get a green state.

## State JSON Minimum

- Every automation-triggered agent action must write valid JSON to the requested state file.
- The JSON must include at least:
  - `project_id`
  - `phase`
  - `status`
  - `summary`
  - `updated_at`
- Include `smoke_command` for smoke results when available.
- Include `e2e_command` for e2e submission or resubmission results when available.
- Never write placeholder success fields or claim completion without the corresponding smoke pass or e2e submission having actually happened.

## Blocking And Failure Rules

- Do not dispatch `fullrun` if `smoke` has not succeeded in the current topic context.
- Do not mark a project successful if the topic contract, required inputs, or required artifacts are still missing.
- Mark the project `blocked` instead of looping retries when a required external dependency is unavailable, the configured topic contract cannot be satisfied, or the required environment is unavailable and cannot be restored within the current repair attempt.
- When blocked, state the concrete blocker in `summary` and avoid speculative or fabricated remediation claims.