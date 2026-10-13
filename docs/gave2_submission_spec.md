# GAVE2 Task 2 Submission Spec

## Required output per case
For each CFP case, generate:
- artery mask
- vein mask
- overlap mask

## Packaging target
Produce a submission-ready folder that can be transformed into the official upload package without extra manual relabeling.

## Naming and structure policy used in this repo
Until the official organizer packaging script is added, keep outputs under a deterministic structure such as:

```text
submission/
  case_id/
    artery.png
    vein.png
    overlap.png
```

or an equivalent flat structure documented by the framework run.

## Hard requirements
- every required case must have a prediction
- outputs must be reproducible from a single inference command
- any post-processing used for submission must be scripted
- do not mix training labels into leaderboard/final prediction folders

## Validation checklist before upload
- all required case IDs present
- output image sizes match CFP target canvas
- binary / label encoding is consistent across all cases
- no empty submission folder
- final run records checkpoint path, inference command, and output root

## Challenge-score alignment
A valid submission is not enough. The preferred packaging preserves artery / vein separation and overlap consistency because the official score is `0.3*(0.3*Sen+0.3*Spec+0.4*Acc)+0.4*DSC+0.3*(0.5*Cor+0.5*(1-INF))`.
