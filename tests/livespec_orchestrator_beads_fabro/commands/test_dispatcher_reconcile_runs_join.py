"""Tests for the classification of attributed runs into orphans and holds."""

from __future__ import annotations

import json
from collections.abc import Sequence

from livespec_orchestrator_beads_fabro.commands._dispatcher_reconcile_runs_attribution import (
    ORPHAN_REASON_ITEM_MISSING,
    ORPHAN_REASON_ITEM_NOT_ACTIVE,
    ORPHAN_REASON_SUPERSEDED_RUN,
    FactoryRunInventory,
    journaled_runs,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_reconcile_runs_grace import (
    BLOCKED_HOLD_UNMEASURED,
    BLOCKED_HOLD_WITHIN_GRACE,
    ORPHAN_REASON_BLOCKED_PAST_GRACE,
    BlockedRunGrace,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_reconcile_runs_join import (
    blocked_grace_candidate_ids,
    classify_blocked_holds,
    classify_orphans,
)
from livespec_orchestrator_beads_fabro.commands._fabro_port_records import FabroRunSummary


def test_blocked_run_whose_item_closed_is_an_orphan() -> None:
    orphans = classify_orphans(
        inventory=_inventory(
            runs=[_run(run_id="01BLOCKED", work_item_id="bd-ib-closed", status_kind="blocked")],
            item_statuses={"bd-ib-closed": "closed"},
        )
    )

    assert [(run.run_id, run.orphan_reason, run.status_kind) for run in orphans] == [
        ("01BLOCKED", ORPHAN_REASON_ITEM_NOT_ACTIVE, "blocked")
    ]


def test_live_remote_run_is_not_an_orphan_with_nobody_watching() -> None:
    journal = json.dumps(
        {"stage": "dispatch-run-stamp", "work_item_id": "bd-ib-live", "run_id": "01LIVE"}
    )

    orphans = classify_orphans(
        inventory=_inventory(
            runs=[_run(run_id="01LIVE", work_item_id="bd-ib-live", status_kind="running")],
            item_statuses={"bd-ib-live": "active"},
            journal=journal,
        )
    )

    assert orphans == ()


def test_active_item_with_no_journaled_run_is_left_alone() -> None:
    orphans = classify_orphans(
        inventory=_inventory(
            runs=[_run(run_id="01LIVE", work_item_id="bd-ib-live", status_kind="running")],
            item_statuses={"bd-ib-live": "active"},
        )
    )

    assert orphans == ()


def test_superseded_and_missing_runs_are_reported_with_their_own_reasons() -> None:
    journal = "\n".join(
        [
            json.dumps(
                {
                    "stage": "dispatch-run-stamp",
                    "work_item_id": "bd-ib-super",
                    "fabro_run_id": "01OLD",
                }
            ),
            json.dumps(
                {
                    "stage": "dispatch-run-stamp",
                    "work_item_id": "bd-ib-super",
                    "fabro_run_id": "01NEW",
                }
            ),
            json.dumps(
                {
                    "stage": "dispatch-run-stamp",
                    "work_item_id": "bd-ib-gone",
                    "run_id": "01GONE",
                }
            ),
        ]
    )

    orphans = classify_orphans(
        inventory=_inventory(
            runs=[
                _run(run_id="01OLD", work_item_id="bd-ib-super", status_kind="paused"),
                _run(run_id="01NEW", work_item_id="bd-ib-super", status_kind="running"),
                _run(run_id="01GONE", work_item_id="bd-ib-gone", status_kind="starting"),
            ],
            item_statuses={"bd-ib-super": "active"},
            journal=journal,
        )
    )

    assert [(run.run_id, run.orphan_reason) for run in orphans] == [
        ("01OLD", ORPHAN_REASON_SUPERSEDED_RUN),
        ("01GONE", ORPHAN_REASON_ITEM_MISSING),
    ]
    assert orphans[1].work_item_status is None
    assert orphans[0].factory_name == "hp"


def test_a_parked_run_past_grace_is_an_orphan_carrying_its_measurement() -> None:
    orphans = classify_orphans(
        inventory=_inventory(
            runs=[_run(run_id="01PARKED", work_item_id="bd-ib-live", status_kind="blocked")],
            item_statuses={"bd-ib-live": "blocked"},
        ),
        grace=BlockedRunGrace(grace_seconds=1800, parked_seconds_by_run={"01PARKED": 1801.0}),
    )

    assert [(run.run_id, run.orphan_reason) for run in orphans] == [
        ("01PARKED", ORPHAN_REASON_BLOCKED_PAST_GRACE)
    ]
    assert (orphans[0].parked_seconds, orphans[0].grace_seconds) == (1801.0, 1800)


def test_a_parked_run_inside_grace_is_held_rather_than_orphaned() -> None:
    policy = BlockedRunGrace(
        grace_seconds=1800,
        parked_seconds_by_run={"01YOUNG": 300.0, "01UNKNOWN": None},
    )
    inventory = _inventory(
        runs=[
            _run(run_id="01YOUNG", work_item_id="bd-ib-live", status_kind="blocked"),
            _run(run_id="01UNKNOWN", work_item_id="bd-ib-busy", status_kind="blocked"),
        ],
        item_statuses={"bd-ib-live": "blocked", "bd-ib-busy": "active"},
    )

    orphans = classify_orphans(inventory=inventory, grace=policy)
    held = classify_blocked_holds(inventory=inventory, grace=policy)

    assert orphans == ()
    assert [(run.run_id, run.hold_reason, run.seconds_remaining) for run in held] == [
        ("01YOUNG", BLOCKED_HOLD_WITHIN_GRACE, 1500.0),
        ("01UNKNOWN", BLOCKED_HOLD_UNMEASURED, None),
    ]
    assert held[0].grace_seconds == 1800
    assert held[0].work_item_status == "blocked"


def test_a_zero_grace_disables_the_arm_and_restores_the_moot_question_reading() -> None:
    disabled = BlockedRunGrace(grace_seconds=0, parked_seconds_by_run={})
    inventory = _inventory(
        runs=[_run(run_id="01PARKED", work_item_id="bd-ib-live", status_kind="blocked")],
        item_statuses={"bd-ib-live": "blocked"},
    )

    orphans = classify_orphans(inventory=inventory, grace=disabled)
    held = classify_blocked_holds(inventory=inventory, grace=disabled)

    assert [(run.run_id, run.orphan_reason) for run in orphans] == [
        ("01PARKED", ORPHAN_REASON_ITEM_NOT_ACTIVE)
    ]
    assert held == ()


def test_a_superseded_parked_run_keeps_the_moot_reading_and_never_waits() -> None:
    journal = "\n".join(
        [
            json.dumps(
                {
                    "stage": "dispatch-run-stamp",
                    "work_item_id": "bd-ib-live",
                    "fabro_run_id": "01OLD",
                }
            ),
            json.dumps(
                {
                    "stage": "dispatch-run-stamp",
                    "work_item_id": "bd-ib-live",
                    "fabro_run_id": "01NEW",
                }
            ),
        ]
    )
    inventory = _inventory(
        runs=[_run(run_id="01OLD", work_item_id="bd-ib-live", status_kind="blocked")],
        item_statuses={"bd-ib-live": "active"},
        journal=journal,
    )

    orphans = classify_orphans(
        inventory=inventory,
        grace=BlockedRunGrace(grace_seconds=1800, parked_seconds_by_run={"01OLD": 1.0}),
    )

    assert [(run.run_id, run.orphan_reason) for run in orphans] == [
        ("01OLD", ORPHAN_REASON_SUPERSEDED_RUN)
    ]
    assert orphans[0].parked_seconds is None
    assert blocked_grace_candidate_ids(inventory=inventory) == ()


def test_only_a_blocked_run_with_a_live_item_is_worth_measuring() -> None:
    candidates = blocked_grace_candidate_ids(
        inventory=_inventory(
            runs=[
                _run(run_id="01PARKED", work_item_id="bd-ib-live", status_kind="blocked"),
                _run(run_id="01BUSY", work_item_id="bd-ib-busy", status_kind="blocked"),
                _run(run_id="01RUNNING", work_item_id="bd-ib-running", status_kind="running"),
                _run(run_id="01DONE", work_item_id="bd-ib-closed", status_kind="blocked"),
                _run(run_id="01GONE", work_item_id="bd-ib-gone", status_kind="blocked"),
            ],
            item_statuses={
                "bd-ib-live": "blocked",
                "bd-ib-busy": "active",
                "bd-ib-running": "active",
                "bd-ib-closed": "closed",
            },
        )
    )

    assert candidates == ("01PARKED", "01BUSY")


def test_a_targeted_pass_measures_its_own_items_park_and_nobody_elses() -> None:
    """The grace arm costs an `inspect` per governed run, so it stays targeted.

    The control is the SAME inventory with no narrowing, which returns both
    runs — so a miss below is the narrowing working rather than the predicate
    failing to reach either run.
    """
    runs = [
        _run(run_id="01MINE", work_item_id="bd-ib-mine", status_kind="blocked"),
        _run(run_id="01THEIRS", work_item_id="bd-ib-theirs", status_kind="blocked"),
    ]
    item_statuses = {"bd-ib-mine": "blocked", "bd-ib-theirs": "blocked"}
    targeted = _inventory(runs=runs, item_statuses=item_statuses, only_work_item_id="bd-ib-mine")
    swept = _inventory(runs=runs, item_statuses=item_statuses)

    assert blocked_grace_candidate_ids(inventory=swept) == ("01MINE", "01THEIRS")
    assert blocked_grace_candidate_ids(inventory=targeted) == ("01MINE",)
    # The run the narrowing skipped keeps whatever reason the ledger had for
    # it, rather than silently becoming invisible to the classification.
    assert [
        (run.run_id, run.orphan_reason)
        for run in classify_orphans(
            inventory=targeted,
            grace=BlockedRunGrace(grace_seconds=1800, parked_seconds_by_run={"01MINE": 1.0}),
        )
    ] == [("01THEIRS", ORPHAN_REASON_ITEM_NOT_ACTIVE)]


def test_classification_without_a_grace_policy_is_the_moot_question_join() -> None:
    inventory = _inventory(
        runs=[_run(run_id="01PARKED", work_item_id="bd-ib-live", status_kind="blocked")],
        item_statuses={"bd-ib-live": "blocked"},
    )

    orphans = classify_orphans(inventory=inventory)
    held = classify_blocked_holds(inventory=inventory)

    assert [run.orphan_reason for run in orphans] == [ORPHAN_REASON_ITEM_NOT_ACTIVE]
    assert held == ()


def _inventory(
    *,
    runs: Sequence[FabroRunSummary],
    item_statuses: dict[str, str],
    journal: str | None = None,
    only_work_item_id: str | None = None,
) -> FactoryRunInventory:
    return FactoryRunInventory(
        runs=runs,
        item_statuses=item_statuses,
        journaled=journaled_runs(text=_fixture_journal(runs=runs) if journal is None else journal),
        id_prefix="bd-ib",
        factory_name="hp",
        factory_server_url="https://hp.example:32276",
        only_work_item_id=only_work_item_id,
    )


def _fixture_journal(*, runs: Sequence[FabroRunSummary]) -> str:
    return "\n".join(
        json.dumps(
            {
                "stage": "dispatch-run-stamp",
                "run_id": run.run_id,
                "work_item_id": run.work_item_id,
            }
        )
        for run in runs
        if run.work_item_id is not None
    )


def _run(*, run_id: str, work_item_id: str | None, status_kind: str) -> FabroRunSummary:
    return FabroRunSummary(
        run_id=run_id,
        status_kind=status_kind,
        goal=None if work_item_id is None else f"Work-item: {work_item_id}",
        total_usd_micros=None,
        work_item_id=work_item_id,
    )
