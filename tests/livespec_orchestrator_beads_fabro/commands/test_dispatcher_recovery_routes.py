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
from livespec_orchestrator_beads_fabro.commands._dispatcher_recovery_measurements import (
    MEASUREMENT_FORGE_PULL_REQUEST,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_recovery_preserved import (
    PRESERVED_SOURCE_EARLIER_PRESERVED_PUBLISH_REF,
    PRESERVED_SOURCE_PUBLISHED_HEAD,
    PRESERVED_SOURCE_TERMINAL_TREE,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_recovery_records import (
    PRESERVED_WORK_ABSENT,
    RECOVERY_ROUTE_STAGE,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_recovery_release import (
    released_for_recovery,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_recovery_routes import (
    ROUTE_FRESH,
    ROUTE_HELD,
    RecoveryLoss,
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
    """A scripted subprocess seam; see the sibling module for why state is class-level.

    An unscripted argv answers an empty exit 0 HERE, unlike the wave modules'
    seams, because two cases below are about reads that find NOTHING rather than
    reads that fail — and `calls` is what lets a read that must not have happened
    at all be asserted as an absence of its own.
    """

    answers: ClassVar[dict[str, CommandResult]] = {}
    calls: ClassVar[list[str]] = []

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
        _Shell.calls.append(joined)
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


def _route(*, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> routing.RecoveryRouting:
    """Route the one released candidate against whatever `_Shell` is scripted with."""
    journal = _journal(tmp_path=tmp_path, records=_released_history())
    _Shell.calls = []
    monkeypatch.setattr(ShellCommandRunner, "run", _Shell.run)
    return routing.route_recovery(
        args=_args(repo=tmp_path, journal=journal),
        repo=tmp_path,
        candidates=[_work_item()],
        journal=journal,
    )


def test_a_released_item_whose_forge_listing_fails_is_held_before_anything_else(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The FORGE measurement, named, and the reads below it never spent.

    `test_dispatcher_recovery_routing_unobservable.py` drives the factory read
    through a whole wave; this is the forge half, which fails one step earlier —
    and the claim it adds is that nothing BELOW the failed measurement is
    attempted, so a hold does not pay for origin round trips whose answers could
    not be used anyway.
    """
    _Shell.answers = {"gh pr list": CommandResult(exit_code=1, stdout="", stderr="boom")}

    routed = _route(tmp_path=tmp_path, monkeypatch=monkeypatch)
    route = routed.route_for(work_item_id=_ITEM_ID)

    assert route is not None
    assert route.route == ROUTE_HELD
    assert route.hold is not None
    assert [one.name for one in route.hold.measurements] == [MEASUREMENT_FORGE_PULL_REQUEST]
    assert [call for call in _Shell.calls if "ls-remote" in call] == []


def test_a_fallback_permitting_refusal_with_no_preserved_work_is_fresh_with_the_loss_recorded(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Every read answered, the branch carries no pull request, nothing was preserved.

    This is the one route that discards work, so it is the one that has to be
    earned: the refusal is fallback-permitting, every preserved-work source was
    asked, and each named nothing. The route carries that finding plus the loss
    it names, which together are the clause's "with that loss recorded"; the
    record the loss produces is covered by
    `test_dispatcher_recovery_fresh_loss_record.py`.
    """
    _Shell.answers = {"gh pr list": CommandResult(exit_code=0, stdout="[]", stderr="")}

    routed = _route(tmp_path=tmp_path, monkeypatch=monkeypatch)

    assert routed.route_for(work_item_id=_ITEM_ID) == RecoveryRoute(
        work_item_id=_ITEM_ID,
        route=ROUTE_FRESH,
        loss=RecoveryLoss(
            source_run_id=_RUN,
            sources_asked=(
                PRESERVED_SOURCE_TERMINAL_TREE,
                PRESERVED_SOURCE_PUBLISHED_HEAD,
                PRESERVED_SOURCE_EARLIER_PRESERVED_PUBLISH_REF,
            ),
        ),
        preserved_work=PRESERVED_WORK_ABSENT,
    )
    assert len([call for call in _Shell.calls if "ls-remote" in call]) == 3
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


def test_an_unmeasured_item_journals_no_route_at_all(tmp_path: Path) -> None:
    """A row routing never saw records nothing, rather than a route nobody took.

    A marked rework row the valve re-admits is the case: it reaches the launch
    with no route, and a `recovery-route` row claiming it was routed `fresh`
    would report a decision that was never made — on the one stage a reader
    greps to find out which route an item took.
    """
    journal = _journal(tmp_path=tmp_path, records=())

    launch.journal_recovery_route(route=None, journal=journal)

    assert _rows(journal=journal, stage=RECOVERY_ROUTE_STAGE) == ()


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
