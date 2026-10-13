# Evaluation Run Logic Explained

Date: 2026-06-05

This document explains how the current ResearchClawEval runs are organized, why outputs appear outside Docker containers, how repeated run directories relate to one another, and where to find the currently correct scripts.

It is intentionally written outside `docs/` and `Report/`.

## Short Answer

The evaluation is not one monolithic in-container run. It is a host-orchestrated serial evaluation.

The host machine starts a `systemd --user` job. That job runs a serial shell runner. The serial runner invokes one framework-specific script at a time. Each framework script creates or reuses an isolated host-side run directory, then starts the framework inside Docker or a headless agent environment with that host directory bind-mounted into the container.

Because the framework workspace is bind-mounted, files written inside the container are immediately written on the host. That is why results appear outside the container.

The main current run root is:

```text
$RESEARCHCLAWEVAL_ROOT/real_eval/runs/systemd-six-resume-repair4-20260604-125723
```

The current active resume log root is:

```text
$RESEARCHCLAWEVAL_ROOT/real_eval/systemd_runs/systemd-six-resume-repair4-20260604-125723-stage13-resume-20260605-150040
```

The current run root is the main artifact directory, but not a fully self-contained archive of every input and every provenance log. The systemd logs, fixed inputs, dataset, API configuration, and in one case a source-run provenance record live outside it.

## Execution Model

The execution stack has four layers.

### 1. Host `systemd --user` Job

The background job is submitted through `systemd-run --user`.

The generic systemd wrapper is:

```text
real_eval/scripts/run_six_serial_babylm_systemd_job.sh
```

It:

- creates a systemd log directory under `real_eval/systemd_runs/<run_id>/`;
- writes a global `state.json`;
- writes a global `summary.txt`;
- tees stdout/stderr into `run.log`;
- invokes the configured serial runner.

This layer is outside Docker. It is the host-level execution record.

### 2. Serial Runner

The serial runner decides which framework script runs next.

For the current resumed run, the serial runner is:

```text
real_eval/scripts/run_six_serial_babylm_resume_from_04_current.sh
```

It currently runs:

```text
04_autoresearchclaw_resume_current_babylm.sh
05_deepscientist_real_babylm.sh
06_drclaw_real_babylm.sh
07_evoscientist_real_babylm.sh
```

This is not the original full six-script runner. It is a continuation runner. It intentionally does not rerun AI-Researcher or ARIS, because both already completed in the same main run root.

The older repaired full-ish runner is:

```text
real_eval/scripts/run_six_serial_babylm_resume_repair2.sh
```

It runs:

```text
01_ai_researcher_resume_repair2_babylm.sh
03_aris_real_babylm.sh
04_autoresearchclaw_real_babylm.sh
05_deepscientist_real_babylm.sh
06_drclaw_real_babylm.sh
07_evoscientist_real_babylm.sh
```

Important: this runner still uses `04_autoresearchclaw_real_babylm.sh`, whose original configuration caused the 24-hour AutoResearchClaw Stage 12 timeout. The current active recovery uses `04_autoresearchclaw_resume_current_babylm.sh` instead.

### 3. Framework-Specific Script

Each framework has its own script because each framework expects different inputs and a different entry point.

Examples:

```text
01_ai_researcher_resume_repair2_babylm.sh
03_aris_real_babylm.sh
04_autoresearchclaw_real_babylm.sh
04_autoresearchclaw_resume_current_babylm.sh
05_deepscientist_real_babylm.sh
06_drclaw_real_babylm.sh
07_evoscientist_real_babylm.sh
```

The script normally does these things:

1. Creates a per-framework run root under the main run root.
2. Copies or reuses a framework repository/workspace.
3. Writes `provider.env` and `semantic.env`.
4. Writes framework-specific input files.
5. Mounts the run directory, dataset, and task contract into Docker.
6. Runs the real framework entry point.
7. Writes a per-framework `state.json`.
8. Leaves logs and artifacts in the per-framework host directory.

### 4. Container / Headless Agent Runtime

The framework code usually runs inside Docker. Docker is used as the environment boundary, not as the permanent storage boundary.

