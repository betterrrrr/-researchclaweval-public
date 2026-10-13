# BabyLM 2026 Strict-Small Contract

Topic id: `babylm` (Topic 1), evaluation variant `GPT / gpt-5.4`.

The framework receives only the read-only BabyLM Strict-Small dataset projected
at `/data/BabyLM-2026-Strict-Small` and this contract. It must own question
refinement, idea formation, method selection, experiment design, execution,
comparison, selection, analysis, and final artifact delivery through its
documented native entrypoint.

The host fixes only the visible data (6 `*.train.txt` files, no separate validation
set), the train/validation split policy (framework must split the train data into
train/validation sets), the perplexity/loss evaluation policy, resource and
wall-clock limits, and the output schema. The host must not prescribe an
algorithm family, representation, architecture, hyperparameters, experiment
sequence, baseline, or selected method.

Before the first experiment the framework must write and lock
`research_idea.json`, including a hypothesis, rationale, expected failure modes,
and discriminating experiments. It must then run 2-4 materially distinct
experiments using the real dataset and write `experiment_trace.json`,
`final_report.md`, and its native submission artifacts. The framework may not
author root-level `score.json`; the host creates that artifact after validation.

Proxy, n-gram-only, toy, copied, stale, or host-authored results are invalid.
