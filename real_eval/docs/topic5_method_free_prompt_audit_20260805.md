# Topic 5 (TDC-ADMET-Tox) Method-Free Prompt Audit

Campaign date: 2026-08-05 (ds variant, model deepseek-v4-flash)

## Audit conclusion

The shared Topic 5 input generator (`automation/scripts/generate_tdc_admet_tox_native_inputs.py`)
prescribed concrete methods in the runtime brief and framework adapters until 2026-08-05.
All prescription text has been removed and the generator now emits only host-permitted
constraints. Affected runs dispatched before this audit are contaminated and must be
re-run under the method-free inputs.

| Prompt source | Previous prescribed content | Status |
|---|---|---|
| RUNTIME_BRIEF (all frameworks) | "Prefer classical ML (logistic regression, gradient boosting, random forest, TF-IDF/feature-based descriptors) over deep learning" | Removed |
| RUNTIME_BRIEF hard order | "(1) build a fast classical-ML baseline that finishes in minutes" | Removed |
| AI-Researcher metaprompt HARD_PLAN | "fast classical-ML baseline (TF-IDF or fingerprint features with logistic regression / random forest / gradient boosting)" | Removed |
| AI-Researcher metaprompt EVALUATION | "prefer classical ML over slow deep training" | Removed |
| AI-Scientist-v2 topic | "fast classical-ML baseline first (logistic regression / random forest / gradient boosting on TF-IDF or fingerprint features)" | Removed |
| AutoResearchClaw dataset_schema_hint | "Featurize the smiles column (e.g. char n-gram TF-IDF)" | Removed |
| Contract / execution budget / per-framework wrappers | no algorithm-family language found | Clean |

## Frozen method-free policy

The host now fixes only: the TDC-ADMET-Tox question (AMES/hERG/DILI), the visible
long-format data schema and train/validation/test split, the official metric
(unweighted macro average of endpoint AUROCs), compute/wall-clock/request budgets,
the 2-to-4 experiment count range, one validation candidate per configuration,
installed dependency and network policy, the scorer/validator CLIs, and the root
artifact schema (predictions.csv, experiment_trace.json, environment.json,
paper.md + claims). The framework owns the hypothesis, method choice, feature
representation, architecture, hyperparameters, experiment rationale, comparison,
and final selection. Method names that appear in framework-authored artifacts
(research_idea.json, experiment_trace.json) are framework decisions, not host
prescriptions.

Verified: `generate_tdc_admet_tox_native_inputs.py` AST parses; RUNTIME_BRIEF,
AI-Researcher metaprompt, AI-Scientist-v2 topic, and AutoResearchClaw config
contain no TF-IDF / fingerprint / logistic / random-forest / gradient-boosting /
SVC / SGDClassifier / "classical ML" / "prefer classical" terms.

## Contamination scope

All Topic 5 ds-variant runs dispatched before this audit used the prescribed
generator and are non-admissible as method-free primary results. This includes
01 (0.7782), 03 (0.7991), 04 (blocked), 05 (0.8380), 06 (0.8047), 07 (0.7821),
and the failed 02 run. Re-run each framework under the cleaned generator with a
fresh run id; prior runs are preserved as evaluation data but excluded from the
method-free ranking.

## Re-run policy

Fresh physical run ids and workspaces; no reuse or backfill of prior artifacts.
Framework `research_idea.json` must predate the first experiment and record the
framework's own hypothesis and method rationale.

## Method-free re-run results (2026-08-06)

Serial re-run under cleaned inputs, one fresh attempt per framework (01 and 06
needed one retry each; 02 and 04 are framework-failures, see notes). Scores are
host-computed macro-average AUROC over the hidden test labels.

| Framework | Previous (contaminated) | Method-free | Experiments | Run id suffix | Notes |
|---|---|---|---|---|---|
| 01 AI-Researcher | 0.7782 | **0.7868** | 4 | mf-01_ai_researcher-20260806-032549 | 1st attempt (20260805-235944) failed audit: trace `config_file` used glob `runs/config_001_*`; retry succeeded |
| 02 AI-Scientist-v2 | failed | **failed** | - | mf-02_ai_scientist_v2-20260805-235944 | Same failure twice (contaminated + method-free): no root predictions.csv after BFT tree search timeout; framework-failure, not prompt-related |
| 03 ARIS | 0.7991 | **0.8041** | 3 | mf-03_aris-20260805-235944 | passed |
| 04 AutoResearchClaw | blocked | blocked | - | - | Framework finalize code ignores dataset schema hint (hardcoded 5-field trace); blocked, not re-run |
| 05 DeepScientist | 0.8380 | **0.8235** | 3 | mf-05_deepscientist-20260805-235944 | Native run + audit passed; host wrapper `du` numeric bug (fixed in `tdc_admet_tox_framework_fullrun.sh`) prevented state.json; state completed from preserved run evidence |
| 06 Dr. Claw | 0.8047 | **0.8493** | 4 | mf-06_drclaw-20260806-032549 | 1st attempt (20260805-235944) failed audit: trace `resource_budget` missing `network_policy` key; retry succeeded |
| 07 EvoScientist | 0.7821 | **0.7903** | 3 | mf-07_evoscientist-20260805-235944 | passed |

Host-side fix applied: `real_eval/scripts/tdc_admet_tox_framework_fullrun.sh`
lines 468-470 now sanitize `du -sk` output before the numeric budget comparison
(previously failed `[[ ... -gt ... ]]` and skipped state.json writing).
