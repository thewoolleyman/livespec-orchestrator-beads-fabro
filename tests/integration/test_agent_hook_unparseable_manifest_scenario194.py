"""The agent-hook route of `SPECIFICATION/scenarios.md` Scenario 194.

WHAT THIS BINDS. Scenario 194 — "A conflicted pyproject.toml does not make the
repository's agent hooks refuse every tool call" — has two sub-scenarios: a
conflicted manifest lets a guarded call through and says so on standard error,
and a parseable manifest leaves every guard decision exactly as it was. Both
are properties of the LAUNCHER that this repository's `.claude/settings.json`
puts in front of each `uv run`-started PreToolUse hook command, because `uv`
refuses an unparseable manifest with exit status 2 before any guard's own
Python boundary can run, and Claude Code reads that status as a deny.

WHY THE COMMANDS ARE READ OFF `.claude/settings.json` RATHER THAN RETYPED. The
scenario is about the hook commands this repository COMMITS — "a uv-launched
PreToolUse hook command of this repository" — so a module carrying its own copy
of them would keep passing while the committed wiring said something else. Each
case below resolves those commands from the settings file and drives the
launcher with the very argv the committed line hands it. The unit tier
(`tests/hooks/test_livespec_uv_hook_launcher.py`) pins the SHAPE of that
wiring; this tier asserts the BEHAVIOUR every committed command reaches
through it.

NOTHING IS SPAWNED. `check-tests-no-subprocess-spawn` governs this
repository's tests, and the claims here are WHETHER the wrapped command is
launched and WHAT its status does — neither needs a real child process, so the
launcher's own `subprocess.run` is stood in for. The enclosing run's own
manifest is never read either: each case builds its own project directory under
`tmp_path` and points the launcher at that.
"""

from __future__ import annotations

import importlib.util
import json
import shlex
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_LAUNCHER_PATH = _REPO_ROOT / ".claude" / "hooks" / "livespec_uv_hook_launcher.py"
_SETTINGS_PATH = _REPO_ROOT / ".claude" / "settings.json"
_MODULE_NAME = "livespec_uv_hook_launcher_scenario194"

_MANIFEST_NAME = "pyproject.toml"
_PROJECT_DIR_ENV_VAR = "CLAUDE_PROJECT_DIR"
_UV_LAUNCH_TOKEN = "uv run"
_GUARD_ARGV0 = "mise"
_GUARDED_TOOLS = ("Write", "Edit", "MultiEdit", "Bash")
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


def uv_launched_commands() -> list[str]:
    """The committed PreToolUse hook commands that start a guard through `uv run`."""
    settings = json.loads(_SETTINGS_PATH.read_text(encoding="utf-8"))
    return [
        hook["command"]
        for entry in settings["hooks"]["PreToolUse"]
        for hook in entry["hooks"]
        if _UV_LAUNCH_TOKEN in hook["command"]
    ]


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


def _guard_argv(*, command: str, project: Path) -> list[str]:
    """The argv of the GUARD one committed hook command runs.

    The guard's own invocation starts at `mise`; anything ahead of it is the
    launcher prefix, whose presence the unit tier asserts. Slicing from that
    token rather than testing for the prefix keeps each case here about
    behaviour instead of re-reading the wiring.
    """
    expanded = shlex.split(command.replace("$CLAUDE_PROJECT_DIR", str(project)))
    return expanded[expanded.index(_GUARD_ARGV0) :]


def _record_invocations(
    *, launcher: ModuleType, monkeypatch: pytest.MonkeyPatch, returncode: int = 0
) -> list[list[str]]:
    """Stand in for the wrapped guard and record every argv it is given."""
    recorded: list[list[str]] = []

    def _fake_run(*, args: list[str], check: bool) -> subprocess.CompletedProcess[bytes]:
        assert check is False, "the wrapped guard's own status is the launcher's answer"
        recorded.append(list(args))
        return subprocess.CompletedProcess(args=args, returncode=returncode)

    monkeypatch.setattr(launcher.subprocess, "run", _fake_run)
    return recorded


