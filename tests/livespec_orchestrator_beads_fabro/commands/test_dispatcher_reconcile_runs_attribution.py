"""Tests for the journal index and the run-to-work-item attribution beneath it."""

from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands import _dispatcher_reconcile_runs_join as join
from livespec_orchestrator_beads_fabro.commands._dispatcher_reconcile_runs_attribution import (
    NON_TERMINAL_STATUS_KINDS,
    ORPHAN_REASON_ITEM_MISSING,
    ORPHAN_REASON_ITEM_NOT_ACTIVE,
    ORPHAN_REASON_SUPERSEDED_RUN,
    FactoryRunInventory,
    attributed_runs,
    journaled_runs,
    read_journaled_runs,
)
from livespec_orchestrator_beads_fabro.commands._fabro_port_records import FabroRunSummary
from livespec_orchestrator_beads_fabro.commands._run_attribution import RunAttribution


def test_a_run_is_joined_to_its_item_with_the_ledgers_own_reason() -> None:
    rows = attributed_runs(
        inventory=_inventory(
            runs=[_run(run_id="01BLOCKED", work_item_id="bd-ib-closed", status_kind="blocked")],
            item_statuses={"bd-ib-closed": "closed"},
        )
    )

    assert [(row.run.run_id, row.work_item_id, row.base_reason) for row in rows] == [
        ("01BLOCKED", "bd-ib-closed", ORPHAN_REASON_ITEM_NOT_ACTIVE)
    ]


def test_a_live_remote_run_carries_no_moot_reason_at_all() -> None:
    journal = json.dumps(
        {"stage": "dispatch-run-stamp", "work_item_id": "bd-ib-live", "run_id": "01LIVE"}
    )

    rows = attributed_runs(
        inventory=_inventory(
            runs=[_run(run_id="01LIVE", work_item_id="bd-ib-live", status_kind="running")],
            item_statuses={"bd-ib-live": "active"},
            journal=journal,
        )
    )

    assert [row.base_reason for row in rows] == [None]


