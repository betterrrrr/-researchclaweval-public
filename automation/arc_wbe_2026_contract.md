# ARC-WBE-2026 Contract

## Topic

- Topic id: `arc_wbe_2026`
- Topic label: `ARC-WBE-2026`
- Dataset environment variable: `ARC_WBE_2026_DATASET_ROOT`
- Canonical dataset root: `data/arc_white_box_estimation_2026`

## Objective

Produce an official-comparable ARC White-Box Estimation Challenge 2026 result. A framework must consume the local ARC-WBE inputs, implement or execute a reproducible estimator workflow, and preserve evidence for the reported score.

## Required Inputs

- The materialized ARC-WBE dataset under `ARC_WBE_2026_DATASET_ROOT`.
- The **visible validation subset** at `<dataset root>/visible-validation/`, mounted read-only inside the framework container next to the dataset. See "Visible Validation Set" below.
- The generated topic-native inputs under `inputs/`, including `docs/arc_wbe_2026_summary.md` and this contract.
- The local scorer `automation/scripts/run_arc_wbe_2026_local_score.py` and its official adapter.

## Visible Validation Set

The framework is given a small labelled subset so it can **evaluate its own estimator with the official metric** — something the main dataset deliberately does not allow, because the weights-only projection carries no target activations.

- Location: `<dataset root>/visible-validation/data/*.parquet` (also visible at `/data/arc_wbe_2026/visible-validation/`).
- Columns: `mlp_id`, `mlp_name`, `mlp_seed`, `weights`, `all_layer_means`, `final_means` — i.e. weights **and** the ground-truth activations.
- Size: 10 MLPs out of 100. The scoring set is the other 90 and is never mounted into the framework container.
- The two sets are **disjoint by `mlp_id`**, so self-evaluation cannot leak into the scored result. The split is frozen; both files' sha256 are recorded in `<dataset root>/split_manifest.json`.

Record each experiment's self-evaluation result under `framework_visible_validation` in `experiment_trace.json`, using the same shape as the official metric (`n_mlps`, `adjusted_final_layer_score`, `final_layer_mse`, `all_layers_mse`). A qualitative sentence is not a substitute: without a numeric field, the trace cannot support `b0`/`bT`/`AUP`/`UR` and those dimensions fall back to the judge's ordinal path.

## Required Outputs

- An official-format submission artifact when the selected workflow can produce one.
- Root-level `research_idea.json`, `estimator.py`, `submission.json`, `experiment_trace.json`, and `final_report.md`, all produced by the framework workflow in the current workspace.
- The framework must write and lock `research_idea.json` before its first experiment. It must include the hypothesis, method rationale, expected failure modes, and comparison logic.
- `experiment_trace.json` must prove 2 to 4 materially different experiments, identify the selected experiment, record framework-native execution and the injected internal API model/base URL, and set `idea_artifact: "research_idea.json"` and `idea_locked_before_experiments: true`.
- The host runs the local official scorer after the native framework exits. Only the host may create root-level `score.json`; an official-comparable completion requires `score_source: "official_adapter_whest_run"`.
- The estimator must produce real per-layer predictions that depend on `mlp.weights`; scalar, broadcast, zero-filled, synthetic, placeholder, copied, or fallback predictions are inadmissible.
- `predict(mlp)` must return a real prediction matrix of shape `(mlp.depth, mlp.width)` = `(32, 256)`: the predicted mean activation of each of the 256 hidden neurons in each of the 32 layers. A final-layer-only `(256,)` vector, a scalar, or any other shape is invalid and will be rejected by the official adapter.
- The official adapter must fail closed on missing, malformed, non-finite, or shape-mismatched predictions. It must never normalize a scalar or 1-D value into a prediction matrix.
- If the official adapter scorer fails, the host must not search for an older score, accept an explicit score artifact, or run a second fallback estimator path.

## Execution Rules

- Use only ARC-WBE-2026 inputs from the current fresh run workspace and read-only dataset mount.
- Do not route this topic to any other topic's inputs, runners, contracts, datasets, or scores.
- The framework owns the hypothesis, algorithm family, feature representation, architecture, hyperparameters, experiment sequence, comparison, and selected method. Host prompts must not prescribe any of them.
- Keep raw weights, complete tensor arrays, `all_layer_means`, and `final_means` out of logs and prompts. The visible-validation subset above **is** readable by the framework for self-evaluation, but its arrays must not be pasted into logs, prompts, or reports — record only the scalar metrics.
- Use the configured provider and model for framework reasoning. Framework-internal clients must not substitute another model or public provider.
- Framework-internal OpenAI-compatible clients must read `OPENAI_BASE_URL`, `OPENAI_API_KEY`, and `OPENAI_MODEL` from the injected environment. Do not hardcode an endpoint or model.
- Follow `automation/arc_wbe_2026_execution_budget.md`. Immediately promote the selected experiment after the final allowed experiment.
- Treat tool-call scoring as out of scope unless the official ARC adapter explicitly supports it; preserve trace evidence instead.
- Do not claim successful scoring without a real local score artifact or official-format evidence.
- The host must not generate, repair, promote, or backfill framework-authored research artifacts.

## Isolation

- Every evaluation uses a fresh physical workspace under `real_eval/runs/<run_id>/<framework>/workspace`.
- Fixed framework repositories are templates only and must not receive generated artifacts.
