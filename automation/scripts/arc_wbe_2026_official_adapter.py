from __future__ import annotations

import re
from pathlib import Path

ARIS_ADAPTER_KIND = "aris_estimator_predict"
DEEPSCIENTIST_ADAPTER_KIND = "deepscientist_weights_predict"
DRCLAW_ADAPTER_KIND = "drclaw_build_estimator_predict"
GENERIC_NATIVE_ADAPTER_KIND = "generic_native_estimator_predict"


def _normalize_framework_hint(framework_hint: str | None) -> str | None:
    if framework_hint is None:
        return None
    normalized = (
        framework_hint.strip()
        .lower()
        .replace(".", "")
        .replace("_", "")
        .replace("-", "")
        .replace(" ", "")
    )
    aliases = {
        "03": "03",
        "aris": "03",
        "01": "01",
        "airesearcher": "01",
        "02": "02",
        "aiscientistv2": "02",
        "04": "04",
        "autoresearchclaw": "04",
        "05": "05",
        "deepscientist": "05",
        "06": "06",
        "drclaw": "06",
        "07": "07",
        "evoscientist": "07",
    }
    return aliases.get(normalized)


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore")


def _scan_file(path: Path, framework_hint: str | None) -> dict[str, object] | None:
    if not path.exists():
        return None

    resolved_path = path.resolve()
    text = _read_text(path)
    normalized_hint = _normalize_framework_hint(framework_hint)
    if re.search(r"return\s+(?:\w+\.)?(?:zeros|ones|full|empty)\s*\(", text):
        raise ValueError(f"placeholder constant prediction is not admissible: {resolved_path}")
    if re.search(r"\b(?:placeholder|synthetic\s+prediction|fallback\s+prediction)\b", text, re.I):
        raise ValueError(f"placeholder prediction language is not admissible: {resolved_path}")
    if (
        normalized_hint == "03"
        and "class Estimator" in text
        and re.search(
            r"def\s+predict\s*\(\s*self\s*,\s*mlp\b",
            text,
        )
    ):
        return {
            "adapter_kind": ARIS_ADAPTER_KIND,
            "framework_hint": normalized_hint,
            "workspace": resolved_path.parent,
            "source_path": resolved_path,
            "source_symbol": "Estimator",
        }
    if normalized_hint == "05" and re.search(
        r"class\s+(WhiteBoxEstimator|DiagonalMomentEstimator|WeightsOnlyEstimator|Estimator)\b",
        text,
    ):
        source_symbol = next(
            (
                name
                for name in (
                    "WhiteBoxEstimator",
                    "DiagonalMomentEstimator",
                    "WeightsOnlyEstimator",
                    "Estimator",
                )
                if f"class {name}" in text
            ),
            "Estimator",
        )
        predict_input = None
        if re.search(r"def\s+predict\s*\(\s*self\s*,\s*weights\b", text):
            predict_input = "weights"
        elif re.search(r"def\s+predict\s*\(\s*self\s*,\s*mlp\b", text):
            predict_input = "mlp"
        if predict_input is None:
            return None
        return {
            "adapter_kind": DEEPSCIENTIST_ADAPTER_KIND,
            "framework_hint": normalized_hint,
            "workspace": resolved_path.parent,
            "source_path": resolved_path,
            "source_symbol": source_symbol,
            "predict_input": predict_input,
        }
    if normalized_hint == "06" and "def build_estimator" in text:
        predict_input = None
        if re.search(r"def\s+predict\s*\(\s*self\s*,\s*mlp\b", text):
            predict_input = "mlp"
        elif re.search(r"def\s+predict\s*\(\s*self\s*,\s*weights\b", text):
            predict_input = "weights"
        if predict_input is None:
            return None
        return {
            "adapter_kind": DRCLAW_ADAPTER_KIND,
            "framework_hint": normalized_hint,
            "workspace": resolved_path.parent,
            "source_path": resolved_path,
            "source_symbol": "build_estimator",
            "predict_input": predict_input,
        }
    if normalized_hint in {"01", "02", "04", "07"}:
        has_builder = "def build_estimator" in text
        has_estimator_class = re.search(r"class\s+Estimator\b", text) is not None
        predict_input = None
        if re.search(r"def\s+predict\s*\(\s*self\s*,\s*mlp\b", text):
            predict_input = "mlp"
        elif re.search(r"def\s+predict\s*\(\s*self\s*,\s*weights\b", text):
            predict_input = "weights"
        if predict_input is not None and (has_builder or has_estimator_class):
            return {
                "adapter_kind": GENERIC_NATIVE_ADAPTER_KIND,
                "framework_hint": normalized_hint,
                "workspace": resolved_path.parent,
                "source_path": resolved_path,
                "source_symbol": "build_estimator" if has_builder else "Estimator",
                "predict_input": predict_input,
            }
    return None


