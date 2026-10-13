# PsyDefDetect Summary

## Topic
- Topic id: `psydefdetect`
- Topic label: `PsyDefDetect`
- Dataset root: `$PSYDEFDETECT_DATASET_ROOT`
- Contract file: `automation/psydefdetect_contract.md`

## Objective
Detect levels of psychological defense mechanisms in supportive conversations.

## Input
For each target help-seeker utterance, use the target utterance and its preceding conversation context.

## Labels
The task uses DMRS-inspired defense mechanism levels plus two auxiliary classes:

- `0`: No Defense
- `1`: Action Defenses
- `2`: Major Image-Distorting
- `3`: Disavowal
- `4`: Minor Image-Distorting
- `5`: Neurotic
- `6`: Obsessional
- `7`: High-Adaptive
- `8`: Needs More Information

## Primary Metric
The official score is macro-F1 over positive classes 1-8. Class `0` is excluded from the official macro-F1 calculation.

## Expected Deliverables
- prediction artifact for the evaluation split
- score artifact or reproducible scoring command
- `final_report.md`
- logs and workspace traces
