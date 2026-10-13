from __future__ import annotations

import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CONFIG = ROOT / 'real_eval/config/seven_gave2_fullrun_frameworks.json'
HELPER = ROOT / 'real_eval/scripts/gave2_framework_fullrun.sh'
VALIDATOR = ROOT / 'real_eval/scripts/validate_framework_run.py'

WRAPPERS = {
    '01': ROOT / 'real_eval/scripts/01_ai_researcher_gave2_task2_fullrun.sh',
    '02': ROOT / 'real_eval/scripts/02_ai_scientist_v2_gave2_task2_fullrun.sh',
    '03': ROOT / 'real_eval/scripts/03_aris_gave2_task2_fullrun.sh',
    '04': ROOT / 'real_eval/scripts/04_autoresearchclaw_gave2_task2_fullrun.sh',
    '05': ROOT / 'real_eval/scripts/05_deepscientist_gave2_task2_fullrun.sh',
    '06': ROOT / 'real_eval/scripts/06_drclaw_gave2_task2_fullrun.sh',
    '07': ROOT / 'real_eval/scripts/07_evoscientist_gave2_task2_fullrun.sh',
}


def test_fullrun_config_has_seven_frameworks():
    data = json.loads(CONFIG.read_text(encoding='utf-8'))
    frameworks = data['frameworks']
    assert len(frameworks) == 7
    assert [item['id'] for item in frameworks] == ['01', '02', '03', '04', '05', '06', '07']


def test_fullrun_wrappers_do_not_ship_explicit_block_reason_placeholders():
    for wrapper in WRAPPERS.values():
        text = wrapper.read_text(encoding='utf-8')
        assert 'FRAMEWORK_BLOCK_REASON=' not in text, f'{wrapper.name} still hard-blocks instead of reusing the BabyLM runtime pattern'


def test_fullrun_ai_researcher_and_ai_scientist_reuse_container_runtime_not_host_stub():
    for key in ['01', '02']:
        text = WRAPPERS[key].read_text(encoding='utf-8')
        assert 'FRAMEWORK_RUNTIME_KIND="docker"' in text, f'{WRAPPERS[key].name} should reuse container runtime'
        assert 'raise SystemExit(0)' not in text, f'{WRAPPERS[key].name} still contains host stub command'


def test_fullrun_ai_researcher_uses_provider_prefixed_litellm_models():
    text = WRAPPERS['01'].read_text(encoding='utf-8')
    assert 'REAL_EVAL_MODEL' in text
    assert 'REAL_EVAL_FRAMEWORK_MODEL' in text
    assert 'AI_RESEARCHER_COMPLETION_MODEL' in text
    assert 'AI_RESEARCHER_CHEAP_MODEL' in text
    assert '--model "$AI_RESEARCHER_COMPLETION_MODEL"' in text


def test_fullrun_ai_scientist_preserves_bfts_artifacts_after_timeout():
    text = WRAPPERS['02'].read_text(encoding='utf-8')
    assert 'AI_SCIENTIST_BFTS_TIMEOUT_SECONDS:-14400' in text
    assert 'bfts_rc=$?' in text
    assert 'BFTS timed out' in text
    assert 'baseline_summary.json' in text
    assert 'research_summary.json' in text


def test_fullrun_ai_scientist_uses_supported_openai_vlm_models_for_review_and_writeup():
    text = WRAPPERS['02'].read_text(encoding='utf-8')
    assert 'AI_SCIENTIST_MODEL="${REAL_EVAL_FRAMEWORK_MODEL:-${REAL_EVAL_MODEL:-gpt-5.4}}"' in text
    assert 'AI_SCIENTIST_VISION_MODEL="${REAL_EVAL_VISION_MODEL:-gpt-4o-2024-11-20}"' in text
    assert '--model $AI_SCIENTIST_MODEL' in text
    assert '--model_review_vision $AI_SCIENTIST_VISION_MODEL' in text
    assert '--vision-model $AI_SCIENTIST_VISION_MODEL' in text


def test_fullrun_autoresearchclaw_accepts_packaged_deliverables_after_late_paper_failure():
    text = WRAPPERS['04'].read_text(encoding='utf-8')
    assert 'arc_rc=$?' in text
    assert 'deliverables/manifest.json' in text
    assert 'pipeline_summary.json' in text
    assert 'AutoResearchClaw returned non-zero after packaging deliverables' in text


def test_fullrun_validator_tracks_gave2_metric_artifacts(tmp_path):
    run_root = tmp_path / 'run'
    artifacts = run_root / 'workspace/project/artifacts'
    logs = run_root / 'logs'
    artifacts.mkdir(parents=True)
    logs.mkdir()
    (run_root / 'fullrun_manifest.json').write_text('{}\n', encoding='utf-8')
    (run_root / 'state.json').write_text('{"status": "finished"}\n', encoding='utf-8')
    (logs / 'e2e.log').write_text('finished\n', encoding='utf-8')
    (artifacts / 'results_refined.json').write_text(json.dumps({
        'baseline': {
            'name': 'baseline_se_unet_refined',
            'best_val': {
                'vessel_dice': 0.766663934099121,
                'av_macro_f1': 0.18537791391710864,
                'official_composite_score': 0.47602092400811485,
            },
        },
        'fgse': {
            'name': 'fgse_unet_refined',
            'best_val': {
                'vessel_dice': 0.9504241632256429,
                'av_macro_f1': 0.16794858828764522,
                'official_composite_score': 0.5591863757566441,
            },
        },
    }), encoding='utf-8')

    completed = subprocess.run([
        'python3',
        str(VALIDATOR),
        '--framework',
        'gave2_fullrun',
        '--run-root',
        str(run_root),
        '--state-file',
        str(run_root / 'state.json'),
    ], check=True, text=True, capture_output=True)

    manifest = json.loads(completed.stdout)
    metrics = manifest['evidence']['gave2_metrics']
    assert metrics['source'] == 'workspace/project/artifacts/results_refined.json'
    assert metrics['best_model'] == 'fgse_unet_refined'
    assert metrics['models']['fgse_unet_refined']['official_composite_score'] == 0.5591863757566441
    assert metrics['models']['baseline_se_unet_refined']['official_composite_score'] == 0.47602092400811485
    assert set(metrics['models']) == {'baseline_se_unet_refined', 'fgse_unet_refined'}

    state = json.loads((run_root / 'state.json').read_text(encoding='utf-8'))
    assert state['gave2_metrics']['best_model'] == 'fgse_unet_refined'


