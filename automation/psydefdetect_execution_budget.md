# PsyDefDetect Execution Budget

This budget applies to every PsyDefDetect framework evaluation.

## Hard Limits

- Run exactly 2 to 4 materially different experiments. Never start a fifth experiment.
- Each experiment must write a compact result record containing its id, method, official score, and artifact paths.
- After experiment 2, only run another experiment when it tests a specific improvement over the current best result. There may be at most two such follow-ups.
- Do not paste complete experiment source code or full prediction files into the agent context. Keep a short results ledger instead.
- For an API-backed experiment, construct the client from `OPENAI_BASE_URL`, `OPENAI_API_KEY`, and `OPENAI_MODEL`; do not hardcode `api.openai.com`. Record `framework_internal_model` equal to `OPENAI_MODEL` and the injected base URL in the final trace.

## Mandatory Finalization

Immediately after the last allowed experiment, stop exploration and use the framework's own comparison/finalization flow to select the highest-scoring valid experiment, score it with the provided local scorer, and promote its outputs to `/workspace/predictions.jsonl` (or `/workspace/submission.csv`), `/workspace/score.json`, `/workspace/experiment_trace.json`, and `/workspace/final_report.md`.

The experiment trace must record the 2 to 4 executed experiments, `framework_native_execution: true`, `consumed_topic_input: true`, `workspace_trace_root`, and `selected_experiment_id`. Do not begin another experiment after finalization begins. If finalization cannot be completed, stop with a concrete blocker.
