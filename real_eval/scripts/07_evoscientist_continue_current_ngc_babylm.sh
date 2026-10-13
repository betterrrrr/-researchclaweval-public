#!/usr/bin/env bash
set -euo pipefail

ROOT="${RESEARCHCLAWEVAL_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
source "$ROOT/real_eval/scripts/lib_real_eval.sh"

RUN_ID="${REAL_EVAL_RUN_ID:-$(date +%Y%m%d-%H%M%S)}"
BASE="${REAL_EVAL_RUN_ROOT:-$ROOT/real_eval/runs/$RUN_ID/07_evoscientist_real_babylm_ngc_current}"
WORK="$BASE/workspace"
LOG_DIR="$BASE/logs"
DATASET_ROOT="${BABYLM_DATASET_ROOT:-$ROOT/BabyLM-2026-Strict-Small}"
SOURCE_BASE="${EVOSCIENTIST_CURRENT_SOURCE_BASE:-}"
SOURCE_WORK="${SOURCE_BASE:+$SOURCE_BASE/workspace}"
IMAGE="${EVOSCIENTIST_NGC_IMAGE:-evoscientist-ngc-babylm:runtime-ready}"

if [[ -z "$SOURCE_BASE" ]]; then
  echo "EVOSCIENTIST_CURRENT_SOURCE_BASE is required for fresh continuation runs" >&2
  exit 19
fi
if [[ ! -f "$SOURCE_WORK/scripts/train_babylm.py" || ! -f "$SOURCE_WORK/scripts/evaluate_babylm.py" ]]; then
  echo "Missing current EvoScientist-generated scripts under $SOURCE_WORK/scripts" >&2
  exit 20
fi

real_eval_require_clean_dir "$BASE"
mkdir -p "$WORK/scripts" "$WORK/input" "$WORK/artifacts" "$LOG_DIR"

cp "$SOURCE_WORK/scripts/train_babylm.py" "$WORK/scripts/train_babylm.py"
cp "$SOURCE_WORK/scripts/evaluate_babylm.py" "$WORK/scripts/evaluate_babylm.py"
for file in prompt.md research_request.md todos.md; do
  if [[ -f "$SOURCE_WORK/$file" ]]; then
    cp "$SOURCE_WORK/$file" "$WORK/$file"
  fi
done
if [[ -d "$SOURCE_WORK/input" ]]; then
  cp -a "$SOURCE_WORK/input/." "$WORK/input/"
fi

python3 - "$WORK/scripts/train_babylm.py" <<'PY'
from pathlib import Path
import sys

path = Path(sys.argv[1])
text = path.read_text(encoding="utf-8")
text = text.replace("evaluation_strategy=", "eval_strategy=")
text = text.replace("        tokenizer=tokenizer,\n", "        processing_class=tokenizer,\n")
text = text.replace("        overwrite_output_dir=True,\n", "")
old = '''    tokenizer.save_model(out_dir)
    hf_tok = PreTrainedTokenizerFast(
        tokenizer_file=None,
        vocab_file=os.path.join(out_dir, "vocab.json"),
        merges_file=os.path.join(out_dir, "merges.txt"),
        bos_token="<|endoftext|>",
        eos_token="<|endoftext|>",
        unk_token="<|endoftext|>",
        pad_token="<|pad|>",
    )
'''
new = '''    tokenizer.save_model(out_dir)
    tokenizer_json = os.path.join(out_dir, "tokenizer.json")
    tokenizer.save(tokenizer_json)
    hf_tok = PreTrainedTokenizerFast(
        tokenizer_file=tokenizer_json,
        bos_token="<|endoftext|>",
        eos_token="<|endoftext|>",
        unk_token="<|endoftext|>",
        pad_token="<|pad|>",
    )
'''
if old not in text:
    raise SystemExit("Expected ByteLevelBPETokenizer construction block not found")
text = text.replace(old, new)
path.write_text(text, encoding="utf-8")
PY

cat > "$BASE/state.json" <<EOF
{"project_id":"07","name":"EvoScientist","run_id":"$RUN_ID","status":"starting_ngc_current_continue","workspace":"$WORK","source_workspace":"$SOURCE_WORK"}
EOF

