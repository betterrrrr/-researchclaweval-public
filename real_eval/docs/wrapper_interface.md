# Wrapper interface

A **wrapper** is the one file you write to make ResearchClawEval run *your*
research-agent framework. It does not contain any evaluation logic. It declares
how to launch your framework, then hands off to the shared topic runner.

This document describes the interface that the shared runners actually consume.
It is derived from `real_eval/scripts/*_framework_fullrun.sh` (the five topic
runners) and the wrappers under `real_eval/scripts/`.

## Shape of a wrapper

```bash
#!/usr/bin/env bash
set -euo pipefail

ROOT="${RESEARCHCLAWEVAL_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
source "$ROOT/real_eval/scripts/lib_real_eval.sh"

export FRAMEWORK_NAME="MyFramework"
export FRAMEWORK_SLUG="99_myframework_babylm_fullrun"
export FRAMEWORK_SRC="$(my_framework_resolve_source "$ROOT")"

# ... the variable table below ...

exec "$ROOT"/real_eval/scripts/babylm_framework_fullrun.sh
```

The last line is the whole point: your wrapper declares, the topic runner
executes. `babylm_framework_fullrun.sh`, `arc_framework_fullrun.sh`,
`mountaincar_framework_fullrun.sh`, `psydefdetect_framework_fullrun.sh` and
`tdc_admet_tox_framework_fullrun.sh` all consume the same variables, so a
wrapper written against one topic is portable to the others.

## Required variables

The runners use `${VAR:?VAR is required}` for these. A wrapper that omits any
of them aborts immediately, before any container starts.

| Variable | Meaning |
|---|---|
| `FRAMEWORK_RUNTIME_KIND` | Execution backend. Every current wrapper uses `docker`. |
| `FRAMEWORK_ENTRY_PATHS` | Newline-separated, repo-relative paths to the files copied into the container as task input (contract, brief, execution budget). Read with `mapfile`. |
| `FRAMEWORK_PROVIDER_INJECTION` | Human-readable description of how the LLM provider reaches your framework. Recorded in the run manifest. |
| `FRAMEWORK_NATIVE_LOG_MARKER` | See "Native execution proof" below. |

## Optional variables

| Variable | Default | Meaning |
|---|---|---|
| `FRAMEWORK_EXECUTOR_KIND` | `framework_cli` | How the framework is driven. In use: `framework_cli`, `official_framework_skill`, `framework_internal_codex_runner`, `framework_skill_executor`. |
| `FRAMEWORK_ENTRYPOINT` | *(empty)* | Container entrypoint override. Empty means use the image default. |
| `FRAMEWORK_ENTRY_PREFIX` | *(empty)* | Command prefix placed before the runtime command. |
| `FRAMEWORK_NAME` / `FRAMEWORK_SLUG` | — | Display name and the run's directory slug. |
| `FRAMEWORK_SRC` | — | Path to your framework checkout. `real_eval_resolve_framework_source "$ROOT" <id>` resolves it for registered adapters. |
| `FRAMEWORK_RUNTIME_IMAGE` | — | Image tag, e.g. `ai-researcher:runtime-ready`. |
| `FRAMEWORK_RUNTIME_COMMAND` | — | The shell script executed inside the container. |
| `FRAMEWORK_NATIVE_ENTRYPOINT` | — | Recorded native entrypoint string, e.g. `node server/cli.js chat`. |
| `FRAMEWORK_COMMAND_LABEL` | — | Human-readable label for the launched command. |
| `FRAMEWORK_DOCKER_ARGS` | — | Extra `docker run` arguments. |
| `FRAMEWORK_GPUS` / `FRAMEWORK_DISABLE_GPU` | — | Device allocation. Applied through `CUDA_VISIBLE_DEVICES`. |
| `FRAMEWORK_CONTAINER_HOME` / `_WORKDIR` / `_CODEX_HOME` | — | Container-side home, workdir, and codex config dir. |
| `FRAMEWORK_HOST_HOME_DIR` | — | Host home mounted into the container. |
| `FRAMEWORK_NEEDS_HOST_CODEX` | — | Set when the framework shells out to a host `codex`. |
| `FRAMEWORK_PROVIDER_BASE_URL` | — | Base URL recorded in the manifest. |
| `FRAMEWORK_DATASET_ROOT` | — | Dataset root for topics that require it. |
| `FRAMEWORK_LOG_FORBIDDEN_PATTERN` | — | Pattern that must **not** appear in the log. |
| `FRAMEWORK_NATIVE_PROCESS_MARKERS` | — | Additional process-level native markers. |
| `FRAMEWORK_AUDIT_FILE` / `FRAMEWORK_IMAGE_ID` | — | Audit and image pinning for TDC. |

## Native execution proof

This is the core contract of the whole harness, and it is not optional.

```bash
if [[ "$run_rc" -eq 0 ]] && ! rg -Fq "$FRAMEWORK_NATIVE_LOG_MARKER" "$LOG_FILE"; then
    # run judged non-native
fi
```

If the container exits `0` but the marker is absent from the log, **the run is
judged non-native and is not scored**. A framework cannot pass by shelling out
to your own script from the outside; the marker has to be emitted from inside
the framework's own execution.

The marker convention in existing wrappers is
`<FRAMEWORK>_<TOPIC>_<MODEL>_NATIVE`, for example
`AI_RESEARCHER_BABYLM_GPT_NATIVE` or `AUTORESEARCHCLAW_BABYLM_GPT_NATIVE`.
Make it unique per run configuration so a marker cannot be replayed across runs.

Inside `FRAMEWORK_RUNTIME_COMMAND`, emit it early:

```bash
echo "MYFRAMEWORK_BABYLM_NATIVE"
```

## What not to hardcode

These are the failure modes that make a wrapper unusable for anyone but its
author:

- **Model ids.** Put the evaluation target in `OPENAI_MODEL` (or the
  topic-specific `*_MODEL` variable) and read it. Do not bake
  `deepseek-v4-flash` into the entrypoint — your reader will use a different
  model.
- **Repository roots.** Use
  `ROOT="${RESEARCHCLAWEVAL_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"`.
  A literal absolute path breaks every other checkout.
- **Dataset roots.** Read from `BABYLM_DATASET_ROOT`, `ARC_WBE_2026_DATASET_ROOT`,
  `PSYDEFDETECT_DATASET_ROOT`, `TDC_ADMET_TOX_DATASET_ROOT`,
  `MOUNTAINCAR_CONTINUOUS_DATASET_ROOT`. Do not assume a directory that only
  exists on your machine.
- **`PROVIDER_CONFIG`.** The `provider_config` file is yours, not the
  repository's, and `api/` is git-ignored. Either require the variable with
  `:?` or point at `provider.example.toml`.
- **Device ids.** Leave GPU selection to `FRAMEWORK_GPUS`.

## The other half of the contract

A wrapper only launches your framework. What your framework must *produce* is
specified separately, per topic, in `automation/<topic>_contract.md`. Read the
contract for your topic — it defines the required artifacts
(`experiment_trace.json`, `score.json`, `final_report.md`, the prediction file),
the experiment count (typically 2–4), and the trace fields that must be
populated. A wrapper that launches cleanly but produces no conforming artifacts
scores nothing.

## A worked reference

See `real_eval/templates/my_framework_wrapper.sh` for a skeleton with no
machine-specific values, and any existing wrapper under
`real_eval/scripts/0*_*_fullrun.sh` for a complete example.
