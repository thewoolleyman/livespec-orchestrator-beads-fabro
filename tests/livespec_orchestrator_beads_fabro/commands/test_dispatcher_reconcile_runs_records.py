"""Tests for the reconciler's journal records and their field set."""

from __future__ import annotations

from dataclasses import dataclass, field

from livespec_orchestrator_beads_fabro.commands import _dispatcher_reconcile_runs_records as records
from livespec_orchestrator_beads_fabro.commands._dispatcher_reconcile_runs_join import OrphanRun
from livespec_orchestrator_beads_fabro.commands._dispatcher_reconcile_runs_terminate import (
    TERMINATION_ROUTE_CANCEL,
    TERMINATION_ROUTE_RM,
    TerminationOutcome,
)


@dataclass(kw_only=True)
class _Journal:
    written: list[dict[str, object]] = field(default_factory=list)

    def append(self, *, record: dict[str, object]) -> None:
        self.written.append(record)


def test_one_reconciled_record_carries_the_whole_join_and_disposition() -> None:
    journal = _Journal()
    run = records.reconciled_from(
        orphan=_orphan(),
        termination=TerminationOutcome(
            route=TERMINATION_ROUTE_CANCEL,
            succeeded=True,
            detail="cancel route returned 200",
        ),
        export_comment_id="c-9",
    )

    records.journal_reconciled(journal=journal, run=run)

    assert journal.written == [
        {
            "stage": "orphan-run-reconciled",
            "run_id": "01ORPHAN",
            "factory_name": "hp",
            "factory_server_url": "https://hp.example:32276",
            "status_kind": "blocked",
            "work_item_id": "bd-ib-orphan",
            "tenant": "bd-ib",
            "attribution_source": "journal",
            "work_item_status": "closed",
            "orphan_reason": "item-not-active",
            "termination_route": TERMINATION_ROUTE_CANCEL,
            "termination_succeeded": True,
            "termination_detail": "cancel route returned 200",
            "export_comment_id": "c-9",
            "parked_seconds": None,
            "grace_seconds": None,
        }
    ]


def test_a_past_grace_record_carries_the_measurement_that_justified_the_reap() -> None:
    journal = _Journal()
    run = records.reconciled_from(
        orphan=_orphan(
            orphan_reason="blocked-past-grace",
            work_item_status="blocked",
            parked_seconds=2400.5,
            grace_seconds=1800,
        ),
        termination=TerminationOutcome(
            route="questions-answer",
            succeeded=True,
            detail="answered question q-1 with '[A] Abandon (leave open for triage)'",
        ),
        export_comment_id="c-9",
    )

    records.journal_reconciled(journal=journal, run=run)

    assert (run.parked_seconds, run.grace_seconds) == (2400.5, 1800)
    assert journal.written[0]["parked_seconds"] == 2400.5
    assert journal.written[0]["grace_seconds"] == 1800
    assert journal.written[0]["orphan_reason"] == "blocked-past-grace"


def test_the_rm_fallback_gets_its_own_distinct_stage_name() -> None:
    journal = _Journal()
    run = records.reconciled_from(
        orphan=_orphan(),
        termination=TerminationOutcome(
            route=TERMINATION_ROUTE_RM,
            succeeded=True,
            detail="fabro rm -f exited 0",
        ),
        export_comment_id=None,
    )

    records.journal_reconciled(journal=journal, run=run)

    assert [record["stage"] for record in journal.written] == [
        "orphan-run-reconciled",
        "orphan-run-reconcile-rm-fallback",
    ]


def test_a_dry_run_record_names_no_route_it_did_not_take() -> None:
    run = records.reconciled_from(orphan=_orphan(), termination=None, export_comment_id=None)

    assert run.termination_route == records.TERMINATION_ROUTE_NONE
    assert run.termination_succeeded is False
    assert run.termination_detail == "dry run: nothing was exported or terminated"


def test_export_and_error_records_carry_their_own_stages() -> None:
    journal = _Journal()

    records.journal_export(journal=journal, orphan=_orphan(), body="pointer text")
    records.journal_error(
        journal=journal,
        error=records.ReconcileError(
            factory_name="vps",
            factory_server_url=None,
            run_id=None,
            work_item_id=None,
            reason="factory-server-url-missing",
            detail="no server url",
        ),
    )

    assert [record["stage"] for record in journal.written] == [
        "orphan-run-reconcile-export",
        "orphan-run-reconcile-error",
    ]
    assert journal.written[0]["pointer_body"] == "pointer text"
    assert journal.written[1]["reason"] == "factory-server-url-missing"


def _orphan(
    *,
    orphan_reason: str = "item-not-active",
    work_item_status: str = "closed",
    parked_seconds: float | None = None,
    grace_seconds: int | None = None,
) -> OrphanRun:
    return OrphanRun(
        run_id="01ORPHAN",
        factory_name="hp",
        factory_server_url="https://hp.example:32276",
        status_kind="blocked",
        work_item_id="bd-ib-orphan",
        tenant="bd-ib",
        attribution_source="journal",
        work_item_status=work_item_status,
        orphan_reason=orphan_reason,
        parked_seconds=parked_seconds,
        grace_seconds=grace_seconds,
    )
