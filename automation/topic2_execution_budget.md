# MountainCar-Continuous Native Execution Budget

This budget is mandatory for MountainCar-Continuous native framework evaluation runs.

1. Before the first experiment, write and lock `/workspace/research_idea.json` with the hypothesis, method rationale, expected failure modes, and comparison logic.
2. The framework owns method choice. The host does not prescribe an algorithm family, feature representation, architecture, hyperparameters, experiment sequence, baseline, or selected method.
3. Run one or more materially different, framework-native experiments chosen from the framework-authored idea. The framework decides the number of experiments.
4. Keep only a compact experiment ledger in context: experiment id, artifact path, framework-visible result, and decision. Do not paste full source files, checkpoint tensors, or verbose training output into the conversation.
5. Each framework-internal API client must use the injected `OPENAI_BASE_URL`, `OPENAI_API_KEY`, and `OPENAI_MODEL`. Do not hardcode a public provider, another provider, or a model name.
6. Each training command has a hard timeout of `1800` seconds. A run may spend no more than `training_command_timeout` seconds on a single training command.
7. Immediately after the final permitted experiment, select one valid result and promote the selected framework artifacts. Do not continue exploration after finalization begins.
8. Before exit, write `/workspace/experiment_trace.json` with `framework_native_execution: true`, `consumed_topic_input: true`, `workspace_trace_root: "/workspace"`, `experiments` (an array of one or more experiment objects, each with `experiment_id`), `selected_experiment_id`, `framework_internal_model`, `framework_internal_api_base_url`, `idea_artifact: "research_idea.json"`, and `idea_locked_before_experiments: true`.
9. A valid native handoff requires framework-produced root-level `/workspace/research_idea.json`, `/workspace/experiment_trace.json`, `/workspace/final_report.md`, exactly five checkpoints under `/workspace/checkpoints/`, `/workspace/config.yaml`, and the code under `/workspace/src/` required to reconstruct the model. The host creates `/workspace/score.json` only after the native framework exits.
10. If the framework cannot finish within its execution budget, exit with a concrete blocker. Do not fabricate metrics, score files, or traces.
11. A score is admissible only when the host runs the frozen `evaluate.py` against the framework-produced checkpoints. Checkpoint-count mismatches, a modified evaluator, an un-loadable model, or a missing config are invalid.

## Delivery Contract

- The frozen evaluator requires `assert len(checkpoint_files) == 5`. Fewer or more than five checkpoints fail closed.
- The evaluator rebuilds the model through `get_model_ready()` and loads each checkpoint, so `config.yaml`, `networks.py`, and the checkpoints must stay mutually compatible.
- The `Model` class name in `networks.py` must remain `Model`; renaming it fails evaluation.
- Checkpoint filenames must start with the config file stem (`config`), e.g. `config-42-0.pkl` ... `config-42-4.pkl`.
