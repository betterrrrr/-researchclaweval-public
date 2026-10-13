# BabyLM Strict-Small Native Execution Budget

This budget is mandatory for BabyLM Strict-Small native framework evaluation runs.

1. Before the first experiment, write and lock `/workspace/research_idea.json` with the hypothesis, method rationale, expected failure modes, and comparison logic.
2. The framework owns method choice. The host does not prescribe an algorithm family, feature representation, architecture, hyperparameters, experiment sequence, baseline, or selected method.
3. Run 2 to 4 materially different, framework-native experiments chosen from the framework-authored idea. Do not start a fifth experiment.
4. The primary metric is **word-level validation perplexity**. Evaluate all experiments using the same tokenizer and preprocessing. Record word-level `validation_perplexity` for each experiment in the trace. Character-level or subword-level perplexity is not accepted as the primary metric.
5. Keep only a compact experiment ledger in context: experiment id, artifact path, framework-visible validation result, and decision. Do not paste dataset rows, tokenized text, language-model outputs, or verbose tool outputs into the conversation.
6. Each framework-internal API client must use the injected `OPENAI_BASE_URL`, `OPENAI_API_KEY`, and `OPENAI_MODEL`. Do not hardcode a public provider, another provider, or a model name.
7. Immediately after the final permitted experiment, select one valid result and promote the selected framework artifacts. Do not continue exploration after finalization begins.
8. Before exit, write `/workspace/experiment_trace.json` with `framework_native_execution: true`, `consumed_topic_input: true`, `workspace_trace_root: "/workspace"`, `experiments` (an array of experiment objects, each with `experiment_id`, `name`, `validation_perplexity`), `selected_experiment_id`, `framework_internal_model`, `framework_internal_api_base_url`, `idea_artifact: "research_idea.json"`, and `idea_locked_before_experiments: true`. The trace JSON must be **strict valid JSON**: do not use `NaN`, `Infinity`, or `-Infinity` (convert them to `null`).
9. A valid native handoff requires framework-produced root-level `/workspace/research_idea.json`, `/workspace/experiment_trace.json`, and `/workspace/final_report.md`. The host creates `/workspace/score.json` only after the native framework exits.
10. If the framework cannot finish within its execution budget, exit with a concrete blocker. Do not fabricate metrics, score files, or traces.
11. A score is admissible only when the official scorer reads the framework experiment trace and produces a validated perplexity score. Proxy, toy, copied, stale, or host-authored results are invalid.

## Dataset Layout

The dataset is mounted at `/data/BabyLM-2026-Strict-Small` and contains **only** `*.train.txt` files (6 domain files, one sentence per line, already tokenized). There is **no** separate validation set. The framework must split the training data into train/validation sets itself (e.g., held-out 10% of tokens or lines per domain). Generated experiment code must:

- Read `.txt` files (not `.train.txt` specifically — the extension is `.txt`).
- **Not** silently swallow file-reading exceptions (no bare `except: pass` around file I/O).
- Check that the loaded data is non-empty and raise a clear error if it is not.
- Report the train/validation split size at load time.