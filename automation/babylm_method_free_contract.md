# BabyLM 2026 Strict-Small Method-Free Contract (Word-Level Perplexity)

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

## Evaluation Metric

The primary metric is **word-level validation perplexity**. The framework must
evaluate all experiments using the official BabyLM strict evaluation pipeline or
compute word-level perplexity on a held-out validation split using the same
tokenizer and preprocessing across all experiments. Character-level or
subword-level perplexity is not accepted as the primary metric. The
`experiment_trace.json` must record word-level `validation_perplexity` for each
experiment.

## Required Workflow

Before the first experiment the framework must write and lock
`research_idea.json`, including a hypothesis, rationale, expected failure modes,
and discriminating experiments. It must then run 2-4 materially distinct
experiments using the real dataset and write `experiment_trace.json` (with
word-level `validation_perplexity` for each experiment), `final_report.md`, and
its native submission artifacts. The framework may not author root-level
`score.json`; the host creates that artifact after validation.

Proxy, toy, copied, stale, or host-authored results are invalid.