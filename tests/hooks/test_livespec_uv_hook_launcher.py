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
import json
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_HOOKS_DIR = _REPO_ROOT / ".claude" / "hooks"
_LAUNCHER_PATH = _HOOKS_DIR / "livespec_uv_hook_launcher.py"
_SETTINGS_PATH = _REPO_ROOT / ".claude" / "settings.json"
_MODULE_NAME = "livespec_uv_hook_launcher_under_test"

_MANIFEST_NAME = "pyproject.toml"
_PROJECT_DIR_ENV_VAR = "CLAUDE_PROJECT_DIR"
_GUARD_COMMAND = ["mise", "exec", "--", "uv", "run", "--no-sync", "python", "guard.py"]
_REFUSAL_STATUS = 2

# The committed wiring, spelled out rather than derived: a test that recomputed
# the expected command from the settings file would agree with any rewiring at
# all, including one that dropped a guard.
_UV_LAUNCH_TOKEN = "uv run"
_LAUNCHER_PREFIX = 'python3 "$CLAUDE_PROJECT_DIR/.claude/hooks/livespec_uv_hook_launcher.py"'
_UV_LAUNCHED_GUARDS = (
    'mise exec -- uv run --no-sync python "$CLAUDE_PROJECT_DIR/.claude/hooks/livespec_tdd_order_guard.py"',
    "mise exec -- uv run --no-sync python -m livespec_dev_tooling.agent_hooks.pretooluse_background_guard",
)

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


def test_a_conflicted_manifest_says_on_stderr_which_guard_it_skipped(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A silent stand-down is indistinguishable from a guard that passed.

    The one line is the whole operator surface for this state: it has to name
    the manifest as the cause and the guard as what was given up, or an agent
    whose write sailed through has no way to know the guard did not decide it.
    """
    launcher = _load_launcher()
    _write_manifest(project=tmp_path, body=_CONFLICTED_MANIFEST)
    _ = _record_invocations(launcher=launcher, monkeypatch=monkeypatch)

    assert _drive(launcher=launcher, project=tmp_path, monkeypatch=monkeypatch) == 0
    notice = capsys.readouterr().err.splitlines()
    assert len(notice) == 1, f"exactly one line belongs on stderr, got: {notice}"
    assert str(tmp_path / _MANIFEST_NAME) in notice[0], "the line must name the manifest"
    assert "unparseable" in notice[0], "the line must say the manifest is unparseable"
    assert "skipped" in notice[0], "the line must say the guard was skipped"
    assert " ".join(_GUARD_COMMAND) in notice[0], "the line must name the skipped guard"


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


def test_a_parseable_manifest_writes_nothing_to_stderr(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The notice belongs to the stand-down alone, not to every guarded call."""
    launcher = _load_launcher()
    _write_manifest(project=tmp_path, body=_PARSEABLE_MANIFEST)
    _ = _record_invocations(launcher=launcher, monkeypatch=monkeypatch)

    assert _drive(launcher=launcher, project=tmp_path, monkeypatch=monkeypatch) == 0
    assert capsys.readouterr().err == ""


# --- the committed wiring, and the arms that must not cost a guard --------


def test_every_uv_launched_pretooluse_hook_command_is_routed_through_the_launcher() -> None:
    """An unwired launcher protects nothing, and a rewired guard protects less.

    The single equality carries both halves of the claim: the launcher sits in
    FRONT of each uv-started PreToolUse command, and what follows it is that
    command verbatim — so on a manifest that parses, each of these hook
    commands still reaches exactly the decision it reached before.
    """
    settings = json.loads(_SETTINGS_PATH.read_text(encoding="utf-8"))
    uv_launched = [
        hook["command"]
        for entry in settings["hooks"]["PreToolUse"]
        for hook in entry["hooks"]
        if _UV_LAUNCH_TOKEN in hook["command"]
    ]

    assert uv_launched == [f"{_LAUNCHER_PREFIX} {guard}" for guard in _UV_LAUNCHED_GUARDS]


def test_the_manifest_is_resolved_from_the_working_directory_without_a_project_dir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Claude Code sets the project directory, and a call without it still decides."""
    launcher = _load_launcher()
    _write_manifest(project=tmp_path, body=_CONFLICTED_MANIFEST)
    invocations = _record_invocations(launcher=launcher, monkeypatch=monkeypatch)
    monkeypatch.delenv(_PROJECT_DIR_ENV_VAR, raising=False)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sys, "argv", [str(_LAUNCHER_PATH), *_GUARD_COMMAND])

    assert launcher.main() == 0
    assert invocations == []
    assert _MANIFEST_NAME in capsys.readouterr().err


def test_a_manifest_that_cannot_be_read_still_launches_the_guard(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An absent manifest is not a conflicted one, so the guard must still decide.

    Standing a guard down on every manifest this launcher cannot read would
    turn an unrelated environment fault into a silent loss of enforcement, so
    this arm fails toward the guard rather than toward the allow.
    """
    launcher = _load_launcher()
    invocations = _record_invocations(launcher=launcher, monkeypatch=monkeypatch)

    assert _drive(launcher=launcher, project=tmp_path, monkeypatch=monkeypatch) == 0
    assert invocations == [_GUARD_COMMAND]


def test_a_launcher_that_cannot_start_the_guard_allows_the_call(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The hook boundary is fail-open: trouble here must never read as a deny."""
    launcher = _load_launcher()
    _write_manifest(project=tmp_path, body=_PARSEABLE_MANIFEST)

    def _explode(**_kwargs: object) -> subprocess.CompletedProcess[bytes]:
        raise OSError("the wrapped guard could not be started")

    monkeypatch.setattr(launcher.subprocess, "run", _explode)

    assert _drive(launcher=launcher, project=tmp_path, monkeypatch=monkeypatch) == 0