For example, AutoResearchClaw is launched with a mount shaped like:

```text
-v <host-run-repo>:/workspace/AutoResearchClaw
```

Inside the container, AutoResearchClaw writes to:

```text
/workspace/AutoResearchClaw/artifacts/...
```

Because `/workspace/AutoResearchClaw` is a bind mount, the same files appear on the host at:

```text
real_eval/runs/<run_id>/04_autoresearchclaw_real_babylm/repo/artifacts/...
```

This is expected. It is not leakage. It is how host-side artifact capture works.

## Why Files Are Outside the Container

Docker containers are ephemeral in these scripts. Most are run with `--rm`, meaning the container is deleted after completion.

If outputs stayed only in the container filesystem, they would be lost when the container exits. Therefore the scripts mount host directories into the container.

The intended storage model is:

```text
Host run directory = durable artifact store
Docker container = temporary execution environment
Dataset mount = read-only external input
API/env files = generated per-run config
```

So the files being outside the container is correct. The isolation is not "all files stay inside Docker"; it is "the framework runs inside Docker, but its workspace is mounted to a per-run host directory."

## Main Directories

### Main Artifact Root

```text
$RESEARCHCLAWEVAL_ROOT/real_eval/runs/systemd-six-resume-repair4-20260604-125723
```

Current subprojects inside it:

```text
01_ai_researcher_resume_repair2_babylm
03_aris_real_babylm
04_autoresearchclaw_real_babylm
```

`05`, `06`, and `07` do not yet exist in this run root because the outer serial runner has not advanced past AutoResearchClaw.

### Systemd Log Roots

Original run:

```text
$RESEARCHCLAWEVAL_ROOT/real_eval/systemd_runs/systemd-six-resume-repair4-20260604-125723
```

AutoResearchClaw Stage 13 resume run:

```text
$RESEARCHCLAWEVAL_ROOT/real_eval/systemd_runs/systemd-six-resume-repair4-20260604-125723-stage13-resume-20260605-150040
```

These directories are not framework artifacts, but they are the host-level execution truth: command order, stdout/stderr, active/fail state, and systemd summary.

### Fixed Inputs Outside the Run Root

The run uses fixed host-side inputs:

```text
$RESEARCHCLAWEVAL_ROOT/api/codex_gpt54_shubiaobiao.toml
$RESEARCHCLAWEVAL_ROOT/api/_semantic_scholar_api_usage.md
$RESEARCHCLAWEVAL_ROOT/BabyLM-2026-Strict-Small
$RESEARCHCLAWEVAL_ROOT/BabyLM-10M_七框架任务包装与分发指南.md
```

Those are not copied wholesale into every run root. They are referenced, parsed, or mounted.

## Relationship Between Multiple Runs

There are many run directories because the evaluation was repaired iteratively.

They are not all equivalent.

### Smoke / Debug / Fix Check Runs

Examples:

```text
longcheck-20260603-150320
longcheck-isolated-20260603-151024
fixcheck-20260603-154128
fixcheck-20260603-155233
fixcheck-target-20260603-160317
fixcheck-final-20260603-161353
```

These were exploratory checks and repair attempts. They are not the canonical final evaluation.

### Early Systemd Six Runs

Examples:

```text
systemd-six-20260603-174900
systemd-six-20260603-195426
systemd-six-20260603-200316
systemd-six-repair-20260603-203549
systemd-six-repair2-20260603-203759
```

These were earlier six-script attempts. Some produced useful real artifacts; some failed and informed repairs.

Important provenance point:

```text
systemd-six-repair2-20260603-203759
```

is the source run for AI-Researcher's real training/evaluation workplace used later by the repaired writing resume script.

### Resume-Repair Runs

Examples:

```text
systemd-six-resume-repair2-20260603-213507
systemd-six-resume-repair2-20260603-213636
systemd-six-resume-repair2-20260603-213813
systemd-six-resume-repair2-20260603-214012
systemd-six-resume-repair3-20260604-121555
systemd-six-resume-repair4-20260604-125723
```

These are repaired runs that reused or bridged earlier real artifacts where appropriate.