def test_superseded_and_missing_and_terminal_and_foreign_runs() -> None:
    journal = "\n".join(
        [
            "not-json",
            json.dumps(["not-a-mapping"]),
            json.dumps({"stage": "dispatch-id", "work_item_id": "bd-ib-super"}),
            json.dumps({"stage": "fabro-run", "run_id": "01ORPHANED"}),
            json.dumps({"stage": "dispatch-run-stamp", "work_item_id": "bd-ib-no-run"}),
            json.dumps({"stage": "dispatch-run-stamp", "run_id": "01NOITEM"}),
            json.dumps({"work_item_id": "bd-ib-super", "run_id": ""}),
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

    rows = attributed_runs(
        inventory=_inventory(
            runs=[
                _run(run_id="01OLD", work_item_id="bd-ib-super", status_kind="paused"),
                _run(run_id="01NEW", work_item_id="bd-ib-super", status_kind="running"),
                _run(run_id="01GONE", work_item_id="bd-ib-gone", status_kind="starting"),
                _run(run_id="01DONE", work_item_id="bd-ib-super", status_kind="succeeded"),
                _run(run_id="01FOREIGN", work_item_id="overseer-abc", status_kind="blocked"),
                _run(run_id="01NOGOAL", work_item_id=None, status_kind="blocked"),
            ],
            item_statuses={"bd-ib-super": "active"},
            journal=journal,
        )
    )

    assert [(row.run.run_id, row.base_reason) for row in rows] == [
        ("01OLD", ORPHAN_REASON_SUPERSEDED_RUN),
        ("01NEW", None),
        ("01GONE", ORPHAN_REASON_ITEM_MISSING),
    ]
    assert rows[2].work_item_status is None


def test_journal_attribution_wins_over_the_goal_regex() -> None:
    journal = json.dumps(
        {"stage": "dispatch-run-stamp", "work_item_id": "bd-ib-real", "run_id": "01RUN"}
    )

    rows = attributed_runs(
        inventory=_inventory(
            runs=[_run(run_id="01RUN", work_item_id="bd-ib-wrong", status_kind="running")],
            item_statuses={"bd-ib-real": "closed", "bd-ib-wrong": "active"},
            journal=journal,
        )
    )

    assert [(row.work_item_id, row.base_reason) for row in rows] == [
        ("bd-ib-real", ORPHAN_REASON_ITEM_NOT_ACTIVE)
    ]


def test_a_ledger_stamped_run_is_spared_though_its_goal_text_names_a_closed_item() -> None:
    """The stamp is the whole point: the goal regex alone gets this run wrong.

    The control below runs the IDENTICAL join with no attribution and shows it
    carrying a moot reason, so this pair discriminates the ledger leg from the
    regex leg rather than merely exercising it.
    """
    rows = attributed_runs(
        inventory=_inventory(
            runs=[_run(run_id="01RUN", work_item_id="bd-ib-closed", status_kind="running")],
            item_statuses={"bd-ib-closed": "closed", "bd-ib-active": "active"},
            attribution=RunAttribution(metadata_run_ids={"01RUN": "bd-ib-active"}),
        )
    )

    assert [(row.work_item_id, row.base_reason) for row in rows] == [("bd-ib-active", None)]


def test_the_same_run_without_a_recorded_stamp_is_out_of_scope() -> None:
    rows = attributed_runs(
        inventory=_inventory(
            runs=[_run(run_id="01RUN", work_item_id="bd-ib-closed", status_kind="running")],
            item_statuses={"bd-ib-closed": "closed", "bd-ib-active": "active"},
            journal="",
        )
    )

    assert rows == ()


def test_an_untyped_precomputed_journal_map_cannot_bypass_the_launch_stamp_filter() -> None:
    rows = attributed_runs(
        inventory=_inventory(
            runs=[_run(run_id="01RUN", work_item_id="bd-ib-closed", status_kind="running")],
            item_statuses={"bd-ib-closed": "closed"},
            journal="",
            attribution=RunAttribution(journal_run_ids={"01RUN": "bd-ib-closed"}),
        )
    )

    assert rows == ()


def test_goal_text_is_an_explicitly_labeled_read_only_hint_with_tenant_scope() -> None:
    rows = attributed_runs(
        inventory=_inventory(
            runs=[
                _run(run_id="01LOCAL", work_item_id="bd-ib-closed", status_kind="running"),
                _run(run_id="01FOREIGN", work_item_id="overseer-closed", status_kind="running"),
            ],
            item_statuses={"bd-ib-closed": "closed"},
            journal="",
            allow_goal_text_attribution=True,
        )
    )

    assert [(row.run.run_id, row.attribution_source) for row in rows] == [("01LOCAL", "goal-text")]


def test_ledger_metadata_outranks_the_journal_which_outranks_the_goal_text() -> None:
    journal = json.dumps(
        {
            "stage": "dispatch-run-stamp",
            "work_item_id": "bd-ib-journaled",
            "run_id": "01RUN",
        }
    )

    rows = attributed_runs(
        inventory=_inventory(
            runs=[_run(run_id="01RUN", work_item_id="bd-ib-goal", status_kind="running")],
            item_statuses={
                "bd-ib-goal": "active",
                "bd-ib-journaled": "acceptance",
                "bd-ib-stamped": "closed",
            },
            journal=journal,
            attribution=RunAttribution(metadata_run_ids={"01RUN": "bd-ib-stamped"}),
        )
    )

    assert [(row.work_item_id, row.base_reason) for row in rows] == [
        ("bd-ib-stamped", ORPHAN_REASON_ITEM_NOT_ACTIVE)
    ]


def test_recorded_metadata_ownership_does_not_depend_on_an_item_prefix() -> None:
    rows = attributed_runs(
        inventory=_inventory(
            runs=[_run(run_id="01RUN", work_item_id="bd-ib-goal", status_kind="running")],
            item_statuses={"bd-ib-goal": "closed"},
            attribution=RunAttribution(metadata_run_ids={"01RUN": "overseer-abc"}),
        )
    )

    assert [(row.work_item_id, row.attribution_source) for row in rows] == [
        ("overseer-abc", "metadata")
    ]


def test_read_journaled_runs_reads_a_file_and_tolerates_an_absent_one(tmp_path: Path) -> None:
    present = tmp_path / "journal.jsonl"
    _ = present.write_text(
        json.dumps({"stage": "dispatch-run-stamp", "work_item_id": "bd-ib-one", "run_id": "01ONE"})
        + "\n",
        encoding="utf-8",
    )

    read = read_journaled_runs(path=present)
    absent = read_journaled_runs(path=tmp_path / "missing.jsonl")

    assert read.newest_run_id_by_item == {"bd-ib-one": "01ONE"}
    assert read.item_id_by_run == {"01ONE": "bd-ib-one"}
    assert absent.newest_run_id_by_item == {}


def test_every_non_terminal_status_kind_is_in_scope() -> None:
    assert set(NON_TERMINAL_STATUS_KINDS) == {
        "blocked",
        "paused",
        "runnable",
        "running",
        "starting",
    }


def test_a_merge_held_items_terminal_run_is_left_alone_rather_than_reaped() -> None:
    """A terminal run on an `active` item under a MATCHING journaled run id is no orphan.

    This is the reconciliation half of the ratified merge hold, and it is a
    regression lock on two independent reasons the reconciler leaves such a run
    alone: the run is terminal, and — were it not — its item is `active` under
    the newest journaled run id for that item, so it carries no moot reason.

    The controls are the two ways this could go wrong in the held population's
    exact shape: a NON-terminal run over the same item and the same journal is
    attributed with `base_reason=None` (proving the item's `active`-with-a-hold
    state is not itself read as moot), while a run the same item has superseded
    is still reported. A test that only asserted the held run's absence could
    not tell "left alone" from "never looked at any run at all".
    """
    journal = "\n".join(
        [
            json.dumps(
                {
                    "stage": "dispatch-run-stamp",
                    "work_item_id": "bd-ib-held",
                    "run_id": "01SUPERSEDED",
                }
            ),
            json.dumps(
                {
                    "stage": "dispatch-run-stamp",
                    "work_item_id": "bd-ib-held",
                    "run_id": "01HELD",
                }
            ),
        ]
    )

    rows = attributed_runs(
        inventory=_inventory(
            runs=[
                _run(run_id="01HELD", work_item_id="bd-ib-held", status_kind="succeeded"),
                _run(run_id="01SUPERSEDED", work_item_id="bd-ib-held", status_kind="running"),
            ],
            item_statuses={"bd-ib-held": "active"},
            journal=journal,
        )
    )

    assert [(row.run.run_id, row.base_reason) for row in rows] == [
        ("01SUPERSEDED", ORPHAN_REASON_SUPERSEDED_RUN)
    ]

    live = attributed_runs(
        inventory=_inventory(
            runs=[_run(run_id="01HELD", work_item_id="bd-ib-held", status_kind="running")],
            item_statuses={"bd-ib-held": "active"},
            journal=journal,
        )
    )

    assert [(row.run.run_id, row.base_reason) for row in live] == [("01HELD", None)]


def test_the_attribution_layer_is_no_longer_reachable_through_the_classifier() -> None:
    """The layers moved apart, so the classifier must not still export them.

    Asserting the new module HAS the names is not enough: a re-export left
    behind in the join would let a caller keep importing them from there, and
    the split would be cosmetic rather than structural.
    """
    assert not hasattr(join, "journaled_runs")
    assert not hasattr(join, "read_journaled_runs")
    assert not hasattr(join, "JournaledRuns")
    assert "NON_TERMINAL_STATUS_KINDS" not in join.__all__


def _inventory(
    *,
    runs: Sequence[FabroRunSummary],
    item_statuses: dict[str, str],
    journal: str | None = None,
    attribution: RunAttribution | None = None,
    allow_goal_text_attribution: bool = False,
) -> FactoryRunInventory:
    return FactoryRunInventory(
        runs=runs,
        item_statuses=item_statuses,
        journaled=journaled_runs(text=_fixture_journal(runs=runs) if journal is None else journal),
        id_prefix="bd-ib",
        factory_name="hp",
        factory_server_url="https://hp.example:32276",
        allow_goal_text_attribution=allow_goal_text_attribution,
        **({} if attribution is None else {"attribution": attribution}),
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
