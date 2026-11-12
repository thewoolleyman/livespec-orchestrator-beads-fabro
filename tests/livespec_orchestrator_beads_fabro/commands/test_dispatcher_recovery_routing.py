"""Recovery routing's directly owned route-selection behaviour."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from livespec_orchestrator_beads_fabro.commands import _dispatcher_recovery_routing as routing
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import JournalFile
from livespec_orchestrator_beads_fabro.commands._dispatcher_recovery_preserved import (
    PreservedWorkUnobservable,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_recovery_routes import (
    RecoveryHold,
    RecoveryRoute,
    RecoverySeed,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_seed_ruling import SeedRuling
from livespec_orchestrator_beads_fabro.types import WorkItem


def test_recapture_exhaustion_holds_the_terminal_ref_when_no_pull_request_is_open(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Recovery routing supplies terminal preservation to the explicit hold."""
    item = WorkItem(
        id="bd-ib-p6ammc",
        type="feature",
        status="ready",
        title="recapture hold",
        description="",
        origin="freeform",
        gap_id=None,
        rank="a0",
        assignee=None,
        depends_on=(),
        captured_at="2026-11-11T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
        admission_policy="auto",
        acceptance_policy="ai-only",
    )
    journal = JournalFile(path=tmp_path / "journal.jsonl")
    journal.path.write_text(
        "\n".join(
            json.dumps(row)
            for row in (
                {"stage": "dispatch-id", "work_item_id": item.id, "dispatch_id": "d"},
                {"stage": "fabro-run", "work_item_id": item.id, "run_id": "run"},
                {
                    "stage": "outcome",
                    "outcome": {
                        "work_item_id": item.id,
                        "status": "blocked",
                        "stage": "non_converged",
                        "detail": "LIVESPEC_RECAPTURE_EXHAUSTED",
                    },
                },
            )
        )
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        routing,
        "gather_resume",
        lambda **_kwargs: SimpleNamespace(
            observation=SimpleNamespace(pull_request=None, pull_request_head=None),
            earlier_run_ids=("run",),
            publications=(),
        ),
    )
    monkeypatch.setattr(
        routing,
        "verified_preserved_seed",
        lambda **_kwargs: RecoverySeed(
            source_run_id="run",
            remote="origin",
            commit_sha="b" * 40,
            preservation_ref="refs/heads/needs-human/run",
            preservation_tip_sha="b" * 40,
        ),
    )

    routed = routing.route_recovery(
        args=argparse.Namespace(), repo=tmp_path, candidates=[item], journal=journal
    )

    route = routed.route_for(work_item_id=item.id)
    assert route is not None
    assert route.hold is not None
    assert "refs/heads/needs-human/run at " + "b" * 40 in route.hold.refusals[0]


@pytest.mark.parametrize(
    ("resolved", "expected_route"),
    [
        (
            RecoveryRoute(
                work_item_id="bd-ib-p6ammc",
                route="held",
                hold=RecoveryHold(refusals=("ref moved",)),
            ),
            "held",
        ),
        (
            RecoveryRoute(
                work_item_id="bd-ib-p6ammc",
                route="seeded",
                seed=RecoverySeed(
                    source_run_id="run",
                    remote="origin",
                    commit_sha="c" * 40,
                    preservation_ref="refs/heads/needs-human/run",
                ),
            ),
            "seeded",
        ),
    ],
)
def test_a_current_ruling_uses_its_verified_resolution(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    resolved: RecoveryRoute,
    expected_route: str,
) -> None:
    """A ruled ref either holds or seeds before the ordinary resume ladder."""
    item = WorkItem(
        id="bd-ib-p6ammc",
        type="feature",
        status="ready",
        title="recapture hold",
        description="",
        origin="freeform",
        gap_id=None,
        rank="a0",
        assignee=None,
        depends_on=(),
        captured_at="2026-11-11T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
        admission_policy="auto",
        acceptance_policy="ai-only",
    )
    monkeypatch.setattr(routing, "unobservable_measurements", lambda **_kwargs: ())
    monkeypatch.setattr(routing, "non_fallback_refusals", lambda **_kwargs: ())
    monkeypatch.setattr(routing, "current_ruling_route", lambda **_kwargs: resolved)
    monkeypatch.setattr(
        routing,
        "current_seed_ruling",
        lambda **_kwargs: SeedRuling(
            work_item_id=item.id,
            preservation_ref="refs/heads/needs-human/run",
            commit_sha="c" * 40,
            invoker="test",
            reason="test",
            instant="2026-11-11T00:00:00Z",
        ),
    )
    monkeypatch.setattr(
        routing,
        "gather_resume",
        lambda **_kwargs: SimpleNamespace(
            observation=SimpleNamespace(), earlier_run_ids=("run",), publications=()
        ),
    )

    routed = routing.route_recovery(
        args=argparse.Namespace(),
        repo=tmp_path,
        candidates=[item],
        journal=JournalFile(path=tmp_path / "journal.jsonl"),
    )

    route = routed.route_for(work_item_id=item.id)
    assert route is not None
    assert route.route == expected_route