The current main run is:

```text
systemd-six-resume-repair4-20260604-125723
```

This is the main run root to inspect for the current evaluation's per-framework artifacts.

### AutoResearchClaw Stage 13 Resume Runs

Examples:

```text
systemd-six-resume-repair4-20260604-125723-stage13-resume-20260605-145632
systemd-six-resume-repair4-20260604-125723-stage13-resume-20260605-150040
```

These are not new full six-agent evaluations. They are host-level systemd logs for resuming the same main run from AutoResearchClaw Stage 13.

The currently relevant one is:

```text
systemd-six-resume-repair4-20260604-125723-stage13-resume-20260605-150040
```

It continues writing into:

```text
real_eval/runs/systemd-six-resume-repair4-20260604-125723/04_autoresearchclaw_real_babylm
```

## Are Runs Complete by Themselves?

The answer depends on the run.

### AI-Researcher in the Current Run

Current AI-Researcher directory:

```text
real_eval/runs/systemd-six-resume-repair4-20260604-125723/01_ai_researcher_resume_repair2_babylm
```

This directory contains the current AI-Researcher evaluation package:

- copied/repaired repo;
- writing logs;
- generated paper sections;
- final PDF;
- copied real experiment workspace;
- copied checkpoint/evaluation evidence;
- writing contract manifest.

However, it is not a pure from-zero training run. Its `state.json` says:

```text
source_run_id: systemd-six-repair2-20260603-203759
```

That means the AI-Researcher writing run used real training/evaluation evidence that came from an earlier source run and was copied/materialized into the current run directory.

For evaluating the current AI-Researcher paper result, the current directory is the main truth.

For reconstructing the original training provenance from the moment training happened, you still need the earlier source run logs.

### ARIS in the Current Run

Current ARIS directory:

```text
real_eval/runs/systemd-six-resume-repair4-20260604-125723/03_aris_real_babylm
```

This is effectively self-contained for the current ARIS execution: workspace, logs, outputs, and state are under that directory.

### AutoResearchClaw in the Current Run

Current AutoResearchClaw directory:

```text
real_eval/runs/systemd-six-resume-repair4-20260604-125723/04_autoresearchclaw_real_babylm
```

This contains the AutoResearchClaw repo copy and artifacts. It was first run from Stage 1 through Stage 12, then resumed from Stage 13 after the 24-hour timeout problem.

The artifacts stay in the same main run root. The Stage 13 resume systemd logs are outside, under `real_eval/systemd_runs/...stage13-resume...`.

### DeepScientist / DrClaw / EvoScientist

These have not run yet in the current `systemd-six-resume-repair4-20260604-125723` run root because the serial runner is still inside AutoResearchClaw.

When they run, their directories should appear as:

```text
05_deepscientist_real_babylm
06_drclaw_real_babylm
07_evoscientist_real_babylm
```

## Error Scripts vs Corrected Scripts

There are two categories of scripts now.

### Earlier Scripts That Exposed Errors

Examples:

```text
run_six_serial_babylm.sh
submit_six_serial_babylm_systemd_user.sh
04_autoresearchclaw_real_babylm.sh
```

These were part of earlier attempts. Some are still useful as references, but they should not be assumed to represent the currently repaired path.

In particular, `04_autoresearchclaw_real_babylm.sh` originally changed AutoResearchClaw to a very large runtime/search configuration. That produced the Stage 12 24-hour timeout. It is not the safe continuation script.

### Corrected Current Continuation Scripts

For the current run, the corrected continuation scripts are:

```text
real_eval/scripts/submit_six_serial_babylm_resume_from_04_current_systemd_user.sh
real_eval/scripts/run_six_serial_babylm_resume_from_04_current.sh
real_eval/scripts/04_autoresearchclaw_resume_current_babylm.sh
```

These scripts are correct for continuing this current run from AutoResearchClaw Stage 13 and then moving to 05/06/07.

They do not represent a clean from-zero six-framework run.

### Corrected AI-Researcher Writing Resume Script

The corrected AI-Researcher writing resume script is:

```text
real_eval/scripts/01_ai_researcher_resume_repair2_babylm.sh
```

