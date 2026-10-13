from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CONFIG = ROOT / 'real_eval/config/seven_gave2_smoke_frameworks.json'
RUNNER = ROOT / 'real_eval/scripts/run_seven_serial_gave2_smoke.sh'
PREFLIGHT = ROOT / 'real_eval/scripts/preflight_seven_serial_gave2_smoke.sh'
REGISTRY = ROOT / 'real_eval/docs/gave2_smoke_test_register.md'

EXPECTED = {
    '01': ('AI-Researcher', 'real_eval/scripts/01_ai_researcher_gave2_task2_smoke.sh', '/workspace/AI-Researcher/data/gave2/task2'),
    '02': ('AI-Scientist-v2', 'real_eval/scripts/02_ai_scientist_v2_gave2_task2_smoke.sh', '/workspace/data/gave2/task2'),
    '03': ('ARIS', 'real_eval/scripts/03_aris_gave2_task2_smoke.sh', '/work/data/gave2/task2'),
    '04': ('AutoResearchClaw', 'real_eval/scripts/04_autoresearchclaw_gave2_task2_smoke.sh', '/workspace/AutoResearchClaw/data/gave2/task2'),
    '05': ('DeepScientist', 'real_eval/scripts/05_deepscientist_gave2_task2_smoke.sh', '/workspace/data/gave2/task2'),
    '06': ('Dr. Claw', 'real_eval/scripts/06_drclaw_gave2_task2_smoke.sh', '/home/evosci/dr-claw/smoke-gave2/data/gave2/task2'),
    '07': ('EvoScientist', 'real_eval/scripts/07_evoscientist_gave2_task2_smoke.sh', '/workspace/data/gave2/task2'),
}

FORBIDDEN = ['resume', 'source_run', 'source-run', 'run_framework_babylm_proxy', 'placeholder results']


def test_smoke_contract_files_exist():
    missing = [str(p) for p in [CONFIG, RUNNER, PREFLIGHT, REGISTRY] if not p.exists()]
    assert not missing, f'missing smoke contract files: {missing}'


def test_smoke_config_has_seven_frameworks_and_uses_gave2_smoke_validator():
    data = json.loads(CONFIG.read_text(encoding='utf-8'))
    frameworks = data['frameworks']
    assert len(frameworks) == 7
    ids = [item['id'] for item in frameworks]
    assert ids == list(EXPECTED.keys())
    for item in frameworks:
        name, wrapper, _ = EXPECTED[item['id']]
        assert item['name'] == name
        assert item['wrapper'] == wrapper
        assert item['validator'] == 'gave2_smoke'


def test_smoke_wrappers_exist_and_block_old_patterns():
    for _, (_, wrapper_rel, _) in EXPECTED.items():
        wrapper = ROOT / wrapper_rel
        assert wrapper.exists(), f'missing wrapper: {wrapper_rel}'
        text = wrapper.read_text(encoding='utf-8')
        lowered = text.lower()
        for marker in FORBIDDEN:
            assert marker not in lowered, f'{wrapper_rel} contains forbidden marker: {marker}'


def test_smoke_wrappers_include_workspace_local_dataset_mounts():
    for _, (_, wrapper_rel, dataset_mount) in EXPECTED.items():
        wrapper = ROOT / wrapper_rel
        text = wrapper.read_text(encoding='utf-8')
        assert '/data/gave2/task2:ro' in text, f'{wrapper_rel} missing shared dataset mount'
        assert dataset_mount in text, f'{wrapper_rel} missing workspace dataset mount {dataset_mount}'
        assert 'automation/gave2_task2_contract.md' in text or '/input/contract.md' in text


def test_runner_references_smoke_preflight_and_config():
    text = RUNNER.read_text(encoding='utf-8')
    assert 'seven_gave2_smoke_frameworks.json' in text
    assert 'preflight_seven_serial_gave2_smoke.sh' in text
    assert 'gave2_smoke' in (CONFIG.read_text(encoding='utf-8'))


def test_register_tracks_red_green_targets():
    text = REGISTRY.read_text(encoding='utf-8')
    for needle in [
        '旧 workspace / old topic 混入',
        'dataset 仅挂到 /data',
        'Dr. Claw 依赖与路径假设',
        'EvoScientist phase2 / CUDA 路线',
        '状态',
    ]:
        assert needle in text
