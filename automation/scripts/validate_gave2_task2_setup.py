#!/usr/bin/env python3
from __future__ import annotations

import json
import os
from pathlib import Path

REPO_ROOT = Path(os.environ.get('RESEARCHCLAWEVAL_ROOT', Path(__file__).resolve().parents[2]))
MANIFEST_PATH = REPO_ROOT / 'automation' / 'gave2_task2_manifest.json'
DATASET_ROOT = Path(os.environ.get('GAVE2_DATASET_ROOT', REPO_ROOT / 'data' / 'gave2' / 'task2'))
VISIBLE_SOURCE = Path(
    os.environ.get(
        'GAVE2_DATASET_SOURCE_ROOT',
        os.environ.get('GAVE2_DATASET_ROOT', REPO_ROOT / 'GAVE2_preliminary'),
    )
)

REQUIRED_DATA_COUNTS = {
    'training/images': 50,
    'training/masks': 50,
    'training/FFA_A': 50,
    'training/FFA_AV': 50,
    'training/av': 50,
    'training/biomarker': 50,
    'validation/images': 50,
    'validation/masks': 50,
    'validation/FFA_A': 50,
    'validation/FFA_AV': 50,
}

KEYWORDS = {
    'docs/gave2_task2_summary.md': ['GAVE2 Task 2', 'official score'],
    'docs/gave2_metric_spec.md': ['Score_task2', 'DSC'],
    'docs/gave2_submission_spec.md': ['submission-ready', 'artery', 'vein', 'overlap'],
    'docs/gave2_data_layout.md': ['training/', 'validation/', 'FFA_A', 'FFA_AV'],
    'automation/gave2_task2_contract.md': ['GAVE2-Task2', 'Framework-native entry files'],
    'DeepScientist/DEEPSCIENTIST_BRIEF.md': ['GAVE2 Task 2', 'Cross-Modal FFA-Guided'],
    'Auto-claude-code-research-in-sleep/RESEARCH_BRIEF.md': ['cross-modal retinal artery-vein segmentation', 'Maximize the official GAVE2 Task 2 score'],
    'AI-Scientist-v2/ai_scientist/ideas/gave2_task2_topic.md': ['Cross-Modal FFA-Guided', 'official composite score'],
    'AutoResearchClaw/config.arc.yaml': ['gave2-task2', 'official_task2_score'],
    'EvoScientist/EVOSCIENTIST_BRIEF.md': ['submission-oriented multimodal segmentation project', 'official Task 2 score'],
}


def main() -> int:
    issues: list[str] = []
    findings: dict[str, object] = {}

    if not MANIFEST_PATH.exists():
        raise SystemExit(f'missing manifest: {MANIFEST_PATH}')
    manifest = json.loads(MANIFEST_PATH.read_text(encoding='utf-8'))
    findings['topic_label'] = manifest.get('topic_label')
    findings['dataset_root'] = manifest.get('dataset_root')
    findings['visible_source'] = manifest.get('visible_source')

    files = manifest.get('files', [])
    missing_files = [rel for rel in files if not (REPO_ROOT / rel).exists()]
    if missing_files:
        issues.append(f'missing files: {missing_files}')
    findings['file_count'] = len(files)

    symlink_ok = DATASET_ROOT.exists()
    findings['dataset_root_exists'] = symlink_ok
    findings['dataset_root_is_symlink'] = DATASET_ROOT.is_symlink()
    findings['dataset_root_resolved'] = str(DATASET_ROOT.resolve()) if DATASET_ROOT.exists() else None
    if not DATASET_ROOT.exists():
        issues.append(f'missing dataset root: {DATASET_ROOT}')
    elif DATASET_ROOT.resolve() != VISIBLE_SOURCE.resolve():
        issues.append(f'dataset root does not resolve to visible source: {DATASET_ROOT.resolve()} != {VISIBLE_SOURCE.resolve()}')

    counts = {}
    for rel, expected in REQUIRED_DATA_COUNTS.items():
        path = DATASET_ROOT / rel
        actual = len(list(path.glob('*'))) if path.exists() else -1
        counts[rel] = {'expected': expected, 'actual': actual}
        if actual != expected:
            issues.append(f'count mismatch for {rel}: expected {expected}, got {actual}')
    findings['dataset_counts'] = counts

    keyword_results = {}
    for rel, needles in KEYWORDS.items():
        path = REPO_ROOT / rel
        ok = path.exists()
        text = path.read_text(encoding='utf-8', errors='ignore') if ok else ''
        hits = {needle: (needle in text) for needle in needles}
        keyword_results[rel] = hits
        for needle, present in hits.items():
            if not present:
                issues.append(f'missing keyword in {rel}: {needle}')
    findings['keyword_results'] = keyword_results

    output = {
        'ok': not issues,
        'issues': issues,
        'findings': findings,
    }
    print(json.dumps(output, ensure_ascii=False, indent=2))
    return 0 if output['ok'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