It fixes the repeated missing-folder pattern by materializing and checking the AI-Researcher writing-stage workspace contract before invoking the writer.

It is a writing resume script. It depends on a source real training/evaluation workplace.

## Does a Corrected Script Include Earlier Work?

Usually no.

A repair or resume script generally includes only the work from the repair point forward, plus copied or referenced artifacts from earlier stages.

For example:

```text
04_autoresearchclaw_resume_current_babylm.sh
```

does not rerun AutoResearchClaw Stages 1-12. It reuses the existing AutoResearchClaw artifacts and resumes from the checkpoint at Stage 13.

Similarly:

```text
01_ai_researcher_resume_repair2_babylm.sh
```

does not rerun the original AI-Researcher training stage. It copies/bridges the real training/evaluation evidence from the source run and then runs the corrected writing stage.

Therefore, a corrected resume script is not the same as a corrected from-zero script.

## Where Is the Truly Correct Script?

There is currently no single fully consolidated "golden from-zero six-framework script" that includes all fixes and starts every framework from nothing.

What exists now:

### Correct for Current Continuation

Use:

```text
real_eval/scripts/submit_six_serial_babylm_resume_from_04_current_systemd_user.sh
```

This is the correct script for the current state. It continues the existing run from AutoResearchClaw and then should proceed to 05/06/07.

### Correct for AI-Researcher Writing Resume

Use:

```text
real_eval/scripts/01_ai_researcher_resume_repair2_babylm.sh
```

This is correct for AI-Researcher writing-stage recovery when valid real experiment evidence already exists.

### Not Yet Consolidated

A truly correct from-zero six-framework script should be created separately.

It should incorporate:

- the AI-Researcher workspace contract preflight;
- the LLM retry fix;
- AutoResearchClaw bounded experiment/refinement settings;
- AutoResearchClaw BabyLM recovery prompt conflict fix;
- strict per-framework artifact checks;
- systemd background execution;
- serial stop-on-failure behavior;
- explicit run provenance metadata.

Until that consolidated script exists, do not treat the older from-zero runner as fully corrected.

## How to Read the Current Evidence

For current main artifacts:

```text
real_eval/runs/systemd-six-resume-repair4-20260604-125723
```

For host-level execution logs:

```text
real_eval/systemd_runs/systemd-six-resume-repair4-20260604-125723
real_eval/systemd_runs/systemd-six-resume-repair4-20260604-125723-stage13-resume-20260605-150040
```

For AI-Researcher current result:

```text
real_eval/runs/systemd-six-resume-repair4-20260604-125723/01_ai_researcher_resume_repair2_babylm
```

Final AI-Researcher PDF:

```text
real_eval/runs/systemd-six-resume-repair4-20260604-125723/01_ai_researcher_resume_repair2_babylm/repo/research_agent/babylm/target_sections/babylm_10m/iclr2025_conference.pdf
```

For ARIS current result:

```text
real_eval/runs/systemd-six-resume-repair4-20260604-125723/03_aris_real_babylm
```

For AutoResearchClaw current result:

```text
real_eval/runs/systemd-six-resume-repair4-20260604-125723/04_autoresearchclaw_real_babylm
```

## Practical Rule

When judging whether an output is valid, do not only ask "which directory has a file?"

Ask:

1. Which systemd unit produced it?
2. Which framework script produced it?
3. Which per-framework `state.json` records it?
4. Was it a from-zero run or a resume run?
5. If it was a resume run, which source run or checkpoint did it use?
6. Are checkpoints/evaluation JSON present?
7. Are logs present for the stage that produced the claimed artifact?

For the current work, the answer is:

- Main artifact root: `systemd-six-resume-repair4-20260604-125723`
- Active continuation log: `systemd-six-resume-repair4-20260604-125723-stage13-resume-20260605-150040`
- AI-Researcher: finished, but writing-resume based on source run `systemd-six-repair2-20260603-203759`
- ARIS: finished in current run root
- AutoResearchClaw: still active in current run root, resumed from Stage 13
- DeepScientist/DrClaw/EvoScientist: not yet reached in the current run root