def _write_manifest(*, project: Path, body: str) -> None:
    _ = (project / _MANIFEST_NAME).write_text(body, encoding="utf-8")


def _drive(
    *, launcher: ModuleType, project: Path, guard: list[str], monkeypatch: pytest.MonkeyPatch
) -> int:
    """Run the launcher exactly as the committed hook command invokes it."""
    monkeypatch.setenv(_PROJECT_DIR_ENV_VAR, str(project))
    monkeypatch.setattr(sys, "argv", [str(_LAUNCHER_PATH), *guard])
    exit_code = launcher.main()
    assert isinstance(exit_code, int)
    return exit_code


# --- "A conflicted pyproject.toml lets a guarded tool call through ..." ----


@pytest.mark.parametrize("command", uv_launched_commands())
@pytest.mark.parametrize("tool", _GUARDED_TOOLS)
def test_a_conflicted_manifest_allows_the_call_and_names_the_skipped_guard(
    tool: str,
    command: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Every guarded tool stays usable, and the one stderr line says why.

    The tool is a parameter rather than an input because the launcher runs
    AHEAD of the guard that reads the payload: what the scenario claims is that
    none of the four guarded tools is refused in this state, and the launcher
    reaches the same verdict for each. Pairing it with every committed command
    is what makes the claim cover "a uv-launched PreToolUse hook command of
    this repository" rather than one of them.
    """
    launcher = _load_launcher()
    _write_manifest(project=tmp_path, body=_CONFLICTED_MANIFEST)
    guard = _guard_argv(command=command, project=tmp_path)
    invocations = _record_invocations(launcher=launcher, monkeypatch=monkeypatch)

    allowed = _drive(launcher=launcher, project=tmp_path, guard=guard, monkeypatch=monkeypatch)

    assert allowed == 0, f"a {tool} call must not be refused while the manifest is conflicted"
    assert invocations == [], "uv must not be reached: its refusal is what this removes"
    notice = capsys.readouterr().err.splitlines()
    assert len(notice) == 1, f"exactly one line belongs on stderr, got: {notice}"
    assert str(tmp_path / _MANIFEST_NAME) in notice[0]
    assert "unparseable" in notice[0]
    assert "skipped" in notice[0]
    assert shlex.join(guard) in notice[0]


# --- "A parseable pyproject.toml leaves every guard decision unchanged" ----


@pytest.mark.parametrize("command", uv_launched_commands())
def test_a_parseable_manifest_launches_the_committed_guard_verbatim(
    command: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The guard reaches `uv` with the argv the settings file committed."""
    launcher = _load_launcher()
    _write_manifest(project=tmp_path, body=_PARSEABLE_MANIFEST)
    guard = _guard_argv(command=command, project=tmp_path)
    invocations = _record_invocations(launcher=launcher, monkeypatch=monkeypatch)

    allowed = _drive(launcher=launcher, project=tmp_path, guard=guard, monkeypatch=monkeypatch)

    assert allowed == 0
    assert invocations == [guard], "the committed guard must run exactly as committed"
    assert capsys.readouterr().err == "", "an unchanged decision is also an unchanged surface"


@pytest.mark.parametrize("command", uv_launched_commands())
def test_a_parseable_manifest_returns_the_committed_guards_own_refusal(
    command: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A guard that denies still denies: the launcher returns its status."""
    launcher = _load_launcher()
    _write_manifest(project=tmp_path, body=_PARSEABLE_MANIFEST)
    guard = _guard_argv(command=command, project=tmp_path)
    _ = _record_invocations(launcher=launcher, monkeypatch=monkeypatch, returncode=_REFUSAL_STATUS)

    refused = _drive(launcher=launcher, project=tmp_path, guard=guard, monkeypatch=monkeypatch)

    assert refused == _REFUSAL_STATUS
