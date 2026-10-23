"""One item's cost across a release-and-re-dispatch sequence, counted once.

`SPECIFICATION/contracts.md` section "Factory-configurable ACP fallback
priority" -> "Cost follows every attempt": "An item's cost across a
release-and-re-dispatch sequence is the sum of those records and the final
run's cost. Each run or probe cost observation MUST have a stable identity and
MUST be counted at most once across reconciliation and resume. ... A shared
availability probe MUST NOT be charged in full to multiple items."

THE FOLD IS AN OBSERVATION AND RETURNS NO VERDICT, which is the same
paragraph's "Attempt-cost records are observations only and never yield a gate
verdict". Nothing here refuses, defers or disposes anything; the fail-closed
gate of section "Fail-closed cost gate (keyed on `--item` presence)" keeps
reading only successful runs with a confirmed run record and never reads this.

COUNTED ONCE IS KEYED ON THE OBSERVATION IDENTITY AND NEVER ON THE ROW. The
journal is append-only, and a reconciliation replay and a resume both re-derive
the same observation from the same terminal -- so two rows carrying one
identity are one charge. Deduplicating on the whole row would count them twice
the moment anything about the second append differed, which the append layer
GUARANTEES it does: `JournalFile.append` stamps its own `at` and invoker onto
every record.

A ROW WHOSE IDENTITY CANNOT BE READ IS CARRIED, NOT DROPPED, and that asymmetry
is deliberate. Dropping it would under-report a real charge while leaving a
well-formed row behind -- the expensive direction -- so it is carried with no
identity and therefore with nothing to deduplicate on. That costs nothing: such
a row also states no readable figure, so every copy of it contributes the same
absence and the duplicates cannot move a total.

A ROW'S FIGURE IS READ AS THE ROW STATES IT, including when it states none. A
reader that substituted zero for an unstated figure would make a run nobody
could price indistinguishable from a run that genuinely cost nothing, which is
the one distinction the attempt-cost record exists to carry.

ONE UNOBSERVABLE FIGURE DARKENS THE WHOLE TOTAL, which is the same paragraph's
"If any included attempt has unobservable cost, the sequence total MUST be
unobservable; a known subtotal MAY be displayed only when explicitly labeled
incomplete." The dangerous wrong answer here is the SUBTOTAL and not zero: a
sequence whose records are mostly priced carries a plausible number, and
reporting it as the total produces a figure smaller than the truth that reads
exactly like a complete observation -- the same reason an unpriceable component
poisons one run's whole total in `_dispatcher_cost_attempts`. So the subtotal
survives as its own field, carrying the one label the clause permits, and the
total is simply absent.

THE FINAL RUN IS ONE TERM OF THE SAME SUM AND IS NOT GUARDED SEPARATELY. A
sequence whose releases are all priced and whose final run is dark is exactly
as unobservable as the other way round, and a reader that guarded only the
records would report the released attempts' spend as the whole cost of the
work. `_figures` is where that single-sum reading is stated.

THE PEER'S FOLD SEES NOTHING AT ALL -- not a share, and not a zero. A
confirmation turn run inside one item's admission evaluation establishes
availability every peer then benefits from, and charging it to each of them
would multiply one spend by the size of the queue. The record names one item,
so selecting by that name is the whole of "MUST NOT be charged in full to
multiple items".
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from livespec_orchestrator_beads_fabro.commands._acp_journal_records import journal_records
from livespec_orchestrator_beads_fabro.commands._dispatcher_cost_attempts import (
    ATTEMPT_COST_STAGE,
)

__all__: list[str] = [
    "SUBTOTAL_INCOMPLETE_LABEL",
    "AttemptCostObservation",
    "SequenceCost",
    "attempt_cost_observations",
    "item_attempt_cost_observations",
    "sequence_cost",
]

# The one label the clause permits a displayed subtotal to carry. Named here so
# every surface that renders a partial figure spells it the same way: a reader
# cannot tell a subtotal from a total except by the label, so two spellings of
# it are two chances to display one unlabelled.
SUBTOTAL_INCOMPLETE_LABEL = "incomplete"


@dataclass(frozen=True, kw_only=True)
class AttemptCostObservation:
    """One attempt-cost record, as the sequence fold reads it.

    `identity` is `None` only for a row whose own identity could not be read,
    which is carried rather than dropped per the module docstring. `usd_micros`
    is `None` for a row that states no figure -- the cost-unobservable arm of
    the record -- and is never substituted.
    """

    identity: str | None
    source: str | None
    usd_micros: int | None


@dataclass(frozen=True, kw_only=True)
class SequenceCost:
    """What one item's whole release-and-re-dispatch sequence cost.

    `usd_micros` is `None` when ANY included figure was unobservable, which is
    the clause's own rule and is deliberately not the subtotal: see the module
    docstring for why a plausible partial figure is the expensive wrong answer.

    `subtotal_usd_micros` counts every figure the sequence's records and its
    final run actually stated, and `subtotal_label` is
    `SUBTOTAL_INCOMPLETE_LABEL` exactly when it is a subtotal rather than the
    whole cost -- carried as a field rather than left to a reader to infer from
    `usd_micros`, because a renderer that forgot the inference displays a
    partial figure as a total and nothing in its output says otherwise.

    `counted_identities` names the observations that were counted -- each once
    -- so a reader can check the arithmetic against the journal rather than
    taking the total on trust.
    """

    usd_micros: int | None
    subtotal_usd_micros: int
    subtotal_label: str | None
    counted_identities: tuple[str, ...]


def attempt_cost_observations(
    *, records: Sequence[Mapping[str, Any]], work_item_id: str
) -> tuple[AttemptCostObservation, ...]:
    """Every attempt-cost observation charged to ONE item, each counted once.

    In journal order, which is the order the sequence happened in, so a reader
    comparing the fold against the file reads them the same way round.
    """
    seen: set[str] = set()
    found: list[AttemptCostObservation] = []
    for record in records:
        if record.get("stage") != ATTEMPT_COST_STAGE:
            continue
        if record.get("work_item_id") != work_item_id:
            continue
        identity = _identity(record=record)
        if identity is not None and identity in seen:
            continue
        if identity is not None:
            seen.add(identity)
        found.append(
            AttemptCostObservation(
                identity=identity,
                source=_source(record=record),
                usd_micros=_usd_micros(record=record),
            )
        )
    return tuple(found)


def item_attempt_cost_observations(
    *, journal_path: Path | None, work_item_id: str
) -> tuple[AttemptCostObservation, ...]:
    """The same fold, over one dispatch journal read through the shared reader.

    `journal_records` drops only the lines it cannot read, which is what a
    shared append-only file requires: one truncated line from a crash mid-append
    is an ordinary event, and a reader that discarded the whole file on it would
    report an item with a long release history as having spent nothing.
    """
    return attempt_cost_observations(
        records=journal_records(journal_path=journal_path), work_item_id=work_item_id
    )


def sequence_cost(
    *, observations: Sequence[AttemptCostObservation], final_run_usd_micros: int | None
) -> SequenceCost:
    """The clause's own arithmetic: these records plus the final run's cost."""
    figures = _figures(observations=observations, final_run_usd_micros=final_run_usd_micros)
    observable = all(figure is not None for figure in figures)
    subtotal = sum(figure for figure in figures if figure is not None)
    return SequenceCost(
        usd_micros=subtotal if observable else None,
        subtotal_usd_micros=subtotal,
        subtotal_label=None if observable else SUBTOTAL_INCOMPLETE_LABEL,
        counted_identities=tuple(one.identity for one in observations if one.identity is not None),
    )


def _figures(
    *, observations: Sequence[AttemptCostObservation], final_run_usd_micros: int | None
) -> tuple[int | None, ...]:
    """Every figure the sequence is made of, each as its own record stated it.

    The final run's figure rides the SAME tuple as the records', because the
    clause makes it one term of one sum and a reader that treated it separately
    would have two places to decide what an unstated figure means.
    """
    return (*(one.usd_micros for one in observations), final_run_usd_micros)


def _identity(*, record: Mapping[str, Any]) -> str | None:
    value = record.get("observation_id")
    return value if isinstance(value, str) and value else None


def _source(*, record: Mapping[str, Any]) -> str | None:
    value = record.get("source")
    return value if isinstance(value, str) and value else None


def _usd_micros(*, record: Mapping[str, Any]) -> int | None:
    """The figure this row states, or `None` when it states none.

    `bool` is excluded explicitly: a JSON `true` is an `int` in Python and is
    never a valid micro-USD count, so admitting one would price a sequence at
    one micro-USD per malformed row.
    """
    value = record.get("usd_micros")
    return value if isinstance(value, int) and not isinstance(value, bool) else None
