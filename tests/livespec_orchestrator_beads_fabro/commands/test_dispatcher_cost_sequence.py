"""An item's cost across a release-and-re-dispatch sequence, counted once.

Binds `SPECIFICATION/contracts.md` section "Factory-configurable ACP fallback
priority" -> "Cost follows every attempt": "An item's cost across a
release-and-re-dispatch sequence is the sum of those records and the final
run's cost. Each run or probe cost observation MUST have a stable identity and
MUST be counted at most once across reconciliation and resume. ... A shared
availability probe MUST NOT be charged in full to multiple items."

THE SUM IS CHECKED WITH EVERY FIGURE DISTINCT, which is what makes the
arithmetic evidence. Three equal figures add to the same total whether a
replayed observation was counted once, twice, or dropped, so the fixtures below
price every attempt differently and the expected totals are arithmetic only the
correct fold can produce.

COUNTED ONCE IS ASSERTED THROUGH THE IDENTITY AND NOT THROUGH THE ROW, because
the journal is append-only: a reconciliation replay and a resume both re-derive
the same observation from the same terminal, so two rows carrying one identity
are one charge. Deduplicating on the whole row would count them twice the
moment anything about the second append differed -- which the append layer
guarantees it does, since it stamps its own `at`.

THE SHARED PROBE IS ASSERTED FROM THE OTHER ITEM'S SIDE. A confirmation turn
run inside one item's admission evaluation establishes availability every peer
then benefits from; charging it to each of them would multiply one spend by the
size of the queue. So the row names one item, and a peer's fold must see
nothing at all -- not a share, not a zero.
"""

from __future__ import annotations

import importlib
import json
from pathlib import Path
from typing import Any

from livespec_orchestrator_beads_fabro.commands._dispatcher_cost_attempts import (
    ATTEMPT_COST_CONFIRMATION_TURN,
    ATTEMPT_COST_RELEASED_RUN,
    ATTEMPT_COST_STAGE,
    attempt_cost_identity,
)

_COMMANDS = (
    Path(__file__).resolve().parents[3]
    / ".claude-plugin"
    / "scripts"
    / "livespec_orchestrator_beads_fabro"
    / "commands"
)
_MODULE = "_dispatcher_cost_sequence"
_MODULE_PATH = _COMMANDS / f"{_MODULE}.py"

_ITEM = "bd-ib-seq"
_PEER = "bd-ib-peer"
_FACTORY = "hp"
_FIRST_RELEASE_RUN = "01FIRSTRELEASEDRUN"
_SECOND_RELEASE_RUN = "01SECONDRELEASEDRUN"
_PROBE_RUN = "01CONFIRMATIONTURN"

# Every figure distinct, per the module docstring, so the totals below are
# reachable by exactly one fold.
_FIRST_RELEASE_MICROS = 1_000
_SECOND_RELEASE_MICROS = 20_000
_PROBE_MICROS = 300
_FINAL_RUN_MICROS = 4_000_000


def _module() -> Any:
    """The sequence fold, through an in-body import.

    In-body so this file's FIRST failing assertion is a genuine check on the
    committed file rather than a collection error.
    """
    assert _MODULE_PATH.is_file(), _MODULE_PATH
    return importlib.import_module(f"livespec_orchestrator_beads_fabro.commands.{_MODULE}")


def _row(
    *,
    work_item_id: str = _ITEM,
    source: str = ATTEMPT_COST_RELEASED_RUN,
    run_id: str = _FIRST_RELEASE_RUN,
    node_attempt: str = "implement",
    usd_micros: int | None,
) -> dict[str, object]:
    """One appended attempt-cost row, as the journal carries it."""
    return {
        "stage": ATTEMPT_COST_STAGE,
        "observation_id": attempt_cost_identity(
            source=source, factory=_FACTORY, run_id=run_id, node_attempt=node_attempt
        ),
        "source": source,
        "work_item_id": work_item_id,
        "factory": _FACTORY,
        "run_id": run_id,
        "node_attempt": node_attempt,
        "occurred_at": "2026-10-12T09:10:00Z",
        "attempts": [],
        "usd_micros": usd_micros,
        "cost_observable": usd_micros is not None,
    }


def _sequence_rows() -> list[dict[str, object]]:
    """Two releases and one confirmation turn, each charged to this item."""
    return [
        _row(run_id=_FIRST_RELEASE_RUN, usd_micros=_FIRST_RELEASE_MICROS),
        _row(
            source=ATTEMPT_COST_CONFIRMATION_TURN,
            run_id=_PROBE_RUN,
            node_attempt="confirm",
            usd_micros=_PROBE_MICROS,
        ),
        _row(run_id=_SECOND_RELEASE_RUN, usd_micros=_SECOND_RELEASE_MICROS),
    ]


def _observations(*, records: list[dict[str, object]], work_item_id: str = _ITEM) -> Any:
    module = _module()
    return module.attempt_cost_observations(  # pyright: ignore[reportAttributeAccessIssue]
        records=tuple(records), work_item_id=work_item_id
    )


def _cost(*, records: list[dict[str, object]], final_run_usd_micros: int | None) -> Any:
    module = _module()
    return module.sequence_cost(  # pyright: ignore[reportAttributeAccessIssue]
        observations=_observations(records=records),
        final_run_usd_micros=final_run_usd_micros,
    )


def test_the_sequence_fold_surface_exists() -> None:
    """The three entry points an item's sequence cost is read through."""
    module = _module()
    for name in (
        "attempt_cost_observations",
        "item_attempt_cost_observations",
        "sequence_cost",
    ):
        assert hasattr(module, name), name


