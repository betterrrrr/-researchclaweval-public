#!/usr/bin/env python3
"""测评流水线汇总：把 12 项指标拼成一张表。

格子 = (framework, topic, model)。默认口径 **140 格 = 7 框架 × 5 topic × 4 模型**：
- 03–07 走 `real_eval/runs`（主 root）；
- 01/02 走**独立 root** `real_eval/runs_0102`（外部交付包，见 `AUX_RUNS_ROOTS`）。
想回到早先的 5 框架 100 格口径：加 `--no-aux`。

12 项里：
- b0 / bT / AUP / UR / ED  → 轨迹类（本脚本算）；
- PQ / PEA / ER / OU / ECC / SC / CC → 判官七维（从 run 根 score.json 读，已有）。

归属**一律走 manifest**（目录名只作最后回退），因为历史上靠目录名推框架错标过好几轮。
口径与边界见 `docs/evaluation_metrics.md`。
"""

from __future__ import annotations

import os

import argparse
import csv
import hashlib
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from trajectory_metrics import (  # noqa: E402
    DEFAULT_RUNS_ROOT,
    analyze_run,
    detect_topic,
    find_trace,
    iter_manifests,
    load_anchors,
)

# manifest.framework 是**显示名**，不是 2 位码。
# 键已按 `_norm` 归一（去分隔符、小写）：`Dr. Claw` → `drclaw`。
FRAMEWORK_BY_DISPLAY = {
    "airesearcher": "01",
    "aiscientistv2": "02",
    "aris": "03",
    "autoresearchclaw": "04",
    "deepscientist": "05",
    "drclaw": "06",
    "evoscientist": "07",
}

FRAMEWORK_NAME = {
    "01": "AI-Researcher", "02": "AI-Scientist-v2", "03": "ARIS",
    "04": "AutoResearchClaw", "05": "DeepScientist", "06": "DrClaw",
    "07": "EvoScientist",
}

# ⚠️ 顺序即优先级：**必须先判 5.6 再判 6**
# （归一化后 `gpt56luna` 与 `gpt6luna` 只差一个字符，先判 6 会把 5.6 吞掉）
#
# 匹配前**先去分隔符**：实测目录名里 5.6 至少有 `gpt-5.6-luna` / `gpt56luna` /
# `gpt-5-6-luna` 三种写法，只认前两种会整片漏掉（曾漏掉 06×mc 的多个格子）。
MODEL_RULES = (
    (("gpt56",), "GPT-5.6-Luna"),
    (("gpt6",), "GPT-6-Luna"),
    (("deepseek",), "DeepSeek-V4"),
    (("kimi",), "Kimi-K2.6"),
)


def _norm(text: object) -> str:
    """去掉所有非字母数字并转小写 —— 让 `gpt-5-6-luna`、`gpt5.6luna`、`gpt56luna` 等价。"""
    return "".join(ch for ch in str(text or "").lower() if ch.isalnum())

MODEL_ORDER = ("GPT-6-Luna", "GPT-5.6-Luna", "DeepSeek-V4", "Kimi-K2.6")
TOPIC_ORDER = ("arc", "mc", "babylm", "psydef", "tdc")
FRAMEWORK_ORDER = ("03", "04", "05", "06", "07")

# 额外 root：**01/02 的 run records 来自外部交付包**（协作者环境跑完交回来的），
# 落在独立目录，且**只允许这两个框架**。
#
# 为什么不并进 real_eval/runs：那底下有 2026-08 的 01 pilot（53 个 `01-*` 目录）。
# 一旦合并扫描，01 的格子会同时命中 pilot 与交付 run，n_runs_in_cell / 代表 run
# 就混了两批不可比的记录。**root 与允许的框架绑在一起**，才不会靠目录名猜。
AUX_RUNS_ROOTS: tuple[tuple[Path, tuple[str, ...]], ...] = (
    (Path(os.environ.get("REAL_EVAL_RUNS_0102_ROOT", Path(__file__).resolve().parents[2] / "real_eval" / "runs_0102")), ("01", "02")),
)

# runs/ 底下**不是 run** 的记录性目录（按名字片段认）。
#
# 实例：交付包 `runs/01_ai_researcher__mountaincar_continuous__adjudication_mcar01_ge1_20260928/`
# 是 01 MountainCar 的**追溯裁定记录**，自身没有 manifest / workspace，但子目录里各有一份
# `*/workspace/experiment_trace.json`。`trace_internal_model` 会顺着子目录读到一个模型名
# —— 归属回退于是把整个记录目录判成 `(01, mc, DeepSeek-V4)`，凭空给该格多算一个 run。
# 实测确认过，故显式排除；不做「按名字改写」，交付副本保持原样。
NON_RUN_DIR_PATTERNS = ("__adjudication_",)

