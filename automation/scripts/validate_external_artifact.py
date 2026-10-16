#!/usr/bin/env python3
"""外部交付包验收 + 官方出分。

场景：协作者用他们自己的环境/框架跑，只交回研究产物（见
`docs/external_artifact_handover.md`）。本脚本做两件事：

1. **静态验收**（默认）—— 结构 + **真载荷**检查。判据来自各 topic 的官方评分器，
   而不是「数量/md5/字节数」这类结构指标（那两个假阳性实例见规范 §7）。
2. **官方出分**（`--score`）—— 静态验收全绿后，调 host 评分器重算官方分。
   `--apply` 才把分落进 `workspace/score.json`，否则只写到包内 `_score.json`。

设计约定：
- 只读；除了 `--apply` 时不碰被验收的包。
- 每条判据都带**证据**，失败时给可读原因（官方链路很多地方是静默失败的）。
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import pickle
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "automation" / "scripts"
sys.path.insert(0, str(SCRIPTS))

TOPICS = ("arc", "mc", "babylm", "psydef", "tdc")

# 与 run_mountaincar_continuous_host_score.py 的 DEFAULT_TOPIC_ROOT 一致
DEFAULT_TOPIC2_ROOT = ROOT / "data" / "topic2"
DEFAULT_ARC_ROOT = ROOT / "data" / "arc_white_box_estimation_2026"
# arc 的官方分只对 **scoring** 子集算（90 个 MLP），与框架可见的
# visible-validation（10 个）互斥。指向整个 root 会把可见集的标签算进去 ——
# 既评错集合，又让框架能靠自评集里的真值刷分。
# 切分见 automation/scripts/make_arc_wbe_2026_visible_validation.py。
DEFAULT_ARC_SCORING_ROOT = DEFAULT_ARC_ROOT / "scoring"
DEFAULT_PSYDEF_ROOT = ROOT / "data" / "psydefdetect"
DEFAULT_TDC_ROOT = ROOT / "data" / "tdc_admet_tox"
CANONICAL_PSYDEF_SPLIT = ROOT / "automation" / "psydefdetect_split.canonical.json"

# ARC 评分运行时。持久副本由 `.tools/whest/setup.sh` 重建；
# /tmp 那份是历史遗留、会被清空，仅作回退。
WHEST_VENV_BIN = ROOT / ".tools" / "whest" / ".venv" / "bin" / "whest"
LEGACY_WHEST_BIN = Path("/tmp/whest-starterkit/whest-starterkit/.venv/bin/whest")

# 外部框架走 generic 分支：要求 `class Estimator` 或 `build_estimator`，
# 且 predict 是带 self 的方法。hint 必须落在 {01..07} 内，否则扫描直接抛。
DEFAULT_FRAMEWORK_HINT = "04"

PROVENANCE_REQUIRED = (
    "framework",
    "model",
    "topic",
    "native_entrypoint",
    "run_started_at",
    "run_finished_at",
)

# 适配器与评分器的反占位符守卫（arc_wbe_2026_official_adapter._scan_file）
PLACEHOLDER_CONST_RE = re.compile(r"return\s+(?:\w+\.)?(?:zeros|ones|full|empty)\s*\(")
PLACEHOLDER_WORD_RE = re.compile(
    r"\b(?:placeholder|synthetic\s+prediction|fallback\s+prediction)\b", re.I
)

TDC_TEST_FIELDS = ("sample_id", "endpoint", "smiles")
TDC_PRED_FIELDS = ("sample_id", "endpoint", "probability")

# 评分沙箱是密封的：只有标准库 + flopscope.numpy + whestbench API。
# 唯一的例外是适配器会注入只含 erf 的 scipy.special 垫片。
SANDBOX_FORBIDDEN_ROOTS = {"torch", "numpy", "scipy"}
SANDBOX_ALLOWED_SCIPY_SPECIAL = {"erf"}


class Report:
    """收集判据结果；每项带证据，便于回给交付方。"""

    def __init__(self, package: Path, topic: str) -> None:
        self.package = package
        self.topic = topic
        self.checks: list[dict[str, object]] = []

    def add(self, name: str, ok: bool, evidence: str = "", *, fatal: bool = True) -> bool:
        self.checks.append(
            {"check": name, "status": "PASS" if ok else "FAIL", "evidence": evidence,
             "fatal": fatal}
        )
        return ok

    @property
    def ok(self) -> bool:
        return all(c["status"] == "PASS" or not c["fatal"] for c in self.checks)

    def dump(self, extra: dict[str, object] | None = None) -> dict[str, object]:
        payload: dict[str, object] = {
            "package": str(self.package),
            "topic": self.topic,
            "verdict": "ACCEPT" if self.ok else "REJECT",
            "failed": [c["check"] for c in self.checks if c["status"] == "FAIL" and c["fatal"]],
            "warnings": [c["check"] for c in self.checks if c["status"] == "FAIL" and not c["fatal"]],
            "checks": self.checks,
        }
        if extra:
            payload.update(extra)
        return payload


def resolve_whest_bin() -> tuple[Path | None, str]:
    """找 whest 运行时。优先仓库内持久副本，/tmp 那份只作回退。"""
    if WHEST_VENV_BIN.is_file():
        return WHEST_VENV_BIN, "仓库内持久副本"
    if LEGACY_WHEST_BIN.is_file():
        return LEGACY_WHEST_BIN, "⚠️ /tmp 回退（会被清空；跑 .tools/whest/setup.sh 重建）"
    return None, "未找到（跑 .tools/whest/setup.sh 重建）"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_json(path: Path) -> object | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


class _Stub:
    """占位类型：把 pickle 里引用的类全部替换成它，从而无需真实运行时。"""

    def __init__(self, *args: object, **kwargs: object) -> None:
        pass

    def __setstate__(self, state: object) -> None:
        pass

    def __setitem__(self, key: object, value: object) -> None:
        pass

    def __getitem__(self, key: object) -> None:
        return None

    def __reduce__(self) -> object:  # pragma: no cover - 仅防御
        return (_Stub, ())


# 这些模块的类必须用真的，否则连顶层 dict 本身都会变成桩
_SAFE_MODULES = {"builtins", "__builtin__", "collections", "collections.abc", "_collections"}


class _PeekUnpickler(pickle.Unpickler):
    """只读顶层容器的「结构窥探器」：不导入 jax/torch/flax，也不构造真对象。"""

    def find_class(self, module: str, name: str) -> object:  # noqa: D102
        if module in _SAFE_MODULES:
            try:
                return super().find_class(module, name)
            except Exception:  # noqa: BLE001
                return _Stub
        return _Stub

    def persistent_load(self, pid: object) -> None:  # noqa: D102
        return None


def peek_top_level_keys(path: Path) -> tuple[list[str] | None, str]:
    """读 checkpoint 顶层 dict 的键，**不要求** jax/flax/torch 可用。

    先按常规反序列化；若因缺依赖失败（历史教训：「要装某包才能打开」本身就是
    载荷类型信号），退回结构窥探 —— 顶层容器本身不依赖这些类型，能照样读出来。
    """
    try:
        with path.open("rb") as handle:
            obj = pickle.load(handle)
        if isinstance(obj, dict):
            return sorted(map(str, obj)), "direct"
    except Exception as first_error:  # noqa: BLE001
        try:
            with path.open("rb") as handle:
                obj = _PeekUnpickler(handle).load()
            if isinstance(obj, dict):
                return sorted(map(str, obj)), "peek"
        except Exception:  # noqa: BLE001
            pass
        return None, f"{type(first_error).__name__}: {first_error}"
    return None, f"not a dict ({type(obj).__name__})"


# ---------------------------------------------------------------- 通用必交件


def check_common(pkg: Path, rep: Report) -> Path | None:
    ws = pkg / "workspace"
    if not rep.add("workspace/ 目录存在", ws.is_dir(), str(ws)):
        return None

    for name in ("research_idea.json", "experiment_trace.json"):
        path = ws / name
        parsed = read_json(path) if path.is_file() else None
        rep.add(
            f"workspace/{name} 可解析",
            parsed is not None,
            "missing" if not path.is_file() else ("parse error" if parsed is None else "ok"),
        )

    report_md = ws / "final_report.md"
    size = report_md.stat().st_size if report_md.is_file() else 0
    rep.add("workspace/final_report.md 非空", size > 0, f"{size} bytes")

    prov = pkg / "PROVENANCE.json"
    payload = read_json(prov) if prov.is_file() else None
    prov_evidence = (
        "ok" if isinstance(payload, dict)
        else ("missing" if not prov.is_file() else "parse error")
    )
    if rep.add("PROVENANCE.json 存在且可解析", isinstance(payload, dict), prov_evidence):
        assert isinstance(payload, dict)
        missing = [k for k in PROVENANCE_REQUIRED if not payload.get(k)]
        rep.add("PROVENANCE.json 必填字段齐", not missing, f"missing: {missing}")
        origin = payload.get("evaluator_origin")
        rep.add(
            "PROVENANCE.evaluator_origin 合法",
            origin in {"self_provided", "host_injected_expected"},
            f"got {origin!r}",
        )
        for field in ("run_started_at", "run_finished_at"):
            value = str(payload.get(field) or "")
            # 单调时钟被当成 Unix 秒的历史事故：1970-xx
            bad = value.startswith("1970-") or not value.endswith("Z")
            rep.add(f"PROVENANCE.{field} 是 UTC ISO8601", not bad, f"got {value!r}")

    # 日志路径必须与七维判官读的完全一致（见 hybrid_judge.build_sandbox）：
    # 判官只认 logs/e2e.log → logs/native.log → logs/native_stdout.log，
    # **不读根目录的 run.log**。这里若不同步，校验器会放行一个判官读不到日志的包，
    # 而判官缺日志不报错、照常给分 —— ER/SC/CC 三维会静默变成假分。
    log = next(
        (p for p in (pkg / "logs/e2e.log", pkg / "logs/native.log",
                     pkg / "logs/native_stdout.log") if p.is_file()),
        pkg / "logs/e2e.log",
    )
    log_size = log.stat().st_size if log.is_file() else 0
    rep.add(
        "logs/e2e.log 存在且非空（判官日志路径）",
        log_size > 0,
        f"{log.relative_to(pkg)}: {log_size} bytes",
        fatal=False,
    )
    return ws


# ---------------------------------------------------------------------- arc


def _collect_predict_signatures(tree: ast.AST) -> list[dict[str, object]]:
    found: list[dict[str, object]] = []

    def walk(node: ast.AST, class_name: str | None) -> None:
        for child in ast.iter_child_nodes(node):
            if isinstance(child, ast.ClassDef):
                walk(child, child.name)
            elif isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if child.name in {"predict", "build_estimator", "estimate"}:
                    args = [a.arg for a in child.args.posonlyargs + child.args.args]
                    found.append(
                        {
                            "name": child.name,
                            "in_class": class_name,
                            "args": args,
                            "lineno": child.lineno,
                        }
                    )
                walk(child, class_name)
            else:
                walk(child, class_name)

    walk(tree, None)
    return found


def _forbidden_imports(tree: ast.AST) -> list[str]:
    """找出评分沙箱里不可用的 import。"""
    bad: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.split(".")[0] in SANDBOX_FORBIDDEN_ROOTS:
                    bad.append(f"import {alias.name}")
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            root = module.split(".")[0]
            if root == "scipy":
                # 适配器只注入了 erf 垫片
                if module == "scipy.special" and all(
                    a.name in SANDBOX_ALLOWED_SCIPY_SPECIAL for a in node.names
                ):
                    continue
                bad.append(f"from {module} import ...")
            elif root in SANDBOX_FORBIDDEN_ROOTS:
                bad.append(f"from {module} import ...")
    return bad


def check_arc(pkg: Path, ws: Path, rep: Report, hint: str) -> None:
    estimator = ws / "estimator.py"
    # 适配器只读 workspace/estimator.py，不递归 —— 位置是硬要求
    if not rep.add("workspace/estimator.py 存在（位置是硬要求）", estimator.is_file(), str(estimator)):
        return

    text = estimator.read_text(encoding="utf-8", errors="ignore")

    rep.add(
        "不含占位符常量返回",
        not PLACEHOLDER_CONST_RE.search(text),
        "matched return zeros(/ones(/full(/empty(",
    )
    rep.add(
        "不含 placeholder 措辞",
        not PLACEHOLDER_WORD_RE.search(text),
        "matched placeholder/synthetic prediction/fallback prediction",
    )

    try:
        tree = ast.parse(text)
        rep.add("estimator.py 可 ast.parse", True, "ok")
    except SyntaxError as exc:
        rep.add("estimator.py 可 ast.parse", False, f"{exc}")
        return

    banned = _forbidden_imports(tree)
    rep.add(
        "不含沙箱禁用的 import（扫描能过、执行阶段才挂）",
        not banned,
        f"sandbox has no pip step; offenders={banned}"
        if banned
        else "只用 stdlib / flopscope / whestbench（或 scipy.special.erf）",
    )

    has_class = re.search(r"class\s+Estimator\b", text) is not None
    has_factory = "def build_estimator" in text
    rep.add("有 class Estimator 或 build_estimator（generic 分支要求）",
            has_class or has_factory, f"class Estimator={has_class} build_estimator={has_factory}")

    sigs = _collect_predict_signatures(tree)
    method = [s for s in sigs if s["name"] == "predict" and s["in_class"]]
    if not rep.add(
        "predict 是带 self 的方法（模块级 def predict(mlp) 会被静默扫不到）",
        bool(method),
        f"saw: {[ (s['name'], s['in_class'], s['lineno']) for s in sigs ]}",
    ):
        return

    sig = method[0]
    args = list(sig["args"])  # type: ignore[arg-type]
    # self 之外至少要有 (mlp|weights,)；官方引擎是 predict(mlp, budget)
    has_mlp = any(a in {"mlp", "weights"} for a in args[1:])
    rep.add(
        "predict 的第一个实参是 mlp/weights",
        has_mlp,
        f"args={args} (line {sig['lineno']})",
    )
    rep.add(
        "predict 带 budget 参数（少写会让 100/100 MLP 全 TypeError）",
        any(a == "budget" for a in args),
        f"args={args}; 官方调用是 estimator.predict(mlp, estimated_budget)",
        fatal=False,
    )

    # 真实扫描：官方链路在 hint 不合法时会抛异常并被吞掉，只剩「零诊断」的一句话
    try:
        from arc_wbe_2026_official_adapter import scan_workspace_for_official_adapter

        result = scan_workspace_for_official_adapter(ws, framework_hint=hint)
        rep.add(
            "适配器扫描能识别（预跑）",
            isinstance(result, dict),
            f"adapter_kind={result.get('adapter_kind')} symbol={result.get('source_symbol')} "
            f"predict_input={result.get('predict_input')}",
        )
    except Exception as exc:  # noqa: BLE001 - 官方链路就是靠吞异常静默的
        rep.add("适配器扫描能识别（预跑）", False,
                f"hint={hint!r} → {type(exc).__name__}: {exc}")

    # 出分依赖 whest 运行时；静态验收阶段就报出来，别等到 --score 才失败
    whest_bin, source = resolve_whest_bin()
    rep.add(
        "whest 运行时可用",
        whest_bin is not None,
        f"{whest_bin}（{source}）" if whest_bin else source,
        fatal=False,
    )


# ----------------------------------------------------------------------- mc


def check_mc(
    pkg: Path, ws: Path, rep: Report, topic_root: Path, config_fname: str
) -> None:
    protected = topic_root / "protected" / "evaluate.py"
    workspace_copy = ws / "evaluate.py"
    if protected.is_file() and workspace_copy.is_file():
        same = sha256_file(protected) == sha256_file(workspace_copy)
        rep.add(
            "workspace/evaluate.py 与冻结副本逐字节一致",
            same,
            f"protected={sha256_file(protected)[:16]} workspace={sha256_file(workspace_copy)[:16]}",
        )
    else:
        rep.add(
            "evaluate.py 缺失 → 将由 host 注入并标注",
            True,
            f"workspace has it={workspace_copy.is_file()}; host protected exists={protected.is_file()}",
            fatal=False,
        )

    stem = Path(config_fname).stem  # "config" for src/config.yaml
    ckpt_dir = ws / "checkpoints"
    files = sorted(ckpt_dir.glob(f"{stem}*.pkl")) if ckpt_dir.is_dir() else []
    rep.add(
        f"checkpoints/{stem}*.pkl 恰好 5 个",
        len(files) == 5,
        f"found {len(files)}: {[f.name for f in files][:8]}",
    )
    expected = [f"{stem}-42-{i}.pkl" for i in range(5)]
    rep.add(
        "命名是 config-42-{0..4}.pkl",
        [f.name for f in files] == expected,
        f"got {[f.name for f in files]} want {expected}",
        fatal=False,
    )

    # 关键：真打开看载荷。「恰好 5 个 pkl」能过而仍然无分 —— 见规范 §7
    for path in files:
        keys, how = peek_top_level_keys(path)
        if keys is None:
            rep.add(f"{path.name} 顶层带 network 键", False, how)
            continue
        note = "" if how == "direct" else "（结构窥探，本机无 jax/torch 运行时）"
        rep.add(
            f"{path.name} 顶层带 network 键",
            "network" in keys,
            f"top-level keys={keys}{note}",
        )

    cfg = ws / config_fname
    if rep.add(f"{config_fname} 存在", cfg.is_file(), str(cfg)):
        try:
            import yaml

            parsed = yaml.safe_load(cfg.read_text(encoding="utf-8"))
            nested = (
                isinstance(parsed, dict)
                and isinstance(parsed.get("train_config"), dict)
                and isinstance(parsed["train_config"].get("network_config"), dict)
            )
            rep.add(
                "config.yaml 是嵌套 schema（train_config.network_config）",
                nested,
                f"top-level keys={sorted(parsed) if isinstance(parsed, dict) else type(parsed).__name__}"
                f"（扁平 YAML 会在构造 Model 时 TypeError）",
            )
        except Exception as exc:  # noqa: BLE001
            rep.add("config.yaml 可解析", False, f"{type(exc).__name__}: {exc}")


# ------------------------------------------------------------------- babylm


def check_babylm(pkg: Path, ws: Path, rep: Report) -> None:
    trace = ws / "experiment_trace.json"
    if not trace.is_file():
        rep.add("experiment_trace.json 存在", False, str(trace))
        return
    payload = read_json(trace)
    if not isinstance(payload, dict):
        rep.add("experiment_trace.json 可解析为 dict", False, "not a dict")
        return

    from run_babylm_score import extract_perplexity

    values: list[float] = []
    for exp in payload.get("experiments", []) or []:
        ppl = extract_perplexity(exp)
        if ppl is not None:
            values.append(ppl)
    for result in payload.get("results", []) or []:
        ppl = extract_perplexity(result)
        if ppl is not None:
            values.append(ppl)
    top = payload.get("best_validation_perplexity")
    if isinstance(top, (int, float)) and top > 0:
        values.append(float(top))

    rep.add(
        "trace 里有有限的 validation_perplexity",
        bool(values),
        f"values={sorted(values)[:8]}"
        if values
        else "trace contains no finite validation metric（null 值会导致整格无分）",
    )
    rep.add(
        "该分是框架自报、无法独立验证",
        True,
        "run_babylm_score.py 直接读交付方的 experiment_trace.json 取最小值；"
        "请一并交训练脚本与日志以便审计",
        fatal=False,
    )


# -------------------------------------------------------------------- psydef


def _load_psydef_predictions(path: Path) -> tuple[dict[str, int], str]:
    predictions: dict[str, int] = {}
    if path.suffix.lower() == ".jsonl":
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                continue
            item_id = item.get("id")
            label = item.get("predicted_label", item.get("label"))
            if isinstance(item_id, str) and isinstance(label, int):
                predictions[item_id] = label
    else:
        import csv

        with path.open(newline="", encoding="utf-8") as handle:
            for row in csv.DictReader(handle):
                item_id = row.get("id")
                raw = row.get("predicted_label") or row.get("label")
                try:
                    if item_id and raw is not None:
                        predictions[item_id] = int(raw)
                except (TypeError, ValueError):
                    continue
    return predictions, path.name


def check_psydef(
    pkg: Path, ws: Path, rep: Report, split_path: Path, predictions: Path | None
) -> None:
    canonical_sha = sha256_file(CANONICAL_PSYDEF_SPLIT) if CANONICAL_PSYDEF_SPLIT.is_file() else None

    # 交付方**自称**用的划分，必须和 canonical 一致 —— 自造划分会引入近重复泄漏
    prov = read_json(pkg / "PROVENANCE.json")
    claimed = (prov or {}).get("split_sha256") if isinstance(prov, dict) else None
    if isinstance(claimed, dict):
        for name, digest in claimed.items():
            if "psydef" not in str(name).lower():
                continue
            rep.add(
                "PROVENANCE 声称的划分 sha256 == canonical",
                canonical_sha is not None and str(digest) == canonical_sha,
                f"{name}={str(digest)[:16]} canonical={str(canonical_sha)[:16]}",
            )

    if rep.add("canonical 划分 manifest 存在", split_path.is_file(), str(split_path)):
        if canonical_sha is not None:
            same = sha256_file(split_path) == canonical_sha
            rep.add(
                "评分所用划分 manifest 的 sha256 == canonical",
                same,
                f"got {sha256_file(split_path)[:16]} canonical {canonical_sha[:16]}"
                "（自造划分会引入近重复泄漏，见规范 §6.2）",
            )
    split = read_json(split_path)
    eval_ids = set((split or {}).get("eval_record_ids") or []) if isinstance(split, dict) else set()
    if eval_ids:
        rep.add("划分含 eval_record_ids", True, f"{len(eval_ids)} ids")

    candidates = [predictions] if predictions else []
    candidates += [ws / "predictions.jsonl", ws / "predictions.csv"]
    found = next((p for p in candidates if p and p.is_file()), None)
    if not rep.add("predictions.jsonl 存在", found is not None,
                   f"tried {[str(p) for p in candidates if p]}"):
        return

    assert found is not None
    parsed, name = _load_psydef_predictions(found)
    rep.add("predictions 可解析出 (id, int label)", bool(parsed), f"{name}: {len(parsed)} rows")

    if eval_ids and parsed:
        missing = sorted(eval_ids - set(parsed))
        rep.add(
            "覆盖全部 eval id",
            not missing,
            f"missing {len(missing)} of {len(eval_ids)}: {missing[:8]}",
        )


# ---------------------------------------------------------------------- tdc


def check_tdc(
    pkg: Path, ws: Path, rep: Report, public_root: Path, hidden_labels: Path | None,
    predictions: Path | None
) -> None:
    pred = predictions or (ws / "predictions.csv")
    if not rep.add("predictions.csv 存在", pred.is_file(), str(pred)):
        return

    import csv

    with pred.open(newline="", encoding="utf-8") as handle:
        reader = csv.reader(handle)
        header = next(reader, None)
    rep.add(
        "表头精确等于 sample_id,endpoint,probability",
        tuple(header or ()) == TDC_PRED_FIELDS,
        f"got {header}",
    )

    keys: list[tuple[str, str]] = []
    with pred.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames == list(TDC_PRED_FIELDS):
            for row in reader:
                keys.append((row["sample_id"], row["endpoint"]))
    dupes = len(keys) - len(set(keys))
    rep.add("无重复 (sample_id, endpoint)", dupes == 0, f"{dupes} duplicates")

    public_test = public_root / "test.csv"
    if public_test.is_file() and keys:
        with public_test.open(newline="", encoding="utf-8") as handle:
            reader = csv.reader(handle)
            pub_header = next(reader, None)
            rep.add(
                "public test 表头符合契约（自查，防数据集被换）",
                tuple(pub_header or ()) == TDC_TEST_FIELDS,
                f"got {pub_header}",
                fatal=False,
            )
            pub_keys = [(r[0], r[1]) for r in reader if len(r) >= 3]
        rep.add(
            "predictions 键集合与 public test 一致",
            set(pub_keys) == set(keys),
            f"pred={len(set(keys))} test={len(set(pub_keys))} "
            f"missing={len(set(pub_keys) - set(keys))} extra={len(set(keys) - set(pub_keys))}",
        )

    if hidden_labels and hidden_labels.is_file():
        with hidden_labels.open(newline="", encoding="utf-8") as handle:
            reader = csv.reader(handle)
            next(reader, None)
            lab_keys = {(r[0], r[1]) for r in reader if len(r) >= 3}
        rep.add(
            "predictions 键集合与隐藏标签一致",
            set(lab_keys) == set(keys),
            f"missing={len(set(lab_keys) - set(keys))} extra={len(set(keys) - set(lab_keys))}",
        )
    else:
        rep.add("隐藏标签可用（仅 host 侧）", False, "未提供 --hidden-labels，跳过键集合比对",
                fatal=False)


# ------------------------------------------------------------------- 出分


def run_scorer(topic: str, pkg: Path, ws: Path, args: argparse.Namespace, out: Path) -> dict:
    """调官方评分器。输出一律先写临时路径（评分器拒绝覆盖已存在的 score.json）。"""
    cmd: list[str]
    if topic == "mc":
        cmd = [sys.executable, str(SCRIPTS / "run_mountaincar_continuous_host_score.py"),
               "--workspace", str(ws), "--output-score", str(out),
               "--dataset-root", str(args.dataset_root or DEFAULT_TOPIC2_ROOT)]
    elif topic == "babylm":
        cmd = [sys.executable, str(SCRIPTS / "run_babylm_score.py"),
               "--run-root", str(pkg), "--output-score", str(out)]
    elif topic == "psydef":
        cmd = [sys.executable, str(SCRIPTS / "run_psydefdetect_local_score.py"),
               "--dataset-root", str(args.dataset_root or DEFAULT_PSYDEF_ROOT),
               "--split-manifest", str(args.split_manifest or CANONICAL_PSYDEF_SPLIT),
               "--predictions", str(args.predictions or ws / "predictions.jsonl"),
               "--output-score", str(out)]
    elif topic == "tdc":
        cmd = [sys.executable, str(SCRIPTS / "run_tdc_admet_tox_host_score.py"),
               "--public-dataset-root", str(args.dataset_root or DEFAULT_TDC_ROOT / "public"),
               "--hidden-labels", str(args.hidden_labels
                                      or DEFAULT_TDC_ROOT / "hidden" / "test_labels.csv"),
               "--predictions", str(args.predictions or ws / "predictions.csv"),
               "--output-score", str(out)]
    elif topic == "arc":
        cmd = [sys.executable, str(SCRIPTS / "run_arc_wbe_2026_local_score.py"),
               "--workspace", str(ws), "--output-score", str(out),
               "--dataset-root", str(args.dataset_root or DEFAULT_ARC_SCORING_ROOT),
               "--framework-hint", args.framework_hint,
               "--whest-output-root", str(out.parent / "_whest_out")]
    else:  # pragma: no cover - argparse 已限定 choices
        raise SystemExit(f"unsupported topic {topic}")

    whest_bin = args.whest_bin or resolve_whest_bin()[0]
    if whest_bin:
        cmd += ["--whest-bin", str(whest_bin)]
    completed = subprocess.run(cmd, text=True, capture_output=True, cwd=str(ROOT))
    return {
        "cmd": " ".join(cmd),
        "returncode": completed.returncode,
        "stdout_tail": completed.stdout[-2000:],
        "stderr_tail": completed.stderr[-2000:],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="外部交付包验收 + 官方出分")
    parser.add_argument("--package", type=Path, required=True)
    parser.add_argument("--topic", required=True, choices=TOPICS)
    parser.add_argument("--framework-hint", default=DEFAULT_FRAMEWORK_HINT,
                        help="arc 用；外部框架走 generic 分支（01/02/04/07）")
    parser.add_argument("--dataset-root", type=Path)
    parser.add_argument("--split-manifest", type=Path)
    parser.add_argument("--predictions", type=Path)
    parser.add_argument("--hidden-labels", type=Path)
    parser.add_argument("--whest-bin")
    parser.add_argument("--config-fname", default="src/config.yaml")
    parser.add_argument("--score", action="store_true", help="静态验收通过后调官方评分器")
    parser.add_argument("--apply", action="store_true",
                        help="把分数落进 workspace/score.json（默认只写包内 _score.json）")
    parser.add_argument("--report", type=Path, help="报告输出路径")
    args = parser.parse_args(argv)

    pkg = args.package.resolve()
    rep = Report(pkg, args.topic)
    ws = check_common(pkg, rep)

    if ws is not None:
        if args.topic == "arc":
            check_arc(pkg, ws, rep, args.framework_hint)
        elif args.topic == "mc":
            check_mc(pkg, ws, rep, args.dataset_root or DEFAULT_TOPIC2_ROOT, args.config_fname)
        elif args.topic == "babylm":
            check_babylm(pkg, ws, rep)
        elif args.topic == "psydef":
            check_psydef(pkg, ws, rep,
                         args.split_manifest or CANONICAL_PSYDEF_SPLIT, args.predictions)
        elif args.topic == "tdc":
            # 隐藏标签是我们侧的资产，默认直接用它把键集合比对做满
            hidden = args.hidden_labels or (DEFAULT_TDC_ROOT / "hidden" / "test_labels.csv")
            check_tdc(pkg, ws, rep,
                      args.dataset_root or DEFAULT_TDC_ROOT / "public",
                      hidden, args.predictions)

    extra: dict[str, object] = {}
    if args.score:
        if not rep.ok:
            extra["score"] = {"skipped": "静态验收未通过，未出分"}
        else:
            out = pkg / "_score.json"
            if out.exists():
                out.unlink()
            extra["score"] = run_scorer(args.topic, pkg, ws, args, out)  # type: ignore[arg-type]
            if out.is_file():
                extra["score_payload"] = read_json(out)  # type: ignore[assignment]
                if args.apply:
                    target = ws / "score.json"  # type: ignore[operator]
                    if target.exists():
                        extra["applied"] = f"refused: {target} 已存在"
                    else:
                        target.write_bytes(out.read_bytes())
                        extra["applied"] = str(target)

    payload = rep.dump(extra)
    report_path = args.report or (pkg / "_intake_report.json")
    report_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                           encoding="utf-8")

    for check in rep.checks:
        mark = "PASS" if check["status"] == "PASS" else ("FAIL" if check["fatal"] else "WARN")
        print(f"[{mark}] {check['check']}  {check['evidence']}")
    print(f"\nverdict: {payload['verdict']}   report: {report_path}")
    return 0 if rep.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
