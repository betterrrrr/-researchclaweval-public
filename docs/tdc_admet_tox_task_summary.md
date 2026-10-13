# TDC-ADMET-Tox Task Summary

TDC-ADMET-Tox is a three-endpoint binary molecular property prediction task covering mutagenicity (`AMES`), cardiac ion-channel liability (`hERG`), and drug-induced liver injury (`DILI`). Each row is an immutable molecule record identified by `sample_id`, represented by a canonical input SMILES string, and assigned to exactly one endpoint.

The research framework receives labeled training and validation data and unlabeled final-test structures. It may complete 2 to 4 model or feature configurations, then must select one approach using validation evidence. After the framework exits, a host-only scorer joins `predictions.csv` to hidden test labels and computes the leaderboard result.

The main score is the unweighted macro average of endpoint AUROC values. AUPRC, Brier score, 10-bin expected calibration error, runtime, and reproducibility are retained as secondary evidence but do not change the main ranking.

The task is designed to run offline after dataset materialization. External structure lookup, web access, runtime model downloads, and access to hidden labels are prohibited.

