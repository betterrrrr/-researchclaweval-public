#!/usr/bin/env bash
# Fix the 3 scripts that lost their TRACE block
TRACE_BLOCK=$(cat <<'TRACEBLOCK'

# Patch experiment_trace.json with correct environment values
echo "DEEPSCIENTIST_PATCHING_TRACE"
if [[ -f /workspace/experiment_trace.json ]]; then
  python3 -c "
import json, os
p = '/workspace/experiment_trace.json'
d = json.loads(open(p).read())
d['framework_internal_model'] = os.environ.get('OPENAI_MODEL', d.get('framework_internal_model', ''))
d['framework_internal_api_base_url'] = os.environ.get('OPENAI_BASE_URL', d.get('framework_internal_api_base_url', ''))
open(p, 'w').write(json.dumps(d, indent=2, ensure_ascii=False))
print(f'Patched experiment_trace.json: model={d[\"framework_internal_model\"]} url={d[\"framework_internal_api_base_url\"]}')
"
fi
TRACEBLOCK
)

for script in 05_deepscientist_arc_wbe_2026_fullrun.sh 05_deepscientist_psydefdetect_fullrun.sh 05_deepscientist_tdc_admet_tox_fullrun.sh; do
  f="${RESEARCHCLAWEVAL_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}/real_eval/scripts/$script"
  # Insert TRACE_BLOCK before the last "fi\nEOF" pattern
  sed -i '/^fi$/{
    /^fi$/!b
    :a;n;/^EOF$/!ba
    i\
'"$TRACE_BLOCK"'
  }' "$f"
  echo "$script: patched"
done