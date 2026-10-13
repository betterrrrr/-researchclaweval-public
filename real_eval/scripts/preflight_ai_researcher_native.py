#!/usr/bin/env python3
"""preflight_ai_researcher_native.py

Source-parity and import-precedence gate that runs before native AI-Researcher
launch.  Classifies every resolved import, validates framework-boundary
compliance, unions static/runtime/optional import coverage, and blocks dispatch
on any violation.

Exit codes:
  0  — gate passed, manifest written
  1  — gate blocked (violations found)
  2  — internal error (bad args, I/O failure, etc.)

Usage:
  python3 preflight_ai_researcher_native.py \
      --source-root $(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)/AI-Researcher \
      --output /tmp/preflight_manifest.json

  python3 preflight_ai_researcher_native.py \
      --source-root $(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)/AI-Researcher \
      --output /tmp/preflight_manifest.json \
      --runtime-traces /tmp/trace_*.json \
      --lock-file /path/to/requirements.txt \
      --sbom /path/to/sbom.json \
      --framework-root workspace/AI-Researcher \
      --framework-root runtime-adapter
"""

from __future__ import annotations

import argparse
import hashlib
import importlib
import importlib.util
import json
import re
import sys
import tokenize
from pathlib import Path
from types import ModuleType
from typing import Any, Dict, List, Optional, Set, Tuple

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# The one allowed nonliteral dynamic import pattern.
# Actual category is one of the subdirectories under benchmark/process/dataset_candidate/.
ALLOWED_NONLITERAL_PATTERN = re.compile(
    r"^benchmark\.process\.dataset_candidate\.\w+\.metaprompt$"
)

# Import categories (ordered by precedence in classification).
CAT_FRAMEWORK_OWNED = "framework_owned"
CAT_STDLIB = "stdlib"
CAT_THIRD_PARTY = "third_party"
CAT_BUILTIN = "builtin"
CAT_EXTENSION = "extension"
CAT_FROZEN = "frozen"
CAT_NAMESPACE_PACKAGE = "namespace_package"
CAT_FAILED = "failed"  # module that could not be classified

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _resolved_path(mod: ModuleType) -> Optional[Path]:
    """Return the physical file path of *mod*, or None."""
    try:
        f = mod.__file__
    except AttributeError:
        return None
    if f is not None:
        p = Path(f)
        return p.resolve() if p.exists() else p
    return None


def _import_name_to_path(name: str, source_root: Path) -> Optional[Path]:
    """Guess the file path a top-level import would resolve to under *source_root*.

    This is only used for static-analysis-time resolution when the module
    hasn't been imported yet.
    """
    parts = name.split(".")
    # Try package/__init__.py first, then package.py
    for suffix in ("/__init__.py", ".py", ".so", ".pyd"):
        candidate = source_root / "/".join(parts) / "__init__.py" if suffix == "/__init__.py" else None
        if candidate is None:
            candidate = source_root / "/".join(parts[:-1]) / (parts[-1] + suffix)
        if candidate and candidate.exists():
            return candidate.resolve()
    # Handle namespace packages (directory with no __init__.py)
    dir_candidate = source_root / "/".join(parts)
    if dir_candidate.is_dir() and not (dir_candidate / "__init__.py").is_file():
        return dir_candidate.resolve()
    return None


# ---------------------------------------------------------------------------
# Import graph builder (static analysis)
# ---------------------------------------------------------------------------


