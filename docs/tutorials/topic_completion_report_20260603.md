# Topic Completion Report

Date: 2026-06-03

Scope:

- Topic source: `collected_paper_pdfs_20260603_by_topic/`
- Evidence source: current repository artifacts under the seven agent workspaces.
- Completion is judged from files that exist now, not from paper quality.

Stage scale:

- `idea`: idea, brief, proposal, or research topic exists.
- `experiment`: runnable code, metrics, evaluation JSON, plots, or run manifest exists.
- `report`: Markdown/LaTeX writeup or final report exists.
- `PDF`: compiled paper PDF exists.

## Topic-Level Completion

| Topic | Current stage | Evidence | Judgment |
|---|---:|---|---|
| BabyLM and sample-efficient language modeling | PDF | `AI-Scientist-v2/experiments/2026-06-01_10-40-10_forgetting_weighted_loss_attempt_0/idea.md`, `experiment_results/.../experiment_code.py`, `logs/0-run/research_summary.json`, 3 PDFs under `collected_paper_pdfs_20260603_by_topic/01_babylm_and_sample_efficient_language_modeling/` | This topic reached idea, experiment, writeup, and compiled PDF in AI-Scientist-v2. The current shared BabyLM-10M harness also reached experiment/report stages across multiple other agents, but mostly as Markdown/JSON rather than PDF. |
| Tiny sklearn classification and feature weighting | PDF | AI-Researcher `paper_agent/tiny_cls/target_sections/digits_iris_light/iclr2025_conference.pdf` plus `metrics.json`; AI-Scientist-v2 bootstrap experiment PDFs plus `idea.md`; ARIS `paper/main.pdf` | Completed through experiments and PDF papers. This is mostly earlier runtime verification / lightweight benchmark work, not the current BabyLM target. |
| Compositional generalization | PDF | `AI-Scientist-v2/experiments/2026-04-28_22-42-22_compositional_regularization_nn_attempt_0/idea.md`, experiment result plots/code, `logs/0-run/research_summary.json`, and compiled PDF | Completed through idea, experiment, and PDF. The paper itself reports a negative result. |
| Graph learning and recommendation | PDF | AI-Researcher example PDFs for DCCF, HGCL, NodeFormer, and Difformer; some example directories also include experiment/result JSON files | Completed to PDF as AI-Researcher example papers. Evidence is strongest for NodeFormer/Difformer because their directories contain result JSON; DCCF/HGCL mainly have final paper PDFs in the collected set. |
| Generative modeling, flows, and quantization | PDF | AI-Researcher example PDFs for continuous normalizing flows, FSQ, and rotation VQ; FSQ/rotation VQ include training/result JSON files | Completed to PDF as AI-Researcher example papers. |
| Random matrix spectral statistics | PDF | `AutoResearchClaw_paper_I_random_matrix.pdf` | Completed to PDF as an AutoResearchClaw showcase paper. Current repo evidence for this topic is primarily the final PDF, not a full local run directory. |
| Weak-IV / econometrics / causal estimators | PDF | `AutoResearchClaw_paper_II_weak_iv_estimators.pdf` | Completed to PDF as an AutoResearchClaw showcase paper. Current repo evidence for this topic is primarily the final PDF. |
| SIR/SEIR epidemic model identifiability | PDF | `AutoResearchClaw_paper_III_sir_seir_identifiability.pdf` | Completed to PDF as an AutoResearchClaw showcase paper. |
| Krylov preconditioners / sparse linear systems | PDF | `AutoResearchClaw_paper_IV_krylov_preconditioners.pdf` | Completed to PDF as an AutoResearchClaw showcase paper. |
| Vision model efficiency and distillation | PDF | `AutoResearchClaw_paper_VII_fame_token_merging.pdf`, `AutoResearchClaw_paper_VIII_craft_distillation.pdf` | Completed to PDF as AutoResearchClaw showcase papers. |
| Reinforcement learning exploration | PDF | `AutoResearchClaw_paper_VI_lace_exploration.pdf` | Completed to PDF as an AutoResearchClaw showcase paper. |
| LoRA and LLM fine-tuning | PDF | `AutoResearchClaw_paper_V_gard_lora.pdf` | Completed to PDF as an AutoResearchClaw showcase paper. |
| AI-generated text detection | PDF | DeepScientist case PDFs `DS_TDT.pdf` and `DS_T_Detect.pdf` | Completed to PDF as DeepScientist case papers. |
| Multi-agent failure attribution | PDF | DeepScientist case PDF `DS_A2P.pdf` | Completed to PDF as a DeepScientist case paper. |

## Current BabyLM-10M Agent Runtime

This is separate from the collected PDF topics above. It reflects the current BabyLM-10M automation artifacts.

| Agent | Current BabyLM stage | Evidence | Notes |
|---|---:|---|---|
| 01 AI-Researcher | experiment + report | `AI-Researcher/workplace_paper/task_babylm_10m_gpt-5.4/workplace/workplace/project/run_manifest.json`, `eval/proxy_strict_small_eval.json`, `reports/proxy_report.md` | Has baseline and improved proxy scores, but no BabyLM PDF in the current run. |
| 02 AI-Scientist-v2 | paper PDF for separate BabyLM idea | `AI-Scientist-v2/experiments/2026-06-01_10-40-10_forgetting_weighted_loss_attempt_0/` | Has idea, synthetic BabyLM experiment artifacts, writeup, and PDFs. It is not represented in `automation/state/projects/*.json` for the current chain. |
| 03 ARIS | brief + experiment + report | `Auto-claude-code-research-in-sleep/.aris-codex-project/RESEARCH_BRIEF.md`, `babylm_proxy/run_manifest.json`, `babylm_proxy/reports/proxy_report.md` | Reached report stage, no BabyLM PDF. |
| 04 AutoResearchClaw | Markdown paper/final verified draft | `AutoResearchClaw/artifacts/project4-e2e/pipeline_summary.json`, `stage-23/paper_final_verified.md` | Artifact summary says stages 17-23 completed with `final_status: done`; no compiled PDF found for this BabyLM run. |
| 05 DeepScientist | brief + experiment + final report | `DeepScientist/.deepscientist_home/quests/001/brief.md`, `babylm_proxy/run_manifest.json`, `paper/final_report.md` | Reached final-report Markdown, no BabyLM PDF. |
| 06 dr-claw | experiment + publication Markdown | `dr-claw/.runtime-home/user/dr-claw/babylm-10m-project-e2e-remediated/Experiment/babylm_proxy/run_manifest.json`, `Publication/paper/main.md` | Reached publication Markdown, no BabyLM PDF. |
| 07 EvoScientist | experiment + final report | `EvoScientist/workspace/babylm_proxy/run_manifest.json`, `EvoScientist/workspace/final_report.md` | Reached final-report Markdown, no BabyLM PDF. |

## Overall Read

- All 14 topic buckets in `collected_paper_pdfs_20260603_by_topic/` have at least one compiled PDF because that directory was built from paper PDFs.
- The strongest end-to-end evidence is in topics where the repo also contains idea files and experiment artifacts: BabyLM/AI-Scientist-v2, tiny sklearn classification, compositional generalization, and several AI-Researcher example topics.
- The AutoResearchClaw and DeepScientist showcase/case topics are complete to PDF, but the local evidence in this repo is mostly final paper PDFs rather than full preserved run logs.
- For the current seven-agent BabyLM-10M chain, most agents reached experiment plus report/paper Markdown. Only the AI-Scientist-v2 BabyLM-related experiment has compiled PDFs in the current collected set.