JUDGE_DIMS = ("pq", "pea", "er", "ou", "ecc", "sc", "cc")

# 裁定不可入账的 run（占位符 / 非官方 metric / 数据集或划分与 canonical 不符）。
# 登记文件与理由见 `automation/scripts/score_exclusions.json` —— 不在这里硬编码。
EXCLUSIONS_PATH = Path(__file__).resolve().parent / "score_exclusions.json"


def load_exclusions() -> dict[str, dict]:
    if not EXCLUSIONS_PATH.is_file():
        return {}
    try:
        payload = json.loads(EXCLUSIONS_PATH.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return {}
    out: dict[str, dict] = {}
    for entry in payload.get("exclusions") or []:
        if not (isinstance(entry, dict) and entry.get("run_dir")):
            continue
        run_dir = str(entry["run_dir"])
        out[run_dir] = entry
        # 单元可能嵌在 run 目录下一层（如 `<run>/03_aris_arc_wbe_2026_fullrun`）。
        # **必须带路径前缀**：单看单元名会误伤所有同名单元
        # （`03_aris_arc_wbe_2026_fullrun` 这种名字在几十个 run 里重复出现）。
        if entry.get("unit_dir"):
            out[f"{run_dir}/{entry['unit_dir']}"] = entry
    return out


def exclusion_keys(unit: Path) -> tuple[str, ...]:
    """能唯一指到某个单元的键：单元名 + `父目录/单元名`。"""
    return (unit.name, f"{unit.parent.name}/{unit.name}")

# 官方分的键与方向（方向已知，直接用，不重复推导）
OFFICIAL_KEY = {"arc": "score", "mc": "score", "babylm": "perplexity",
                "psydef": "psydefdetect_score", "tdc": "main_score"}
LOWER_BETTER = {"arc", "babylm"}

# `score_source` 字段 → 档位。**判据在源字段里，不在值的大小里**：
# BabyLM 的官方评分器就是「读 trace 取最小有限值」，所以它天生是 framework_self_reported，
# 与同表的 official_adapter_whest_run（真官方的外部评分器）**不是一个档位**。
OFFICIAL_SOURCE_CLASS = {
    "official_adapter_whest_run": "official_scorer",
    "official_evaluate_py": "official_scorer",
    "host_hidden_test_labels": "official_scorer",
    "host_local_scorer": "official_scorer",
    "framework_experiment_trace": "framework_self_reported",
    "manual_record": "manual_record",
}


def classify_official_metric_implemented(value: object) -> str:
    """`official_metric_implemented` 是**指标说明**（如 "macro-F1 over labels 1-8, excluding label 0"），
    不是源标签；有它就说明该 run 用的是**官方指标口径**的实现（psydef 的 8 格属于这种 → 官方口径）。
    """
    return "official_scorer" if isinstance(value, str) and value.strip() else "unlabeled"


def classify_official_source(source: object) -> str:
    return OFFICIAL_SOURCE_CLASS.get(str(source or ""), "unlabeled")


def judge_model_of(unit: Path | None) -> str | None:
    """该格判官分由哪个模型产出 —— 写进表里。**跨批引用前必须看这一列**：
    01/02/04/07 是 `DeepSeek-V4.1-Flash`，03/05/06 早期的格子是 `DeepSeek-V4-Flash`，
    换判官模型实测会让 52% 的维度位移（平均绝对偏移 0.34，最大 1.0）。"""
    if unit is None:
        return None
    for candidate in (unit / "score.json", unit / "workspace" / "score.json"):
        if not candidate.is_file():
            continue
        try:
            payload = json.loads(candidate.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            continue
        model = ((payload or {}).get("evaluation") or {}).get("judge_model")
        if model:
            return str(model)
    return None


def judge_substitution(unit: Path) -> str | None:
    """该 run 的判官分是否用了**替身产物**（如 `final_report.md` 缺失、用框架自己写的 `paper.md` 顶）。

    读 `<unit>/score.json` 的 `judge_provenance.substitutions`。有替身时**必须**在
    `basis_judge` 里标出来 —— 否则会与"四件产物齐全"的判官分混为一谈（两者不可直接并列）。
    """
    for candidate in (unit / "score.json", unit / "workspace" / "score.json"):
        if not candidate.is_file():
            continue
        try:
            payload = json.loads(candidate.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            continue
        subs = ((payload or {}).get("judge_provenance") or {}).get("substitutions") or {}
        if isinstance(subs, dict) and subs:
            return ",".join(sorted(f"{k}<-{v}" for k, v in subs.items()))
    return None


def _official_source_field(run: Path | None, topic: str) -> str:
    """读出**该格官方分那个文件**里的源字段，**归成档位**返回（official_scorer / framework_self_reported /
    manual_record / unlabeled）。

    只认 `_score_candidates` 里的文件顺序（与 `official_score` 一致），不猜。
    """
    if run is None:
        return ""
    key = OFFICIAL_KEY.get(topic, "score")
    for candidate in _score_candidates(run):
        if not candidate.is_file():
            continue
        try:
            payload = json.loads(candidate.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            continue
        if not isinstance(payload, dict) or not isinstance(payload.get(key), (int, float)):
            continue
        for field in ("score_source", "source"):
            value = payload.get(field)
            if isinstance(value, str) and value:
                return classify_official_source(value)      # 直接返回**档位**，不再让调用方二次映射
        if classify_official_metric_implemented(payload.get("official_metric_implemented")) != "unlabeled":
            return "official_scorer"
    # 旁挂 provenance：旧版评分器的 score.json 不记源，项目惯例是把出处**另存**在
    # `workspace/score_provenance.json`（root:644 的 score.json 写不了）。管线此前没读它，
    # 于是 11 个 psydef 格被判成「出处未标」。
    import os
    for probe in (run / "workspace" / "score_provenance.json", run / "score_provenance.json"):
        if not probe.is_file():
            continue
        try:
            side = json.loads(probe.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            continue
        if isinstance(side, dict):
            for field in ("score_source", "source"):
                value = side.get(field)
                if isinstance(value, str) and value:
                    return classify_official_source(value)
    return "unlabeled"


def babylm_trace_score(unit: Path) -> float | None:
    """BabyLM 的官方评分规则 = 读 trace 取**最小有限值**（`run_babylm_score.py`）。

    `score.json` 没写 `perplexity` 键时按**同一条规则**回退（实测有 12 格属于这种情况：
    `official_final` 空、而数字就在同一行的 `bT_raw` 里）。
    这里直接复用官方评分器的 `extract_perplexity`，**不另写一套抽取规则** —— 两套规则迟早会分叉。
    """
    trace = find_trace(unit)
    if trace is None:
        return None
    try:
        import run_babylm_score as BS  # 官方评分器（同目录），只用它的抽取函数
    except Exception:  # noqa: BLE001
        return None
    try:
        payload = json.loads(trace.read_text(encoding="utf-8", errors="ignore"))
    except Exception:  # noqa: BLE001
        return None
    values = []
    # ⚠️ 实测有 trace 的**顶层是 list**（不是 dict）—— 官方 `run_babylm_score.py` 在那种形状上
    # 会 `AttributeError` 直接崩，即它**算不出分**。这里按同一语义宽容处理（把 list 当作实验序列），
    # 属于**比官方评分器宽**的口径，故在 `basis_official` 里仍标 framework_self_reported。
    if isinstance(payload, list):
        for exp in payload:
            v = BS.extract_perplexity(exp)
            if v is not None:
                values.append(v)
        return min(values) if values else None
    for exp in payload.get("experiments") or []:
        v = BS.extract_perplexity(exp)
        if v is not None:
            values.append(v)
    for res in payload.get("results") or []:
        v = BS.extract_perplexity(res)
        if v is not None:
            values.append(v)
    top = payload.get("best_validation_perplexity")
    if isinstance(top, (int, float)) and top > 0:
        values.append(float(top))
    return min(values) if values else None


def canon_model(*candidates: object) -> str | None:
    """把各种写法归一成 4 个规范模型名之一。"""
    for raw in candidates:
        text = _norm(raw)
        if not text or text == "none":
            continue
        for needles, name in MODEL_RULES:
            if any(n in text for n in needles):
                return name
    return None


def framework_code(manifest: dict | None, unit: Path, run_dir: Path | None = None) -> str | None:
    """单元 manifest 优先，其次**单元目录名前缀**（如 `03_aris_topic2_fullrun`），
    最后才回退 run 目录名。"""
    if isinstance(manifest, dict):
        display = _norm(manifest.get("framework"))
        if display in FRAMEWORK_BY_DISPLAY:
            return FRAMEWORK_BY_DISPLAY[display]
    # 单元目录名常形如 `03_aris_...` / `07_evoscientist_...`
    for name in (unit.name, (run_dir or unit).name):
        norm = _norm(name)
        match = re.match(r"^0([1-7])", norm)
        if match and norm[:2] in FRAMEWORK_NAME:
            return norm[:2]
        for prefix, code in (("f03", "03"), ("f04", "04"), ("f05", "05"),
                             ("f06", "06"), ("f07", "07")):
            if norm.startswith(prefix):
                return code
        for needle, code in (("aris", "03"), ("autoresearchclaw", "04"),
                             ("deepscientist", "05"), ("drclaw", "06"),
                             ("evoscientist", "07")):
            if needle in norm:
                return code
    return None


def iter_units(run_dir: Path) -> list[Path]:
    """列出 run 目录下的**归属单元**。

    有内层 manifest 时，每个含 manifest 的子目录各是一个单元（批次目录 → 多单元）；
    没有内层 manifest 时，run 目录自身就是单元。
    """
    units = sorted({path.parent for path in run_dir.glob("*/fullrun_manifest.json")})
    if units:
        return units
    return [run_dir]


def read_unit_manifest(unit: Path) -> dict | None:
    """只读**该单元自己**的 manifest —— 绝不跨单元借用。"""
    path = unit / "fullrun_manifest.json"
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return None
    return payload if isinstance(payload, dict) else None


def read_manifest(run_dir: Path) -> dict | None:
    """外层优先，内层单元兜底（多数 run 的 manifest 在内层）。"""
    for path in iter_manifests(run_dir):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            continue
        if isinstance(payload, dict):
            return payload
    return None


def trace_internal_model(run_dir: Path) -> str | None:
    for candidate in (run_dir / "workspace" / "experiment_trace.json",
                      *sorted(run_dir.glob("*/workspace/experiment_trace.json"))):
        if not candidate.is_file():
            continue
        try:
            payload = json.loads(candidate.read_text(encoding="utf-8", errors="ignore"))
        except Exception:  # noqa: BLE001
            continue
        if isinstance(payload, dict):
            value = payload.get("framework_internal_model")
            if value:
                return str(value)
    return None


def _score_candidates(unit: Path) -> list[Path]:
    """单元目录 → 其所在 run 根，两层都找（判官分常写在 run 根）。"""
    roots = [unit]
    if unit.parent != unit and unit.parent.name and not unit.parent.name.startswith("_"):
        roots.append(unit.parent)
    out: list[Path] = []
    for root in roots:
        out.extend([root / "workspace" / "score.json", root / "score.json"])
    return out


def read_judge_dims(unit: Path) -> dict[str, float | None]:
    """判官七维从 `score.json` 的 `evaluation.dimensions` 读（与官方分是**两个不同文件**）。"""
    for candidate in _score_candidates(unit):
        if not candidate.is_file():
            continue
        try:
            payload = json.loads(candidate.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            continue
        dims = ((payload or {}).get("evaluation") or {}).get("dimensions") or {}
        out: dict[str, float | None] = {}
        for dim in JUDGE_DIMS:
            entry = dims.get(dim)
            value = entry.get("score") if isinstance(entry, dict) else None
            out[dim] = float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else None
        if any(v is not None for v in out.values()):
            return out
    return {dim: None for dim in JUDGE_DIMS}


def official_score(unit: Path, topic: str) -> float | None:
    key = OFFICIAL_KEY.get(topic)
    if not key:
        return None
    for candidate in _score_candidates(unit):
        if not candidate.is_file():
            continue
        try:
            payload = json.loads(candidate.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            continue
        if isinstance(payload, dict):
            value = payload.get(key)
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                return float(value)
    return None


def collect_cells(runs_root: Path, allowed: tuple[str, ...] | None = None) -> dict[tuple[str, str, str], list[Path]]:
    """扫描 runs/ 建立 (framework, topic, model) → **单元目录**列表。

    ⚠️ 归属单元是**内层单元目录**，不是 run 目录。

    实测：一个 run 目录可以是**批次目录**，同时装着 7 个框架的单元，且**没有外层 manifest**。
    早先按 run 目录归属时，这类目录会被判成排序第一的那个框架（`01_ai_researcher_*`）
    并把其余 6 个框架的格子整个丢掉 —— 这是"覆盖率低"的主要成因之一。
    例：`topic2-kimi-fullrun-20260818-1/07_evoscientist_topic2_fullrun`。

    `allowed` 是**该 root 允许的框架码**；None 表示按 `FRAMEWORK_ORDER`（主 root 口径）。
    root 与框架绑定是刻意的：01/02 的交付 run 与 2026-08 的 01 pilot 不在同一个 root。
    """
    allow = FRAMEWORK_ORDER if allowed is None else allowed
    cells: dict[tuple[str, str, str], list[Path]] = {}
    if not runs_root.is_dir():
        return cells
    for run_dir in sorted(runs_root.iterdir()):
        if not run_dir.is_dir() or run_dir.name.startswith("_"):
            continue
        if any(p in run_dir.name for p in NON_RUN_DIR_PATTERNS):
            continue
        for unit in iter_units(run_dir):
            manifest = read_unit_manifest(unit)
            fw = framework_code(manifest, unit, run_dir)
            topic = detect_topic(unit)
            model = canon_model(
                (manifest or {}).get("evaluation_model"),
                trace_internal_model(unit),
                unit.name,
                run_dir.name,
            )
            if fw not in allow or not topic or not model:
                continue
            cells.setdefault((fw, topic, model), []).append(unit)
    return cells


def pick_representative(runs: list[Path], topic: str, anchors: dict) -> tuple[Path, str]:
    """取代表单元 —— **优先「有真实轨迹」，其次「实验数够裁判排序」**。

    轨迹是稀缺资源，而官方分可另从整格取「每格最优」，两者不必同一个单元。
    两次踩坑都在这：
    - 按官方分选 → 把有轨迹的单元丢掉，arc 整列变 0/21；
    - 无轨迹时返回 `runs[0]`（任意第一个）→ 选到 **0 实验**的单元，
      裁判无从排序，实测 39 个序数任务里 **29 个**因此白跑（`insufficient_experiments: n=0`）。
    """
    analysed = [(analyze_run(r, topic, anchors, strict_anchors=False), r) for r in runs]
    with_traj = [r for rec, r in analysed if rec.get("basis") == "trace_metric"]
    if with_traj:
        return with_traj[0], "has_trajectory"
    # 没有同族字段 -> 将走裁判序数；必须挑实验数最多的单元，否则裁判没得排
    ranked = sorted(
        ((int(rec.get("n_experiments") or 0), r) for rec, r in analysed),
        key=lambda pair: pair[0], reverse=True,
    )
    if ranked and ranked[0][0] >= 2:
        return ranked[0][1], "most_experiments_for_ordinal"
    return (ranked[0][1] if ranked else runs[0]), "insufficient_experiments"


def best_official(runs: list[Path], topic: str) -> tuple[float | None, Path | None]:
    """整格里最优的官方分（与权威矩阵「每格最优」口径一致）。

    ⚠️ 剔除必须做在**候选阶段**，不能做在"选出最优之后"：
    否则一个占位符 0.0（arc 越小越好，它天然是最优）会先被选中、再被置空，
    把同格另一个**合法**的 0.0665 一起丢掉 —— 实测就这么少算了一格。
    """
    exclusions = load_exclusions()
    pairs = []
    for r in runs:
        if any(k in exclusions for k in exclusion_keys(r)):
            continue
        value = official_score(r, topic)
        if value is not None:
            pairs.append((value, r))
    if not pairs and topic == "babylm":
        # 回退：BabyLM 的官方分本来就写在 trace 里（见 `babylm_trace_score` 的说明）。
        # **只在 score.json 没给分时才走这条**，并会在 `basis_official` 里标成
        # framework_self_reported —— 不与真官方的外部评分器同档。
        for r in runs:
            if any(k in exclusions for k in exclusion_keys(r)):
                continue
            value = babylm_trace_score(r)
            if value is not None:
                pairs.append((value, r))
        if pairs:
            best = min(pairs, key=lambda x: x[0])
            return best[0], best[1], "framework_self_reported"
    if not pairs:
        return None, None, "none"
    best = (min if topic in LOWER_BETTER else max)(pairs, key=lambda x: x[0])
    return best[0], best[1], "scored"


def best_judge(runs: list[Path]) -> tuple[Path | None, dict[str, float | None]]:
    """判官七维同样**不绑代表 run** —— 被评过的 run 往往不是有轨迹的那个。

    实测：绑代表 run 时只有 7/96 格有判官分；按格内任取被评过的 run 后覆盖大幅上升。
    """
    for run_dir in runs:
        dims = read_judge_dims(run_dir)
        if any(v is not None for v in dims.values()):
            return run_dir, dims
    return None, {dim: None for dim in JUDGE_DIMS}


JUDGE_CACHE_DIR = Path(__file__).resolve().parent / ".judge_cache"


def _cache_path(kind: str, unit: Path) -> Path:
    key = hashlib.sha1(str(unit.resolve()).encode("utf-8")).hexdigest()[:16]
    return JUDGE_CACHE_DIR / f"{kind}__{key}.json"


def cached_judge(kind: str, unit: Path, topic: str, runner, **kwargs) -> dict[str, object]:
    """裁判调用走磁盘缓存 —— 3 采样 × 上百格很贵，重跑不该重复付费。"""
    path = _cache_path(kind, unit)
    if path.is_file():
        try:
            cached = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(cached, dict):
                cached["_cached"] = True
                return cached
        except Exception:  # noqa: BLE001
            pass
    result = runner(unit, topic, **kwargs)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    result["_cached"] = False
    return result


def build_row(
    cell: tuple[str, str, str], runs: list[Path], anchors: dict,
    judge_opts: dict[str, object] | None = None,
) -> dict[str, object]:
    fw, topic, model = cell
    run_dir, how = pick_representative(runs, topic, anchors)
    traj = analyze_run(run_dir, topic, anchors, strict_anchors=False)
    judge_run, judge = best_judge(runs)
    off_value, off_run, off_kind = best_official(runs, topic)

    row: dict[str, object] = {
        "framework": fw,
        "framework_name": FRAMEWORK_NAME.get(fw, fw),
        "topic": topic,
        "model": model,
        "run_dir": run_dir.name,          # 轨迹取自这个 run
        "run_selection": how,
        "n_runs_in_cell": len(runs),
        "n_points": traj.get("n_points"),
        "metric_field": traj.get("metric_field"),
        "flat_trajectory": traj.get("flat_trajectory"),
        # 轨迹五项
        "b0": traj.get("b0"),
        "bT": traj.get("bT"),
        "aup": traj.get("aup"),
        "aup_rel": traj.get("aup_rel"),
        "t_first": traj.get("t_first"),
        "ur": traj.get("ur"),
        # 原始尺度（保留，便于复算与对账）
        "b0_raw": traj.get("b0_raw"),
        "bT_raw": traj.get("bT_raw"),
        # 官方终值：整格最优，**可能来自另一个 run**，所以单独记来源
        "official_final": off_value if off_value is not None else traj.get("official_final"),
        "official_run_dir": (off_run or run_dir).name,
        # 官方分的档位：**2026-10-12 新增**。此前 official_final 一列混着「真官方外部评分器」
        # 与「框架自报」而不加区分，BabyLM 又天生是后者 —— 出表时极易误读成官方。
        "basis_official": (
            "framework_self_reported" if off_kind == "framework_self_reported"
            else _official_source_field(off_run, topic) if off_value is not None
            else "none"),
        "bt_vs_official": traj.get("bt_vs_official"),
        # 逐指标 basis（表里没有 basis 列就会被误读）
        "basis_trajectory": traj.get("basis") or (
            "pending_anchor" if traj.get("anchor_error") else "none"
        ),
        "basis_judge": (
            f"judge_7dim_substituted({judge_substitution(judge_run)})" if judge_run and judge_substitution(judge_run)
            else "judge_7dim" if any(v is not None for v in judge.values())
            else "missing"),
        "judge_run_dir": judge_run.name if judge_run else None,
        "judge_model": judge_model_of(judge_run),
        # ED 与序数兜底的默认值（未开 --judge 时保持 null）
        "ed": None, "ed_n_clusters": None, "basis_ed": "not_run",
        "traj_error": traj.get("error"),
    }

    if judge_opts:
        import trajectory_judge as TJ

        dry = bool(judge_opts.get("dry"))
        samples = int(judge_opts.get("samples", 3))
        budget: list[int] = judge_opts["budget"]  # type: ignore[assignment]

        def run_or_defer(kind: str, runner) -> dict[str, object]:
            """缓存命中就直接用；未命中且还有预算才真调；dry 只登记不调。"""
            path = _cache_path(kind, run_dir)
            if path.is_file() or dry or budget[0] <= 0:
                if path.is_file():
                    return cached_judge(kind, run_dir, topic, runner, samples=samples)
                row[f"_would_call_{kind}"] = True
                return {"_deferred": True}
            budget[0] -= 1
            result = cached_judge(kind, run_dir, topic, runner, samples=samples)
            row["_judge_called"] = True
            return result

        # ① 轨迹：没有同族字段的格子走裁判**序数**评估
        if row["basis_trajectory"] != "trace_metric":
            ordinal = run_or_defer("ordinal", TJ.assess_trajectory_ordinal)
            if not ordinal.get("_deferred"):
                row["basis_trajectory"] = "judge_ordinal"
                row["ordinal_error"] = ordinal.get("error")
                row["ordinal_agreement"] = ordinal.get("agreement")
                row["low_confidence"] = ordinal.get("low_confidence")
                row["is_performance_measurement"] = False
                for key in ("b0", "bT", "b0_raw", "bT_raw", "aup", "aup_rel",
                            "t_first", "ur"):
                    if ordinal.get(key) is not None:
                        row[key] = ordinal[key]
                row["n_points"] = row["n_points"] or ordinal.get("n_experiments")
        else:
            row["is_performance_measurement"] = True

        # ② ED：与轨迹口径无关，独立于上面
        ed = run_or_defer("ed", TJ.assess_ed)
        if not ed.get("_deferred"):
            row["ed"] = ed.get("ed")
            row["ed_n_clusters"] = ed.get("n_clusters")
            row["ed_error"] = ed.get("error")
            row["ed_agreement"] = ed.get("agreement")
            row["basis_ed"] = "judge_cluster" if ed.get("ed") is not None else "unavailable"

    row.update(judge)

    # 裁定不可入账的 run：**不静默丢格**，而是把值置空 + 标注原因，行仍留在表里。
    # 轨迹与官方分分开判：只有当**轨迹来源的那个 run** 被剔除时，轨迹才一起置空。
    exclusions = load_exclusions()
    traj_hit = next((exclusions[k] for k in exclusion_keys(run_dir) if k in exclusions), None)
    off_candidates = exclusion_keys(off_run) if off_run is not None else (
        (str(row.get("official_run_dir")),) if row.get("official_run_dir") else ())
    off_hit = next((exclusions[k] for k in off_candidates if k in exclusions), None)
    if traj_hit or off_hit:
        hit = traj_hit or off_hit
        scope = str(hit.get("scope") or "score")   # score | both
        row["excluded_recorded_score"] = hit.get("recorded_score")
        row["exclusion_class"] = hit.get("class")
        row["exclusion_scope"] = scope
        row["exclusion_reason"] = f"{hit.get('class')}（scope={scope}）：见 automation/scripts/score_exclusions.json"
        if off_hit:
            row["official_final"] = None
        if traj_hit and scope == "both":
            for key in ("b0", "bT", "b0_raw", "bT_raw", "aup", "aup_rel", "t_first", "ur"):
                row[key] = None
            row["n_points"] = None
            row["flat_trajectory"] = None
            row["basis_trajectory"] = f"excluded_{hit.get('class')}"
    return row


def parse_aux_spec(spec: str) -> tuple[Path, tuple[str, ...]]:
    """`PATH:01,02` → (Path, ("01","02"))。"""
    path_text, _, codes_text = spec.rpartition(":")
    codes = tuple(code.strip() for code in codes_text.split(",") if code.strip())
    if not path_text or not codes:
        raise argparse.ArgumentTypeError(f"额外 root 格式应为 PATH:01,02，收到 {spec!r}")
    return Path(path_text), codes


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="12 项指标汇总成表（默认 7 框架 140 格）")
    parser.add_argument("--runs-root", type=Path, default=DEFAULT_RUNS_ROOT)
    parser.add_argument("--aux-runs-root", action="append", type=parse_aux_spec,
                        default=None, metavar="PATH:01,02",
                        help="额外 root + 该 root 允许的框架码（可重复）；"
                             "默认用内置的 runs_0102")
    parser.add_argument("--no-aux", action="store_true",
                        help="不扫额外 root → 回到 5 框架 100 格口径")
    parser.add_argument("--out-prefix", type=Path, default=Path("/tmp/evaluation_metrics"))
    parser.add_argument("--csv", action="store_true", help="同时输出 CSV")
    parser.add_argument("--judge", action="store_true",
                        help="对缺同族字段的格子跑裁判序数评估，并算 ED（要调 LLM）")
    parser.add_argument("--judge-samples", type=int, default=3,
                        help="每次裁判调用采样几次（默认 3，用于报一致性）")
    parser.add_argument("--judge-limit", type=int,
                        help="最多对多少格调裁判（冒烟用）；已缓存的格子不算在内")
    parser.add_argument("--dry-run", action="store_true",
                        help="只报将要发生多少次裁判调用，不真的调")
    parser.add_argument("--workers", type=int, default=1,
                        help="并发处理的格子数（默认 1 = 串行）。裁判调用是网络等待为主，"
                             "加并发只压墙钟，不改任何取值口径")
    args = parser.parse_args(argv)
    workers = max(1, args.workers)

    anchors = load_anchors()
    if args.no_aux:
        aux_roots: tuple[tuple[Path, tuple[str, ...]], ...] = ()
    elif args.aux_runs_root:
        aux_roots = tuple(args.aux_runs_root)
    else:
        aux_roots = AUX_RUNS_ROOTS

    roots: list[tuple[Path, tuple[str, ...]]] = [(args.runs_root, FRAMEWORK_ORDER)]
    roots.extend(aux_roots)

    cells: dict[tuple[str, str, str], list[Path]] = {}
    scanned: list[str] = []
    for root, allowed in roots:
        if not root.is_dir():
            print(f"[warn] root 不存在，跳过: {root}", file=sys.stderr)
            continue
        found = collect_cells(root, allowed=allowed)
        for cell, units in found.items():
            cells.setdefault(cell, []).extend(units)
        scanned.append(f"{root} ({'/'.join(allowed)})")
    if not cells:
        print("[warn] 一个格子都没扫到 —— 检查 --runs-root", file=sys.stderr)

    budget = [args.judge_limit if args.judge_limit is not None else 10**9]

    judge_opts: dict[str, object] | None = None
    if args.judge or args.dry_run:
        judge_opts = {"samples": args.judge_samples, "budget": budget, "dry": args.dry_run}

    # 裁判调用是**网络等待为主**，格子之间互不相干（各自的缓存文件按 run 路径分文件，
    # 不同格子写不到同一个文件），所以可以按格并行。默认 `--workers 1` = 原行为。
    #
    # ⚠️ `judge_opts["budget"]` 是共享计数器，并发下可能略微超额（几格的量级）。
    # 需要严格上限时用 `--workers 1`；或者只给 `--judge-limit` 留足余量。
    cell_items = sorted(cells.items())
    if workers > 1 and judge_opts and not args.dry_run:
        from concurrent.futures import ThreadPoolExecutor
        print(f"并发 {workers} 个格子（每格内部仍顺序）")
        with ThreadPoolExecutor(max_workers=workers) as pool:
            rows = list(pool.map(
                lambda item: build_row(item[0], item[1], anchors, judge_opts), cell_items))
    else:
        rows = [build_row(cell, runs, anchors, judge_opts) for cell, runs in cell_items]

    if args.dry_run:
        width = args.judge_samples
        would_ord = sum(1 for r in rows if r.get("_would_call_ordinal"))
        would_ed = sum(1 for r in rows if r.get("_would_call_ed"))
        need_ord = sum(1 for r in rows if r["basis_trajectory"] != "trace_metric")
        need_ed = len(rows)
        cached = (need_ord + need_ed) - (would_ord + would_ed)
        print("=== DRY RUN：没有真的调用 ===")
        print(f"  序数任务: 需要 {need_ord}，其中缓存命中 {need_ord - would_ord}，待调用 {would_ord}")
        print(f"  ED 任务:  需要 {need_ed}，其中缓存命中 {need_ed - would_ed}，待调用 {would_ed}")
        print(f"  合计缓存命中（免费）: {cached}")
        print(f"  采样 {args.judge_samples} 次 → 预计 LLM 调用约 "
              f"{(would_ord + would_ed) * width} 次")
        print(f"  缓存目录: {JUDGE_CACHE_DIR}")
        return 0

    payload = {"runs_root": str(args.runs_root), "runs_roots": scanned,
               "n_cells": len(rows), "rows": rows}
    args.out_prefix.parent.mkdir(parents=True, exist_ok=True)
    args.out_prefix.with_suffix(".json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    if args.csv:
        # 列名必须取**所有行键的并集**：走裁判路径的行会多出
        # ordinal_error / _judge_called / low_confidence 等键，
        # 只取第一行会 ValueError（实测踩到，整轮 CSV 导出失败）。
        cols: list[str] = []
        for row in rows:
            for key in row:
                if key not in cols:
                    cols.append(key)
        with args.out_prefix.with_suffix(".csv").open("w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=cols, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(rows)

    # 覆盖率：只报事实，不美化
    def count(pred) -> int:
        return sum(1 for r in rows if pred(r))

    print(f"格子数: {len(rows)}")
    print(f"  轨迹-真实指标(trace_metric): {count(lambda r: r['basis_trajectory'] == 'trace_metric')}")
    print(f"  轨迹-裁判序数(judge_ordinal): {count(lambda r: r['basis_trajectory'] == 'judge_ordinal' and r.get('b0') is not None)}")
    print(f"  轨迹-仍无值:                 {count(lambda r: r.get('b0') is None)}")
    print(f"  判官七维有值:                {count(lambda r: r['basis_judge'] == 'judge_7dim')}")
    print(f"  ED 有值:                     {count(lambda r: r.get('ed') is not None)}")

    print("\n按 topic：")
    for topic in TOPIC_ORDER:
        sub = [r for r in rows if r["topic"] == topic]
        if not sub:
            continue
        real = sum(1 for r in sub if r["basis_trajectory"] == "trace_metric")
        ordi = sum(1 for r in sub if r["basis_trajectory"] == "judge_ordinal" and r.get("b0") is not None)
        ed = sum(1 for r in sub if r.get("ed") is not None)
        print(f"   {topic:8s} 真实 {real:2d}  序数 {ordi:2d}  共 {len(sub):2d}   ED {ed:2d}")

    print("\n按框架（格子数 / 官方终值有值 / 判官七维有值）：")
    for fw in sorted({r["framework"] for r in rows}):
        sub = [r for r in rows if r["framework"] == fw]
        off = sum(1 for r in sub if r.get("official_final") is not None)
        jud = sum(1 for r in sub if r["basis_judge"] == "judge_7dim")
        name = FRAMEWORK_NAME.get(fw, fw)
        print(f"   {fw} {name:18s} 共 {len(sub):3d}   官方 {off:3d}   判官 {jud:3d}")

    if judge_opts:
        called = count(lambda r: r.get("_judge_called"))
        print(f"\n本轮实际发生裁判调用（未走缓存）的格子: {called}")

    missing = [f"{r['framework']}×{r['topic']}×{r['model']}" for r in rows
               if r.get("b0") is None]
    if missing:
        print(f"\n仍无 b0 的格子 ({len(missing)}):")
        for m in missing[:12]:
            print(f"   {m}")
    print(f"\n-> {args.out_prefix.with_suffix('.json')}")
    return 0


def _unit_of(cells: dict, row: dict) -> Path:
    """按行里的 run_dir 找回它所属的单元目录（用于缓存键）。"""
    for units in cells.values():
        for u in units:
            if u.name == row["run_dir"]:
                return u
    return Path("/nonexistent")


if __name__ == "__main__":
    raise SystemExit(main())
