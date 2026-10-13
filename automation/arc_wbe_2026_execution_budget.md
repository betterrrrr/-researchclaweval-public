# ARC-WBE-2026 Native Execution Budget

This budget is mandatory for ARC-WBE-2026 native framework evaluation runs.

1. Before the first experiment, write and lock `/workspace/research_idea.json` with the hypothesis, method rationale, expected failure modes, and comparison logic.
2. The framework owns method choice. The host does not prescribe an algorithm family, feature representation, architecture, hyperparameters, experiment sequence, baseline, or selected method.
3. Run 2 to 4 materially different, framework-native experiments chosen from the framework-authored idea. Do not start a fifth experiment.
4. Keep only a compact experiment ledger in context: experiment id, artifact path, framework-visible validation result, and decision. Do not paste dataset rows, weights, tensor arrays, or verbose tool outputs into the conversation.
5. Each framework-internal API client must use the injected `OPENAI_BASE_URL`, `OPENAI_API_KEY`, and `OPENAI_MODEL`. Do not hardcode a public provider, another provider, or a model name.
6. Immediately after the final permitted experiment, select one valid result and promote the selected framework artifacts. Do not continue exploration after finalization begins.
7. Before exit, write `/workspace/experiment_trace.json` with `framework_native_execution: true`, `consumed_topic_input: true`, `workspace_trace_root: "/workspace"`, `experiments`, `selected_experiment_id`, `estimator_artifact`, `framework_internal_model`, `framework_internal_api_base_url`, `idea_artifact: "research_idea.json"`, and `idea_locked_before_experiments: true`.
8. A valid native handoff requires framework-produced root-level `/workspace/research_idea.json`, `/workspace/estimator.py`, `/workspace/submission.json`, `/workspace/experiment_trace.json`, and `/workspace/final_report.md`. The host creates `/workspace/score.json` only after the native framework exits.
9. If the framework cannot finish within its execution budget, exit with a concrete blocker. Do not fabricate metrics, score files, or traces.
10. A score is admissible only when the official adapter executes the framework estimator against the labeled host dataset. Adapter scalar/1-D broadcasting, zero/synthetic/placeholder predictions, stale score discovery, explicit-score copying, and fallback estimator paths are forbidden.
