# Topic 4 Method-Free Prompt Audit

Campaign date: 2026-08-05

## Audit conclusion

The previous Topic 4 input contract prescribed concrete methods in the shared
generator and in four framework adapters:

| Framework | Models affected | Previous prescribed content |
|---|---|---|
| AI-Researcher | GPT, Kimi, DeepSeek | Word/character TF-IDF linear baselines |
| AI-Scientist-v2 | GPT, Kimi, DeepSeek | Word TF-IDF + LogisticRegression and character TF-IDF + LinearSVC/SGDClassifier |
| AutoResearchClaw | GPT, Kimi, DeepSeek | The same two named conditions, enforced by plan/code validators |
| DeepScientist | GPT, Kimi, DeepSeek | The same two named conditions in the native runner message |

ARIS, Dr. Claw, and EvoScientist did not contain those concrete algorithm
requirements in their active Topic 4 prompts. Their prompts were still aligned
to the method-free policy for this campaign.

## Frozen method-free policy

The host now fixes only the PsyDefDetect question, visible dataset, dialogue-level
split, official macro-F1 over labels 1-8, installed dependency/network policy,
two-experiment budget, scorer CLI, and root artifact schema. The framework owns
the hypothesis, method choice, representation, architecture, hyperparameters,
experiment rationale, comparison, and final selection. `research_idea.json` is
required before the first experiment.

The generated input pack contains no TF-IDF, LogisticRegression, LinearSVC,
SGDClassifier, or equivalent named algorithm requirement. A framework may still
choose one of those methods itself; that is recorded as a framework decision in
`research_idea.json` and `experiment_trace.json`, not as a host prescription.

## Campaign controls

Three model-specific specs passed adaptation, freeze, and dispatch validation:

- `real_eval/config/psydefdetect_method_free_gpt_20260805.json`
- `real_eval/config/psydefdetect_method_free_kimi_20260805.json`
- `real_eval/config/psydefdetect_method_free_deepseek_20260805.json`

All seven runtime images passed same-image smoke checks. GPT provider requests,
Kimi relay requests at `host.docker.internal:8787`, and DeepSeek relay requests
at `host.docker.internal:8788` were verified from the framework images. The
initial audit treated ARIS as terminal `blocked` because its process contains
`codex exec`. The admission rule was subsequently corrected on 2026-08-06:
ARIS's documented `/experiment-bridge` official Codex skill is eligible when
its runtime evidence proves that the skill owns the complete native workflow;
generic host-authored Codex loops remain blocked. The earlier ARIS run state is
preserved as historical evidence and is not retroactively promoted.

## Run policy

Every full run and recovery uses a fresh physical run id. Existing Topic 4
outputs remain untouched. Recovery attempts are separate observations and are
not silently merged into the synchronized primary view.

As of the audit, GPT and DeepSeek recovery campaigns are progressing through
later frameworks with `REAL_EVAL_CONTINUE_ON_FAILURE=1`. The first Kimi attempt
was stopped after repeated relay timeouts and preserved; a new Kimi recovery
campaign is running. Partial native outcomes are valid evaluation evidence but
missing/invalid root handoffs remain `N/A` for scoring.
