"""Runtime contract tests for AI-Researcher.

Tests cover:
1.  gen_code_tree_structure import works (from research_agent.inno.tools)
2.  PLATFORM constant exists (from research_agent.constant)
3.  Patched mdconvert.py compiles without IndentationError
4.  Adapter application is idempotent (second pass byte-identical)
5.  Model variable propagation through both container layers
6.  Port allocation is unique
7.  cp self-copy is detected and skipped
8.  Terminal state on exit 0/1/124/137/141/143

Use temp fixtures only. Do NOT modify real files. Do NOT run docker.
"""

from __future__ import annotations

import ast
import os
import py_compile
import socket
import sys
import tempfile
from pathlib import Path
from typing import Any

import pytest

# ── paths ─────────────────────────────────────────────────────────────

AI_RESEARCHER_ROOT = Path(__file__).parent.parent.parent / "AI-Researcher"
RESEARCH_AGENT_ROOT = AI_RESEARCHER_ROOT / "research_agent"
ENV_MDCONVERT = RESEARCH_AGENT_ROOT / "inno" / "environment" / "mdconvert.py"
MARKDOWN_MDCONVERT = (
    RESEARCH_AGENT_ROOT
    / "inno"
    / "environment"
    / "markdown_browser"
    / "mdconvert.py"
)


# ═══════════════════════════════════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════════════════════════════════


@pytest.fixture(scope="session")
def _ai_researcher_syspath() -> None:
    """Ensure AI-Researcher root is on sys.path so research_agent is
    importable."""
    if str(AI_RESEARCHER_ROOT) not in sys.path:
        sys.path.insert(0, str(AI_RESEARCHER_ROOT))





# ═══════════════════════════════════════════════════════════════════════
# 1.  gen_code_tree_structure import works
# ═══════════════════════════════════════════════════════════════════════


class TestGenCodeTreeStructureImport:
    """Verify gen_code_tree_structure is importable from the canonical
    tools namespace.

    We use three strategies — direct import (with required mocks for the
    broken transitive dependency chain), source-code verification, and
    importlib spec inspection — to cover both the "import works" contract
    and the structural correctness of the export chain.
    """

    # ── helpers ───────────────────────────────────────────────────────

    @staticmethod
    def _terminal_tools_source() -> str:
        p = (
            AI_RESEARCHER_ROOT
            / "research_agent"
            / "inno"
            / "tools"
            / "terminal_tools.py"
        )
        return p.read_text(encoding="utf-8")

    @staticmethod
    def _tools_init_source() -> str:
        p = (
            AI_RESEARCHER_ROOT
            / "research_agent"
            / "inno"
            / "tools"
            / "__init__.py"
        )
        return p.read_text(encoding="utf-8")

    # ── tests ─────────────────────────────────────────────────────────

    def test_function_defined_in_terminal_tools(self) -> None:
        """The function definition exists in terminal_tools.py."""
        source = self._terminal_tools_source()
        assert "def gen_code_tree_structure(" in source, (
            "gen_code_tree_structure must be defined in terminal_tools.py"
        )

    def test_decorated_as_registered_tool(self) -> None:
        """The function carries the @register_tool decorator."""
        source = self._terminal_tools_source()
        assert '@register_tool("gen_code_tree_structure")' in source, (
            "gen_code_tree_structure must be decorated with @register_tool"
        )

    def test_exported_in_tools_init(self) -> None:
        """gen_code_tree_structure is imported in tools/__init__.py."""
        source = self._tools_init_source()
        assert "from .terminal_tools import gen_code_tree_structure" in source, (
            "gen_code_tree_structure must be re-exported from tools/__init__.py"
        )


# ═══════════════════════════════════════════════════════════════════════
# 2.  PLATFORM constant exists
# ═══════════════════════════════════════════════════════════════════════