class StaticImportGraph:
    """Walk a source tree and extract all import statements."""

    def __init__(self, source_root: Path) -> None:
        self.source_root = source_root.resolve()
        self.py_files: List[Path] = []
        self._collect_files()

    def _collect_files(self) -> None:
        if not self.source_root.is_dir():
            return
        for path in self.source_root.rglob("*.py"):
            # Skip hidden dirs, cache, venv, etc.
            rel = path.relative_to(self.source_root)
            if any(
                part.startswith(".") or part == "__pycache__"
                for part in rel.parts
            ):
                continue
            # Skip node_modules, site-packages, etc.
            if "site-packages" in rel.parts:
                continue
            self.py_files.append(path)

    # ── parsing helpers ──────────────────────────────────────────────

    @staticmethod
    def _parse_imports(filepath: Path) -> Dict[str, Set[str]]:
        """Return {literal: {module_names}} and {nonliteral: patterns}.

        Returns dict with keys 'literal_imports', 'nonliteral_imports'.
        """
        result: Dict[str, Set[str]] = {
            "literal_imports": set(),
            "nonliteral_imports": set(),
        }
        try:
            with filepath.open("rb") as fh:
                tokens = list(tokenize.tokenize(fh.readline))
        except Exception:
            return result

        i = 0
        while i < len(tokens):
            tok = tokens[i]
            # import X, import X.Y, import X as Z
            if tok.type == tokenize.NAME and tok.string == "import":
                i += 1
                while i < len(tokens) and tokens[i].type != tokenize.NEWLINE:
                    if tokens[i].type == tokenize.NAME:
                        name = tokens[i].string
                        # Read dotted name
                        j = i + 1
                        while j < len(tokens) and tokens[j].type == tokenize.OP and tokens[j].string == ".":
                            j += 1
                            if j < len(tokens) and tokens[j].type == tokenize.NAME:
                                name += "." + tokens[j].string
                                j += 1
                            else:
                                break
                        # Check if this is a nonliteral (dynamic) import
                        # We capture it as a literal candidate; nonliteral
                        # detection is done via pattern matching below.
                        if name not in ("as",):
                            result["literal_imports"].add(name)
                        i = j
                        continue
                    elif tokens[i].type == tokenize.OP and tokens[i].string == ",":
                        i += 1
                        continue
                    elif tokens[i].type == tokenize.NAME and tokens[i].string == "as":
                        # skip the 'as' alias
                        i += 2
                        continue
                    i += 1
                continue

            # from X import Y, from X import Y as Z
            if (
                tok.type == tokenize.NAME
                and tok.string == "from"
                and i + 2 < len(tokens)
            ):
                # Collect the module part
                j = i + 1
                parts = []
                while j < len(tokens) and tokens[j].type != tokenize.NAME or tokens[j].string != "import":
                    if tokens[j].type == tokenize.NAME:
                        parts.append(tokens[j].string)
                    elif tokens[j].type == tokenize.OP and tokens[j].string == ".":
                        if parts:
                            parts[-1] += "."
                    elif tokens[j].type == tokenize.OP and tokens[j].string == ",":
                        pass
                    elif tokens[j].type == tokenize.NEWLINE:
                        break
                    j += 1
                if j < len(tokens) and tokens[j].type == tokenize.NAME and tokens[j].string == "import":
                    module_name = "".join(parts).rstrip(".")
                    if module_name:
                        result["literal_imports"].add(module_name)
                    # Collect imported names
                    j += 1
                    names = set()
                    while j < len(tokens) and tokens[j].type != tokenize.NEWLINE:
                        if tokens[j].type == tokenize.NAME:
                            names.add(tokens[j].string)
                            j += 1
                        elif tokens[j].type == tokenize.OP and tokens[j].string == ",":
                            j += 1
                        elif tokens[j].type == tokenize.NAME and tokens[j].string == "as":
                            j += 2
                        else:
                            j += 1
                i = j
                continue

            i += 1

        # Nonliteral detection: look for __import__(), importlib.import_module(),
        # or string-based imports in the source text.
        try:
            text = filepath.read_text(encoding="utf-8", errors="replace")
        except Exception:
            text = ""

        # __import__("...") calls
        for m in re.finditer(r'__import__\s*\(\s*["\']([^"\']+)["\']', text):
            result["nonliteral_imports"].add(m.group(1))

        # importlib.import_module("...")
        for m in re.finditer(
            r'import_module\s*\(\s*["\']([^"\']+)["\']', text
        ):
            result["nonliteral_imports"].add(m.group(1))

        # Dynamic string-based imports like module = f"benchmark.process.dataset_candidate.{category}.metaprompt"
        # These are nonliteral patterns — we capture the pattern prefix
        for m in re.finditer(
            r'["\'](benchmark\.process\.dataset_candidate\.\w+\.metaprompt)["\']',
            text,
        ):
            result["nonliteral_imports"].add(m.group(1))

        return result

    def build(self) -> Dict[str, Any]:
        """Walk all .py files and return the static import graph.

        Returns:
          {
            "files": {rel_path: {"sha256": ..., "imports": [...], "nonliteral_imports": [...]}},
            "all_literal_imports": [sorted unique],
            "all_nonliteral_imports": [sorted unique],
          }
        """
        all_literal: Set[str] = set()
        all_nonliteral: Set[str] = set()
        files: Dict[str, Any] = {}

        for fp in sorted(self.py_files):
            rel = str(fp.relative_to(self.source_root))
            parsed = self._parse_imports(fp)
            literals = parsed["literal_imports"]
            nonliterals = parsed["nonliteral_imports"]
            all_literal.update(literals)
            all_nonliteral.update(nonliterals)
            files[rel] = {
                "sha256": sha256_file(fp),
                "imports": sorted(literals),
                "nonliteral_imports": sorted(nonliterals),
            }

        return {
            "files": files,
            "all_literal_imports": sorted(all_literal),
            "all_nonliteral_imports": sorted(all_nonliteral),
        }


# ---------------------------------------------------------------------------
# Classifier
# ---------------------------------------------------------------------------