def scan_workspace_for_official_adapter(
    workspace: Path, framework_hint: str | None = None
) -> dict[str, object]:
    normalized_hint = _normalize_framework_hint(framework_hint)
    if normalized_hint not in {"01", "02", "03", "04", "05", "06", "07"}:
        raise ValueError(f"no supported official adapter candidate found under {workspace}")

    workspace = workspace.resolve()
    source_path = workspace / "estimator.py"
    result = _scan_file(source_path, normalized_hint)
    if result is not None:
        result["workspace"] = workspace
        return result
    raise ValueError(f"no supported official adapter candidate found under {workspace}")


def _render_adapter(scan_result: dict[str, object]) -> str:
    source_path = Path(scan_result["source_path"])
    adapter_kind = str(scan_result["adapter_kind"])
    scipy_compat = """
import math
import types


def _install_scipy_special_compat():
    if "scipy.special" in sys.modules:
        return
    scipy_module = sys.modules.get("scipy")
    if scipy_module is None:
        scipy_module = types.ModuleType("scipy")
        sys.modules["scipy"] = scipy_module
    special_module = types.ModuleType("scipy.special")

    def erf(values):
        try:
            import numpy as _np

            return _np.vectorize(math.erf)(values)
        except Exception:
            if isinstance(values, (list, tuple)):
                return [math.erf(value) for value in values]
            return math.erf(values)

    special_module.erf = erf
    scipy_module.special = special_module
    sys.modules["scipy.special"] = special_module


_install_scipy_special_compat()
"""

    if adapter_kind == ARIS_ADAPTER_KIND:
        return f"""from __future__ import annotations

import importlib.util
import inspect
import sys
from pathlib import Path

from whestbench import BaseEstimator

_SOURCE = Path({str(source_path)!r})
_SPEC = importlib.util.spec_from_file_location("framework_estimator", _SOURCE)
assert _SPEC is not None and _SPEC.loader is not None
_MODULE = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = _MODULE
_SPEC.loader.exec_module(_MODULE)


class OfficialAdapterEstimator(BaseEstimator):
    def __init__(self) -> None:
        self._impl = _MODULE.Estimator()

    def predict(self, mlp, budget=None):
        import numpy as _np
        parameters = inspect.signature(self._impl.predict).parameters
        if "budget" in parameters:
            result = self._impl.predict(mlp, budget=budget)
        else:
            result = self._impl.predict(mlp)
        result = _np.asarray(result, dtype=_np.float64)
        expected_shape = (int(mlp.depth), int(mlp.width))
        if result.shape != expected_shape:
            raise ValueError("framework estimator returned shape %s; expected %s" % (result.shape, expected_shape))
        if not _np.isfinite(result).all():
            raise ValueError("framework estimator returned non-finite predictions")
        if not _np.any(result):
            raise ValueError("framework estimator returned an all-zero placeholder prediction")
        if result.shape[1] > 1 and _np.all(result == result[:, :1]):
            raise ValueError("framework estimator returned a width-broadcast prediction")
        if result.shape[0] > 1 and _np.all(result == result[:1, :]):
            raise ValueError("framework estimator returned a depth-broadcast prediction")
        return result
"""

    if adapter_kind == DEEPSCIENTIST_ADAPTER_KIND:
        source_symbol = str(scan_result["source_symbol"])
        predict_input = str(scan_result.get("predict_input", "weights"))
        predict_body = """        weights = mlp.weights
        module_np = getattr(_MODULE, "np", None)
        if module_np is not None and hasattr(module_np, "asarray"):
            weights = module_np.asarray(weights)
        result = self._impl.predict(weights)"""
        if predict_input == "mlp":
            predict_body = """        parameters = inspect.signature(self._impl.predict).parameters
        if "budget" in parameters:
            result = self._impl.predict(mlp, budget=budget)
        else:
            result = self._impl.predict(mlp)"""
        predict_body += """
        import numpy as _np
        result = _np.asarray(result, dtype=_np.float64)
        expected_shape = (int(mlp.depth), int(mlp.width))
        if result.shape != expected_shape:
            raise ValueError("framework estimator returned shape %s; expected %s" % (result.shape, expected_shape))
        if not _np.isfinite(result).all():
            raise ValueError("framework estimator returned non-finite predictions")
        if not _np.any(result):
            raise ValueError("framework estimator returned an all-zero placeholder prediction")
        if result.shape[1] > 1 and _np.all(result == result[:, :1]):
            raise ValueError("framework estimator returned a width-broadcast prediction")
        if result.shape[0] > 1 and _np.all(result == result[:1, :]):
            raise ValueError("framework estimator returned a depth-broadcast prediction")
        return result"""
        return f"""from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

from whestbench import BaseEstimator
import inspect
{scipy_compat}

_SOURCE = Path({str(source_path)!r})
_SPEC = importlib.util.spec_from_file_location("framework_estimator", _SOURCE)
assert _SPEC is not None and _SPEC.loader is not None
_MODULE = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = _MODULE
_SPEC.loader.exec_module(_MODULE)


class OfficialAdapterEstimator(BaseEstimator):
    def __init__(self) -> None:
        self._impl = getattr(_MODULE, {source_symbol!r})()

    def predict(self, mlp, budget=None):
{predict_body}
"""

    if adapter_kind == DRCLAW_ADAPTER_KIND:
        predict_input = str(scan_result.get("predict_input", "mlp"))
        body = "result = self._impl.predict(mlp, budget=budget)"
        if predict_input == "weights":
            body = "result = self._impl.predict(mlp.weights, budget=budget)"
        return f"""from __future__ import annotations

import importlib.util
import inspect
import sys
from pathlib import Path

from whestbench import BaseEstimator

_SOURCE = Path({str(source_path)!r})
_SPEC = importlib.util.spec_from_file_location("framework_estimator", _SOURCE)
assert _SPEC is not None and _SPEC.loader is not None
_MODULE = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = _MODULE
_SPEC.loader.exec_module(_MODULE)


class OfficialAdapterEstimator(BaseEstimator):
    def __init__(self) -> None:
        self._impl = _MODULE.build_estimator()

    def predict(self, mlp, budget=None):
        import numpy as _np
        parameters = inspect.signature(self._impl.predict).parameters
        if "budget" in parameters:
            {body}
        else:
            result = self._impl.predict(mlp.weights if {predict_input!r} == "weights" else mlp)
        result = _np.asarray(result, dtype=_np.float64)
        expected_shape = (int(mlp.depth), int(mlp.width))
        if result.shape != expected_shape:
            raise ValueError("framework estimator returned shape %s; expected %s" % (result.shape, expected_shape))
        if not _np.isfinite(result).all():
            raise ValueError("framework estimator returned non-finite predictions")
        if not _np.any(result):
            raise ValueError("framework estimator returned an all-zero placeholder prediction")
        if result.shape[1] > 1 and _np.all(result == result[:, :1]):
            raise ValueError("framework estimator returned a width-broadcast prediction")
        if result.shape[0] > 1 and _np.all(result == result[:1, :]):
            raise ValueError("framework estimator returned a depth-broadcast prediction")
        return result
"""

    if adapter_kind == GENERIC_NATIVE_ADAPTER_KIND:
        source_symbol = str(scan_result["source_symbol"])
        predict_input = str(scan_result.get("predict_input", "mlp"))
        constructor = (
            "_MODULE.build_estimator()"
            if source_symbol == "build_estimator"
            else "_MODULE.Estimator()"
        )
        input_expr = "mlp.weights" if predict_input == "weights" else "mlp"
        return f"""from __future__ import annotations

import importlib.util
import inspect
import sys
from pathlib import Path

from whestbench import BaseEstimator

_SOURCE = Path({str(source_path)!r})
_SPEC = importlib.util.spec_from_file_location("framework_estimator", _SOURCE)
assert _SPEC is not None and _SPEC.loader is not None
_MODULE = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = _MODULE
_SPEC.loader.exec_module(_MODULE)


class OfficialAdapterEstimator(BaseEstimator):
    def __init__(self) -> None:
        self._impl = {constructor}

    def predict(self, mlp, budget=None):
        import numpy as _np
        parameters = inspect.signature(self._impl.predict).parameters
        if "budget" in parameters:
            result = self._impl.predict({input_expr}, budget=budget)
        else:
            result = self._impl.predict({input_expr})
        result = _np.asarray(result, dtype=_np.float64)
        expected_shape = (int(mlp.depth), int(mlp.width))
        if result.shape != expected_shape:
            raise ValueError("framework estimator returned shape %s; expected %s" % (result.shape, expected_shape))
        if not _np.isfinite(result).all():
            raise ValueError("framework estimator returned non-finite predictions")
        if not _np.any(result):
            raise ValueError("framework estimator returned an all-zero placeholder prediction")
        if result.shape[1] > 1 and _np.all(result == result[:, :1]):
            raise ValueError("framework estimator returned a width-broadcast prediction")
        if result.shape[0] > 1 and _np.all(result == result[:1, :]):
            raise ValueError("framework estimator returned a depth-broadcast prediction")
        return result
"""

    raise ValueError(f"unsupported adapter kind: {adapter_kind}")


def materialize_official_adapter(scan_result: dict[str, object], output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / "estimator.py"
    path.write_text(_render_adapter(scan_result), encoding="utf-8")
    return path