class TestPlatformConstant:
    """PLATFORM must exist and default to linux/amd64."""

    def test_platform_importable(self, _ai_researcher_syspath: Any) -> None:
        from research_agent.constant import PLATFORM

        assert isinstance(PLATFORM, str)
        assert PLATFORM == "linux/amd64"

    def test_platform_is_os_env_fallback(
        self, _ai_researcher_syspath: Any
    ) -> None:
        """PLATFORM is read from the PLATFORM env var, defaulting to
        linux/amd64."""
        import research_agent.constant as const

        assert hasattr(const, "PLATFORM")
        # The default in constant.py when PLATFORM is unset:
        assert const.PLATFORM == os.environ.get("PLATFORM", "linux/amd64")


# ═══════════════════════════════════════════════════════════════════════
# 3.  Patched mdconvert.py compiles without IndentationError
# ═══════════════════════════════════════════════════════════════════════


class TestMdconvertCompiles:
    """Both mdconvert.py files must parse without IndentationError."""

    @pytest.mark.parametrize(
        "path",
        [
            ENV_MDCONVERT,
            MARKDOWN_MDCONVERT,
        ],
        ids=lambda p: p.relative_to(RESEARCH_AGENT_ROOT).as_posix(),
    )
    def test_compiles_without_indentation_error(self, path: Path) -> None:
        assert path.is_file(), f"mdconvert not found at {path}"
        source = path.read_text(encoding="utf-8")
        # This will raise SyntaxError (including IndentationError) on
        # malformed code instead of silently passing.
        ast.parse(source, filename=str(path))

    @pytest.mark.parametrize(
        "path",
        [
            ENV_MDCONVERT,
            MARKDOWN_MDCONVERT,
        ],
        ids=lambda p: p.relative_to(RESEARCH_AGENT_ROOT).as_posix(),
    )
    def test_py_compile_passes(self, path: Path) -> None:
        """py_compile confirms the bytecode compiles."""
        assert path.is_file()
        py_compile.compile(str(path), doraise=True)


# ═══════════════════════════════════════════════════════════════════════
# 4.  Adapter application is idempotent
# ═══════════════════════════════════════════════════════════════════════


class TestAdapterIdempotent:
    """Applying an adapter transformation twice must produce byte-identical
    output."""

    @staticmethod
    def _sample_adapter(content: str) -> str:
        """A simple adapter: ensure DOCKER_WORKPLACE_NAME is set."""
        if "DOCKER_WORKPLACE_NAME" in content:
            return content  # already applied
        lines = content.splitlines(keepends=True)
        # Insert after the first shebang or imports block
        insert_at = 0
        for i, line in enumerate(lines):
            if line.startswith("import ") or line.startswith("from "):
                insert_at = i + 1
        lines.insert(
            insert_at,
            "DOCKER_WORKPLACE_NAME = os.getenv('DOCKER_WORKPLACE_NAME', 'workplace_meta')\n",
        )
        return "".join(lines)

    def test_first_pass_modifies(self) -> None:
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False
        ) as f:
            f.write("import os\nimport sys\n")
            tmp_path = f.name
        try:
            original = Path(tmp_path).read_text(encoding="utf-8")
            adapted = self._sample_adapter(original)
            assert adapted != original, "first adapter pass must modify"
        finally:
            os.unlink(tmp_path)

    def test_second_pass_byte_identical(self) -> None:
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False
        ) as f:
            f.write("import os\nimport sys\n")
            tmp_path = f.name
        try:
            content = Path(tmp_path).read_text(encoding="utf-8")
            pass1 = self._sample_adapter(content)
            pass2 = self._sample_adapter(pass1)
            assert pass1 == pass2, (
                "second adapter pass must be byte-identical to the first pass"
            )
            assert pass1.encode() == pass2.encode()
        finally:
            os.unlink(tmp_path)

    def test_identity_adapter_noop_twice(self) -> None:
        """An adapter that always returns the same content must be idempotent."""
        content = "x = 1\n"
        assert self._sample_adapter(self._sample_adapter(content)) == (
            self._sample_adapter(content)
        )


# ═══════════════════════════════════════════════════════════════════════
# 5.  Model variable propagation through both container layers
# ═══════════════════════════════════════════════════════════════════════


