# PsyDefDetect Framework Comparison Notes

Updated: 2026-08-05

## Current Interpretation

The current Topic 4 framework comparison is a **best-completed-native-observation / capability-ceiling view**, not a synchronized fixed-budget ranking.

The retained observations come from different recovery runs, model/provider campaigns, experiment counts, and runtime histories. They must therefore remain separated by evaluation model and labeled with their recovery history. A missing score means `N/A`, not zero.

## Native Admission

Only a result with all of the following is eligible for the strict native table:

- framework state and artifact manifest report `finished` with no validation warnings;
- `experiment_trace.json` sets `framework_native_execution: true` and records the effective model/provider;
- the manifest records the documented native entrypoint;
- the entrypoint is visible in the framework e2e log;
- root-level predictions, score, trace, and final report exist.

Older artifacts that have scores but lack runtime entrypoint or provider evidence are retained as historical observations and excluded from strict native ranking.

## Known Gap

AutoResearchClaw (framework 04) has no currently accepted strict-native completion for the DeepSeek or Kimi campaigns. The latest DeepSeek recovery failed in native Stage 10 code generation after upstream timeouts and scorer-placeholder validation. An older GPT run produced artifacts and a trace but predates the current manifest entrypoint evidence gate, so it is historical-only.

## Required Follow-up

Run a synchronized comparison campaign when fairness is required:

- fix one model/provider version across all seven frameworks;
- use the same fresh dataset projection, runtime limit, API/turn budget, and 2-4 experiment allowance;
- submit every framework once through its documented native entrypoint;
- report `research_completed`, `scored`, `contract_complete`, `engineering_complete`, budget exhaustion, runtime, and score separately;
- keep a separate capability-ceiling table for expanded-budget recovery runs.

The synchronized campaign is the basis for a fair framework ranking. The current ceiling table is useful for capability coverage and best-observed performance, but must not be presented as a controlled causal comparison.
