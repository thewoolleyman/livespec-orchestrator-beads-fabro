"""The recovery-routing decisions a healthy drain wave cannot reach.

`test_dispatcher_recovery_routing_resume.py` drives the whole first scenario of
185 through a real wave, which is the right tier for the claim that scenario
makes. It reaches exactly one route per item, though, so the arms below — a
release a LATER dispatch superseded, a released item whose resume is refused, and
an item routing never measured at all — need their own cases.

WHY THE SUPERSEDED RELEASE IS THE LOAD-BEARING CASE HERE. "An item is *released
for recovery* when its LATEST journaled dispatch ended in" one of three releases.
A lifetime reading passes every other case in this file and in its sibling: an
item released once and re-dispatched still carries that release row forever, so
the reading has to be about the newest dispatch rather than about the row's
existence. The fixture therefore records the release and THEN a second launch,
which is the only shape the two readings disagree on.
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any, ClassVar

import pytest

# Import order is load-bearing; see the sibling module's own note.
from livespec_orchestrator_beads_fabro.commands import (
    _dispatcher_admission as _admission,
)
from livespec_orchestrator_beads_fabro.commands import (
    _dispatcher_recovery_launch as launch,
)
from livespec_orchestrator_beads_fabro.commands import (
    _dispatcher_recovery_routing as routing,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandResult
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import (
    JournalFile,
    ShellCommandRunner,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_recovery_release import (
    released_for_recovery,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_recovery_routes import (
    ROUTE_FRESH,
    RecoveryResume,
    RecoveryRoute,
)
from livespec_orchestrator_beads_fabro.types import WorkItem

_ = _admission

_ITEM_ID = "bd-ib-qgcpoc"
_RUN = "01M509HNX5KGKSRV04VQEYVWH6"
_DISPATCH = "a7395318d0c945589105940e7936139f"
_LATER_DISPATCH = "b7395318d0c945589105940e7936139f"


class _Shell:
    """A scripted subprocess seam; see the sibling module for why state is class-level."""

    answers: ClassVar[dict[str, CommandResult]] = {}

    def run(
        self,
        *,
        argv: list[str],
        cwd: Path,
        timeout_seconds: float,
        env: dict[str, str] | None = None,
        stdin: int | None = None,
    ) -> CommandResult:
        _ = cwd, timeout_seconds, env, stdin
        joined = " ".join(argv)
        for needle, result in _Shell.answers.items():
            if needle in joined:
                return result
        return CommandResult(exit_code=0, stdout="", stderr="")


def _work_item() -> WorkItem:
    return WorkItem(
        id=_ITEM_ID,
        type="bug",
        status="ready",
        title="A released item whose resume cannot be measured",
        description="",
        origin="freeform",
        gap_id=None,
        rank="a0",
        assignee=None,
        depends_on=(),
        captured_at="2026-10-17T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
        admission_policy="auto",
        acceptance_policy="ai-only",
    )


def _journal(*, tmp_path: Path, records: Sequence[dict[str, object]]) -> JournalFile:
    journal = JournalFile(path=tmp_path / "fabro-dispatch-journal.jsonl")
    _ = journal.path.write_text(
        "".join(f"{json.dumps(record)}\n" for record in records), encoding="utf-8"
    )
    return journal


def _released_history() -> tuple[dict[str, object], ...]:
    """One dispatch of the item that ended in a first-stall release."""
    return (
        {"stage": "dispatch-id", "work_item_id": _ITEM_ID, "dispatch_id": _DISPATCH},
        {"stage": "fabro-run", "work_item_id": _ITEM_ID, "run_id": _RUN},
        {"stage": "stall-cancel-release", "work_item_id": _ITEM_ID, "status": "ready"},
    )


def _args(*, repo: Path, journal: JournalFile) -> argparse.Namespace:
    return argparse.Namespace(
        repo=str(repo),
        journal=str(journal.path),
        workflow_name="implement-work-item",
        fabro_bin="/usr/local/bin/fabro",
    )


def _rows(*, journal: JournalFile, stage: str) -> tuple[dict[str, Any], ...]:
    written = (
        json.loads(line) for line in journal.path.read_text(encoding="utf-8").splitlines() if line
    )
    return tuple(record for record in written if record.get("stage") == stage)


def test_a_release_a_later_dispatch_superseded_is_not_a_release() -> None:
    """A release row plus a NEWER launch row reads as an ordinary dispatch.

    The positive control sits beside it on the same history, because a reading
    that answered False for everything would satisfy the superseded case exactly
    as well as a correct one does.
    """
    released = _released_history()
    assert released_for_recovery(records=released, work_item_id=_ITEM_ID) is True
    assert (
        released_for_recovery(
            records=(
                *released,
                {
                    "stage": "dispatch-id",
                    "work_item_id": _ITEM_ID,
                    "dispatch_id": _LATER_DISPATCH,
                },
            ),
            work_item_id=_ITEM_ID,
        )
        is False
    )


def test_another_items_release_does_not_release_this_one() -> None:
    """The journal spans every item the repository dispatches, so rows are attributed."""
    assert released_for_recovery(records=_released_history(), work_item_id="bd-ib-other") is False


def test_a_released_item_whose_forge_cannot_be_asked_is_routed_fresh(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A refused resume falls through to a plain dispatch and journals no resume.

    The forge listing fails, which is the resume's first measurement, so the
    ladder refuses and there is no anchor to act on. What this case pins is that
    routing does NOT journal a `resume` record it cannot honour: a record written
    there would link the earlier run's identifiers to a dispatch that started
    from `start` on the default branch, and the acceptance pass would then grade
    this run's merge on the earlier run's proof.
    """
    journal = _journal(tmp_path=tmp_path, records=_released_history())
    _Shell.answers = {"gh pr list": CommandResult(exit_code=1, stdout="", stderr="boom")}
    monkeypatch.setattr(ShellCommandRunner, "run", _Shell.run)

    routed = routing.route_recovery(
        args=_args(repo=tmp_path, journal=journal),
        repo=tmp_path,
        candidates=[_work_item()],
        journal=journal,
    )

    assert routed.route_for(work_item_id=_ITEM_ID) == RecoveryRoute(
        work_item_id=_ITEM_ID, route=ROUTE_FRESH
    )
    assert _rows(journal=journal, stage="resume") == ()
    # A `fresh` item IS reclaimed for: clearing the dead run's branch is what
    # lets the new run's `publish_draft` push a plain fast-forward.
    assert routed.reclaims(work_item_id=_ITEM_ID) is True


