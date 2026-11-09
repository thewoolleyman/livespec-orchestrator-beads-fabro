"""What an incident's normal repayment dispatch tells its agent about the marker.

`SPECIFICATION/contracts.md` section "Expedited incident lifecycle", scenario
"a successful incident merge reenters normal factory on the same item": the
repayment pull request removes the `EXPEDITED_INCIDENT_RESPONSE flag: <item-id>`
marker. The completion path refuses closure while master carries it, so a
repayment run that was never told to remove it merges a marker that blocks
completion (measured 2026-11-09, livespec-dev-tooling-e62ss6, PR #3883).

The goal a repayment dispatch carries names the marker, every path that still
carries it, and states that the pull request must leave no file carrying it.
The final case reads the one call site that renders a dispatch's brief and
asserts, structurally, that it passes the section through.
"""

from __future__ import annotations

import ast
import importlib
from pathlib import Path
from typing import Any

import pytest
from livespec_orchestrator_beads_fabro._incident_authority_types import (
    IncidentAttempt,
    IncidentReading,
)
from livespec_orchestrator_beads_fabro.commands import _dispatcher_goal as goal
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine_types import CommandResult
from livespec_orchestrator_beads_fabro.effects._incident_completion_reader import (
    IncidentStanding,
)
from livespec_orchestrator_beads_fabro.types import WorkItem

_MODULE_NAME = "livespec_orchestrator_beads_fabro.commands._dispatcher_goal_repayment"
_COMMANDS = Path(".claude-plugin/scripts/livespec_orchestrator_beads_fabro/commands")
_MODULE_PATH = _COMMANDS / "_dispatcher_goal_repayment.py"
_LOOP_PATH = _COMMANDS / "_dispatcher_loop.py"

_ITEM_ID = "bd-ib-repay1"
_MARKER = f"EXPEDITED_INCIDENT_RESPONSE flag: {_ITEM_ID}"
_REPO = Path("/data/projects/livespec-orchestrator-beads-fabro")
_PATHS = ("src/app.py", "tests/test_app.py")


def _module() -> Any:
    """The module under test, reached only after its path is established.

    The import is inside the body and the path assertion precedes it, so Red is a
    genuine assertion about an absent file rather than a collection error.
    """
    assert _MODULE_PATH.is_file()
    return importlib.import_module(_MODULE_NAME)


def _attempt(*, phase: str) -> IncidentAttempt:
    return IncidentAttempt(
        repository="thewoolleyman/example",
        item_id=_ITEM_ID,
        attempt_id="attempt-1",
        phase=phase,
        operation_id="operation-1",
        generation=3,
        owner="operator:alice",
        base="a" * 40,
        head="b" * 40,
        pr_number=7,
        landed_commits=("c" * 40,),
        landed_trees=("d" * 40,),
        original_paths=("src/app.py",),
        deferred_work=("normal-factory-proof",),
        repayment_required=True,
    )


def _standing(*, kind: str, phase: str = "repayment-ready") -> IncidentStanding:
    attempt = _attempt(phase=phase)
    identities = {"committed_token_id": "t", "current_token_id": "t"}
    reading = IncidentReading(attempt=attempt, is_current=True, **identities)
    return IncidentStanding(
        item_id=_ITEM_ID,
        kind=kind,  # type: ignore[arg-type]
        repository="thewoolleyman/example",
        history=() if kind == "normal" else (attempt,),
        outstanding=(),
        reading=None if kind in ("normal", "unreadable") else reading,
    )


def _work_item() -> WorkItem:
    return WorkItem(
        id=_ITEM_ID,
        type="bug",
        status="ready",
        title="An incident's normal repayment",
        description="Repay the incident.",
        origin="freeform",
        gap_id=None,
        rank="a0",
        assignee=None,
        depends_on=(),
        captured_at="2026-11-09T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
        admission_policy="auto",
        acceptance_policy="ai-only",
    )


class _Runner:
    """Answers the fetch and the grep separately and records every argv."""

    def __init__(self, *, fetch: CommandResult, grep: CommandResult) -> None:
        self.fetch = fetch
        self.grep = grep
        self.argvs: list[list[str]] = []

    def run(self, *, argv: list[str], cwd: Path, timeout_seconds: float, **_: Any) -> CommandResult:
        assert (cwd, timeout_seconds > 0) == (_REPO, True)
        self.argvs.append(argv)
        return self.fetch if argv[1] == "fetch" else self.grep


def _ok(stdout: str = "") -> CommandResult:
    return CommandResult(exit_code=0, stdout=stdout, stderr="")


def _section(*, marker_paths: tuple[str, ...] | None) -> str:
    return _module().repayment_goal_section(
        attempt=_attempt(phase="repayment-ready"), marker_paths=marker_paths
    )


def test_the_section_names_the_marker_every_carrying_path_and_the_no_file_obligation() -> None:
    section = _section(marker_paths=_PATHS)

    assert f"`{_MARKER}`" in section
    assert all(f"- {path}\n" in section for path in _PATHS)
    assert f"MUST leave no file carrying `{_MARKER}`" in section


def test_a_scan_that_found_nothing_still_states_the_no_file_obligation() -> None:
    section = _section(marker_paths=())

    assert "no path" in section.lower()
    assert f"MUST leave no file carrying `{_MARKER}`" in section


