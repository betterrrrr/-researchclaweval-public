# Native Evaluation Standard v1

This standard generalizes the admission, isolation, execution, and reporting
controls established by the later Topic 4 campaigns. It applies to every new
Topic, model/provider version, and seven-framework comparison.

The machine-readable rules are in
`real_eval/standards/native_evaluation_standard.v1.json`. A campaign-specific
spec starts from `real_eval/templates/native_evaluation_spec.v1.json` and must
pass `real_eval/scripts/validate_native_evaluation_spec.py` before dispatch.

## Objective

Measure framework research capability without confusing it with provider,
container, dataset, scorer, or entrypoint integration failures.

The framework owns planning through final artifact delivery. The host owns only
input projection, lifecycle management, official scoring, output validation,
and packaging. A host agent must never create or repair a framework result.

The host also must not prescribe the scientific method. It may lock the research
question, data visibility, split, metric, resources, experiment-count range,
network/safety policy, available dependencies, and output schema. It must not
lock an algorithm family, feature representation, architecture, hyperparameters,
experiment sequence, or selected method.

## Four Adapters

Every campaign freezes four independent adapters.

### Topic adapter

The Topic adapter defines:

- one topic id, contract, dataset environment variable, and read-only container
  mount;
- a native input generator with framework-neutral task information;
- the framework-visible validation policy used to compare experiments;
- one host-owned official scorer and one contract validator;
- the primary metric and the standard native trace fields;
- required framework-authored artifacts and any host-only inputs;
- the exact meaning of a missing score.

For hidden-label tasks, hidden labels must be physically separate from every
framework-visible input. For public-score tasks, the framework may invoke a
validation scorer, but the host remains the owner of the final official score.

### Model adapter

The Model adapter defines:

- the exact model id and evaluation variant;
- provider configuration and wire protocol;
- the container-reachable base URL;
- required client environment variables;
- a relay/provider preflight that makes a real minimal request;
- context, request, batching, and runtime-install policies;
- the runtime evidence needed to prove the effective model and endpoint.

A result from one model adapter never validates another model adapter. Model
versions are reported separately even when they share a provider.

### Framework adapter

Each of framework ids `01` through `07` independently records:

- the documented native entrypoint and its source evidence;
- runtime image tag and immutable image digest;
- provider injection path used by every framework-internal LLM client;
- native log marker and executor kind;
- Topic-specific smoke and full-run wrappers;
- admission evidence from the same image used by the full run.

Generic outer `codex exec` is forbidden as a native full-run entrypoint. A
framework-native official skill or runner may use `codex exec` internally when
the framework's own documented entrypoint explicitly defines that executor and
owns the complete workflow from planning through final artifact delivery. The
adapter must record `executor_kind: "official_framework_skill"` or the legacy
equivalent `"framework_skill_executor"` (or another explicitly admitted native
executor kind), the source/documentation defining the skill, and runtime logs
proving that ownership. A host-authored prompt loop
or imitation workflow remains non-native. If a framework has no compliant
entrypoint, record `unsupported` or `blocked` with a specific reason.

Every framework-visible prompt source is listed in the campaign spec. Before
freeze, each framework requires a prompt audit containing SHA-256 hashes of
those sources and an empty `prescribed_methods` list. Start from
`real_eval/templates/native_prompt_audit.v1.json`. Changing a prompt after the
review invalidates the freeze manifest.

### Campaign adapter

The Campaign adapter defines one synchronized comparison:

- framework order `01` through `07`;
- a common experiment and timeout budget;
- one fresh attempt per framework;
- a fresh physical workspace for every attempt;
- a separate campaign id for every recovery;
- a freeze manifest covering all critical files and image digests.

The synchronized campaign is the primary comparison. Recovery runs contribute
only to the separately labeled best-completed-native view.

## Lifecycle

### 1. Implement the Topic adapter

Before adapting frameworks, complete the contract, dataset projection, input
generator, validation policy, official scorer, and validator. Test the scorer
with a deterministic reference artifact. Do not begin framework work while the
metric or data visibility contract is still changing.

### 2. Implement the Model adapter

Create a provider config and preflight for the exact model. The preflight must
run from each framework image and verify the real wire protocol, model id, and
container-reachable URL. A host-only relay health check is insufficient.

For OpenAI-compatible clients, require `OPENAI_BASE_URL`, `OPENAI_API_KEY`, and
`OPENAI_MODEL`. A framework-specific client may use different names only when
the adapter proves that they resolve to the same frozen model and endpoint.

### 3. Adapt every native framework entrypoint

Keep framework-specific commands in framework-specific wrappers or config
rows. Do not use a single outer prompt to simulate seven frameworks. The
adapter may project inputs and provider settings, but it must not take over
planning, experiment design, execution, comparison, or final delivery.

Prompts describe the problem and constraints, not the solution. They may say
"run 2 materially different experiments" or "use only installed dependencies".
They may not say "Experiment 1 is algorithm X", require a particular baseline,
or prescribe feature extraction, model architecture, hyperparameters, or the
order in which scientific methods must be tried. Mentioning an official
reference baseline for task context is allowed only when the prompt clearly
states that the framework is not required to use or reproduce it.