def test_the_fold_reads_only_this_items_own_attempt_cost_rows() -> None:
    """Another stage's row, and a peer item's row, are not this item's charge."""
    records = [
        *_sequence_rows(),
        {"stage": "provider-limit-release", "work_item_id": _ITEM, "usd_micros": 999_999},
        _row(work_item_id=_PEER, run_id="01PEERSOWNRUN", usd_micros=777_777),
    ]
    observations = _observations(records=records)
    assert [one.usd_micros for one in observations] == [
        _FIRST_RELEASE_MICROS,
        _PROBE_MICROS,
        _SECOND_RELEASE_MICROS,
    ]


def test_a_confirmation_turn_is_charged_to_one_item_and_no_peer_sees_it() -> None:
    """Not a share and not a zero: the peer's fold sees nothing at all."""
    records = _sequence_rows()
    peer = _observations(records=records, work_item_id=_PEER)
    assert peer == ()
    charged = _observations(records=records)
    assert [one.source for one in charged].count(ATTEMPT_COST_CONFIRMATION_TURN) == 1


def test_a_replayed_observation_is_counted_once() -> None:
    """Reconciliation and resume re-derive one identity; it is one charge."""
    first = _row(run_id=_FIRST_RELEASE_RUN, usd_micros=_FIRST_RELEASE_MICROS)
    replayed = {**first, "occurred_at": "2026-10-12T11:45:00Z"}
    observations = _observations(records=[first, replayed, *_sequence_rows()[1:]])
    assert [one.identity for one in observations].count(first["observation_id"]) == 1
    assert len(observations) == 3


def test_the_sequence_total_is_the_records_plus_the_final_runs_cost() -> None:
    """The clause's own arithmetic, over three observations and one final run."""
    cost = _cost(records=_sequence_rows(), final_run_usd_micros=_FINAL_RUN_MICROS)
    assert cost.usd_micros == (
        _FIRST_RELEASE_MICROS + _PROBE_MICROS + _SECOND_RELEASE_MICROS + _FINAL_RUN_MICROS
    )
    assert cost.subtotal_usd_micros == cost.usd_micros
    assert set(cost.counted_identities) == {str(one["observation_id"]) for one in _sequence_rows()}


def test_a_replay_does_not_move_the_total() -> None:
    """The arithmetic control on counting once, with every figure distinct."""
    rows = _sequence_rows()
    once = _cost(records=rows, final_run_usd_micros=_FINAL_RUN_MICROS)
    twice = _cost(records=[*rows, rows[0], rows[2]], final_run_usd_micros=_FINAL_RUN_MICROS)
    assert twice.usd_micros == once.usd_micros


def test_the_fold_reports_the_figure_each_row_states() -> None:
    """Including a row that states its cost absent, which it reads as absent."""
    observations = _observations(
        records=[_row(run_id=_FIRST_RELEASE_RUN, usd_micros=None)],
    )
    assert len(observations) == 1
    assert observations[0].usd_micros is None
    assert observations[0].source == ATTEMPT_COST_RELEASED_RUN


def test_a_row_whose_identity_cannot_be_read_is_carried_rather_than_dropped() -> None:
    """Dropping it would under-report a real charge; carrying it cannot double one.

    Such a row has nothing to deduplicate on, which costs nothing: it states no
    readable figure either, so every copy of it contributes the same absence and
    the duplicates cannot move a total.
    """
    unreadable = {**_row(usd_micros=None), "observation_id": None}
    observations = _observations(records=[unreadable, unreadable])
    assert len(observations) == 2
    assert [one.identity for one in observations] == [None, None]
    cost = _cost(records=[unreadable, unreadable], final_run_usd_micros=_FINAL_RUN_MICROS)
    assert cost.counted_identities == ()
    assert cost.subtotal_usd_micros == _FINAL_RUN_MICROS


def test_the_subtotal_counts_only_the_figures_the_rows_state() -> None:
    """A row that states no figure contributes nothing rather than a zero."""
    rows = [
        _row(run_id=_FIRST_RELEASE_RUN, usd_micros=_FIRST_RELEASE_MICROS),
        _row(run_id=_SECOND_RELEASE_RUN, usd_micros=None),
    ]
    cost = _cost(records=rows, final_run_usd_micros=_FINAL_RUN_MICROS)
    assert cost.subtotal_usd_micros == _FIRST_RELEASE_MICROS + _FINAL_RUN_MICROS


def test_the_journal_reader_skips_a_line_it_cannot_read(tmp_path: Path) -> None:
    """One truncated line from a crash mid-append must not blind the fold.

    A reader that discarded the whole file on one unparseable line would report
    an item with a long release history as having spent nothing -- a gauge that
    passes when blinded, which this repository treats as worse than the honest
    violation.
    """
    module = _module()
    path = tmp_path / "journal.jsonl"
    lines = [json.dumps(one) for one in _sequence_rows()]
    _ = path.write_text("\n".join([lines[0], '{"stage": "attempt-c', *lines[1:]]) + "\n")
    observations = module.item_attempt_cost_observations(  # pyright: ignore[reportAttributeAccessIssue]
        journal_path=path, work_item_id=_ITEM
    )
    assert [one.usd_micros for one in observations] == [
        _FIRST_RELEASE_MICROS,
        _PROBE_MICROS,
        _SECOND_RELEASE_MICROS,
    ]
