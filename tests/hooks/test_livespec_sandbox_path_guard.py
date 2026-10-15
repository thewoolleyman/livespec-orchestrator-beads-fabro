"""Coverage for the sandbox path guard — the PreToolUse hook Scenario 180 names.

The policy beside this file decides; this hook is the only place that READS the
sandbox and emits a verdict. So these cases build a REAL sandbox layout on disk
— a root, a clone outside it, and the working-directory link between them —
and drive `main()` in-process against it. A test that stubbed the filesystem
out would leave exactly the half a reader cannot check by eye unexercised: that
the link is found by what it points at, that an unreadable root yields no
protection rather than a crash, and that the clone outside the root is defended
at all.

THE REFUSAL IS THE POINT, AND SO IS ITS TIMING. A PreToolUse deny stops the
whole tool call, so the first segment of `cd /tmp && rm -rf /workspace && mkdir
-p /workspace` never runs either — which is what the governing clause means by
"before any part of it executes", and why the incident case below asserts that
the working directory still exists after the hook has spoken.

FAIL-OPEN AT THE BOUNDARY, deliberately and asymmetrically. The decision is
exact, but a crashing PreToolUse hook wedges every Bash call in the session, so
malformed input, an unmodelled payload shape, an unreadable sandbox root and a
bug inside the guard all pass through silently at exit 0.

`.claude/hooks/` is not an importable package and the guard imports its sibling
policy the way a script does, so that directory goes on `sys.path` before the
module is loaded by file location. The load happens INSIDE each test body and
the first assertion is that the file exists, so a Red commit fails on a genuine
assertion rather than at collection time.
"""

from __future__ import annotations

import importlib.util
import io
import json
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_HOOKS_DIR = _REPO_ROOT / ".claude" / "hooks"
_GUARD_PATH = _HOOKS_DIR / "livespec_sandbox_path_guard.py"
_MODULE_NAME = "livespec_sandbox_path_guard_under_test"

_SANDBOX_ROOT_ENV_VAR = "LIVESPEC_SANDBOX_ROOT"
_PROJECT_DIR_ENV_VAR = "CLAUDE_PROJECT_DIR"
_LINK_NAME = "livespec-orchestrator-beads-fabro"


def _load_guard() -> ModuleType:
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


class _Layout:
    """A sandbox the way the engine builds one, on a real filesystem.

    `root` holds the working-directory LINK and the Dispatcher's own
    materialized siblings; `clone` sits outside `root` entirely, which is the
    layout the 2026-10-15 incident ran in and the reason a protected set keyed
    on "inside the root" would not have saved it.
    """

    def __init__(self, *, base: Path) -> None:
        self.root = base / "workspace"
        self.clone = base / "repos" / "thewoolleyman" / _LINK_NAME
        self.clone.mkdir(parents=True)
        self.root.mkdir()
        (self.root / ".livespec").mkdir()
        self.link = self.root / _LINK_NAME
        self.link.symlink_to(self.clone)


def _payload(*, command: str, cwd: str | None) -> str:
    body: dict[str, Any] = {"tool_name": "Bash", "tool_input": {"command": command}}
    if cwd is not None:
        body["cwd"] = cwd
    return json.dumps(body)


def _run_guard(
    *,
    guard: ModuleType,
    payload: str | Any,
    monkeypatch: pytest.MonkeyPatch,
    sandbox_root: str | None,
    project_dir: str | None,
) -> None:
    """Drive `main()` over `payload`, asserting it always reports exit 0."""
    monkeypatch.delenv(_SANDBOX_ROOT_ENV_VAR, raising=False)
    monkeypatch.delenv(_PROJECT_DIR_ENV_VAR, raising=False)
    if sandbox_root is not None:
        monkeypatch.setenv(_SANDBOX_ROOT_ENV_VAR, sandbox_root)
    if project_dir is not None:
        monkeypatch.setenv(_PROJECT_DIR_ENV_VAR, project_dir)
    monkeypatch.setattr(sys, "stdin", io.StringIO(payload) if isinstance(payload, str) else payload)

    assert guard.main() == 0


def _refusal_reason(*, captured: str) -> str:
    emitted = json.loads(captured)
    hook_output = emitted["hookSpecificOutput"]
    assert hook_output["hookEventName"] == "PreToolUse"
    assert hook_output["permissionDecision"] == "deny"
    return str(hook_output["permissionDecisionReason"])


class _ExplodingStdin:
    """A `sys.stdin` stand-in whose `read()` raises a non-JSON error."""

    def read(self) -> str:
        raise RuntimeError("stdin went away")


# ---------------------------------------------------------------------------
# The measured incident, refused
# ---------------------------------------------------------------------------


