#!/usr/bin/env bash
# 01/02 的 LLM 评测（轨迹序数 + ED + 七维判官）—— 一条命令跑完，可中断续跑。
#
# 前置：JUDGE_API_KEY 必须在环境里（判官只从环境变量读密钥，源码刻意无默认值）。
#       export JUDGE_API_KEY=...        # 或放到文件里： set -a; . /path/judge.env; set +a
#
# 用法：
#   bash automation/scripts/run_llm_eval_0102.sh --check          # 只花 1 次调用验通路
#   bash automation/scripts/run_llm_eval_0102.sh --dry-run        # 0 次调用，报预算
#   bash automation/scripts/run_llm_eval_0102.sh                  # 全量（≈402 次调用）
#   LIMIT=3 bash automation/scripts/run_llm_eval_0102.sh          # 冒烟：3 个格子
set -euo pipefail

cd "$(dirname "$0")/../.."
REPO=$PWD
S=automation/scripts
MODE=${1:-run}

if [ "$MODE" != "--dry-run" ]; then
  if [ -z "${JUDGE_API_KEY:-}" ]; then
    cat >&2 <<'MSG'
缺少 JUDGE_API_KEY。三种给法（任选其一）：
  1) 临时：   export JUDGE_API_KEY=ppapi-...     # 本 shell 有效，之后重跑本脚本
  2) 文件：   install -m600 /dev/null ~/.config/researchclaweval/judge.env
              printf 'export JUDGE_API_KEY=ppapi-...\n' >> ~/.config/researchclaweval/judge.env
              set -a; . ~/.config/researchclaweval/judge.env; set +a
  3) 写进 ~/.bashrc（每个新 shell 自动带上）
密钥不会被打进日志：本脚本只读环境变量，不回显、不落盘。
MSG
    exit 2
  fi
fi

echo "== 判官模型/端点 =="
python3 - <<'PY'
import importlib.util, os
spec=importlib.util.spec_from_file_location("o","real_eval/evaluation/judge/orchestrator.py")
m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
print(f"  model={os.environ.get('JUDGE_MODEL', m.DEFAULT_MODEL)}  base={os.environ.get('JUDGE_API_BASE', m.DEFAULT_API_BASE)}")
PY

if [ "$MODE" = "--dry-run" ]; then
  echo "== ① 轨迹序数 + ED（预算） =="
  python3 "$S/evaluation_metrics_report.py" --dry-run --out-prefix /tmp/eval_dry
  echo "== ② 七维判官（预算） =="
  python3 "$S/judge_0102_cells.py" --dry-run | head -8
  exit 0
fi

if [ "$MODE" = "--check" ]; then
  echo "== 预检：对 1 个最完整的 run 只调 1 个维度（1 次调用） =="
  python3 - <<'PY'
import importlib.util, sys
spec=importlib.util.spec_from_file_location("o","real_eval/evaluation/judge/orchestrator.py")
m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
run="${REAL_EVAL_RUNS_0102_ROOT:?set REAL_EVAL_RUNS_0102_ROOT}/01_ai_researcher__arc_wbe_2026__gpt-6-luna__fullrun_arc_01_g6luna_20260928_045904"
arts=m.load_artifacts(run)
res=m.call_llm(m.build_prompt(m.load_prompt("sc"), arts), model=m.DEFAULT_MODEL)
score=res.get("score")
print(f"  sc 维度返回: score={score}  keys={sorted(res)[:6]}")
if score is None:
    print("  ❌ 通路不通，别跑全量。error=", str(res.get("error"))[:200]); sys.exit(1)
print("  ✅ 通路正常（这 1 次调用不会被缓存，全量时该维度会重调一次）")
PY
  exit 0
fi

LIMIT=${LIMIT:-}
WORKERS=${WORKERS:-6}
LIMIT_ARG=()
[ -n "$LIMIT" ] && LIMIT_ARG=(--judge-limit "$LIMIT")

echo "== ① 轨迹序数 + ED（57 任务 × 3 采样 ≈ 171 次调用，并发 $WORKERS，带缓存可续跑） =="
python3 "$S/evaluation_metrics_report.py" --judge --csv --workers "$WORKERS" \
        "${LIMIT_ARG[@]}" --out-prefix analysis/evaluation_metrics

echo "== ② 七维判官（33 run × 7 维 = 231 次调用，并发 $WORKERS，幂等可续跑） =="
python3 "$S/judge_0102_cells.py" --workers "$WORKERS" ${LIMIT:+--limit "$LIMIT"}

echo "== ③ 重出总表（此时裁判结果全在缓存/score.json 里，不新增调用） =="
python3 "$S/evaluation_metrics_report.py" --judge --csv --out-prefix analysis/evaluation_metrics | tail -20
echo
echo "完成。总表： analysis/evaluation_metrics.{json,csv}"
