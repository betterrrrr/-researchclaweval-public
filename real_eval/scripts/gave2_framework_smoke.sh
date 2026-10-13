#!/usr/bin/env bash
set -euo pipefail

ROOT="${RESEARCHCLAWEVAL_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
source "$ROOT/real_eval/scripts/lib_real_eval.sh"
BASE="${REAL_EVAL_RUN_ROOT:?REAL_EVAL_RUN_ROOT is required}"
FRAMEWORK_NAME="${FRAMEWORK_NAME:?FRAMEWORK_NAME is required}"
FRAMEWORK_SLUG="${FRAMEWORK_SLUG:?FRAMEWORK_SLUG is required}"
IMAGE="${IMAGE:?IMAGE is required}"
CONTAINER_WORKDIR="${CONTAINER_WORKDIR:?CONTAINER_WORKDIR is required}"
WORKSPACE_DATASET_PATH="${WORKSPACE_DATASET_PATH:?WORKSPACE_DATASET_PATH is required}"
ENTRY_MAP="${ENTRY_MAP:?ENTRY_MAP is required}"
SMOKE_CMD="${SMOKE_CMD:-true}"
EXTRA_DOCKER_ARGS="${EXTRA_DOCKER_ARGS:-}"
DATASET_ROOT="${GAVE2_DATASET_ROOT:-$(real_eval_resolve_topic_dataset "$ROOT" gave2_task2)}"
CONTRACT_FILE="${GAVE2_CONTRACT_FILE:-$ROOT/automation/gave2_task2_contract.md}"

LOG_DIR="$BASE/logs"
LOG_FILE="$LOG_DIR/smoke.log"
STATE_FILE="$BASE/state.json"
MANIFEST_FILE="$BASE/smoke_manifest.json"
ENTRY_DESTS_FILE="$BASE/entry_dests.txt"
CONTAINER_SCRIPT="$BASE/container_smoke.sh"
HOST_WORKDIR="$BASE/workspace$CONTAINER_WORKDIR"
CONTAINER_NAME="gave2_smoke_${FRAMEWORK_SLUG}"

real_eval_require_clean_dir "$BASE"
mkdir -p "$HOST_WORKDIR" "$LOG_DIR"

if [[ ! -d "$DATASET_ROOT" ]]; then
  echo "missing dataset root: $DATASET_ROOT" >&2
  exit 21
fi
if [[ ! -f "$CONTRACT_FILE" ]]; then
  echo "missing contract file: $CONTRACT_FILE" >&2
  exit 22
fi
if [[ ! -f "$ROOT/automation/gave2_task2_manifest.json" ]]; then
  bash "$ROOT/real_eval/scripts/prepare_seven_serial_gave2_task2.sh" >/dev/null
fi

cleanup_container() {
  docker ps -a --format '{{.Names}}' | rg "^${CONTAINER_NAME}$" | xargs -r docker rm -f >/dev/null 2>&1 || true
}
trap cleanup_container EXIT

: > "$ENTRY_DESTS_FILE"
declare -a copied=()
while IFS= read -r mapping; do
  [[ -z "$mapping" ]] && continue
  src_rel="${mapping%%::*}"
  dst_rel="${mapping##*::}"
  src="$ROOT/$src_rel"
  dst="$HOST_WORKDIR/$dst_rel"
  if [[ ! -f "$src" ]]; then
    echo "missing source input: $src" >&2
    exit 23
  fi
  mkdir -p "$(dirname "$dst")"
  cp "$src" "$dst"
  printf '%s\n' "$dst_rel" >> "$ENTRY_DESTS_FILE"
  copied+=("$dst_rel")
done <<< "$ENTRY_MAP"

