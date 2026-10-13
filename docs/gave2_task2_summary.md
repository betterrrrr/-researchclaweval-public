# GAVE2 Task 2 Summary

## Goal
Optimize GAVE2 Task 2 official score for cross-modal retinal artery-vein segmentation.

## Official task framing
- Input per case:
  - 1 CFP image
  - 1 early-phase FFA image (`FFA_A`)
  - 1 late-phase / arteriovenous-filling FFA image (`FFA_AV`)
- Prediction target on CFP:
  - artery mask
  - vein mask
  - overlap mask

## Official split contract
- 50 train
- 50 preliminary leaderboard
- 50 final blind evaluation

## Local repository status
- Standardized local path: `data/gave2/task2`
- Current visible local copy comes from `GAVE2_preliminary`
- Visible files confirmed locally:
  - `training/`: 50 CFP + 50 masks + 50 FFA_A + 50 FFA_AV + 50 av + 50 biomarker
  - `validation/`: 50 CFP + 50 masks + 50 FFA_A + 50 FFA_AV
- Therefore this repo currently materializes the train split plus the preliminary visible split.
- The blind final split is part of the challenge contract but is not present as visible files in this checkout.

## Optimization target
- Task 2 is the core task.
- Overall challenge weighting: Task 2 contributes 0.4 to the total score.
- Primary objective: maximize Task 2 official score, not generic novelty.

## Shared references
- Metric spec: `docs/gave2_metric_spec.md`
- Submission spec: `docs/gave2_submission_spec.md`
- Data layout: `docs/gave2_data_layout.md`