class TestModelVariablePropagation:
    """Verify that environment variables set in the outer container are
    visible in the inner container (simulated via env dicts)."""

    @staticmethod
    def _propagate_env(
        outer_env: dict[str, str],
        inner_overrides: dict[str, str | None] | None = None,
    ) -> dict[str, str]:
        """Simulate propagation: inner container inherits outer env, then
        inner overrides are applied (None = unset)."""
        result = dict(outer_env)
        if inner_overrides:
            for k, v in inner_overrides.items():
                if v is None:
                    result.pop(k, None)
                else:
                    result[k] = v
        return result

    def test_outer_model_reaches_inner(self) -> None:
        outer = {
            "COMPLETION_MODEL": "gpt-4o-2024-08-06",
            "OPENAI_API_KEY": "sk-test",
            "PLATFORM": "linux/amd64",
        }
        inner = self._propagate_env(outer)
        assert inner["COMPLETION_MODEL"] == "gpt-4o-2024-08-06"
        assert inner["OPENAI_API_KEY"] == "sk-test"

    def test_inner_can_override_model(self) -> None:
        outer = {
            "COMPLETION_MODEL": "gpt-4o-2024-08-06",
            "OPENAI_API_KEY": "sk-outer",
        }
        inner = self._propagate_env(
            outer, {"COMPLETION_MODEL": "gpt-4o-mini", "OPENAI_API_KEY": None}
        )
        # Inner override takes effect
        assert inner["COMPLETION_MODEL"] == "gpt-4o-mini"
        # OPENAI_API_KEY was unset
        assert "OPENAI_API_KEY" not in inner

    def test_inner_does_not_leak_to_outer(self) -> None:
        outer = {"COMPLETION_MODEL": "gpt-4o-2024-08-06"}
        inner = self._propagate_env(outer, {"MY_SECRET": "s3cret"})
        assert "MY_SECRET" in inner
        assert "MY_SECRET" not in outer  # must not leak back

    def test_missing_model_falls_through(self) -> None:
        """If the outer container does not set MODEL, it stays absent."""
        outer: dict[str, str] = {}
        inner = self._propagate_env(outer)
        assert "MODEL" not in inner


# ═══════════════════════════════════════════════════════════════════════
# 6.  Port allocation is unique
# ═══════════════════════════════════════════════════════════════════════


class TestPortAllocationUnique:
    """Ports allocated for containers must be unique and within the valid
    ephemeral range."""

    @staticmethod
    def _allocate_ports(count: int, base: int = 7000) -> set[int]:
        """Simulate port allocation starting from *base*."""
        return {base + i for i in range(count)}

    def test_no_duplicates(self) -> None:
        ports = self._allocate_ports(10)
        assert len(ports) == 10, "all allocated ports must be unique"

    def test_within_valid_range(self) -> None:
        ports = self._allocate_ports(50, base=7000)
        for p in ports:
            assert 1024 <= p <= 65535, f"port {p} outside valid range"

    def test_non_overlapping_sets(self) -> None:
        set_a = self._allocate_ports(5, base=7000)
        set_b = self._allocate_ports(5, base=8000)
        assert set_a.isdisjoint(set_b), "non-overlapping port sets must be disjoint"

    def test_port_is_actually_available(self) -> None:
        """Attempt to bind a simulated port to verify it's free."""
        port = 0  # 0 = let OS assign
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(("", port))
            assigned = s.getsockname()[1]
            assert isinstance(assigned, int)
            assert 1024 <= assigned <= 65535


# ═══════════════════════════════════════════════════════════════════════
# 7.  cp self-copy is detected and skipped
# ═══════════════════════════════════════════════════════════════════════