cat > "$CONTAINER_SCRIPT" <<EOF
#!/usr/bin/env bash
set -euo pipefail
count_files(){ find "\$1" -maxdepth 1 -type f | wc -l; }
[[ -f /input/contract.md ]]
[[ -d /data/gave2/task2/training/images ]]
[[ -d /data/gave2/task2/validation/images ]]
[[ -d "$WORKSPACE_DATASET_PATH/training/images" ]]
[[ -d "$WORKSPACE_DATASET_PATH/validation/images" ]]
[[ "\$(count_files /data/gave2/task2/training/images)" -eq 50 ]]
[[ "\$(count_files /data/gave2/task2/validation/images)" -eq 50 ]]
[[ "\$(count_files $WORKSPACE_DATASET_PATH/training/images)" -eq 50 ]]
[[ "\$(count_files $WORKSPACE_DATASET_PATH/validation/images)" -eq 50 ]]
while IFS= read -r rel; do
  [[ -f "\$PWD/\$rel" ]]
done < /input/entry_dests.txt
$SMOKE_CMD
EOF
chmod 755 "$CONTAINER_SCRIPT"

real_eval_write_state "$STATE_FILE" "{\"status\":\"starting\",\"framework\":\"$FRAMEWORK_NAME\",\"image\":\"$IMAGE\",\"workdir\":\"$CONTAINER_WORKDIR\"}"

extra_args=()
if [[ -n "$EXTRA_DOCKER_ARGS" ]]; then
  while IFS= read -r line; do
    [[ -z "$line" ]] && continue
    extra_args+=("$line")
  done <<< "$EXTRA_DOCKER_ARGS"
fi

set +e
docker run --rm --name "$CONTAINER_NAME" --user 0:0 \
  "${extra_args[@]}" \
  -v "$HOST_WORKDIR":"$CONTAINER_WORKDIR" \
  -v "$DATASET_ROOT":/data/gave2/task2:ro \
  -v "$DATASET_ROOT":"$WORKSPACE_DATASET_PATH":ro \
  -v "$CONTRACT_FILE":/input/contract.md:ro \
  -v "$ENTRY_DESTS_FILE":/input/entry_dests.txt:ro \
  -v "$CONTAINER_SCRIPT":/input/container_smoke.sh:ro \
  -w "$CONTAINER_WORKDIR" \
  "$IMAGE" \
  /input/container_smoke.sh 2>&1 | tee "$LOG_FILE"
rc=${PIPESTATUS[0]}
set -e

python3 - "$MANIFEST_FILE" "$STATE_FILE" "$FRAMEWORK_NAME" "$FRAMEWORK_SLUG" "$IMAGE" "$CONTAINER_WORKDIR" "$WORKSPACE_DATASET_PATH" "$DATASET_ROOT" "$CONTRACT_FILE" "$rc" "$LOG_FILE" "${copied[@]}" <<'PY'
from pathlib import Path
import json
import sys

manifest_path = Path(sys.argv[1])
state_path = Path(sys.argv[2])
framework, slug, image, workdir, ws_dataset, dataset_root, contract_file, rc, log_file = sys.argv[3:12]
copied = sys.argv[12:]
checks = {
    'shared_dataset_mount': True,
    'workspace_dataset_mount': True,
    'entry_files_present': bool(copied),
    'container_rc_zero': int(rc) == 0,
}
manifest = {
    'framework': framework,
    'slug': slug,
    'image': image,
    'workdir': workdir,
    'workspace_dataset_path': ws_dataset,
    'dataset_root': dataset_root,
    'contract_file': contract_file,
    'copied_inputs': copied,
    'log_file': log_file,
    'checks': checks,
    'all_passed': all(checks.values()),
}
manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding='utf-8')
state = {
    'status': 'finished' if manifest['all_passed'] else 'failed_smoke',
    'framework': framework,
    'slug': slug,
    'artifact_manifest': str(manifest_path),
    'log': log_file,
}
state_path.write_text(json.dumps(state, ensure_ascii=False) + "\n", encoding='utf-8')
PY

if [[ "$rc" -ne 0 ]]; then
  exit "$rc"
fi
