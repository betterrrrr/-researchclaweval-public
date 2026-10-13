# GAVE2 Data Layout

## Canonical standardized path
`data/gave2/task2`

This path is the normalized dataset root used by the new GAVE2 Task 2 input pack.
In this checkout it points to the visible dataset source `GAVE2_preliminary`.

## Visible local tree
```text
training/
  images/      # 50 CFP images
  masks/       # 50 field-of-view masks
  FFA_A/       # 50 early-phase FFA images
  FFA_AV/      # 50 late-phase / AV-filling FFA images
  av/          # 50 artery-vein labels
  biomarker/   # 50 biomarker txt files

validation/
  images/      # 50 CFP images
  masks/       # 50 field-of-view masks
  FFA_A/       # 50 early-phase FFA images
  FFA_AV/      # 50 late-phase / AV-filling FFA images
```

## Case ID convention
- Current visible cases use `g_001` ... `g_100` style IDs.
- Training split: `g_001` ... `g_050`
- Preliminary visible split: `g_051` ... `g_100`

## Mapping assumptions used in the input pack
- CFP image basename is the primary case key.
- `images/`, `FFA_A/`, and `FFA_AV/` are matched by identical case ID stem.
- Training supervision for artery / vein / overlap is expected from `training/av/`.
- `training/masks/` is treated as field-of-view / valid-region support unless the baseline repo documents otherwise.

## Caveat
The challenge contract includes a blind final split of 50 cases, but those files are not visible in this repository snapshot. The input pack therefore references the official 150-case task contract while documenting that the visible local tree currently exposes 100 cases.