def test_an_unobservable_preserved_read_holds_the_fallback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A failed preservation read does not permit a fresh dispatch."""
    item = WorkItem(
        id="bd-ib-p6ammc",
        type="feature",
        status="ready",
        title="recapture hold",
        description="",
        origin="freeform",
        gap_id=None,
        rank="a0",
        assignee=None,
        depends_on=(),
        captured_at="2026-11-11T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
        admission_policy="auto",
        acceptance_policy="ai-only",
    )
    monkeypatch.setattr(
        routing,
        "verified_preserved_seed",
        lambda **_kwargs: PreservedWorkUnobservable(detail="origin unavailable"),
    )
    monkeypatch.setattr(routing, "current_seed_ruling", lambda **_kwargs: None)
    monkeypatch.setattr(routing, "released_for_recovery", lambda **_kwargs: True)
    monkeypatch.setattr(routing, "unobservable_measurements", lambda **_kwargs: ())
    monkeypatch.setattr(routing, "non_fallback_refusals", lambda **_kwargs: ())
    monkeypatch.setattr(routing, "resume_refusals", lambda **_kwargs: ())
    monkeypatch.setattr(
        routing,
        "gather_resume",
        lambda **_kwargs: SimpleNamespace(
            observation=SimpleNamespace(pull_request=None),
            earlier_run_ids=("run",),
            publications=(),
            anchor=None,
        ),
    )

    routed = routing.route_recovery(
        args=argparse.Namespace(),
        repo=tmp_path,
        candidates=[item],
        journal=JournalFile(path=tmp_path / "journal.jsonl"),
    )

    route = routed.route_for(work_item_id=item.id)
    assert route is not None
    assert route.route == "held"
    assert route.hold is not None
    assert route.hold.measurements[0].detail == "origin unavailable"


def test_a_current_hold_ruling_is_recorded_before_release_routing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An operator's existing hold does not enter the ordinary recovery ladder."""
    item = WorkItem(
        id="bd-ib-p6ammc",
        type="feature",
        status="ready",
        title="recapture hold",
        description="",
        origin="freeform",
        gap_id=None,
        rank="a0",
        assignee=None,
        depends_on=(),
        captured_at="2026-11-11T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
        admission_policy="auto",
        acceptance_policy="ai-only",
    )
    monkeypatch.setattr(
        routing,
        "current_seed_ruling",
        lambda **_kwargs: RecoveryHold(refusals=("operator hold",)),
    )

    routed = routing.route_recovery(
        args=argparse.Namespace(),
        repo=tmp_path,
        candidates=[item],
        journal=JournalFile(path=tmp_path / "journal.jsonl"),
    )

    route = routed.route_for(work_item_id=item.id)
    assert route is not None
    assert route.route == "held"
    assert route.hold is not None
    assert route.hold.refusals == ("operator hold",)