class ImportClassifier:
    """Classify import module names into the 7 categories.

    Uses a two-phase approach:
      1. Try to actually import the module (safe builtins/stdlib).
      2. If that fails, resolve by path evidence under the source root and
         site-packages.
    """

    def __init__(
        self,
        source_root: Path,
        framework_roots: List[Path],
        lock_deps: Optional[Set[str]] = None,
        sbom_deps: Optional[Set[str]] = None,
        site_packages_dirs: Optional[List[Path]] = None,
    ) -> None:
        self.source_root = source_root.resolve()
        self.framework_roots = [
            (r.resolve() if r.exists() else self.source_root / r)
            for r in framework_roots
        ]
        self.lock_deps = lock_deps or set()
        self.sbom_deps = sbom_deps or set()
        self.site_packages_dirs = site_packages_dirs or self._find_site_packages()

        # Cache
        self._stdlib_modules: Optional[Set[str]] = None
        self._classifications: Dict[str, str] = {}
        self._resolved_paths: Dict[str, Optional[Path]] = {}
        self._module_hashes: Dict[str, str] = {}
        self._owning_distributions: Dict[str, str] = {}
        self._import_errors: Dict[str, str] = {}

    # ── site-packages discovery ──────────────────────────────────────

    @staticmethod
    def _find_site_packages() -> List[Path]:
        """Return a list of site-packages directories."""
        dirs: List[Path] = []
        for p in sys.path:
            path = Path(p)
            if "site-packages" in path.parts and path.is_dir():
                dirs.append(path.resolve())
        # Also check common locations
        for prefix in (Path(sys.prefix), Path(sys.base_prefix)):
            for sp in (prefix / "lib", prefix / "lib64"):
                if sp.is_dir():
                    for child in sp.iterdir():
                        candidate = child / "site-packages"
                        if candidate.is_dir():
                            dirs.append(candidate.resolve())
        # Deduplicate
        seen = set()
        unique: List[Path] = []
        for d in dirs:
            if str(d) not in seen:
                seen.add(str(d))
                unique.append(d)
        return unique

    # ── stdlib discovery ─────────────────────────────────────────────

    def _get_stdlib_modules(self) -> Set[str]:
        if self._stdlib_modules is not None:
            return self._stdlib_modules
        stdlib: Set[str] = set()
        if hasattr(sys, "stdlib_module_names"):
            stdlib.update(sys.stdlib_module_names)
        # Also include builtin module names
        stdlib.update(sys.builtin_module_names)
        self._stdlib_modules = stdlib
        return stdlib

    # ── classification ───────────────────────────────────────────────

    def _try_import(self, name: str) -> Tuple[Optional[ModuleType], Optional[str]]:
        """Try to import *name* safely. Returns (module, error_string)."""
        try:
            mod = importlib.import_module(name)
            return mod, None
        except ImportError as e:
            return None, str(e)
        except Exception as e:
            return None, str(e)

    def _resolve_under_framework(self, name: str) -> Optional[Path]:
        """Check if *name* resolves under any framework root."""
        for root in self.framework_roots:
            candidate = _import_name_to_path(name, root)
            if candidate is not None:
                return candidate
        # Also check if it's a module already imported that resolves under framework root
        try:
            mod = importlib.import_module(name)
            p = _resolved_path(mod)
            if p is not None:
                for root in self.framework_roots:
                    try:
                        p.relative_to(root)
                        return p
                    except ValueError:
                        continue
        except Exception:
            pass
        return None

    def _resolve_under_site_packages(self, name: str) -> Optional[Path]:
        """Check if *name* resolves under any site-packages directory."""
        # Try import first
        try:
            mod = importlib.import_module(name)
            p = _resolved_path(mod)
            if p is not None:
                for sp in self.site_packages_dirs:
                    try:
                        p.relative_to(sp)
                        return p
                    except ValueError:
                        continue
        except Exception:
            pass
        # Fall back to path resolution
        for sp in self.site_packages_dirs:
            candidate = _import_name_to_path(name, sp)
            if candidate is not None:
                return candidate
        return None

    def _get_distribution(self, name: str) -> str:
        """Get the distribution name (pip package) owning *name*."""
        if name in self._owning_distributions:
            return self._owning_distributions[name]
        try:
            mod = importlib.import_module(name)
            # Try to find the metadata
            p = _resolved_path(mod)
            if p is not None:
                # Walk up to find METADATA or PKG-INFO in dist-info or egg-info
                for parent in [p] + list(p.parents):
                    for infodir in ("dist-info", "egg-info"):
                        for info_file in parent.glob(f"*.{infodir}/METADATA"):
                            text = info_file.read_text(encoding="utf-8", errors="replace")
                            for line in text.splitlines():
                                if line.startswith("Name: "):
                                    dist = line[6:].strip()
                                    self._owning_distributions[name] = dist
                                    return dist
                        for info_file in parent.glob(f"*.{infodir}/PKG-INFO"):
                            text = info_file.read_text(encoding="utf-8", errors="replace")
                            for line in text.splitlines():
                                if line.startswith("Name: "):
                                    dist = line[6:].strip()
                                    self._owning_distributions[name] = dist
                                    return dist
        except Exception:
            pass
        return ""

    def classify(self, name: str) -> str:
        """Classify a single module name into one of the 7 categories.

        Returns the category string (or CAT_FAILED).
        """
        if name in self._classifications:
            return self._classifications[name]

        # Extract the top-level package
        top = name.split(".")[0]

        # 1. Builtin: module.__file__ is None (after successful import)
        # 2. Frozen: in sys.modules with no __file__ (subsumed by builtin check for most)
        # We check these first via actual import.
        mod, err = self._try_import(name)
        if mod is not None:
            p = _resolved_path(mod)
            if p is None:
                # No file path — either builtin or frozen
                if name in sys.builtin_module_names or top in sys.builtin_module_names:
                    self._classifications[name] = CAT_BUILTIN
                    self._module_hashes[name] = "builtin"
                    return CAT_BUILTIN
                # Check if it's in sys.modules with no __file__
                if name in sys.modules and getattr(sys.modules[name], "__file__", None) is None:
                    self._classifications[name] = CAT_FROZEN
                    self._module_hashes[name] = "frozen"
                    return CAT_FROZEN
                # Could be a namespace package
                if hasattr(mod, "__path__") and getattr(mod, "__file__", None) is None:
                    # Check for __init__.py in the path
                    has_init = False
                    for mp in mod.__path__:
                        if (Path(mp) / "__init__.py").is_file():
                            has_init = True
                            break
                    if not has_init:
                        self._classifications[name] = CAT_NAMESPACE_PACKAGE
                        self._module_hashes[name] = "namespace"
                        return CAT_NAMESPACE_PACKAGE
                self._classifications[name] = CAT_BUILTIN
                self._module_hashes[name] = "builtin"
                return CAT_BUILTIN

            # 3. Framework-owned: must resolve below one of the framework roots
            for root in self.framework_roots:
                try:
                    p.relative_to(root)
                    self._classifications[name] = CAT_FRAMEWORK_OWNED
                    self._module_hashes[name] = sha256_file(p) if p.is_file() else "dir"
                    self._resolved_paths[name] = p
                    return CAT_FRAMEWORK_OWNED
                except ValueError:
                    continue

            # 4. Stdlib: named in sys.stdlib_module_names
            stdlib = self._get_stdlib_modules()
            if name in stdlib or top in stdlib:
                self._classifications[name] = CAT_STDLIB
                self._module_hashes[name] = sha256_file(p) if p.is_file() else "stdlib"
                self._resolved_paths[name] = p
                return CAT_STDLIB

            # Check if it's under site-packages
            for sp in self.site_packages_dirs:
                try:
                    p.relative_to(sp)
                    # 5. Third-party: resolves under site-packages and matches lock/SBOM
                    dist = self._get_distribution(name)
                    if self.lock_deps and not dist:
                        # No distribution found but under site-packages — still third-party
                        # but may fail later if absent from lock/SBOM
                        self._classifications[name] = CAT_THIRD_PARTY
                        self._module_hashes[name] = sha256_file(p) if p.is_file() else "sp"
                        self._resolved_paths[name] = p
                        return CAT_THIRD_PARTY
                    # 6. Extension: .so/.pyd suffix
                    if p.suffix in (".so", ".pyd"):
                        self._classifications[name] = CAT_EXTENSION
                        self._module_hashes[name] = sha256_file(p) if p.is_file() else "ext"
                        self._resolved_paths[name] = p
                        return CAT_EXTENSION
                    self._classifications[name] = CAT_THIRD_PARTY
                    self._module_hashes[name] = sha256_file(p) if p.is_file() else "sp"
                    self._resolved_paths[name] = p
                    return CAT_THIRD_PARTY
                except ValueError:
                    continue

            # Check if it's a .so/.pyd extension somewhere else
            if p.suffix in (".so", ".pyd"):
                self._classifications[name] = CAT_EXTENSION
                self._module_hashes[name] = sha256_file(p) if p.is_file() else "ext"
                self._resolved_paths[name] = p
                return CAT_EXTENSION

            # Fallback: check if it's stdlib by name
            if name in stdlib or top in stdlib:
                self._classifications[name] = CAT_STDLIB
                self._module_hashes[name] = sha256_file(p) if p.is_file() else "stdlib"
                self._resolved_paths[name] = p
                return CAT_STDLIB

            # If we got here and path is under source root, it's framework-owned
            try:
                p.relative_to(self.source_root)
                self._classifications[name] = CAT_FRAMEWORK_OWNED
                self._module_hashes[name] = sha256_file(p) if p.is_file() else "dir"
                self._resolved_paths[name] = p
                return CAT_FRAMEWORK_OWNED
            except ValueError:
                pass

            # Unknown — resolution succeeded but classification failed
            self._classifications[name] = CAT_FAILED
            self._import_errors[name] = f"resolved to {p} but no matching category"
            return CAT_FAILED

        # Import failed — try path-based resolution
        # Check framework roots first
        for root in self.framework_roots:
            p = _import_name_to_path(name, root)
            if p is not None:
                self._classifications[name] = CAT_FRAMEWORK_OWNED
                self._module_hashes[name] = sha256_file(p) if p.is_file() else "dir"
                self._resolved_paths[name] = p
                return CAT_FRAMEWORK_OWNED

        # Check site-packages
        sp = self._resolve_under_site_packages(name)
        if sp is not None:
            if sp.suffix in (".so", ".pyd"):
                self._classifications[name] = CAT_EXTENSION
                self._module_hashes[name] = sha256_file(sp) if sp.is_file() else "ext"
                self._resolved_paths[name] = sp
                return CAT_EXTENSION
            self._classifications[name] = CAT_THIRD_PARTY
            self._module_hashes[name] = sha256_file(sp) if sp.is_file() else "sp"
            self._resolved_paths[name] = sp
            return CAT_THIRD_PARTY

        # Check if it's a namespace package (directory with no __init__.py)
        for root in self.framework_roots:
            dir_candidate = root / name.replace(".", "/")
            if dir_candidate.is_dir() and not (dir_candidate / "__init__.py").is_file():
                self._classifications[name] = CAT_NAMESPACE_PACKAGE
                self._module_hashes[name] = "namespace"
                self._resolved_paths[name] = dir_candidate.resolve()
                return CAT_NAMESPACE_PACKAGE

        # Check under source root
        p = _import_name_to_path(name, self.source_root)
        if p is not None:
            self._classifications[name] = CAT_FRAMEWORK_OWNED
            self._module_hashes[name] = sha256_file(p) if p.is_file() else "dir"
            self._resolved_paths[name] = p
            return CAT_FRAMEWORK_OWNED

        # Check if it's a known stdlib despite import failure
        stdlib = self._get_stdlib_modules()
        if name in stdlib or top in stdlib:
            self._classifications[name] = CAT_STDLIB
            self._module_hashes[name] = "stdlib"
            return CAT_STDLIB

        # Absolute failure
        self._classifications[name] = CAT_FAILED
        self._import_errors[name] = err or "unresolved import"
        return CAT_FAILED

    def classify_all(
        self, names: Set[str]
    ) -> Dict[str, Dict[str, Any]]:
        """Classify a set of module names and return detailed results.

        Returns {name: {class, path, hash, owning_distribution, error}}.
        """
        result: Dict[str, Dict[str, Any]] = {}
        for name in sorted(names):
            cat = self.classify(name)
            entry: Dict[str, Any] = {
                "class": cat,
                "path": str(self._resolved_paths.get(name) or ""),
                "hash": self._module_hashes.get(name, ""),
                "owning_distribution": self._get_distribution(name),
                "error": self._import_errors.get(name, ""),
            }
            result[name] = entry
        return result


