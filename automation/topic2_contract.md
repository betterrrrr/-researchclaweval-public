# Topic 2 Contract

## Topic

- Topic id: `topic2`
- Topic label: `Topic 2`
- Topic dataset env: `TOPIC2_DATASET_ROOT`
- Canonical topic root: `data/topic2`
- Upstream: `facebookresearch/MLGym` @ `9d40c1b5035202018cd7091fb4e83a9c68b377c0`
- Upstream task: `rlMountainCarContinuous`

## Objective

Improve the official Average Reward of the MountainCarContinuous-v0
reinforcement-learning task as much as possible under the available resource
budget. A framework must consume the frozen MLGym starter code and protected
evaluator, run its own experiments, and deliver exactly five valid trained
checkpoints plus the config and code required to reconstruct the model.

## Required Inputs

- The frozen starter code under `TOPIC2_DATASET_ROOT/src/`:
  `train.py`, `policy.py`, `networks.py`, `helpers.py`, `config.yaml`,
  `__init__.py`.
- The protected frozen evaluator `TOPIC2_DATASET_ROOT/protected/evaluate.py`.
- The generated topic-native inputs under `inputs/`, including
  `docs/topic2_summary.md` and this contract.
- The host scorer `automation/scripts/run_topic2_host_score.py`.

## Required Outputs

- Exactly five valid trained checkpoints under `checkpoints/`, named so that
  `Path(config_fname).stem + "*.pkl"` matches them (default stem `config`).
- The corresponding `config.yaml` and all code the evaluator needs to
  reconstruct the model (`src/`).
- Root-level `research_idea.json`, `experiment_trace.json`, and
  `final_report.md`, all produced by the framework workflow in the current
  workspace.
- The framework must write and lock `research_idea.json` before its first
  experiment. It must include the hypothesis, method rationale, expected
  failure modes, and comparison logic.
- `experiment_trace.json` must prove one or more materially different experiments,
  identify the selected experiment, record framework-native execution and the
  injected internal API model/base URL, and set `idea_artifact:
  "research_idea.json"` and `idea_locked_before_experiments: true`.
- The host runs the frozen evaluator after the native framework exits. Only the
  host may create root-level `score.json`; a valid completion requires
  `score_source: "official_evaluate_py"`.

## Evaluation Truth

- The frozen `evaluate.py` is the single source of truth.
- It evaluates `batch_size = 256` environments across `SEEDS = [0,1,2,3,4]`,
  each rollout capped at `max_frames = 200`.
- It requires `assert len(checkpoint_files) == 5`.
- Primary metric: `Reward Mean` (higher is better). Secondary: `Reward Std`.
- Do not modify `evaluate.py`, the `Model` class name in `networks.py`, or
  the evaluation seed policy.

## Execution Rules

- Use only Topic 2 inputs from the current fresh run workspace
  and read-only topic asset mount.
- Do not route this topic to any other topic's inputs, runners, contracts,
  datasets, or scores.
- The framework owns the hypothesis, algorithm family, feature representation,
  architecture, hyperparameters, experiment sequence, comparison, and selected
  method. Host prompts must not prescribe any of them.
- Do not use any previous agent trajectory, reference solution, hidden
  benchmark result, or manually provided research method.
- Use the configured provider and model for framework reasoning.
  Framework-internal clients must not substitute another model or public
  provider.
- Framework-internal OpenAI-compatible clients must read `OPENAI_BASE_URL`,
  `OPENAI_API_KEY`, and `OPENAI_MODEL` from the injected environment. Do not
  hardcode an endpoint or model.
- Follow `automation/topic2_execution_budget.md`. Immediately
  promote the selected experiment after the final allowed experiment.
- Do not claim successful scoring without a real host `score.json`.
- The host must not generate, repair, promote, or backfill framework-authored
  research artifacts.

## Isolation

- Every evaluation uses a fresh physical workspace under
  `real_eval/runs/<run_id>/<framework>/workspace`.
- Fixed framework repositories are templates only and must not receive
  generated artifacts.
- The starter code is copied fresh from the frozen topic assets for every run.