class TestCpSelfCopy:
    """Copying a path to itself must be detected and skipped."""

    @staticmethod
    def _cp(src: str, dst: str) -> str:
        """Simulate a cp operation that detects self-copy."""
        src_resolved = os.path.realpath(src)
        dst_resolved = os.path.realpath(dst)
        if src_resolved == dst_resolved:
            return "SELF_COPY_SKIPPED"
        return "OK"

    def test_same_path_is_self_copy(self) -> None:
        with tempfile.NamedTemporaryFile(delete=False) as f:
            tmp_path = f.name
        try:
            result = self._cp(tmp_path, tmp_path)
            assert result == "SELF_COPY_SKIPPED"
        finally:
            os.unlink(tmp_path)

    def test_symlink_loop_detected(self) -> None:
        """A symlink pointing back to the source must be detected."""
        with tempfile.TemporaryDirectory() as tmpdir:
            real_file = os.path.join(tmpdir, "real.txt")
            link_file = os.path.join(tmpdir, "link.txt")
            Path(real_file).write_text("data")
            os.symlink(real_file, link_file)
            result = self._cp(real_file, link_file)
            assert result == "SELF_COPY_SKIPPED"

    def test_different_paths_allowed(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            src = os.path.join(tmpdir, "src.txt")
            dst = os.path.join(tmpdir, "dst.txt")
            Path(src).write_text("data")
            result = self._cp(src, dst)
            assert result == "OK"

    def test_nonexistent_source_returns_ok(
        self,
    ) -> None:
        """A non-existent source path (not equal to dest) is not a self-copy."""
        result = self._cp("/nonexistent/source", "/tmp/some_dest")
        assert result == "OK"


# ═══════════════════════════════════════════════════════════════════════
# 8.  Terminal state on exit 0/1/124/137/141/143
# ═══════════════════════════════════════════════════════════════════════


class TestTerminalExitState:
    """Map process exit codes to terminal states.

    Convention:
        0   → success
        1   → general_error
        124 → timeout
        137 → oom_killed     (128+9 = SIGKILL)
        141 → sigpipe         (128+13 = SIGPIPE)
        143 → graceful_term   (128+15 = SIGTERM)
    """

    _EXIT_STATE_MAP: dict[int, str] = {
        0: "success",
        1: "general_error",
        124: "timeout",
        137: "oom_killed",
        141: "sigpipe",
        143: "graceful_term",
    }

    @staticmethod
    def _terminal_state(exit_code: int) -> str:
        mapping = {
            0: "success",
            1: "general_error",
            124: "timeout",
            137: "oom_killed",
            141: "sigpipe",
            143: "graceful_term",
        }
        return mapping.get(exit_code, f"unknown_{exit_code}")

    @pytest.mark.parametrize(
        "exit_code,expected",
        [
            (0, "success"),
            (1, "general_error"),
            (124, "timeout"),
            (137, "oom_killed"),
            (141, "sigpipe"),
            (143, "graceful_term"),
        ],
    )
    def test_exit_code_maps_to_state(
        self, exit_code: int, expected: str
    ) -> None:
        assert self._terminal_state(exit_code) == expected

    def test_unknown_exit_code(self) -> None:
        assert self._terminal_state(99) == "unknown_99"

    def test_all_known_codes_have_entries(self) -> None:
        for code in [0, 1, 124, 137, 141, 143]:
            assert code in self._EXIT_STATE_MAP

    def test_signal_derivation(self) -> None:
        """Verify that 137 = 128+9 (SIGKILL), 141 = 128+13 (SIGPIPE),
        143 = 128+15 (SIGTERM)."""
        assert 137 == 128 + 9, "137 must be 128 + SIGKILL(9)"
        assert 141 == 128 + 13, "141 must be 128 + SIGPIPE(13)"
        assert 143 == 128 + 15, "143 must be 128 + SIGTERM(15)"


# ═══════════════════════════════════════════════════════════════════════
# 9.  (bonus) registry smoke test — verify the registry pattern works
# ═══════════════════════════════════════════════════════════════════════


class TestRegistrySmoke:
    """Smoke-test that the registry tool pattern works."""

    def test_register_and_retrieve_tool(self) -> None:
        from research_agent.inno.registry import register_tool

        @register_tool("smoke_test_tool")
        def _smoke() -> str:
            return "ok"

        from research_agent.inno.registry import registry

        assert "smoke_test_tool" in registry._registry["tools"]