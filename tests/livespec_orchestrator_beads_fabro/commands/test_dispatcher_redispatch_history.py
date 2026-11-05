"""The item's journaled terminals and recovery rows, graded without a factory."""

from __future__ import annotations

from livespec_orchestrator_beads_fabro.commands._dispatcher_redispatch_history import (
    RECOVERY_STAGE,
    consumed_recovery_attempt_ids,
    item_terminals,
    newest_recovery,
)

_ITEM = "bd-ib-sample"


def _outcome(*, run_id: str | None, status: str = "blocked", **fields: object) -> dict[str, object]:
    outcome: dict[str, object] = {
        "work_item_id": _ITEM,
        "status": status,
        "fabro_run_id": run_id,
        "fabro_factory_name": "petri",
        **fields,
    }
    return {"stage": "outcome", "outcome": outcome}


def _attributable(*, records: list[dict[str, object]]) -> list[bool | None]:
    return [
        terminal.item_attributable
        for terminal in item_terminals(records=records, work_item_id=_ITEM)
    ]


def test_causal_stage_and_workflow_markers_are_item_attributable() -> None:
    records = [
        _outcome(run_id="01A", needs_human_stages=["implement"], detail="x"),
        _outcome(run_id="01B", detail="LIVESPEC_IMPLEMENT_PARTIAL_PROGRESS: incomplete"),
        _outcome(run_id="01C", status="failed", detail="LIVESPEC_NON_CONVERGED: janitor"),
    ]

    assert _attributable(records=records) == [True, True, True]


def test_host_signatures_releases_and_usage_limits_are_not_item_attributable() -> None:
    records = [
        _outcome(run_id="01A", needs_human_stages=["pr"], detail="database is locked"),
        _outcome(
            run_id="01B",
            needs_human_stages=["pr"],
            fabro_failure_cause="the sandbox became unreachable",
        ),
        _outcome(run_id="01C", needs_human_stages=["pr"], provider_usage_limit=True),
        _outcome(run_id="01D", needs_human_stages=["pr"]),
        {"stage": "provider-limit-release", "work_item_id": _ITEM, "run_id": "01D"},
    ]

    assert _attributable(records=records) == [False, False, False, False]


def test_unknown_cause_is_neither_host_nor_item() -> None:
    records = [_outcome(run_id="01A", detail="something nobody classified")]

    assert _attributable(records=records) == [None]


def test_cause_text_is_the_first_line_or_an_explicit_absence() -> None:
    terminals = item_terminals(
        records=[
            _outcome(run_id="01A", detail="first line\nsecond line", needs_human_stages=["x"]),
            _outcome(run_id="01B", needs_human_stages=["x"]),
        ],
        work_item_id=_ITEM,
    )

    assert [terminal.cause for terminal in terminals] == ["first line", "no recorded cause"]


def test_history_restarts_after_a_green_terminal_and_skips_foreign_rows() -> None:
    records: list[dict[str, object]] = [
        _outcome(run_id="01A", needs_human_stages=["x"]),
        _outcome(run_id=None, status="green"),
        _outcome(run_id="01B", needs_human_stages=["x"]),
        _outcome(run_id=None, needs_human_stages=["x"]),
        {"stage": "outcome", "outcome": "not-a-mapping"},
        {"stage": "outcome", "outcome": {"work_item_id": "bd-other", "fabro_run_id": "01Z"}},
        {"stage": "dispatch-id", "work_item_id": _ITEM},
    ]

    runs = [terminal.run_id for terminal in item_terminals(records=records, work_item_id=_ITEM)]

    assert runs == ["01B"]


def _recovery(**fields: object) -> dict[str, object]:
    return {"stage": RECOVERY_STAGE, "work_item_id": _ITEM, **fields}


def test_newest_recovery_reads_typed_fields_and_empties_unusable_ones() -> None:
    records = [
        _recovery(attempt_id="old"),
        _recovery(
            attempt_id=" r2 ",
            prior_run_ids=["01B", 7],
            diagnosis="budget exhausted",
            operation=f"impl:{_ITEM}",
            execution_evidence="resumed",
        ),
    ]

    recovery = newest_recovery(records=records, work_item_id=_ITEM)

    assert recovery is not None
    assert (recovery.attempt_id, recovery.prior_run_ids) == ("r2", ("01B", "7"))
    assert recovery.operation == f"impl:{_ITEM}"


def test_prose_operation_and_malformed_fields_read_as_empty() -> None:
    recovery = newest_recovery(
        records=[_recovery(attempt_id=3, prior_run_ids="01B", operation="try again")],
        work_item_id=_ITEM,
    )

    assert recovery is not None
    assert (recovery.attempt_id, recovery.prior_run_ids, recovery.operation) == ("", (), "")


def test_no_recovery_row_reads_as_none() -> None:
    assert newest_recovery(records=[_outcome(run_id="01A")], work_item_id=_ITEM) is None


def test_a_recovery_is_consumed_by_the_next_launch_only() -> None:
    records = [
        _recovery(attempt_id="r1"),
        {"stage": "ledger-admit", "work_item_id": _ITEM},
        {"stage": "dispatch-id", "work_item_id": "bd-other"},
        _recovery(attempt_id="r2"),
        {"stage": "dispatch-id", "work_item_id": _ITEM},
        _recovery(attempt_id="r3"),
    ]

    assert consumed_recovery_attempt_ids(records=records, work_item_id=_ITEM) == {"r1", "r2"}
