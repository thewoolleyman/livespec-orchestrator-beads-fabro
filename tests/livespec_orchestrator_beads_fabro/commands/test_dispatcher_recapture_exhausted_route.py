"""The route record for a recovery attempt that exhausted proof recapture."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from livespec_orchestrator_beads_fabro.commands._dispatcher_io import JournalFile
from livespec_orchestrator_beads_fabro.commands._dispatcher_recapture_exhausted_route import (
    recapture_exhausted_route,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_recovery_routes import RecoverySeed
from livespec_orchestrator_beads_fabro.types import WorkItem


def _item() -> WorkItem:
    """Return the ready candidate the recovery route owns."""
    return WorkItem(
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


def test_the_route_records_the_terminal_preservation_when_there_is_no_pull_request(
    tmp_path: Path,
) -> None:
    """The explicit hold uses the preservation supplied by recovery routing."""
    route = recapture_exhausted_route(
        gather=SimpleNamespace(
            observation=SimpleNamespace(pull_request=None, pull_request_head=None),
            earlier_run_ids=("run",),
            publications=(),
        ),
        item=_item(),
        journal=JournalFile(path=tmp_path / "journal.jsonl"),
        preserved_seed=lambda _gather: RecoverySeed(
            source_run_id="run",
            remote="origin",
            commit_sha="b" * 40,
            preservation_ref="refs/heads/needs-human/run",
        ),
    )

    assert route.hold is not None
    assert route.hold.refusals == (
        "recapture-exhausted: implementation preserved on refs/heads/needs-human/run at "
        + "b" * 40
        + " ; resume --item bd-ib-p6ammc at proof_capture with a proof rider",
    )


def test_the_route_uses_the_open_pull_request_without_reading_a_terminal_ref(
    tmp_path: Path,
) -> None:
    """An open pull request remains the preferred preserved implementation."""
    route = recapture_exhausted_route(
        gather=SimpleNamespace(
            observation=SimpleNamespace(pull_request=4841, pull_request_head="a" * 40)
        ),
        item=_item(),
        journal=JournalFile(path=tmp_path / "journal.jsonl"),
        preserved_seed=lambda _gather: object(),
    )

    assert route.hold is not None
    assert "implementation preserved on #4841 at " + "a" * 40 in route.hold.refusals[0]


def test_the_route_names_no_preservation_when_the_terminal_ref_is_absent(tmp_path: Path) -> None:
    """A failed terminal-ref read is distinct from a pull-request preservation."""
    route = recapture_exhausted_route(
        gather=SimpleNamespace(
            observation=SimpleNamespace(pull_request=None, pull_request_head=None),
            earlier_run_ids=("run",),
            publications=(),
        ),
        item=_item(),
        journal=JournalFile(path=tmp_path / "journal.jsonl"),
        preserved_seed=lambda _gather: object(),
    )

    assert route.hold is not None
    assert "no preserved implementation observed" in route.hold.refusals[0]
