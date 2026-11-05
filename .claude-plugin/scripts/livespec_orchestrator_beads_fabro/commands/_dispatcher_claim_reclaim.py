"""WIP-cap accounting for active dispatch claims.

This module deliberately chooses WIP-slot reclamation for readable
green-terminal active rows. Bounding by age would still delay recovery behind
an arbitrary clock threshold, and deferral-only surfacing was already shipped
by bd-ib-snyquw.1 but fires after capacity has been refused. Reclaiming here
addresses accumulated stale occupancy; bd-ib-vfsg addresses the upstream
green-outcome race that creates new rows in this state.

The counted total is TENANT-scoped, not per-checkout: a live dispatch lock is
looked for across EVERY checkout of this repository's tenant, because the lock
is written under the invoking `--repo` path and N checkouts otherwise admitted
up to N x `wip_cap` independently (bd-ib-snyquw.6). The widening only ever ADDS
lock-backed rows, so neither guarantee below moves: a green-terminal row is
still reclaimed and uncounted, and an unreadable journal still counts MORE.

A live lock alone is not a held run slot (bd-ib-rtzhfc). A dispatcher keeps
its lock through the post-run legs that follow its factory run, so a row
whose current dispatch has a STAMPED run that the stamp's factory no longer
lists as live is exposed as `ended_run_active_ids` and does not count against
`wip_cap`. `_dispatcher_claim_live_runs.RunSlotBoard` answers that question and
carries the reasoning; both of its fallbacks keep the row counted.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import cast

from livespec_orchestrator_beads_fabro.commands._dispatcher_claim_live_runs import RunSlotBoard
from livespec_orchestrator_beads_fabro.commands._dispatcher_dispatch_lock import (
    live_dispatch_lock,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import JournalFile
from livespec_orchestrator_beads_fabro.commands._dispatcher_tenant_checkouts import (
    tenant_checkouts,
)
from livespec_orchestrator_beads_fabro.effects import AttemptFailure, attempt, parse_json
from livespec_orchestrator_beads_fabro.types import WorkItem

__all__: list[str] = [
    "ActiveClaimAccounting",
    "ActiveClaimHold",
    "claimed_active_accounting",
    "claimed_active_count",
    "claimed_active_projection",
]


@dataclass(frozen=True, kw_only=True)
class ActiveClaimHold:
    work_item_id: str
    reason: str
    backed_by_live_watchable_run: bool


@dataclass(frozen=True, kw_only=True)
class ActiveClaimAccounting:
    """The accounting's own verdict over the `active` rows, class by class.

    `rework_pending_active_ids` is EXPOSED rather than merely excluded from
    `active_count`: a caller composing capacity truth must consume this
    accounting's verdict, and re-deriving the rework class from the raw ledger
    label would put a second authority on the same question.
    """

    active_count: int
    live_lock_active_ids: tuple[str, ...]
    green_terminal_active_ids: tuple[str, ...]
    journal_unreadable_active_ids: tuple[str, ...]
    rework_pending_active_ids: tuple[str, ...] = ()
    ended_run_active_ids: tuple[str, ...] = ()
    actionable_holds: tuple[ActiveClaimHold, ...] = field(default=(), compare=False)


@dataclass(frozen=True, kw_only=True)
class _TerminalHistory:
    last_admit_index: int | None = None
    last_outcome_index: int | None = None
    last_outcome_status: str | None = None


def claimed_active_count(*, repo: Path, items: list[WorkItem], journal: JournalFile) -> int:
    return claimed_active_accounting(repo=repo, items=items, journal=journal).active_count


def claimed_active_projection(
    *, repo: Path, items: list[WorkItem], journal: JournalFile
) -> ActiveClaimAccounting:
    return _claimed_active_accounting(
        repo=repo,
        items=items,
        journal=journal,
        record_abandonment=False,
    )


def claimed_active_accounting(
    *, repo: Path, items: list[WorkItem], journal: JournalFile
) -> ActiveClaimAccounting:
    return _claimed_active_accounting(
        repo=repo,
        items=items,
        journal=journal,
        record_abandonment=True,
    )


def _claimed_active_accounting(
    *,
    repo: Path,
    items: list[WorkItem],
    journal: JournalFile,
    record_abandonment: bool,
) -> ActiveClaimAccounting:
    checkouts = tenant_checkouts(repo=repo)
    histories: dict[str, _TerminalHistory] | None = None
    live_lock_active_ids: list[str] = []
    green_terminal_active_ids: list[str] = []
    journal_unreadable_active_ids: list[str] = []
    rework_pending_active_ids: list[str] = []
    ended_run_active_ids: list[str] = []
    actionable_holds: list[ActiveClaimHold] = []
    slots = RunSlotBoard(repo=repo, journal=journal)
    for item in items:
        if item.status != "active":
            continue
        if _claim_held_live_in_tenant(checkouts=checkouts, work_item_id=item.id):
            (
                live_lock_active_ids
                if slots.holds_run_slot(work_item_id=item.id)
                else ended_run_active_ids
            ).append(item.id)
            continue
        if item.rework_pending:
            # A marked, lock-less `active` row is a SANCTIONED park awaiting its
            # fix-forward re-dispatch, not a leak: excluded from the capacity
            # count and never recorded as an abandoned claim. The classification
            # sits after the live-lock check because the double-selection guard
            # is the lock, never the marker.
            rework_pending_active_ids.append(item.id)
            continue
        if histories is None:
            histories = _terminal_histories(journal=journal)
        if histories is None:
            journal_unreadable_active_ids.append(item.id)
            actionable_holds.append(
                ActiveClaimHold(
                    work_item_id=item.id,
                    reason="journal-unreadable",
                    backed_by_live_watchable_run=False,
                )
            )
            continue
        history = histories.get(item.id)
        if _green_terminal_after_latest_admit(history=history):
            green_terminal_active_ids.append(item.id)
        elif not record_abandonment and history is None:
            actionable_holds.append(
                ActiveClaimHold(
                    work_item_id=item.id,
                    reason="no-outcome-since-ledger-admit",
                    backed_by_live_watchable_run=False,
                )
            )
        if record_abandonment:
            journal.append(record=_abandoned_record(item=item, history=history))
    return ActiveClaimAccounting(
        active_count=(len(live_lock_active_ids) + len(journal_unreadable_active_ids)),
        live_lock_active_ids=tuple(live_lock_active_ids),
        green_terminal_active_ids=tuple(green_terminal_active_ids),
        journal_unreadable_active_ids=tuple(journal_unreadable_active_ids),
        rework_pending_active_ids=tuple(rework_pending_active_ids),
        ended_run_active_ids=tuple(ended_run_active_ids),
        actionable_holds=tuple(actionable_holds),
    )


def _claim_held_live_in_tenant(*, checkouts: tuple[Path, ...], work_item_id: str) -> bool:
    """Does ANY checkout of this tenant hold a live lock on this row?

    ANY, not the invoking one: every checkout pushes to the same
    `origin/master`, so the merge/rebase contention the cap exists to bound is
    a tenant-level property and a checkout-scoped answer does not constrain it.
    """
    return any(
        live_dispatch_lock(repo=checkout, work_item_id=work_item_id) is not None
        for checkout in checkouts
    )


def _green_terminal_after_latest_admit(*, history: _TerminalHistory | None) -> bool:
    if history is None or history.last_outcome_index is None:
        return False
    if (
        history.last_admit_index is not None
        and history.last_outcome_index < history.last_admit_index
    ):
        return False
    return history.last_outcome_status == "green"


def _terminal_histories(*, journal: JournalFile) -> dict[str, _TerminalHistory] | None:
    lines = _journal_lines(path=journal.path)
    if lines is None:
        return None
    histories: dict[str, _TerminalHistory] = {}
    for index, line in enumerate(lines):
        record = _journal_record(line=line)
        if record is None:
            continue
        _record_history(histories=histories, index=index, record=record)
    return histories


def _journal_lines(*, path: Path) -> tuple[str, ...] | None:
    read = attempt(action=lambda: path.read_text(encoding="utf-8"), exceptions=(OSError,))
    if isinstance(read, AttemptFailure):
        return None
    return tuple(line for line in read.splitlines() if line)


def _journal_record(*, line: str) -> dict[str, object] | None:
    parsed = parse_json(text=line)
    if not isinstance(parsed, dict):
        return None
    return cast("dict[str, object]", parsed)


def _record_history(
    *, histories: dict[str, _TerminalHistory], index: int, record: dict[str, object]
) -> None:
    if record.get("stage") == "ledger-admit":
        work_item_id = record.get("work_item_id")
        if isinstance(work_item_id, str):
            histories[work_item_id] = _with_admit(history=histories.get(work_item_id), index=index)
    if record.get("stage") == "outcome":
        outcome = record.get("outcome")
        if isinstance(outcome, dict):
            _record_outcome(
                histories=histories,
                index=index,
                outcome=cast("dict[str, object]", outcome),
            )


def _record_outcome(
    *, histories: dict[str, _TerminalHistory], index: int, outcome: dict[str, object]
) -> None:
    work_item_id = outcome.get("work_item_id")
    status = outcome.get("status")
    if isinstance(work_item_id, str) and isinstance(status, str):
        histories[work_item_id] = _with_outcome(
            history=histories.get(work_item_id), index=index, status=status
        )


def _with_admit(*, history: _TerminalHistory | None, index: int) -> _TerminalHistory:
    if history is None:
        return _TerminalHistory(last_admit_index=index)
    return _TerminalHistory(
        last_admit_index=index,
        last_outcome_index=history.last_outcome_index,
        last_outcome_status=history.last_outcome_status,
    )


def _with_outcome(*, history: _TerminalHistory | None, index: int, status: str) -> _TerminalHistory:
    if history is None:
        return _TerminalHistory(last_outcome_index=index, last_outcome_status=status)
    return _TerminalHistory(
        last_admit_index=history.last_admit_index,
        last_outcome_index=index,
        last_outcome_status=status,
    )


def _abandoned_record(*, item: WorkItem, history: _TerminalHistory | None) -> dict[str, object]:
    if (
        history is None
        or history.last_outcome_index is None
        or (
            history.last_admit_index is not None
            and history.last_outcome_index < history.last_admit_index
        )
    ):
        reason = "no-outcome-since-ledger-admit"
    elif history.last_outcome_status == "green":
        reason = "green-terminal-active-reclaimed"
    else:
        reason = "terminal-outcome-non-green"
    return {
        "stage": "dispatch-claim-abandoned",
        "work_item_id": item.id,
        "status": item.status,
        "reason": reason,
    }