set +e
docker run \
  --rm \
  --gpus all \
  --user "$(id -u):$(id -g)" \
  --entrypoint bash \
  -e CUDA_VISIBLE_DEVICES=0 \
  -e USER="${USER:-runner}" \
  -e LOGNAME="${LOGNAME:-runner}" \
  -e HOME=/workspace/.runtime-home \
  -e XDG_CACHE_HOME=/workspace/.cache \
  -e HF_HOME=/workspace/.cache/huggingface \
  -e TORCH_HOME=/workspace/.cache/torch \
  -e TORCHINDUCTOR_CACHE_DIR=/workspace/.cache/torch_inductor \
  -e PYTHONPATH=/workspace/.runtime_site:/source_workspace/.ngc_site \
  -v "$WORK":/workspace \
  -v "$SOURCE_WORK":/source_workspace:ro \
  -v "$DATASET_ROOT":/data/BabyLM-2026-Strict-Small:ro \
  -w /workspace \
  "$IMAGE" \
  -lc 'set -euo pipefail
mkdir -p "$HOME" "$XDG_CACHE_HOME" "$HF_HOME" "$TORCH_HOME" "$TORCHINDUCTOR_CACHE_DIR"
mkdir -p /workspace/.runtime_site
python - <<'"'"'PY'"'"' || python -m pip install --no-deps --target /workspace/.runtime_site "accelerate>=1.1.0"
try:
    import accelerate  # noqa: F401
except Exception:
    raise SystemExit(1)
PY
python - <<'"'"'PY'"'"'
import inspect
from pathlib import Path
import torch
import transformers
import accelerate
from transformers import Trainer, TrainingArguments

Path("artifacts/logs").mkdir(parents=True, exist_ok=True)
lines = [
    f"torch_version: {torch.__version__}",
    f"transformers_version: {transformers.__version__}",
    f"accelerate_version: {accelerate.__version__}",
    f"cuda_available: {torch.cuda.is_available()}",
    f"device_count: {torch.cuda.device_count()}",
    f"device_name: {torch.cuda.get_device_name(0) if torch.cuda.is_available() else None}",
    f"training_args_has_eval_strategy: {'"'eval_strategy'"' in inspect.signature(TrainingArguments.__init__).parameters}",
    f"trainer_has_processing_class: {'"'processing_class'"' in inspect.signature(Trainer.__init__).parameters}",
]
if not torch.cuda.is_available():
    raise SystemExit("CUDA is unavailable in NGC continuation image")
x = torch.ones((32, 32), device="cuda")
lines.append(f"cuda_matmul_sum: {float((x @ x).sum())}")
Path("artifacts/logs/ngc_preflight.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
print("\n".join(lines))
PY
python scripts/train_babylm.py
python scripts/evaluate_babylm.py
python - <<'"'"'PY'"'"'
import json
from datetime import datetime
from pathlib import Path

root = Path("/workspace")
art = root / "artifacts"
eval_dir = art / "eval"
log_dir = art / "logs"

def load_json(path):
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))

eval_metrics = load_json(eval_dir / "eval_metrics.json")
recomputed = load_json(eval_dir / "eval_metrics_recomputed.json")
model_stats = load_json(log_dir / "model_stats.json")
corpus_stats = model_stats.get("corpus_stats", {})
preflight = (log_dir / "ngc_preflight.txt").read_text(encoding="utf-8") if (log_dir / "ngc_preflight.txt").exists() else ""
env_check = (log_dir / "env_check.txt").read_text(encoding="utf-8") if (log_dir / "env_check.txt").exists() else ""

