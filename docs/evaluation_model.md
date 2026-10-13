# Evaluation Model

ResearchClawEval uses one evaluation chain for all current topics:

`topic -> framework -> mode -> wrapper -> validator -> result`

## Terms

- `topic`: the task contract being evaluated, such as `babylm`, `gave2_task2`, or `arc_wbe_2026`.
- `framework`: one of the seven framework checkouts controlled by this repository.
- `mode`: the depth of the run. Current modes are `input_pack`, `smoke`, and `fullrun`.
- `wrapper`: the script that prepares the workspace, injects inputs and API environment, runs the framework, and writes state/log artifacts.
- `validator`: the post-run checker that decides whether the wrapper output satisfies the minimum contract for that mode.
- `result`: the recorded status, logs, manifests, and summary rows for a concrete `topic x framework x mode` run.

## Directory Roles

- `automation/` is the repair and single-project dispatch lane. It owns the headless loop, per-project state, smoke repair, and systemd dispatch mechanics.
- `real_eval/` is the benchmark lane. It owns formal serial runners, wrappers, validators, framework configs, and cross-framework summaries.
- `framework_evaluator/` is shared evaluator code. It should not grow a third competing run lane.
- `docs/` explains the model and topic contracts. It should not be the only source of truth for runnable framework mappings.

## Registries

The initial registry files live under `real_eval/registry/`:

- `topics.json` lists topic ids, labels, contracts, dataset roots, summaries, and supported modes.
- `frameworks.json` lists framework ids, source directories, API dependencies, and supported topics.
- `runs.json` lists the runnable mapping from `topic_id`, `framework_id`, and `mode` to a wrapper and validator.

Existing runners and wrappers still use the current `real_eval/config/*.json` files by default. For a non-default registry-backed run, set `REAL_EVAL_USE_REGISTRY=1`; the serial runner writes `registry_framework_config.json` under the run root and then uses that generated config. An explicit `REAL_EVAL_FRAMEWORK_CONFIG=/path/to/config.json` takes precedence over the registry switch.

To inspect the current mapping without launching any run:

```bash
python3 real_eval/scripts/registry_matrix.py --topic gave2_task2 --mode fullrun
```

To render a current config shape from the registry without launching any run:

```bash
python3 real_eval/scripts/registry_to_config.py --topic gave2_task2 --mode fullrun
```

To inspect framework and dataset paths resolved from registry metadata:

```bash
python3 real_eval/scripts/registry_paths.py
```

GAVE2 and ARC preflight and full-run helper scripts use the same registry-backed path resolution. With no overrides, paths resolve to the current repository-root layout; with `RESEARCHCLAWEVAL_FRAMEWORKS_ROOT`, `RESEARCHCLAWEVAL_DATASETS_ROOT`, or per-resource environment variables, they can resolve to external asset directories.

To create a serial dry-run plan from the registry without launching wrappers:

```bash
python3 real_eval/scripts/run_registry_serial_dry_run.py --topic gave2_task2 --mode fullrun
```

To run an existing serial runner against the registry-generated config without launching wrappers:

```bash
RESEARCHCLAWEVAL_ROOT="$PWD" \
REAL_EVAL_USE_REGISTRY=1 \
REAL_EVAL_DRY_RUN=1 \
REAL_EVAL_SKIP_PREFLIGHT=1 \
real_eval/scripts/run_seven_serial_gave2_task2_fullrun.sh
```

ARC uses the same registry-backed runner shape:

- `arc_wbe_2026`: ARC White-Box Estimation Challenge 2026 with `input_pack`, `smoke`, and `fullrun` modes.
- ARC `fullrun` may normalize to `finished_degraded` when the framework leaves valid official-format submission evidence without a local official score artifact.

## Result Statuses

Use these status meanings when normalizing future run outputs:

- `blocked`: required inputs or runtime prerequisites are missing before the framework can run.
- `failed`: the wrapper launched but the runtime command exited unsuccessfully.
- `failed_validation`: the wrapper completed, but the validator rejected the artifacts.
- `finished_degraded`: the minimum evidence exists, but the output is incomplete or weaker than the full contract.
- `finished`: both wrapper execution and validator evidence satisfy the mode contract.

Existing state files may still contain older names such as `e2e_passed` or `failed_no_artifacts`. Those are historical compatibility values until the run outputs are normalized.

- `automation/scripts/topic_runtime.py` must remain topic-neutral. Legacy BabyLM placeholders may be supported for compatibility, but new topics must use the generic `RESEARCHCLAWEVAL_TOPIC_*` contract.
