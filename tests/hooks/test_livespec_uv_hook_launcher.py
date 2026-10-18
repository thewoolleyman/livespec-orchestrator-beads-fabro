"""Coverage for the uv hook launcher — the front door of this repo's uv-started hooks.

The launcher is spliced ahead of each `uv run`-started PreToolUse hook command
in `.claude/settings.json`. Its whole job is the decision `uv` itself cannot be
asked to make: when `pyproject.toml` cannot be parsed, `uv run` exits 2 before
the interpreter starts, and Claude Code reads a PreToolUse exit status 2 as a
blocking refusal — so a conflicted manifest refuses every `Write`, `Edit`,
`MultiEdit` and `Bash` call, including the ones that would repair it.

EVERY STAND-DOWN CASE IS PAIRED WITH A PARSEABLE CONTROL. "The guard did not
run" is also what a launcher that never runs anything produces, so a case
asserting the stand-down proves nothing on its own; the control is what makes
the conflicted manifest the cause.

These tests drive `main()` in-process. The wrapped command is stood in for by
patching the launcher's own `subprocess.run`, never by spawning anything:
`check-tests-no-subprocess-spawn` governs this tree, and what is under test is
WHETHER the wrapped command runs and WHAT its status does, neither of which
needs a real child process.

`.claude/hooks/` is not an importable package and Claude Code executes each
hook as a standalone script, so the module is loaded by file location. The load
happens INSIDE each test body and the first assertion is that the file exists,
so a Red commit fails on a genuine assertion rather than at collection time.
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_HOOKS_DIR = _REPO_ROOT / ".claude" / "hooks"
_LAUNCHER_PATH = _HOOKS_DIR / "livespec_uv_hook_launcher.py"
_MODULE_NAME = "livespec_uv_hook_launcher_under_test"

_MANIFEST_NAME = "pyproject.toml"
_GUARD_COMMAND = ["mise", "exec", "--", "uv", "run", "--no-sync", "python", "guard.py"]
_REFUSAL_STATUS = 2

_PARSEABLE_MANIFEST = '[project]\nname = "fixture"\nversion = "0.0.0"\n'
_CONFLICTED_MANIFEST = (
    "[project]\n"
    'name = "fixture"\n'
    "<<<<<<< HEAD\n"
    'version = "0.1.0"\n'
    "=======\n"
    'version = "0.2.0"\n'
    ">>>>>>> origin/master\n"
)


def _load_launcher() -> ModuleType:
    """Load the launcher by file location, asserting it exists first."""
    assert _LAUNCHER_PATH.is_file(), f"launcher not implemented yet: {_LAUNCHER_PATH}"
    spec = importlib.util.spec_from_file_location(_MODULE_NAME, _LAUNCHER_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[_MODULE_NAME] = module
    spec.loader.exec_module(module)
    return module


def _write_manifest(*, project: Path, body: str) -> None:
    _ = (project / _MANIFEST_NAME).write_text(body, encoding="utf-8")


def _record_invocations(
    *, launcher: ModuleType, monkeypatch: pytest.MonkeyPatch, returncode: int = 0
) -> list[list[str]]:
    """Stand in for the wrapped command and record every argv it is given."""
    recorded: list[list[str]] = []

    def _fake_run(*, args: list[str], check: bool) -> subprocess.CompletedProcess[bytes]:
        assert check is False, "the wrapped guard's own status is the launcher's answer"
        recorded.append(list(args))
        return subprocess.CompletedProcess(args=args, returncode=returncode)

    monkeypatch.setattr(launcher.subprocess, "run", _fake_run)
    return recorded


def _drive(*, launcher: ModuleType, project: Path, monkeypatch: pytest.MonkeyPatch) -> int:
    """Run `main()` as Claude Code runs it: argv after the launcher's own path."""
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(project))
    monkeypatch.setattr(sys, "argv", [str(_LAUNCHER_PATH), *_GUARD_COMMAND])
    exit_code = launcher.main()
    assert isinstance(exit_code, int)
    return exit_code


# --- the stand-down, while the manifest cannot be parsed -------------------


def test_a_conflicted_manifest_allows_the_call_without_running_the_guard(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The refusal that wedges a repair turn is the LAUNCHER's, so it stops here.

    `uv run` exits 2 on an unparseable manifest before the guard's own
    fail-open boundary can run, and Claude Code reads that as a deny. Allowing
    the call is what leaves the agent able to resolve the conflict.
    """
    launcher = _load_launcher()
    _write_manifest(project=tmp_path, body=_CONFLICTED_MANIFEST)
    invocations = _record_invocations(launcher=launcher, monkeypatch=monkeypatch)

    assert _drive(launcher=launcher, project=tmp_path, monkeypatch=monkeypatch) == 0
    assert invocations == [], "the guard must not be launched while the manifest is conflicted"


# --- the control: a parseable manifest changes nothing ---------------------


def test_a_parseable_manifest_launches_the_wrapped_guard(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The launcher is a pass-through whenever the manifest parses."""
    launcher = _load_launcher()
    _write_manifest(project=tmp_path, body=_PARSEABLE_MANIFEST)
    invocations = _record_invocations(launcher=launcher, monkeypatch=monkeypatch)

    assert _drive(launcher=launcher, project=tmp_path, monkeypatch=monkeypatch) == 0
    assert invocations == [_GUARD_COMMAND], "the wrapped guard must run exactly as given"


def test_a_parseable_manifest_returns_the_wrapped_guards_own_refusal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A guard that refuses must still refuse: its status is the launcher's."""
    launcher = _load_launcher()
    _write_manifest(project=tmp_path, body=_PARSEABLE_MANIFEST)
    _ = _record_invocations(launcher=launcher, monkeypatch=monkeypatch, returncode=_REFUSAL_STATUS)

    assert (
        _drive(launcher=launcher, project=tmp_path, monkeypatch=monkeypatch) == _REFUSAL_STATUS
    ), "a refusal the guard reached on a parseable manifest must reach Claude Code"