def test_the_incident_command_is_refused_and_the_working_directory_survives(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Assertion 2, written as the command run 01M4YJGC55V86C9V1X07QG3Y2H ran.

    The removal is the SECOND segment, so a guard reading only a command's
    leading word would have let this through — which is the shape the incident
    took. The surviving working directory is asserted because the clause's
    "before any part of it executes" is what a deny decision buys: the `cd`
    does not run either.
    """
    layout = _Layout(base=tmp_path)
    guard = _load_guard()

    _run_guard(
        guard=guard,
        payload=_payload(
            command=f"cd /tmp && rm -rf {layout.root} && mkdir -p {layout.root}",
            cwd=str(layout.clone),
        ),
        monkeypatch=monkeypatch,
        sandbox_root=str(layout.root),
        project_dir=str(layout.clone),
    )

    reason = _refusal_reason(captured=capsys.readouterr().out)
    assert str(layout.root) in reason
    assert "Do NOT retry" in reason
    assert layout.link.is_symlink()
    assert layout.clone.is_dir()
    assert layout.root.is_dir()


@pytest.mark.parametrize("target", ["link", "clone"])
def test_removing_the_working_directory_link_or_the_clone_is_refused(
    target: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The link is found by what it POINTS AT, and the clone sits outside the root."""
    layout = _Layout(base=tmp_path)
    protected = str(layout.link if target == "link" else layout.clone)
    guard = _load_guard()

    _run_guard(
        guard=guard,
        payload=_payload(command=f"rm -rf {protected}", cwd=str(layout.clone)),
        monkeypatch=monkeypatch,
        sandbox_root=str(layout.root),
        project_dir=str(layout.clone),
    )

    assert protected in _refusal_reason(captured=capsys.readouterr().out)


def test_the_repository_is_taken_from_the_payload_when_no_project_dir_is_set(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """`CLAUDE_PROJECT_DIR` is the stable repository, but the payload can stand in."""
    layout = _Layout(base=tmp_path)
    guard = _load_guard()

    _run_guard(
        guard=guard,
        payload=_payload(command=f"rm -rf {layout.root}", cwd=str(layout.clone)),
        monkeypatch=monkeypatch,
        sandbox_root=str(layout.root),
        project_dir=None,
    )

    assert str(layout.root) in _refusal_reason(captured=capsys.readouterr().out)


# ---------------------------------------------------------------------------
# What is NOT refused
# ---------------------------------------------------------------------------


def test_a_removal_under_a_scratch_directory_passes_through(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    layout = _Layout(base=tmp_path)
    guard = _load_guard()

    _run_guard(
        guard=guard,
        payload=_payload(command="rm -rf /tmp/layout-sim", cwd=str(layout.clone)),
        monkeypatch=monkeypatch,
        sandbox_root=str(layout.root),
        project_dir=str(layout.clone),
    )

    assert capsys.readouterr().out == ""


def test_an_unreadable_sandbox_root_protects_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Off-sandbox there is no root to list, so there is no link and no refusal.

    This is the arm that keeps the guard inert in a developer's own checkout,
    where the governing clause does not reach.
    """
    layout = _Layout(base=tmp_path)
    guard = _load_guard()

    _run_guard(
        guard=guard,
        payload=_payload(command=f"rm -rf {layout.clone}", cwd=str(layout.clone)),
        monkeypatch=monkeypatch,
        sandbox_root=str(tmp_path / "no-such-root"),
        project_dir=str(layout.clone),
    )

    assert capsys.readouterr().out == ""


def test_the_default_sandbox_root_is_the_engines_own_mount(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """With no override the guard reads `/workspace`, which is the production path.

    The case asserts the DEFAULT is consulted rather than that a refusal
    follows: this test process is not a factory sandbox, so whatever
    `/workspace` happens to hold here must not protect a temporary clone.
    """
    layout = _Layout(base=tmp_path)
    guard = _load_guard()

    assert guard.DEFAULT_SANDBOX_ROOT == "/workspace"

    _run_guard(
        guard=guard,
        payload=_payload(command=f"rm -rf {layout.clone}", cwd=str(layout.clone)),
        monkeypatch=monkeypatch,
        sandbox_root=None,
        project_dir=str(layout.clone),
    )

    assert capsys.readouterr().out == ""


def test_a_payload_naming_no_repository_at_all_protects_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """An unmodelled payload shape must not be read as the filesystem root."""
    layout = _Layout(base=tmp_path)
    guard = _load_guard()

    _run_guard(
        guard=guard,
        payload=_payload(command=f"rm -rf {layout.root}", cwd=None),
        monkeypatch=monkeypatch,
        sandbox_root=str(layout.root),
        project_dir=None,
    )

    assert capsys.readouterr().out == ""


# ---------------------------------------------------------------------------
# The stdin protocol, and the fail-open boundary
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "payload",
    [
        "",
        "   \n  ",
        "{not json at all",
        json.dumps({"tool_name": "Read", "tool_input": {"command": "rm -rf /workspace"}}),
        json.dumps({"tool_name": "Bash"}),
        json.dumps({"tool_name": "Bash", "tool_input": {"command": ""}}),
    ],
)
def test_an_unusable_payload_passes_through_silently(
    payload: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    layout = _Layout(base=tmp_path)
    guard = _load_guard()

    _run_guard(
        guard=guard,
        payload=payload,
        monkeypatch=monkeypatch,
        sandbox_root=str(layout.root),
        project_dir=str(layout.clone),
    )

    assert capsys.readouterr().out == ""


def test_an_unexpected_runtime_error_fails_open(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A bug inside the guard must never wedge every Bash call in the session."""
    layout = _Layout(base=tmp_path)
    guard = _load_guard()

    _run_guard(
        guard=guard,
        payload=_ExplodingStdin(),
        monkeypatch=monkeypatch,
        sandbox_root=str(layout.root),
        project_dir=str(layout.clone),
    )

    assert capsys.readouterr().out == ""
