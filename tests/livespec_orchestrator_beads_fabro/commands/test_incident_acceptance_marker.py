"""A repayment pull request that still carries the incident marker is not accepted.

`SPECIFICATION/contracts.md` section "Expedited incident lifecycle", scenario
"a successful incident merge reenters normal factory on the same item": the
repayment pull request removes the `EXPEDITED_INCIDENT_RESPONSE flag: <item-id>`
marker. A repayment run that left it in place (measured 2026-11-09,
livespec-dev-tooling#3883) is graded at acceptance with the unremoved marker
named as an outstanding obligation, path by path, so the hold on the item says
what is left rather than only that final proof is owed.

The observation is the repayment PR's own head, read through the forge, and only
for the PR the chain binds as the current repayment carrier.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from livespec_orchestrator_beads_fabro._incident_authority_types import (
    IncidentAttempt,
    IncidentReading,
)
from livespec_orchestrator_beads_fabro.commands import _dispatcher_incident_closure as closure
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine_types import CommandResult
from livespec_orchestrator_beads_fabro.effects._incident_completion_reader import (
    IncidentStanding,
)

_ITEM_ID = "bd-ib-repay2"
_MARKER = f"EXPEDITED_INCIDENT_RESPONSE flag: {_ITEM_ID}"
_REPOSITORY = "thewoolleyman/example"
_REPAIR_PR = 7
_REPAYMENT_PR = 12
_HEAD = "f" * 40
_REPO = Path("/data/projects/example")


def _attempt(*, phase: str, pr_number: int) -> IncidentAttempt:
    return IncidentAttempt(
        repository=_REPOSITORY,
        item_id=_ITEM_ID,
        attempt_id="attempt-1",
        phase=phase,
        operation_id=f"attempt-1#{phase}",
        generation=1,
        owner="operator:alice",
        base="a" * 40,
        head="b" * 40,
        pr_number=pr_number,
        landed_commits=("c" * 40,),
        landed_trees=("d" * 40,),
        original_paths=("src/app.py",),
        deferred_work=(),
        repayment_required=True,
    )


def _standing(*, kind: str = "incident") -> IncidentStanding:
    history = (
        _attempt(phase="master-observation", pr_number=_REPAIR_PR),
        _attempt(phase="repayment-acceptance", pr_number=_REPAYMENT_PR),
    )
    identities = {"committed_token_id": "t", "current_token_id": "t"}
    reading = IncidentReading(attempt=history[-1], is_current=True, **identities)
    return IncidentStanding(
        item_id=_ITEM_ID,
        kind=kind,  # type: ignore[arg-type]
        repository=None if kind == "normal" else _REPOSITORY,
        history=() if kind == "normal" else history,
        outstanding=() if kind == "normal" else ("marker-removal-unobserved",),
        reading=None if kind == "normal" else reading,
    )


def _config(*, repo_root: Path | None = _REPO) -> Any:
    return SimpleNamespace(repo_root=repo_root)


class _Runner:
    """Answers the three forge and tree reads and records every argv."""

    def __init__(self, *, view: CommandResult, grep: CommandResult) -> None:
        self.view = view
        self.grep = grep
        self.argvs: list[list[str]] = []

    def run(self, *, argv: list[str], cwd: Path, timeout_seconds: float, **_: Any) -> CommandResult:
        assert (cwd, timeout_seconds > 0) == (_REPO, True)
        self.argvs.append(argv)
        if argv[0] == "gh":
            return self.view
        return self.grep if argv[1] == "grep" else CommandResult(exit_code=0, stdout="", stderr="")


class _Journal:
    def __init__(self) -> None:
        self.records: list[dict[str, object]] = []

    def append(self, *, record: dict[str, object]) -> None:
        self.records.append(record)


def _head_reply() -> CommandResult:
    return CommandResult(exit_code=0, stdout=f'{{"headRefOid": "{_HEAD}"}}', stderr="")


def _acceptance(
    monkeypatch: pytest.MonkeyPatch,
    *,
    runner: _Runner,
    merged_pr: int = _REPAYMENT_PR,
    kind: str = "incident",
) -> closure.IncidentAcceptance:
    assert "marker_paths" in closure.IncidentAcceptance.__dataclass_fields__
    monkeypatch.setattr(closure, "incident_standing_for", lambda **_: _standing(kind=kind))
    return closure.incident_acceptance_for(
        config=_config(),
        item_id=_ITEM_ID,
        merged_pr=merged_pr,
        runner=runner,  # type: ignore[arg-type]
    )


def _hold_outstanding(*, acceptance: closure.IncidentAcceptance) -> list[str]:
    journal = _Journal()
    assert closure.incident_holds(incident=acceptance, journal=journal, route="complete")  # type: ignore[arg-type]
    [record] = journal.records
    return [str(name) for name in record["outstanding"]]  # type: ignore[attr-defined]


def test_an_unremoved_marker_at_the_repayment_head_is_named_path_by_path_in_the_hold(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    grep = CommandResult(exit_code=0, stdout=f"{_HEAD}:src/app.py\n{_HEAD}:tests/t.py\n", stderr="")
    runner = _Runner(view=_head_reply(), grep=grep)

    acceptance = _acceptance(monkeypatch, runner=runner)
    outstanding = _hold_outstanding(acceptance=acceptance)

    assert acceptance.marker_paths == ("src/app.py", "tests/t.py")
    assert "marker-present:src/app.py" in outstanding
    assert "marker-present:tests/t.py" in outstanding
    assert runner.argvs[0][:3] == ["gh", "pr", "view"]
    assert str(_REPAYMENT_PR) in runner.argvs[0]
    assert _REPOSITORY in runner.argvs[0]
    assert _MARKER in runner.argvs[-1]
    assert _HEAD in runner.argvs[-1]


def test_a_repayment_head_without_the_marker_names_no_marker_obligation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runner = _Runner(view=_head_reply(), grep=CommandResult(exit_code=1, stdout="", stderr=""))

    acceptance = _acceptance(monkeypatch, runner=runner)
    outstanding = _hold_outstanding(acceptance=acceptance)

    assert acceptance.marker_paths == ()
    assert not [name for name in outstanding if name.startswith("marker-present:")]
    assert "marker-removal-unobserved" in outstanding


@pytest.mark.parametrize(
    "view",
    [
        CommandResult(exit_code=1, stdout="", stderr="no such pull request"),
        CommandResult(exit_code=0, stdout="not json", stderr=""),
        CommandResult(exit_code=0, stdout='{"headRefOid": 3}', stderr=""),
        CommandResult(exit_code=0, stdout='{"headRefOid": ""}', stderr=""),
    ],
)
def test_an_unreadable_head_leaves_the_marker_unobserved_rather_than_absent(
    monkeypatch: pytest.MonkeyPatch, view: CommandResult
) -> None:
    runner = _Runner(view=view, grep=CommandResult(exit_code=1, stdout="", stderr=""))

    acceptance = _acceptance(monkeypatch, runner=runner)

    assert acceptance.marker_paths is None
    assert "marker-removal-unobserved" in _hold_outstanding(acceptance=acceptance)
    assert all(argv[0] == "gh" for argv in runner.argvs)


def test_a_tree_that_cannot_be_searched_leaves_the_marker_unobserved(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runner = _Runner(view=_head_reply(), grep=CommandResult(exit_code=2, stdout="", stderr="boom"))

    acceptance = _acceptance(monkeypatch, runner=runner)

    assert acceptance.marker_paths is None


def test_only_the_current_repayment_carrier_is_read(monkeypatch: pytest.MonkeyPatch) -> None:
    runner = _Runner(view=_head_reply(), grep=CommandResult(exit_code=0, stdout="x:y", stderr=""))

    earlier = _acceptance(monkeypatch, runner=runner, merged_pr=_REPAIR_PR)

    assert not earlier.marker_paths
    assert runner.argvs == []


def test_a_normal_item_is_never_read(monkeypatch: pytest.MonkeyPatch) -> None:
    runner = _Runner(view=_head_reply(), grep=CommandResult(exit_code=0, stdout="x:y", stderr=""))

    normal = _acceptance(monkeypatch, runner=runner, kind="normal")

    assert not normal.marker_paths
    assert runner.argvs == []


def test_the_default_runner_is_the_production_shell_runner(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(closure, "incident_standing_for", lambda **_: _standing())
    seen: list[object] = []

    def record(**kwargs: Any) -> tuple[str, ...]:
        seen.append(kwargs["runner"])
        return ()

    monkeypatch.setattr(closure, "pr_head_marker_paths", record)

    acceptance = closure.incident_acceptance_for(
        config=_config(repo_root=tmp_path), item_id=_ITEM_ID, merged_pr=_REPAYMENT_PR
    )

    assert type(seen[0]).__name__ == "ShellCommandRunner"
    assert acceptance.marker_paths == ()


def test_a_caller_with_no_checkout_observes_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(closure, "incident_standing_for", lambda **_: _standing())

    acceptance = closure.incident_acceptance_for(
        config=_config(repo_root=None), item_id=_ITEM_ID, merged_pr=_REPAYMENT_PR
    )

    assert acceptance.marker_paths is None