# ---------------------------------------------------------------------------
# Runtime trace loader
# ---------------------------------------------------------------------------


def load_runtime_traces(trace_globs: List[str]) -> Set[str]:
    """Load runtime-observed imports from trace files.

    Supports JSON trace files and simple text-format import lists.
    Returns a set of fully-qualified module names.
    """
    runtime_imports: Set[str] = set()
    for pattern in trace_globs:
        import glob as _glob_mod
        for path_str in _glob_mod.glob(pattern, recursive=True):
            path = Path(path_str)
            if not path.is_file():
                continue
            try:
                data = json.loads(path.read_text(encoding="utf-8", errors="replace"))
            except (json.JSONDecodeError, OSError):
                # Try as text with one import per line
                try:
                    text = path.read_text(encoding="utf-8", errors="replace")
                    for line in text.splitlines():
                        line = line.strip()
                        if line and not line.startswith("#"):
                            runtime_imports.add(line)
                except OSError:
                    continue
                continue

            # Handle various JSON shapes
            if isinstance(data, dict):
                # experiment_trace.json format
                for key in ("imports", "modules", "dependencies", "imported_modules"):
                    vals = data.get(key, [])
                    if isinstance(vals, list):
                        for v in vals:
                            if isinstance(v, str):
                                runtime_imports.add(v)
                # Nested events
                for ev in data.get("events", []):
                    if isinstance(ev, dict):
                        for key in ("import", "module", "dependency"):
                            val = ev.get(key)
                            if isinstance(val, str):
                                runtime_imports.add(val)
            elif isinstance(data, list):
                for item in data:
                    if isinstance(item, str):
                        runtime_imports.add(item)
                    elif isinstance(item, dict):
                        for key in ("import", "module", "name"):
                            val = item.get(key)
                            if isinstance(val, str):
                                runtime_imports.add(val)

    return runtime_imports