report = f"""# EvoScientist BabyLM-10M Real CUDA Continuation Report

Generated: {datetime.now().isoformat()}

## Run Contract

This report was generated from the current EvoScientist GPU retry state, not from the invalid CPU attempt. The EvoScientist-generated training and evaluation scripts were copied into an isolated continuation workspace and executed with the local CUDA continuation image configured by the wrapper (default: `evoscientist-ngc-babylm:runtime-ready`, derived from `nvcr.io/nvidia/pytorch:25.11-py3`) because the original runtime PyTorch build could not execute CUDA kernels on Blackwell `sm_120`.

## CUDA Runtime Evidence

```text
{preflight.strip()}
```

```text
{env_check.strip()}
```

## Data And Model

- Dataset root inside container: `/data/BabyLM-2026-Strict-Small`
- Train token count: {corpus_stats.get("train_token_count")}
- Validation token count: {corpus_stats.get("val_token_count")}
- Total parameters: {model_stats.get("total_parameters")}
- Checkpoint directory: `artifacts/checkpoints/best`

## Training Metrics

- Trainer eval loss: {eval_metrics.get("eval_loss")}
- Trainer perplexity: {eval_metrics.get("perplexity")}
- Training runtime: {eval_metrics.get("train_runtime")}
- Training samples per second: {eval_metrics.get("train_samples_per_second")}
- Training steps per second: {eval_metrics.get("train_steps_per_second")}
- Recorded training device: {eval_metrics.get("device")}

## Recomputed Evaluation

- Recomputed eval loss: {recomputed.get("eval_loss")}
- Recomputed perplexity: {recomputed.get("perplexity")}
- Recomputed eval batches: {recomputed.get("num_eval_batches")}
- Recomputed device: {recomputed.get("device")}

## Artifact Checklist

- `artifacts/logs/ngc_preflight.txt`
- `artifacts/logs/env_check.txt`
- `artifacts/logs/train_metrics.json`
- `artifacts/logs/model_stats.json`
- `artifacts/eval/eval_metrics.json`
- `artifacts/eval/eval_metrics_recomputed.json`
- `artifacts/eval/samples.txt`
- `artifacts/eval/samples_eval.txt`
- `artifacts/checkpoints/best`

This is a real neural language-model training run over the BabyLM files mounted from the host dataset. It does not use proxy scripts, toy datasets, old checkpoints, or placeholder results.
"""
Path("/workspace/final_report.md").write_text(report, encoding="utf-8")
PY' \
  2>&1 | tee "$LOG_DIR/e2e.log"
rc=${PIPESTATUS[0]}
set -e

if [[ "$rc" -ne 0 ]]; then
  real_eval_write_state "$BASE/state.json" "{\"project_id\":\"07\",\"name\":\"EvoScientist\",\"run_id\":\"$RUN_ID\",\"status\":\"failed_ngc_current_continue\",\"workspace\":\"$WORK\",\"source_workspace\":\"$SOURCE_WORK\",\"log\":\"$LOG_DIR/e2e.log\",\"exit_code\":$rc}"
  exit "$rc"
fi

if ! real_eval_has_artifacts "$WORK"; then
  real_eval_write_state "$BASE/state.json" "{\"project_id\":\"07\",\"name\":\"EvoScientist\",\"run_id\":\"$RUN_ID\",\"status\":\"failed_no_artifacts_ngc_current_continue\",\"workspace\":\"$WORK\",\"source_workspace\":\"$SOURCE_WORK\",\"log\":\"$LOG_DIR/e2e.log\"}"
  exit 13
fi

if ! find "$WORK" -type f \( -iname 'final_report.md' -o -iname '*report*.md' \) -size +500c 2>/dev/null | head -1 | grep -q .; then
  real_eval_write_state "$BASE/state.json" "{\"project_id\":\"07\",\"name\":\"EvoScientist\",\"run_id\":\"$RUN_ID\",\"status\":\"failed_no_report_ngc_current_continue\",\"workspace\":\"$WORK\",\"source_workspace\":\"$SOURCE_WORK\",\"log\":\"$LOG_DIR/e2e.log\"}"
  exit 15
fi

if ! python3 - "$WORK" <<'PY'
import json
import sys
from pathlib import Path

root = Path(sys.argv[1])
devices = []
for path in root.rglob("*.json"):
    if any(part.startswith(".") for part in path.relative_to(root).parts):
        continue
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        continue
    stack = [data]
    while stack:
        item = stack.pop()
        if isinstance(item, dict):
            for key, value in item.items():
                if key.lower() == "device" and isinstance(value, str):
                    devices.append((str(path), value.lower()))
                elif isinstance(value, (dict, list)):
                    stack.append(value)
        elif isinstance(item, list):
            stack.extend(v for v in item if isinstance(v, (dict, list)))

if any(value.startswith("cuda") for _, value in devices):
    raise SystemExit(0)
print("No CUDA device evidence found in JSON artifacts. Observed devices:", devices, file=sys.stderr)
raise SystemExit(1)
PY
then
  real_eval_write_state "$BASE/state.json" "{\"project_id\":\"07\",\"name\":\"EvoScientist\",\"run_id\":\"$RUN_ID\",\"status\":\"failed_cpu_device_ngc_current_continue\",\"workspace\":\"$WORK\",\"source_workspace\":\"$SOURCE_WORK\",\"log\":\"$LOG_DIR/e2e.log\"}"
  exit 14
fi

cat > "$BASE/state.json" <<EOF
{"project_id":"07","name":"EvoScientist","run_id":"$RUN_ID","status":"finished","workspace":"$WORK","source_workspace":"$SOURCE_WORK","log":"$LOG_DIR/e2e.log"}
EOF