Run the static gate while adapters are still `pending`:

```bash
python3 real_eval/scripts/validate_native_evaluation_spec.py \
  --spec real_eval/config/<topic>_<model>_native_spec.json \
  --stage adaptation
```

### 4. Run same-image admission

Admission is not a research experiment. It verifies only that the full-run
runtime can start and reach its dependencies. Each evidence JSON must contain:

```json
{
  "framework_id": "01",
  "status": "passed",
  "model_id": "exact-model-id",
  "container_base_url": "http://host.docker.internal:9999/v1",
  "runtime_image": "framework:runtime-ready",
  "runtime_image_digest": "sha256:...",
  "checks": {
    "native_entrypoint": true,
    "relay_request": true,
    "topic_inputs": true,
    "workspace_write": true,
    "scorer_dependencies": true
  }
}
```

Start from `real_eval/templates/native_admission_evidence.v1.json`; do not
handwave a smoke pass in a framework config or prompt.

Admission must not run full experiments or create accepted research artifacts.
After a pass, set the adapter status to `admitted`, record the evidence path,
and pin the image digest. Failed admission remains `pending` during repair or is
made terminal as `unsupported`/`blocked` with a reason.

Before setting `admitted`, review every shared and framework-specific prompt,
write its prompt-audit JSON, and verify that method selection remains owned by
the framework. Admission evidence proves runtime reachability; prompt-audit
evidence proves ideation freedom. Both are required.

### 5. Freeze the campaign

After all framework admissions reach an admitted or terminal state, freeze the
spec and every critical adapter file:

```bash
python3 real_eval/scripts/freeze_native_evaluation_spec.py \
  --spec real_eval/config/<topic>_<model>_native_spec.json
```

The manifest hashes the spec, standard, contract, provider config, input
generator, scorer, validator, entrypoint evidence, wrappers, smoke scripts, and
admission evidence. Any subsequent change requires a new freeze and normally a
new campaign id.

The freeze command first runs the `freeze` gate. It refuses to create a
manifest while an adapter is pending or while admission evidence, image digest,
provider settings, or required checks do not match the spec.

### 6. Pass the dispatch gate

```bash
python3 real_eval/scripts/validate_native_evaluation_spec.py \
  --spec real_eval/config/<topic>_<model>_native_spec.json \
  --stage dispatch \
  --output real_eval/runs/<run_id>/admission_report.json
```

Do not dispatch when this command fails. Terminal unsupported/blocked rows stay
in the comparison as `N/A` and are not silently removed or replaced.

### 7. Run the synchronized campaign

For every admitted framework:

1. Copy the fixed framework source to a new physical run workspace.
2. Mount only that workspace writable at `/workspace`.
3. Mount Topic inputs and contracts read-only.
4. Start the documented native entrypoint with the frozen model adapter.
5. Run 2 to 4 materially different experiments within the common budget.
6. Write and lock `/workspace/research_idea.json` before the first experiment.
7. Keep a compact experiment ledger in context.
8. Select and promote the final framework artifacts immediately after the last
   experiment.
9. Preserve the complete runtime log and native trace, including proof that the
   idea artifact predates experiment execution.

The host does not repair missing framework artifacts after exit.

### 8. Score, validate, and report

The host runs the official scorer against the selected framework artifact, then
runs the Topic validator. Record these dimensions independently:

- `native_compliance`
- `research_completed`
- `scored`
- `contract_complete`
- `engineering_complete`

Never convert a missing score to zero. Publish two views:

- `synchronized_primary`: the frozen same-campaign attempts;
- `best_completed_native`: the best valid native observation, with every
  recovery and unequal retry history labeled.

Assess the pre-experiment `research_idea.json` separately from task performance.
The idea judge must be blind to framework identity and experiment results, and
use the same frozen rubric for novelty, hypothesis clarity, technical
soundness, feasibility, and experimental discrimination. Idea quality is a
secondary dimension; it must not be folded into the official task score.

## Adding a New Topic

1. Register the Topic id and paths in `real_eval/registry/topics.json`.
2. Write the Topic contract and dataset visibility rules.
3. Implement and test native input generation.
4. Implement and test framework-visible validation scoring.
5. Implement the host official scorer and contract validator.
6. Define framework-authored artifacts and host-authored score artifacts.
7. Add smoke/full-run registry rows and wrappers for all seven frameworks.
8. Create a native evaluation spec from the template.
9. Complete same-image admission for each model adapter.
10. Freeze, dispatch, and report using the lifecycle above.

## Adding a New Model

1. Give the model/provider version a distinct variant name.
2. Add an immutable provider config and exact effective model id.
3. Define the real wire protocol and container-reachable endpoint.
4. Add a minimal real-request preflight for every runtime image.
5. Prove each native framework client consumes the injected provider settings.
6. Set context, request, timeout, and batching budgets before admission.
7. Run same-image admission across all seven framework adapters.
8. Create a new frozen synchronized campaign; never reuse another model's
   admission or result.

## Change Control

Changes before dispatch are allowed only with a regenerated freeze manifest.
Changes after dispatch require a new run id and fresh workspaces. Preserve every
old run, including failed, timed-out, invalid, and partial attempts.