# ---------------------------------------------------------------------------
# Lock / SBOM loader
# ---------------------------------------------------------------------------


def load_lock_deps(lock_file: Optional[str]) -> Set[str]:
    """Load dependency names from a requirements.txt or similar lock file.

    Returns a set of package names (lowercase).
    """
    if not lock_file:
        return set()
    path = Path(lock_file)
    if not path.is_file():
        return set()
    deps: Set[str] = set()
    text = path.read_text(encoding="utf-8", errors="replace")
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or line.startswith("--"):
            continue
        # Strip version specifiers
        for sep in ("==", ">=", "<=", ">", "<", "!=", "~=", "@", ";"):
            idx = line.find(sep)
            if idx != -1:
                line = line[:idx].strip()
                break
        if line:
            deps.add(line.lower().replace("_", "-"))
    return deps


def load_sbom_deps(sbom_file: Optional[str]) -> Set[str]:
    """Load dependency names from a CycloneDX or SPDX SBOM.

    Returns a set of package names (lowercase).
    """
    if not sbom_file:
        return set()
    path = Path(sbom_file)
    if not path.is_file():
        return set()
    deps: Set[str] = set()
    try:
        data = json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except (json.JSONDecodeError, OSError):
        return set()

    # CycloneDX
    for key in ("components", "packages"):
        for comp in data.get(key, []):
            name = comp.get("name", "") or comp.get("Name", "")
            if name:
                deps.add(name.lower().replace("_", "-"))
            # Also check purl
            purl = comp.get("purl", "") or comp.get("Purl", "")
            if purl and "/" in purl:
                pkg = purl.rsplit("/", 1)[-1]
                deps.add(pkg.lower().replace("_", "-"))

    # SPDX
    for pkg in data.get("packages", []):
        name = pkg.get("name", "") or pkg.get("name", "")
        if name:
            deps.add(name.lower().replace("_", "-"))
        # Check external refs
        for ref in pkg.get("externalRefs", []):
            locator = ref.get("locator", "")
            if locator and "/" in locator:
                pkg = locator.rsplit("/", 1)[-1]
                deps.add(pkg.lower().replace("_", "-"))

    return deps