def test_an_item_routing_never_measured_dispatches_and_reclaims_as_before() -> None:
    """A row routing never saw — a marked rework re-admission — is an ordinary dispatch.

    `route_for` answers `None` rather than synthesizing a `fresh` route, because
    "routing never measured this" and "routing decided fresh" are different
    facts; both launch plainly, which is what these two assertions pin.
    """
    empty = routing.RecoveryRouting(routes=())

    assert empty.route_for(work_item_id=_ITEM_ID) is None
    assert empty.reclaims(work_item_id=_ITEM_ID) is True


def _pins(*, seen: list[str]) -> launch.LaunchPins:
    """Pins that record which of the two was applied, and apply nothing else."""

    def _factory(**kwargs: object) -> argparse.Namespace:
        seen.append("factory")
        pinned = kwargs["args"]
        assert isinstance(pinned, argparse.Namespace)
        return pinned

    def _workflow(**kwargs: object) -> argparse.Namespace:
        seen.append("workflow")
        pinned = kwargs["args"]
        assert isinstance(pinned, argparse.Namespace)
        return pinned

    return launch.LaunchPins(factory=_factory, workflow=_workflow)


def test_a_plain_route_takes_both_pins_and_carries_no_resume_state() -> None:
    """Without a route, the launch is byte-for-byte the pre-recovery one."""
    seen: list[str] = []
    args = argparse.Namespace(workflow_name="implement-work-item")

    launched = launch.recovery_launch_args(
        args=args,
        repo=Path("/repo"),
        work_item_id=_ITEM_ID,
        route=None,
        pins=_pins(seen=seen),
    )

    assert seen == ["factory", "workflow"]
    assert getattr(launched, "resume_head", None) is None


def test_a_resume_route_skips_the_workflow_pin_and_keeps_the_requested_name() -> None:
    """The pin PERSISTS what it resolves, so a resume must not reach it.

    `resolve_dispatch_workflow_name` calls `record_dispatch_workflow`, and the
    resume clause forbids writing the item's `dispatch_workflow` metadata. The
    second assertion is the degradation for a journal written before the dispatch
    record carried a workflow name: whatever the invocation asked for stands,
    which leaves the ordinary variant precedence to resolve the item's own pin.
    """
    seen: list[str] = []
    args = argparse.Namespace(workflow_name="implement-work-item")

    launched = launch.recovery_launch_args(
        args=args,
        repo=Path("/repo"),
        work_item_id=_ITEM_ID,
        route=RecoveryRoute(
            work_item_id=_ITEM_ID,
            route="resume",
            resume=RecoveryResume(
                entry_node="proof_capture",
                head="deadbeef",
                pull_request=3001,
                earlier_run_ids=(_RUN,),
                source="watchdog-stall-cancel-record",
                workflow_name=None,
            ),
        ),
        pins=_pins(seen=seen),
    )

    assert seen == ["factory"]
    assert launched.workflow_name == "implement-work-item"
    assert getattr(launched, "resume_entry_node", None) == "proof_capture"
    assert getattr(launched, "resume_head", None) == "deadbeef"
