"""Scenario 180 — a sandbox agent cannot remove the run's working tree.

`SPECIFICATION/scenarios.md` Scenario 180 and the `contracts.md` paragraph "The
run's working tree survives the agent." (ratified in v142) put a refusal
between an ACP agent and the four paths a factory run is built out of. This
module is that scenario's integration-tier binding: one case per Gherkin
scenario, plus its Background premise, each driven through the hook the way
Claude Code drives it — a PreToolUse payload on standard input, a deny payload
on standard output.

WHY THESE RUN AGAINST A REAL FILESYSTEM. The guard's whole job is to find paths
nobody told it about: the working-directory LINK is identified by what it
points at, and the clone lives OUTSIDE the sandbox root, so the protected set
is discovered from the layout rather than configured. A case that stubbed the
filesystem out would exercise the decision ladder and leave the discovery —
the half a reader cannot check by eye — untested. Each case therefore builds
the layout the 2026-10-15 incident ran in: `root/<name>` is a symbolic link to
a clone under a sibling `repos/` tree, with the Dispatcher's own materialized
siblings beside it.

WHY THE HOOK IS DRIVEN IN-PROCESS. `main()` is the whole process contract —
read stdin, write at most one deny payload, exit 0 — and no subprocess is
spawned (`check-tests-no-subprocess-spawn`). The production sandbox root is
`/workspace`; these cases redirect it through the guard's documented override
so a real layout can be built under `tmp_path`.

WHAT THIS BINDING CANNOT COVER, stated so its absence is not read as coverage.
Scenario 180's Background asserts that the agent's ACP adapter runtime OFFERS a
hook that runs before each shell command. That premise is a property of the
runtime, not of this repository, so it is exercised here as the structural fact
this repository controls: the guard is registered on the `Bash` PreToolUse
matcher in the committed `.claude/settings.json`. Whether a dispatched run's
agent actually reaches it is the work-item's HOST-CAPTURED assertion, proved on
the factory against a released build.
"""

from __future__ import annotations

import importlib.util
import io
import json
import sys
from pathlib import Path
from types import ModuleType

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_HOOKS_DIR = _REPO_ROOT / ".claude" / "hooks"
_GUARD_PATH = _HOOKS_DIR / "livespec_sandbox_path_guard.py"
_SETTINGS_PATH = _REPO_ROOT / ".claude" / "settings.json"
_MODULE_NAME = "livespec_sandbox_path_guard_scenario180"

_SANDBOX_ROOT_ENV_VAR = "LIVESPEC_SANDBOX_ROOT"
_PROJECT_DIR_ENV_VAR = "CLAUDE_PROJECT_DIR"
_REPOSITORY_NAME = "livespec-orchestrator-beads-fabro"