# ---------------------------------------------------------------------------
# Main validation / gate
# ---------------------------------------------------------------------------


def validate_and_manifest(
    source_root: Path,
    output_path: Path,
    framework_roots: List[Path],
    lock_file: Optional[str] = None,
    sbom_file: Optional[str] = None,
    runtime_trace_globs: Optional[List[str]] = None,
    deny_unknown: bool = True,
) -> Dict[str, Any]:
    """Run the full preflight gate.

    Returns a manifest dict with:
      - manifest_version
      - source_root
      - framework_roots
      - static_imports: classified imports from source analysis
      - runtime_imports: imports observed at runtime
      - optional_branch_imports: imports from optional/conditional branches
      - union_imports: static ∪ runtime ∪ optional
      - violations: list of blocking issues
      - gate_passed: bool
    """
    violations: List[str] = []

    # ── 1. Static import graph ───────────────────────────────────────
    graph = StaticImportGraph(source_root)
    static_data = graph.build()

    # ── 2. Load lock / SBOM ──────────────────────────────────────────
    lock_deps = load_lock_deps(lock_file)
    sbom_deps = load_sbom_deps(sbom_file)
    known_deps: Set[str] = lock_deps | sbom_deps

    if lock_file and not lock_deps:
        violations.append(f"lock file '{lock_file}' is empty or unreadable")
    if sbom_file and not sbom_deps:
        violations.append(f"SBOM file '{sbom_file}' is empty or unreadable")

    # ── 3. Classify all literal imports ──────────────────────────────
    classifier = ImportClassifier(
        source_root=source_root,
        framework_roots=framework_roots,
        lock_deps=lock_deps,
        sbom_deps=sbom_deps,
    )

    all_literal = set(static_data["all_literal_imports"])
    classified_literal = classifier.classify_all(all_literal)

    # ── 4. Handle nonliteral imports ─────────────────────────────────
    all_nonliteral = set(static_data["all_nonliteral_imports"])
    allowed_nonliteral: Set[str] = set()
    disallowed_nonliteral: Set[str] = set()

    for nl in all_nonliteral:
        if ALLOWED_NONLITERAL_PATTERN.match(nl):
            allowed_nonliteral.add(nl)
        else:
            disallowed_nonliteral.add(nl)

    if disallowed_nonliteral:
        violations.append(
            f"nonliteral imports not matching allowed pattern "
            f"({ALLOWED_NONLITERAL_PATTERN.pattern}): {sorted(disallowed_nonliteral)}"
        )

    # ── 5. Compute recursive imports (transitive closure) ────────────
    # We do a BFS through the classified imports, resolving them and
    # finding their own imports.
    recursive_imports: Set[str] = set(all_literal)
    queue: List[str] = list(all_literal)
    visited: Set[str] = set()

    while queue:
        name = queue.pop(0)
        if name in visited:
            continue
        visited.add(name)
        # Try to resolve the module and find its imports
        try:
            mod = importlib.import_module(name)
            # Get the source file of the module
            p = _resolved_path(mod)
            if p and p.is_file() and p.suffix == ".py":
                # Check if the module is under the source root or framework roots
                is_scope = False
                try:
                    p.relative_to(source_root)
                    is_scope = True
                except ValueError:
                    for root in framework_roots:
                        try:
                            p.relative_to(root)
                            is_scope = True
                            break
                        except ValueError:
                            continue
                if is_scope:
                    parsed = StaticImportGraph._parse_imports(p)
                    for sub_import in parsed["literal_imports"]:
                        if sub_import not in visited:
                            recursive_imports.add(sub_import)
                            queue.append(sub_import)
                    for sub_nl in parsed["nonliteral_imports"]:
                        if ALLOWED_NONLITERAL_PATTERN.match(sub_nl):
                            allowed_nonliteral.add(sub_nl)
                        else:
                            # Recursive nonliteral is also flagged
                            if sub_nl not in all_nonliteral:
                                disallowed_nonliteral.add(sub_nl)
        except Exception:
            pass

    # Re-classify recursive imports
    classified_recursive = classifier.classify_all(recursive_imports - all_literal)
    # Merge into classified_literal
    for name, entry in classified_recursive.items():
        if name not in classified_literal:
            classified_literal[name] = entry

    # ── 6. Load runtime traces ───────────────────────────────────────
    runtime_imports: Set[str] = set()
    if runtime_trace_globs:
        runtime_imports = load_runtime_traces(runtime_trace_globs)

    # ── 7. Optional branch imports ───────────────────────────────────
    # These are imports found inside conditional/try/except blocks.
    # We detect them by scanning for imports inside if/else/try/except
    # blocks in the source.
    optional_imports: Set[str] = set()
    for fp in graph.py_files:
        text = fp.read_text(encoding="utf-8", errors="replace")
        # Simple heuristic: look for imports inside indented blocks
        # that follow if/elif/else/try/except/with lines
        lines = text.splitlines()
        in_conditional = False
        for line in lines:
            stripped = line.strip()
            if re.match(r"^(if |elif |else:|try:|except|with )", stripped):
                in_conditional = True
                continue
            if in_conditional and stripped.startswith(("import ", "from ")):
                # Extract module name
                if stripped.startswith("import "):
                    mod = stripped[7:].split()[0].split(",")[0].strip()
                    optional_imports.add(mod)
                elif stripped.startswith("from "):
                    parts = stripped[5:].split()
                    if parts and parts[0] != "import":
                        mod = parts[0].strip()
                        optional_imports.add(mod)
            if stripped and not stripped.startswith((" ", "\t", "import ", "from ")):
                in_conditional = False

    # Classify optional imports
    classified_optional = classifier.classify_all(optional_imports)

    # ── 8. Union ─────────────────────────────────────────────────────
    union_imports = all_literal | allowed_nonliteral | runtime_imports | optional_imports
    classified_union = classifier.classify_all(union_imports)

    # ── 9. Validation checks ─────────────────────────────────────────

    # 9a. Framework modules outside the two framework roots
    for name, entry in classified_union.items():
        if entry["class"] == CAT_FRAMEWORK_OWNED:
            path_str = entry.get("path", "")
            if path_str:
                p = Path(path_str)
                outside = True
                for root in framework_roots:
                    try:
                        p.relative_to(root)
                        outside = False
                        break
                    except ValueError:
                        continue
                if outside:
                    # Check if it's under source_root at least
                    try:
                        p.relative_to(source_root)
                        outside = False  # Under source root = OK
                    except ValueError:
                        pass
                if outside:
                    violations.append(
                        f"framework-owned module '{name}' resolves outside "
                        f"framework roots: {p}"
                    )

    # 9b. Dependencies absent from lock/SBOM (only for third_party and extension)
    if known_deps:
        for name, entry in classified_union.items():
            if entry["class"] in (CAT_THIRD_PARTY, CAT_EXTENSION):
                dist = entry.get("owning_distribution", "")
                if dist and dist.lower().replace("_", "-") not in known_deps:
                    violations.append(
                        f"dependency '{name}' (distribution: {dist}) not found "
                        f"in lock file or SBOM"
                    )
                elif not dist:
                    # Try the top-level package name
                    top = name.split(".")[0]
                    if top.lower().replace("_", "-") not in known_deps:
                        violations.append(
                            f"dependency '{name}' (top: {top}) has no owning "
                            f"distribution and not found in lock/SBOM"
                        )

    # 9c. Unresolved imports (failed classification)
    for name, entry in classified_union.items():
        if entry["class"] == CAT_FAILED:
            violations.append(
                f"unresolved import '{name}': {entry.get('error', 'no error')}"
            )

    # 9d. Untested branches (optional imports not covered by runtime traces)
    for name in sorted(optional_imports):
        if name not in runtime_imports:
            violations.append(
                f"optional/conditional import '{name}' not covered by runtime traces"
            )

    # ── 10. Build manifest ───────────────────────────────────────────
    manifest = {
        "manifest_version": "1.0.0",
        "source_root": str(source_root.resolve()),
        "framework_roots": [str(r) for r in framework_roots],
        "generated_at": __import__("datetime").datetime.now().isoformat(),
        "static_imports": {
            "file_count": len(static_data["files"]),
            "files": static_data["files"],
            "all_literal_imports": sorted(all_literal),
            "all_nonliteral_imports": sorted(all_nonliteral),
            "allowed_nonliteral": sorted(allowed_nonliteral),
            "disallowed_nonliteral": sorted(disallowed_nonliteral),
            "classified": classified_literal,
            "recursive_imports": sorted(recursive_imports),
        },
        "runtime_imports": {
            "trace_sources": runtime_trace_globs or [],
            "imports": sorted(runtime_imports),
            "classified": classifier.classify_all(runtime_imports),
        },
        "optional_branch_imports": {
            "imports": sorted(optional_imports),
            "classified": classified_optional,
        },
        "union_imports": {
            "total": len(union_imports),
            "imports": sorted(union_imports),
            "classified": classified_union,
        },
        "lock_deps": {
            "source": lock_file or "",
            "count": len(lock_deps),
            "deps": sorted(lock_deps),
        },
        "sbom_deps": {
            "source": sbom_file or "",
            "count": len(sbom_deps),
            "deps": sorted(sbom_deps),
        },
        "violations": violations,
        "gate_passed": len(violations) == 0,
        "summary": {
            "total_imports": len(union_imports),
            "framework_owned": sum(
                1 for e in classified_union.values() if e["class"] == CAT_FRAMEWORK_OWNED
            ),
            "stdlib": sum(
                1 for e in classified_union.values() if e["class"] == CAT_STDLIB
            ),
            "third_party": sum(
                1 for e in classified_union.values() if e["class"] == CAT_THIRD_PARTY
            ),
            "builtin": sum(
                1 for e in classified_union.values() if e["class"] == CAT_BUILTIN
            ),
            "extension": sum(
                1 for e in classified_union.values() if e["class"] == CAT_EXTENSION
            ),
            "frozen": sum(
                1 for e in classified_union.values() if e["class"] == CAT_FROZEN
            ),
            "namespace_package": sum(
                1 for e in classified_union.values() if e["class"] == CAT_NAMESPACE_PACKAGE
            ),
            "failed": sum(
                1 for e in classified_union.values() if e["class"] == CAT_FAILED
            ),
            "violation_count": len(violations),
        },
    }

    # ── 11. Write output ─────────────────────────────────────────────
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False, default=str) + "\n"
    )

    return manifest


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="AI-Researcher native preflight gate: source-parity and "
        "import-precedence validation.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  %(prog)s --source-root /path/to/AI-Researcher --output manifest.json\n"
            "  %(prog)s --source-root /path/to/AI-Researcher --output manifest.json \\\n"
            "      --lock-file requirements.txt --sbom sbom.json \\\n"
            "      --runtime-traces 'traces/*.json' \\\n"
            "      --framework-root workspace/AI-Researcher \\\n"
            "      --framework-root runtime-adapter\n"
        ),
    )
    p.add_argument(
        "--source-root",
        required=True,
        help="Path to the AI-Researcher source root directory",
    )
    p.add_argument(
        "--output",
        required=True,
        help="Path to write the output manifest JSON",
    )
    p.add_argument(
        "--framework-root",
        action="append",
        default=[],
        dest="framework_roots",
        help="Framework-owned path roots (relative to source-root or absolute). "
        "Can be specified multiple times. Defaults to workspace/AI-Researcher "
        "and runtime-adapter if not specified.",
    )
    p.add_argument(
        "--lock-file",
        default=None,
        help="Path to a requirements.txt or similar lock file for dependency "
        "verification",
    )
    p.add_argument(
        "--sbom",
        default=None,
        dest="sbom_file",
        help="Path to a CycloneDX or SPDX SBOM JSON file for dependency "
        "verification",
    )
    p.add_argument(
        "--runtime-traces",
        action="append",
        default=[],
        dest="runtime_trace_globs",
        help="Glob pattern(s) for runtime trace files (JSON or text). "
        "Can be specified multiple times.",
    )
    p.add_argument(
        "--allow-missing-lock",
        action="store_true",
        help="Do not fail if lock file or SBOM is missing or empty",
    )
    p.add_argument(
        "--verbose",
        action="store_true",
        help="Print detailed progress to stderr",
    )
    return p


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    source_root = Path(args.source_root)
    if not source_root.is_dir():
        print(
            f"ERROR: source-root '{source_root}' is not a directory",
            file=sys.stderr,
        )
        return 2

    output_path = Path(args.output)

    # Default framework roots if none specified
    framework_roots = [
        Path(r) if r.startswith("/") else source_root / r
        for r in (args.framework_roots or ["workspace/AI-Researcher", "runtime-adapter"])
    ]

    # Resolve framework roots
    resolved_framework_roots = []
    for r in framework_roots:
        resolved = r.resolve()
        resolved_framework_roots.append(resolved)
        if args.verbose:
            print(f"  framework root: {resolved}", file=sys.stderr)

    if args.verbose:
        print(f"source-root: {source_root.resolve()}", file=sys.stderr)
        print(f"output: {output_path.resolve()}", file=sys.stderr)

    # Validate lock/SBOM
    if args.lock_file and not Path(args.lock_file).is_file():
        if args.allow_missing_lock:
            if args.verbose:
                print(
                    f"  WARNING: lock file '{args.lock_file}' not found (allowed)",
                    file=sys.stderr,
                )
        else:
            print(
                f"ERROR: lock file '{args.lock_file}' not found",
                file=sys.stderr,
            )
            return 2

    if args.sbom_file and not Path(args.sbom_file).is_file():
        if args.allow_missing_lock:
            if args.verbose:
                print(
                    f"  WARNING: SBOM file '{args.sbom_file}' not found (allowed)",
                    file=sys.stderr,
                )
        else:
            print(
                f"ERROR: SBOM file '{args.sbom_file}' not found",
                file=sys.stderr,
            )
            return 2

    # Run gate
    try:
        manifest = validate_and_manifest(
            source_root=source_root,
            output_path=output_path,
            framework_roots=resolved_framework_roots,
            lock_file=args.lock_file,
            sbom_file=args.sbom_file,
            runtime_trace_globs=args.runtime_trace_globs or None,
        )
    except Exception as e:
        print(f"ERROR: preflight gate failed: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc(file=sys.stderr)
        return 2

    # Print result
    gate_passed = manifest["gate_passed"]
    vcount = manifest["summary"]["violation_count"]

    if gate_passed:
        print(
            f"✓ PREFLIGHT GATE PASSED — {manifest['summary']['total_imports']} "
            f"imports classified, 0 violations"
        )
        print(f"  Manifest written to: {output_path.resolve()}")
        return 0
    else:
        print(
            f"✗ PREFLIGHT GATE BLOCKED — {vcount} violation(s) found",
            file=sys.stderr,
        )
        for v in manifest["violations"]:
            print(f"  - {v}", file=sys.stderr)
        print(f"  Manifest written to: {output_path.resolve()}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())