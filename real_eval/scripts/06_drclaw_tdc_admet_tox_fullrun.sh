#!/usr/bin/env bash
set -euo pipefail

ROOT="${RESEARCHCLAWEVAL_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
source "$ROOT/real_eval/scripts/lib_real_eval.sh"
export FRAMEWORK_NAME="Dr. Claw"
export FRAMEWORK_SLUG="06_drclaw_tdc_admet_tox_fullrun"
export FRAMEWORK_SRC="$(real_eval_resolve_framework_source "$ROOT" 06)"
export FRAMEWORK_ENTRY_PREFIX="dr-claw"
export FRAMEWORK_ENTRY_PATHS=$(cat <<'EOF'
dr-claw/TDC_ADMET_TOX_BRIEF.md
dr-claw/dr_claw_benchmark_authorization.md
automation/tdc_admet_tox_contract.md
automation/tdc_admet_tox_execution_budget.md
EOF
)
export FRAMEWORK_RUNTIME_IMAGE="${DRCLAW_RUNTIME_IMAGE:-dr-claw:runtime-ready}"
export FRAMEWORK_DOCKER_ARGS=$(cat <<'EOF'
--user
0:0
EOF
)
export FRAMEWORK_NATIVE_ENTRYPOINT="node server/cli.js chat --model ${TDC_ADMET_TOX_EVAL_MODEL:-gpt-5.4}"
export FRAMEWORK_NATIVE_ENTRYPOINT_FILE="server/cli.js"
export FRAMEWORK_NATIVE_ENTRYPOINT_SOURCE="README.md"
export FRAMEWORK_PROVIDER_INJECTION="Dr. Claw CLI chat client reads the isolated OPENAI_BASE_URL, OPENAI_API_KEY, and OPENAI_MODEL"
export FRAMEWORK_NATIVE_LOG_MARKER="DRCLAW_NATIVE_CHAT_TDC"
export FRAMEWORK_NATIVE_PROCESS_MARKERS=$(cat <<'EOF'
NATIVE_CMD> node server/cli.js chat --model
EOF
)
export FRAMEWORK_EXECUTOR_KIND="framework_cli"
export FRAMEWORK_COMMAND_LABEL="node server/cli.js chat --model ${TDC_ADMET_TOX_EVAL_MODEL:-gpt-5.4}"
export FRAMEWORK_LOG_FORBIDDEN_PATTERN='pip install|npm install|curl |wget |apt-get'
export FRAMEWORK_RUNTIME_COMMAND=$(cat <<'EOF'
set -euo pipefail
echo "DRCLAW_NATIVE_CHAT_TDC"
test -s dr_claw_benchmark_authorization.md
test -s TDC_ADMET_TOX_BRIEF.md
export DRCLAW_MAX_AGENT_TURNS=100
python3 - <<'PY'
import pathlib
p = pathlib.Path("server/cli-chat.js")
s = p.read_text(encoding="utf-8")
old_read = "      case 'Read': {\n        const content = await fs.readFile(resolve(args.path), 'utf-8');"
assert s.count(old_read) == 1, s.count(old_read)
new_read = (
    "      case 'Read': {\n"
    "        const readPath = resolve(args.path);\n"
    "        const readStat = await fs.stat(readPath).catch(() => null);\n"
    "        if (readStat && readStat.isDirectory()) return `${args.path} is a directory. Use LS or Bash ls to list its entries, then Read a file path inside it.`;\n"
    "        const content = await fs.readFile(readPath, 'utf-8');"
)
s = s.replace(old_read, new_read, 1)
old_turn = "  for (let turn = 0; turn < MAX_AGENT_TURNS; turn++) {\n    const response = await streamApiCall(baseUrl, apiKey, model, messages, TOOL_SCHEMAS);\n\n    if (!response.ok) {\n      const errText = await response.text().catch(() => '');\n      console.error(styled(c.red, `  API error ${response.status}: ${errText.slice(0, 300)}\\n`));\n      return;\n    }"
assert s.count(old_turn) == 1, s.count(old_turn)
new_turn = (
    "  for (let turn = 0; turn < MAX_AGENT_TURNS; turn++) {\n"
    "    let response = null;\n"
    "    let errText = '';\n"
    "    for (let attempt = 0; attempt < 6; attempt++) {\n"
    "      response = await streamApiCall(baseUrl, apiKey, model, messages, TOOL_SCHEMAS);\n"
    "      if (response.ok) break;\n"
    "      errText = await response.text().catch(() => '');\n"
    "      if (response.status !== 502 || !errText.includes('upstream_error')) break;\n"
    "      console.log(styled(c.yellow, `  Upstream relay 502, retrying (attempt ${attempt + 2}/6)...`));\n"
    "      await new Promise((r) => setTimeout(r, 10000 * (attempt + 1)));\n"
    "      response = null;\n"
    "    }\n"
    "    if (!response) response = await streamApiCall(baseUrl, apiKey, model, messages, TOOL_SCHEMAS);\n"
    "    if (!response.ok) {\n"
    "      if (!errText) errText = await response.text().catch(() => '');\n"
    "      console.error(styled(c.red, `  API error ${response.status}: ${errText.slice(0, 300)}\\n`));\n"
    "      return;\n"
    "    }"
)
s = s.replace(old_turn, new_turn, 1)
p.write_text(s, encoding="utf-8")
print("cli-chat.js patched")
PY
PS4='NATIVE_CMD> '
set -x
node server/cli.js chat --model "$OPENAI_MODEL" <<'DRCLAW_PROMPT'
This is not a planning-only turn. Read /workspace/TDC_ADMET_TOX_BRIEF.md, /workspace/automation/tdc_admet_tox_contract.md, and /workspace/automation/tdc_admet_tox_execution_budget.md first. Then execute a real Dr. Claw style TDC-ADMET-Tox research workflow in this fresh workspace only, with Dr. Claw itself owning hypothesis generation, 2 to 4 materially distinct bounded foreground experiments, validation comparison by macro AUROC only, selection, runnable final prediction generation, traceable paper writing, and the framework-stage self-audit. Use only visible SMILES and installed libraries. Never create score.json, install packages, download assets, access public internet services, use remote chemistry lookups, launch background experiments, or start a fifth configuration. Record framework_internal_model exactly from OPENAI_MODEL and framework_internal_api_base_url exactly from OPENAI_BASE_URL. In experiment_trace.json set resource_budget with these exact keys and values: cpu_cores=4, memory_gib=16, gpu_count=0, workspace_disk_gib=10, max_experiment_runtime_seconds=3600, max_total_wall_seconds=7200. Produce all real artifacts and exit, or report a precise blocker.
DRCLAW_PROMPT
test -s /workspace/predictions.csv
test -s /workspace/experiment_trace.json
test -s /workspace/environment.json
test -s /workspace/paper.md
test '!' -e /workspace/score.json
EOF
)
exec "$ROOT/real_eval/scripts/tdc_admet_tox_framework_fullrun.sh"