def _load_guard() -> ModuleType:
    """Load the hook by file location, asserting it exists first."""
    assert _GUARD_PATH.is_file()
    if str(_HOOKS_DIR) not in sys.path:
        sys.path.insert(0, str(_HOOKS_DIR))
    spec = importlib.util.spec_from_file_location(_MODULE_NAME, _GUARD_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[_MODULE_NAME] = module
    spec.loader.exec_module(module)
    return module


class _Sandbox:
    """The engine's layout: a root holding a link to a clone outside it."""

    def __init__(self, *, base: Path) -> None:
        self.root = base / "workspace"
        self.clone = base / "repos" / "thewoolleyman" / _REPOSITORY_NAME
        self.clone.mkdir(parents=True)
        (self.clone / ".git").mkdir()
        (self.clone / "src").mkdir()
        (self.clone / "build").mkdir()
        (self.clone / "README.md").write_text("sandbox fixture\n", encoding="utf-8")
        (self.clone / "tests").mkdir()
        (self.clone / "tests" / "conftest.py").write_text("", encoding="utf-8")
        self.root.mkdir()
        (self.root / ".livespec").mkdir()
        self.working_directory = self.root / _REPOSITORY_NAME
        self.working_directory.symlink_to(self.clone)
        self.scratch = base / "tmp" / "layout-sim"
        self.scratch.mkdir(parents=True)


def _verdict(
    *,
    sandbox: _Sandbox,
    command: str,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    working_directory: Path | None = None,
) -> str | None:
    """The refusal reason the hook emits for `command`, or None if it allows it."""
    guard = _load_guard()
    monkeypatch.setenv(_SANDBOX_ROOT_ENV_VAR, str(sandbox.root))
    monkeypatch.setenv(_PROJECT_DIR_ENV_VAR, str(sandbox.clone))
    monkeypatch.setattr(
        sys,
        "stdin",
        io.StringIO(
            json.dumps(
                {
                    "tool_name": "Bash",
                    "tool_input": {"command": command},
                    "cwd": str(working_directory or sandbox.clone),
                }
            )
        ),
    )

    assert guard.main() == 0

    emitted = capsys.readouterr().out
    if not emitted:
        return None
    hook_output = json.loads(emitted)["hookSpecificOutput"]
    assert hook_output["hookEventName"] == "PreToolUse"
    assert hook_output["permissionDecision"] == "deny"
    return str(hook_output["permissionDecisionReason"])


# ---------------------------------------------------------------------------
# Background: the adapter runtime offers a hook that runs before each command
# ---------------------------------------------------------------------------


def test_the_guard_is_registered_on_the_bash_pre_tool_use_matcher() -> None:
    """The premise this repository controls: the hook is wired where it must run.

    A guard that exists and is not registered refuses nothing, and nothing
    about its own behaviour would say so — which is why the registration is
    asserted rather than assumed.
    """
    settings = json.loads(_SETTINGS_PATH.read_text(encoding="utf-8"))

    commands = [
        hook["command"]
        for entry in settings["hooks"]["PreToolUse"]
        if entry["matcher"] == "Bash"
        for hook in entry["hooks"]
    ]

    assert any("livespec_sandbox_path_guard.py" in command for command in commands)


# ---------------------------------------------------------------------------
# Scenario: removing the sandbox root is refused before it runs
# ---------------------------------------------------------------------------


def test_removing_the_sandbox_root_is_refused_before_it_runs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    sandbox = _Sandbox(base=tmp_path)

    reason = _verdict(
        sandbox=sandbox,
        command=f"cd /tmp && rm -rf {sandbox.root} && mkdir -p {sandbox.root}",
        monkeypatch=monkeypatch,
        capsys=capsys,
    )

    assert reason is not None
    assert str(sandbox.root) in reason
    # The deny stops the whole tool call, so not even the leading `cd` runs —
    # which is what the clause's "before any part of it executes" buys, and
    # what the incident lost.
    assert sandbox.working_directory.is_symlink()
    assert sandbox.clone.is_dir()


# ---------------------------------------------------------------------------
# Scenario: a relative removal from a parent directory is refused
# ---------------------------------------------------------------------------


def test_a_relative_removal_from_a_parent_directory_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    sandbox = _Sandbox(base=tmp_path)

    reason = _verdict(
        sandbox=sandbox,
        command=f"cd {sandbox.root.parent} && rm -rf {sandbox.root.name}/",
        monkeypatch=monkeypatch,
        capsys=capsys,
    )

    assert reason is not None
    assert str(sandbox.root) in reason


# ---------------------------------------------------------------------------
# Scenario: removals under a scratch directory and inside the repository run
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("removed", ["scratch-directory", "file-in-the-repository"])
def test_a_scratch_or_in_tree_removal_is_not_refused(
    removed: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    sandbox = _Sandbox(base=tmp_path)
    command = (
        f"rm -rf {sandbox.scratch}"
        if removed == "scratch-directory"
        else f"rm -f {sandbox.clone}/tests/conftest.py"
    )

    assert (
        _verdict(sandbox=sandbox, command=command, monkeypatch=monkeypatch, capsys=capsys) is None
    )


# ---------------------------------------------------------------------------
# Scenario: a command that ALSO removes a protected path is refused
# ---------------------------------------------------------------------------


def test_a_mixed_removal_that_also_names_a_protected_path_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The scratch operand does not license the protected one beside it."""
    sandbox = _Sandbox(base=tmp_path)

    reason = _verdict(
        sandbox=sandbox,
        command=f"rm -rf {sandbox.scratch} {sandbox.root}",
        monkeypatch=monkeypatch,
        capsys=capsys,
    )

    assert reason is not None
    assert str(sandbox.root) in reason


def test_removing_the_clone_repository_directory_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The clone keeps its Git metadata for the engine's next checkpoint."""
    sandbox = _Sandbox(base=tmp_path)
    repository_directory = sandbox.clone / ".git"
    reason = _verdict(
        sandbox=sandbox,
        command=f"rm -rf {repository_directory}",
        monkeypatch=monkeypatch,
        capsys=capsys,
    )

    assert reason is not None
    assert str(repository_directory) in reason


def test_emptying_the_clone_top_level_is_refused_and_names_the_clone(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Scenario 197: `./*` reaches every non-hidden entry, not `.git`."""
    sandbox = _Sandbox(base=tmp_path)

    reason = _verdict(
        sandbox=sandbox,
        command=f"cd {sandbox.clone} && rm -rf ./*",
        monkeypatch=monkeypatch,
        capsys=capsys,
    )

    assert reason is not None
    assert str(sandbox.clone) in reason
    assert str(sandbox.clone / ".git") not in reason


def test_removals_and_moves_that_together_empty_the_clone_are_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Scenario 197 counts every executed segment against the submitted tree."""
    sandbox = _Sandbox(base=tmp_path)

    reason = _verdict(
        sandbox=sandbox,
        command=(
            f"rm -rf {sandbox.clone / 'build'} && "
            f"mv {sandbox.clone / 'src'} {sandbox.scratch} && "
            f"rm {sandbox.clone / 'README.md'} && "
            f"rm -rf {sandbox.clone / 'tests'}"
        ),
        monkeypatch=monkeypatch,
        capsys=capsys,
    )

    assert reason is not None
    assert str(sandbox.clone) in reason


def test_an_allowed_removal_does_not_exempt_clone_git_removal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    sandbox = _Sandbox(base=tmp_path)
    repository_directory = sandbox.clone / ".git"

    reason = _verdict(
        sandbox=sandbox,
        command=f"rm -rf {sandbox.clone / 'build'} {repository_directory}",
        monkeypatch=monkeypatch,
        capsys=capsys,
    )

    assert reason is not None
    assert str(repository_directory) in reason


def test_moving_the_clone_git_directory_away_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    sandbox = _Sandbox(base=tmp_path)
    repository_directory = sandbox.clone / ".git"

    reason = _verdict(
        sandbox=sandbox,
        command=f"mv {repository_directory} {sandbox.scratch / 'git-backup'}",
        monkeypatch=monkeypatch,
        capsys=capsys,
    )

    assert reason is not None
    assert str(repository_directory) in reason


def test_ordinary_in_tree_removals_are_allowed_while_an_entry_remains(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    sandbox = _Sandbox(base=tmp_path)

    for command, removed in (
        (f"rm -rf {sandbox.clone / 'build'}", sandbox.clone / "build"),
        (f"rm {sandbox.clone / 'README.md'}", sandbox.clone / "README.md"),
    ):
        assert (
            _verdict(sandbox=sandbox, command=command, monkeypatch=monkeypatch, capsys=capsys)
            is None
        )
        if removed.is_dir():
            removed.rmdir()
        else:
            removed.unlink()

    assert (sandbox.clone / "src").is_dir()


def test_removing_a_file_inside_clone_git_is_allowed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    sandbox = _Sandbox(base=tmp_path)
    lock = sandbox.clone / ".git" / "index.lock"
    lock.write_text("", encoding="utf-8")

    assert (
        _verdict(
            sandbox=sandbox,
            command=f"rm -f {lock}",
            monkeypatch=monkeypatch,
            capsys=capsys,
        )
        is None
    )


# ---------------------------------------------------------------------------
# Scenario: a protected path mentioned only as data is not refused
# ---------------------------------------------------------------------------


def test_a_protected_path_mentioned_only_as_data_is_not_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """An `echo` argument and a here-document body are both file data."""
    sandbox = _Sandbox(base=tmp_path)
    echoed = f'echo "rm -rf {sandbox.root}"'
    documented = (
        f"cat > {sandbox.scratch}/sim.sh <<'EOF'\n"
        f"cd /tmp && rm -rf {sandbox.root} && mkdir -p {sandbox.root}\n"
        "EOF"
    )

    assert _verdict(sandbox=sandbox, command=echoed, monkeypatch=monkeypatch, capsys=capsys) is None
    assert (
        _verdict(sandbox=sandbox, command=documented, monkeypatch=monkeypatch, capsys=capsys)
        is None
    )
