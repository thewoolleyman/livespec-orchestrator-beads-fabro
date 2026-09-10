"""What the dispatch journal knows, and which work-item each run belongs to.

This is the reconciler's first layer: it turns one factory's raw run
inventory into rows that name a work-item, a ledger status, and the
moot-question reason — if any — that the ledger has for releasing the run.
Deciding what to DO about a row belongs to the classifier above it
(`_dispatcher_reconcile_runs_join.py`).

Four properties of the attribution are deliberate rather than incidental.

A run whose work-item is `active` and whose newest journaled run id IS this
run is never an orphan, even when no dispatcher process is watching it. A
remote run outlives the process that launched it, so "no local process is
watching" is a statement about this host, never about the work.

Destructive attribution accepts recorded facts only: ledger metadata, then
the journal. Goal text is intentionally excluded. It is rendered prose from
the run rather than an ownership record, so it may inform read-only surfaces
but can never authorize cancellation.

The caller contributes only its ledger metadata index. THIS pass builds its
own journal index from typed launch stamps; accepting a caller's untyped
journal map would let outcome or reconciliation records bypass that filter.

Runs that neither this tenant's ledger stamp nor this tenant's dispatch
journal names are OUT OF SCOPE entirely. The family factories are shared —
a dozen tenants submit to the same server — so a text-prefix test is not an
ownership boundary: one tenant prefix can be a prefix of another tenant's
work-item ids. Recorded launch data is the boundary.

Every status kind Fabro can hold that is not terminal is considered. The
predecessor sweep looked only at `runnable` / `running`, which is precisely
why a run parked at the in-loop human gate was never looked at again.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from livespec_orchestrator_beads_fabro.commands._fabro_port_records import FabroRunSummary
from livespec_orchestrator_beads_fabro.commands._run_attribution import (
    GOAL_TEXT_ONLY,
    RunAttribution,
)
from livespec_orchestrator_beads_fabro.effects import (
    AttemptFailure,
    JsonParseFailure,
    attempt,
    parse_json,
)

__all__: list[str] = [
    "ATTRIBUTION_SOURCE_GOAL_TEXT",
    "ATTRIBUTION_SOURCE_JOURNAL",
    "ATTRIBUTION_SOURCE_METADATA",
    "NON_TERMINAL_STATUS_KINDS",
    "ORPHAN_REASON_ITEM_MISSING",
    "ORPHAN_REASON_ITEM_NOT_ACTIVE",
    "ORPHAN_REASON_SUPERSEDED_RUN",
    "AttributedRun",
    "FactoryRunInventory",
    "JournaledRuns",
    "attributed_runs",
    "journaled_runs",
    "read_journaled_runs",
]

NON_TERMINAL_STATUS_KINDS: tuple[str, ...] = (
    "blocked",
    "paused",
    "runnable",
    "running",
    "starting",
)

ORPHAN_REASON_ITEM_MISSING = "item-missing"
ORPHAN_REASON_ITEM_NOT_ACTIVE = "item-not-active"
ORPHAN_REASON_SUPERSEDED_RUN = "superseded-run"

_ACTIVE_STATUS = "active"
ATTRIBUTION_SOURCE_METADATA = "metadata"
ATTRIBUTION_SOURCE_JOURNAL = "journal"
ATTRIBUTION_SOURCE_GOAL_TEXT = "goal-text"
# Only the launch stamp is an ownership fact. Outcome and reconciliation
# records may repeat a run id, but accepting those would let an earlier
# inference bootstrap authority for a later destructive pass.
_OWNERSHIP_JOURNAL_STAGES = ("dispatch-run-stamp",)
# Retain both historical spellings within launch stamps.
_RUN_ID_KEYS = ("fabro_run_id", "run_id")


@dataclass(frozen=True, kw_only=True)
class JournaledRuns:
    """What the dispatch journal knows about run-to-item association.

    `newest_run_id_by_item` is last-write-wins over the journal's own append
    order, so a re-dispatch supersedes the run its predecessor recorded.
    """

    newest_run_id_by_item: Mapping[str, str]
    item_id_by_run: Mapping[str, str]


@dataclass(frozen=True, kw_only=True)
class FactoryRunInventory:
    """One factory's run inventory and everything the join reads it against.

    `allow_goal_text_attribution` is observation-only. Destructive callers keep
    it false so rendered prose can never authorize cancellation; diagnostic
    callers may opt in and expose that weaker source explicitly on the row.

    `only_work_item_id` narrows the GRACE arm alone, and only because that arm
    costs a `fabro inspect` per governed run: a targeted pass measures its own
    item's parks and nobody else's. A run it narrows away keeps whatever
    moot-question reason the ledger already had for it, so a targeted pass and
    a sweep still agree about every run they both act on.
    """

    runs: Sequence[FabroRunSummary]
    item_statuses: Mapping[str, str]
    journaled: JournaledRuns
    id_prefix: str
    factory_name: str
    factory_server_url: str
    attribution: RunAttribution = GOAL_TEXT_ONLY
    only_work_item_id: str | None = None
    allow_goal_text_attribution: bool = False


@dataclass(frozen=True, kw_only=True)
class AttributedRun:
    """One non-terminal run joined to its work-item and its moot-question reason.

    `base_reason` is `None` when the LEDGER is still waiting on this run. That
    is not the same as "leave it alone": the grace arm above this layer takes
    a parked run with no moot reason and bounds how long it may hold a slot.
    """

    run: FabroRunSummary
    work_item_id: str
    attribution_source: str
    work_item_status: str | None
    base_reason: str | None


def journaled_runs(*, text: str) -> JournaledRuns:
    """Index authoritative launch stamps by work-item and by run id."""
    newest: dict[str, str] = {}
    item_by_run: dict[str, str] = {}
    for line in text.splitlines():
        record = _record(line=line)
        if record is None:
            continue
        if record.get("stage") not in _OWNERSHIP_JOURNAL_STAGES:
            continue
        work_item_id = _str_value(value=record.get("work_item_id"))
        run_id = _run_id(record=record)
        if work_item_id is None or run_id is None:
            continue
        newest[work_item_id] = run_id
        item_by_run[run_id] = work_item_id
    return JournaledRuns(newest_run_id_by_item=newest, item_id_by_run=item_by_run)


def read_journaled_runs(*, path: Path) -> JournaledRuns:
    """Read the dispatch journal, treating an unreadable file as no knowledge.

    An absent journal is the ordinary state of a fresh clone, and it must not
    make the join louder: with no journaled run ids the `superseded-run` arm
    simply never fires, and every other arm still holds.
    """
    read = attempt(action=lambda: path.read_text(encoding="utf-8"), exceptions=(OSError,))
    if isinstance(read, AttemptFailure):
        return JournaledRuns(newest_run_id_by_item={}, item_id_by_run={})
    return journaled_runs(text=read)


def attributed_runs(*, inventory: FactoryRunInventory) -> tuple[AttributedRun, ...]:
    """Every in-scope non-terminal run, joined to its item and its moot reason."""
    resolved = _resolved_attribution(inventory=inventory)
    rows: list[AttributedRun] = []
    for run in inventory.runs:
        attributed = _recorded_attribution(
            run=run,
            attribution=resolved,
            id_prefix=inventory.id_prefix,
            allow_goal_text=inventory.allow_goal_text_attribution,
        )
        if run.status_kind not in NON_TERMINAL_STATUS_KINDS or attributed is None:
            continue
        work_item_id, attribution_source = attributed
        work_item_status = inventory.item_statuses.get(work_item_id)
        rows.append(
            AttributedRun(
                run=run,
                work_item_id=work_item_id,
                attribution_source=attribution_source,
                work_item_status=work_item_status,
                base_reason=_orphan_reason(
                    work_item_id=work_item_id,
                    work_item_status=work_item_status,
                    run_id=run.run_id,
                    journaled=inventory.journaled,
                ),
            )
        )
    return tuple(rows)


def _resolved_attribution(*, inventory: FactoryRunInventory) -> RunAttribution:
    return RunAttribution(
        metadata_run_ids=inventory.attribution.metadata_run_ids,
        journal_run_ids=inventory.journaled.item_id_by_run,
    )


def _recorded_attribution(
    *,
    run: FabroRunSummary,
    attribution: RunAttribution,
    id_prefix: str,
    allow_goal_text: bool,
) -> tuple[str, str] | None:
    metadata = attribution.metadata_run_ids.get(run.run_id)
    if metadata is not None:
        return metadata, ATTRIBUTION_SOURCE_METADATA
    journaled = attribution.journal_run_ids.get(run.run_id)
    if journaled is not None:
        return journaled, ATTRIBUTION_SOURCE_JOURNAL
    goal_text = run.work_item_id
    if allow_goal_text and goal_text is not None and goal_text.startswith(f"{id_prefix}-"):
        return goal_text, ATTRIBUTION_SOURCE_GOAL_TEXT
    return None


def _orphan_reason(
    *,
    work_item_id: str,
    work_item_status: str | None,
    run_id: str,
    journaled: JournaledRuns,
) -> str | None:
    if work_item_status is None:
        return ORPHAN_REASON_ITEM_MISSING
    if work_item_status != _ACTIVE_STATUS:
        return ORPHAN_REASON_ITEM_NOT_ACTIVE
    newest = journaled.newest_run_id_by_item.get(work_item_id)
    if newest is not None and newest != run_id:
        return ORPHAN_REASON_SUPERSEDED_RUN
    return None


def _record(*, line: str) -> Mapping[str, object] | None:
    parsed = parse_json(text=line)
    if isinstance(parsed, JsonParseFailure) or not isinstance(parsed, dict):
        return None
    return cast("Mapping[str, object]", cast("dict[str, Any]", parsed))


def _run_id(*, record: Mapping[str, object]) -> str | None:
    for key in _RUN_ID_KEYS:
        value = _str_value(value=record.get(key))
        if value is not None:
            return value
    return None


def _str_value(*, value: object) -> str | None:
    if not isinstance(value, str):
        return None
    return value or None