def test_an_unreadable_scan_tells_the_agent_to_find_the_paths_itself() -> None:
    section = _section(marker_paths=None)

    assert "could not be read" in section
    assert f"git grep -l -F -e '{_MARKER}'" in section
    assert f"MUST leave no file carrying `{_MARKER}`" in section


def test_render_goal_carries_the_repayment_section_only_when_one_is_handed_in() -> None:
    section = _section(marker_paths=_PATHS)

    with_section = goal.render_goal(
        item=_work_item(), repo=_REPO, branch="feat/x", repayment=section
    )
    without = goal.render_goal(item=_work_item(), repo=_REPO, branch="feat/x")

    assert section in with_section
    assert _MARKER not in without


def test_the_marker_scan_reads_the_freshly_fetched_default_branch() -> None:
    runner = _Runner(
        fetch=_ok(),
        grep=_ok(
            "refs/remotes/origin/main:src/app.py\nrefs/remotes/origin/main:tests/test_app.py\n"
        ),
    )

    found = _module().marker_paths_on_default_branch(
        runner=runner, repo=_REPO, marker=_MARKER, default_branch="main"
    )

    assert found == _PATHS
    assert runner.argvs[0][:2] == ["git", "fetch"]
    assert "+refs/heads/main:refs/remotes/origin/main" in runner.argvs[0]
    assert runner.argvs[1][:2] == ["git", "grep"]
    assert _MARKER in runner.argvs[1]
    assert "refs/remotes/origin/main" in runner.argvs[1]


@pytest.mark.parametrize(
    ("fetch", "grep", "default_branch", "expected"),
    [
        (_ok(), CommandResult(exit_code=1, stdout="", stderr=""), "main", ()),
        (_ok(), CommandResult(exit_code=2, stdout="", stderr="boom"), "main", None),
        (_ok(), CommandResult(exit_code=1, stdout="", stderr="warning"), "main", None),
        (CommandResult(exit_code=128, stdout="", stderr="no origin"), _ok("x"), "main", None),
        (_ok(), _ok(), None, None),
    ],
)
def test_the_marker_scan_is_unread_rather_than_empty_when_it_cannot_be_taken(
    fetch: CommandResult, grep: CommandResult, default_branch: str | None, expected: object
) -> None:
    runner = _Runner(fetch=fetch, grep=grep)

    found = _module().marker_paths_on_default_branch(
        runner=runner, repo=_REPO, marker=_MARKER, default_branch=default_branch
    )

    assert found == expected


@pytest.mark.parametrize(
    ("kind", "phase"),
    [
        ("normal", "repayment-ready"),
        ("unreadable", "repayment-ready"),
        ("incident", "repair"),
        ("incident", "master-observation"),
        ("incident", "closed"),
    ],
)
def test_only_an_incident_in_a_repayment_phase_gets_a_section(
    monkeypatch: pytest.MonkeyPatch, kind: str, phase: str
) -> None:
    module = _module()
    monkeypatch.setattr(
        module, "incident_standing_for", lambda **_: _standing(kind=kind, phase=phase)
    )
    monkeypatch.setattr(module, "store_config", lambda **_: object())

    assert module.repayment_goal_for(repo=_REPO, item_id=_ITEM_ID) == ""


@pytest.mark.parametrize("phase", ["repayment-ready", "repayment-active"])
def test_a_repayment_dispatch_is_briefed_with_the_paths_found_on_the_default_branch(
    monkeypatch: pytest.MonkeyPatch, phase: str
) -> None:
    module = _module()
    runner = _Runner(fetch=_ok(), grep=_ok("refs/remotes/origin/main:src/app.py\n"))
    monkeypatch.setattr(
        module, "incident_standing_for", lambda **_: _standing(kind="incident", phase=phase)
    )
    monkeypatch.setattr(module, "store_config", lambda **_: object())
    monkeypatch.setattr(module, "resolve_default_branch", lambda **_: "main")

    section = module.repayment_goal_for(repo=_REPO, item_id=_ITEM_ID, runner=runner)

    assert f"`{_MARKER}`" in section
    assert "- src/app.py\n" in section
    assert f"MUST leave no file carrying `{_MARKER}`" in section


def test_the_default_runner_is_the_production_shell_runner(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _module()
    seen: list[object] = []
    monkeypatch.setattr(module, "incident_standing_for", lambda **_: _standing(kind="incident"))
    monkeypatch.setattr(module, "store_config", lambda **_: object())
    monkeypatch.setattr(module, "resolve_default_branch", lambda **kw: seen.append(kw["runner"]))

    section = module.repayment_goal_for(repo=_REPO, item_id=_ITEM_ID)

    assert type(seen[0]).__name__ == "ShellCommandRunner"
    assert "could not be read" in section


def test_the_dispatch_path_passes_the_repayment_section_to_the_one_render_goal_call() -> None:
    """Read from the parsed source, so the answer is not a pattern that happened to fit."""
    tree = ast.parse(_LOOP_PATH.read_text(encoding="utf-8"))
    calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "render_goal"
    ]
    assert len(calls) == 1
    keywords = {keyword.arg: keyword.value for keyword in calls[0].keywords}
    value = keywords["repayment"]
    assert isinstance(value, ast.Call)
    assert isinstance(value.func, ast.Name)
    assert value.func.id == "repayment_goal_for"
