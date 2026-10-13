# GAVE2 Task 2 Metric Spec

## Official formula
`Score_task2 = 0.3*(0.3*Sen+0.3*Spec+0.4*Acc)+0.4*DSC+0.3*(0.5*Cor+0.5*(1-INF))`

## Components
- `Sen`: sensitivity
- `Spec`: specificity
- `Acc`: accuracy
- `DSC`: Dice similarity coefficient
- `Cor`: artery-vein correctness / consistency term from challenge evaluation
- `INF`: incorrectness / infeasible-topology penalty term from challenge evaluation

## Weighting breakdown
- Classification-quality block:
  - `0.3 * (0.3*Sen + 0.3*Spec + 0.4*Acc)`
- Segmentation-quality block:
  - `0.4 * DSC`
- Structure / AV-consistency block:
  - `0.3 * (0.5*Cor + 0.5*(1-INF))`

## Practical implications
- Optimizing Dice alone is insufficient.
- Thin-vessel continuity, crossings, and artery/vein identity matter.
- A model with high local mask overlap can still lose score through AV confusion or topology breaks.

## Local implementation note
Any local evaluator should at minimum log these six components separately before aggregating the final score.