def test_fullrun_helper_supports_repo_relative_path_rewrite_and_docker_tuning():
    text = HELPER.read_text(encoding='utf-8')
    required_markers = [
        'FRAMEWORK_CONTAINER_WORKDIR',
        'FRAMEWORK_DOCKER_ARGS',
        'FRAMEWORK_ENTRYPOINT',
        'repo_basename',
        'workspace_rel',
        'RESEARCHCLAWEVAL_HOST_WORKSPACE',
        '/baseline_repo',
    ]
    for marker in required_markers:
        assert marker in text, f'helper missing required fullrun feature: {marker}'


def test_fullrun_codex_based_wrappers_request_root_or_explicit_entrypoint_when_needed():
    assert 'FRAMEWORK_DOCKER_ARGS' in WRAPPERS['03'].read_text(encoding='utf-8')
    assert 'FRAMEWORK_DOCKER_ARGS' in WRAPPERS['05'].read_text(encoding='utf-8')
    assert 'FRAMEWORK_DOCKER_ARGS' in WRAPPERS['06'].read_text(encoding='utf-8')
    evo_text = WRAPPERS['07'].read_text(encoding='utf-8')
    assert 'FRAMEWORK_ENTRYPOINT="bash"' in evo_text
    assert 'EVOSCIENTIST_MODEL="${REAL_EVAL_FRAMEWORK_MODEL:-${REAL_EVAL_MODEL:-gpt-5.4}}"' in evo_text
    assert 'model: ${EVOSCIENTIST_MODEL}' in evo_text


def test_fullrun_topic_driven_wrappers_read_real_prompt_files_not_empty_shell_substitutions():
    auto_text = WRAPPERS['04'].read_text(encoding='utf-8')
    evo_text = WRAPPERS['07'].read_text(encoding='utf-8')
    ai_researcher_text = WRAPPERS['01'].read_text(encoding='utf-8')
    assert 'cat topic.txt' in auto_text or 'tr "\\n" " " < topic.txt' in auto_text
    assert 'cat gave2_task2_start_message.txt' in evo_text
    assert 'RESEARCHCLAWEVAL_AI_RESEARCHER_HOST_REPO' in ai_researcher_text
    assert 'container_name gave2_task2_eval_\\${REAL_EVAL_RUN_ID}' in ai_researcher_text


def test_gave2_snapshot_purges_babylm_residue_from_clean_workspace(tmp_path):
    src = tmp_path / 'src'
    dst = tmp_path / 'dst'
    (src / 'ai_scientist/ideas').mkdir(parents=True)
    (src / 'scripts').mkdir(parents=True)
    (src / 'runs').mkdir(parents=True)
    (src / 'keep').mkdir(parents=True)
    (src / 'ai_scientist/ideas/babylm_10m_strict_small_topic.md').write_text('old topic', encoding='utf-8')
    (src / 'scripts/run_babylm_native_e2e.sh').write_text('#!/usr/bin/env bash\n', encoding='utf-8')
    (src / 'runs/babylm_native_e2e.log').write_text('old log', encoding='utf-8')
    (src / 'Dockerfile.ngc-babylm').write_text('FROM scratch\n', encoding='utf-8')
    (src / 'keep/gave2_topic.md').write_text('new topic', encoding='utf-8')

    cmd = f"""
set -euo pipefail
source {ROOT}/real_eval/scripts/lib_real_eval.sh
real_eval_rsync_repo {src} {dst}
real_eval_purge_cross_topic_residue {dst} gave2
"""
    subprocess.run(['bash', '-lc', cmd], check=True)

    assert (dst / 'keep/gave2_topic.md').exists()
    assert not (dst / 'ai_scientist/ideas/babylm_10m_strict_small_topic.md').exists()
    assert not (dst / 'scripts/run_babylm_native_e2e.sh').exists()
    assert not (dst / 'runs/babylm_native_e2e.log').exists()
    assert not (dst / 'Dockerfile.ngc-babylm').exists()


def test_gave2_generated_contract_files_do_not_embed_host_checkout_paths():
    generated_files = [
        ROOT / 'automation/gave2_task2_contract.md',
        ROOT / 'automation/gave2_task2_manifest.json',
        ROOT / 'docs/gave2_data_layout.md',
        ROOT / 'docs/gave2_task2_summary.md',
    ]
    forbidden = ['/home/' + 'guang' + 'hao/researchclaweval', str(ROOT)]
    for path in generated_files:
        text = path.read_text(encoding='utf-8')
        for marker in forbidden:
            assert marker not in text, f'{path.relative_to(ROOT)} embeds host path {marker}'
