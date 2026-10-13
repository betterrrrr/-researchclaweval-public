#!/usr/bin/env bash
set -euo pipefail
ROOT="${RESEARCHCLAWEVAL_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
source "$ROOT/real_eval/scripts/lib_real_eval.sh"
echo "[BLOCKED] Topic2 (GAVE2-Task2) is blocked for framework04 (AutoResearchClaw). This wrapper is retained for historical evidence only; no dispatch permitted." >&2
exit 75
export FRAMEWORK_NAME="AutoResearchClaw"
export FRAMEWORK_SLUG="04_autoresearchclaw_gave2_task2_fullrun"
export FRAMEWORK_SRC="$(real_eval_resolve_framework_source "$ROOT" 04)"
export FRAMEWORK_ENTRY_PATHS=$(cat <<'EOF'
AutoResearchClaw/config.arc.yaml
AutoResearchClaw/topic.txt
real_eval/scripts/lib_autoresearchclaw_handoff.sh
docs/gave2_task2_summary.md
docs/gave2_metric_spec.md
docs/gave2_submission_spec.md
docs/gave2_data_layout.md
automation/gave2_task2_contract.md
EOF
)
export FRAMEWORK_RUNTIME_KIND="docker"
export FRAMEWORK_RUNTIME_IMAGE="autoresearchclaw:runtime-opencode"
export FRAMEWORK_ENTRYPOINT="bash"
export FRAMEWORK_RUNTIME_COMMAND=$(cat <<'EOF'
set -euo pipefail
ROOT="${ROOT:-/workspace}"
cp config.project4.yaml config.gave2.yaml
python3 - <<'PY'
import re
from pathlib import Path
p = Path('config.gave2.yaml')
s = p.read_text(encoding='utf-8')
s = s.replace('project4-autoresearchclaw', 'gave2-task2-autoresearchclaw')
s = s.replace('project4', 'gave2-task2')
s = re.sub(r'BabyLM-10M topic\..*?for task packaging and dispatch\.', 'GAVE2 Task 2 multimodal retinal artery-vein segmentation. Use dataset root /workspace/data/gave2/task2 and follow automation/gave2_task2_contract.md together with docs/gave2_metric_spec.md and docs/gave2_submission_spec.md for execution and packaging.', s, flags=re.S)
s = s.replace('- "machine-learning"', '- "medical-imaging"')
s = s.replace('time_budget_sec: 120', 'time_budget_sec: 86400')
s = s.replace('max_iterations: 2', 'max_iterations: 8')
s = s.replace('gpu_required: false', 'gpu_required: true')
s = s.replace('tree_search_enabled: false', 'tree_search_enabled: true')
s = s.replace('tree_search_candidates: 1', 'tree_search_candidates: 3')
s = s.replace('tree_search_max_depth: 1', 'tree_search_max_depth: 2')
s = s.replace('network_policy: "none"', 'network_policy: "restricted"')
p.write_text(s, encoding='utf-8')
PY
topic="$(cat topic.txt | tr '\n' ' ')"
source real_eval/scripts/lib_autoresearchclaw_handoff.sh
apply_autoresearchclaw_stage8_idea_lock_adapter "/workspace"
idea_provenance_contract="Before the first experiment, have the native Stage 8 synthesis write the framework-authored research_idea.json and research_idea_lock_event.json. The lock event must identify AutoResearchClaw as the framework writer, bind the finalized artifact SHA256, and carry a timezone-aware timestamp. Record research_idea.json, idea_locked_before_experiments=true, and first_experiment_started_at in experiment_trace.json."
artifact_root="artifacts/gave2-task2-${REAL_EVAL_RUN_ID}"
set +e
python3 -m researchclaw.cli run \
  --config config.gave2.yaml \
  --topic "$topic $idea_provenance_contract" \
  --output "$artifact_root" \
  --auto-approve
arc_rc=$?
set -e
if [[ "$arc_rc" -ne 0 ]]; then
  exit "$arc_rc"
fi
autoresearchclaw_handoff gave2_task2 /workspace "$artifact_root"
verify_framework_research_idea_json "/workspace"
EOF
)
exec "$ROOT"/real_eval/scripts/gave2_framework_fullrun.sh
