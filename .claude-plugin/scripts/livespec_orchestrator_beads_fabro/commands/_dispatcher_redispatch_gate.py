"""The across-dispatch progress gate: refuse a claim whose history stopped advancing.

`SPECIFICATION/contracts.md`'s across-dispatch required-result progress clause makes
admission compare each completed attempt with the high-water mark that preceded
it, and refuse the NEXT claim once the committed
`dispatcher.redispatch_no_progress_limit` attempts failed to advance it.  This is
that refusal, run by the pre-dispatch wall before any claim exists, and the drain
filter that keeps one refused item from stopping the queue behind it.

THE GATE READS NOTHING FOR AN ITEM WITH NO HISTORY.  A first dispatch needs no
repetition policy, so a repository that has never dispatched the item is not
refused for lacking one; the moment there is history to count, a missing or
invalid limit refuses with its configuration diagnostic instead of an implicit
count.

A TYPED CAUSAL RECOVERY AUTHORIZES ONE EPOCH.  The gate only RECORDS the
authorization (`authorized`); `consume_authorized_recoveries` spends it, and the
wall calls that last, after every other refusal has passed, so a dispatch the
wall goes on to refuse does not burn the recovery.  A spent attempt id stays
spent because its consumption is an append-only ledger comment.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from pathlib import Path
from typing import cast

from livespec_orchestrator_beads_fabro._store_comments import append_work_item_comment
from livespec_orchestrator_beads_fabro.commands._acp_factory_run_reader import FactoryRunReader
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import JournalFile
from livespec_orchestrator_beads_fabro.commands._dispatcher_item_ledger_reads import (
    read_dispatch_comments,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_journal_rows import journal_records
from livespec_orchestrator_beads_fabro.commands._dispatcher_paths import store_config
from livespec_orchestrator_beads_fabro.commands._dispatcher_redispatch_history import (
    RecordedRun,
    RunPayloadReader,
    attempts_from_runs,
    recorded_runs,
    with_diagnosed,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_redispatch_policy import (
    redispatch_no_progress_limit,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_redispatch_progress import (
    CompletedAttempt,
    RedispatchProgressDecision,
    RedispatchRecovery,
    redispatch_progress_decision,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_redispatch_recovery_record import (
    consumed_attempt_ids,
    parse_recovery_comments,
    render_consumed_comment,
)
from livespec_orchestrator_beads_fabro.types import WorkItem

__all__: list[str] = [
    "CommentBodiesReader",
    "consume_authorized_recoveries",
    "redispatch_progress_refusal",
    "redispatch_unrefused_candidates",
]

CommentBodiesReader = Callable[[WorkItem], Sequence[str] | str]

_RECORD_COMMAND = "dispatcher.py record-redispatch-recovery"


def redispatch_progress_refusal(
    *,
    repo: Path,
    items: Sequence[WorkItem],
    journal: JournalFile,
    run_payload: RunPayloadReader | None = None,
    comment_bodies: CommentBodiesReader | None = None,
    authorized: list[tuple[str, str]],
) -> str | None:
    """The first item's refusal text, or `None` when every item may be claimed.

    `authorized` collects `(item id, recovery attempt id)` for each item a fresh
    typed recovery admitted, for the wall to spend once the whole wall passes.
    """
    if not items:
        return None
    records = journal_records(journal=journal)
    for item in items:
        runs = recorded_runs(records=records, item_id=item.id)
        if not runs:
            continue
        refusal = _item_refusal(
            repo=repo,
            item=item,
            runs=runs,
            run_payload=run_payload or _factory_payload(repo=repo),
            comment_bodies=comment_bodies or _ledger_bodies(repo=repo),
            authorized=authorized,
        )
        if refusal is not None:
            return refusal
    return None


def redispatch_unrefused_candidates(
    *, items: Sequence[WorkItem], repo: Path, journal: JournalFile
) -> list[WorkItem]:
    """The candidates the gate admits, so one refused row cannot stop the queue.

    The wall refuses its WHOLE selection on one item; without this filter the
    drain would keep picking a refused row and never reach the work behind it.
    It consumes nothing.
    """
    return [
        item
        for item in items
        if redispatch_progress_refusal(repo=repo, items=(item,), journal=journal, authorized=[])
        is None
    ]


def consume_authorized_recoveries(*, repo: Path, authorized: Sequence[tuple[str, str]]) -> None:
    """Spend each recovery attempt the gate admitted, for good."""
    for item_id, attempt_id in authorized:
        append_work_item_comment(
            path=store_config(repo=repo),
            work_item_id=item_id,
            body=render_consumed_comment(attempt_id=attempt_id),
        )


def _item_refusal(
    *,
    repo: Path,
    item: WorkItem,
    runs: Sequence[RecordedRun],
    run_payload: RunPayloadReader,
    comment_bodies: CommentBodiesReader,
    authorized: list[tuple[str, str]],
) -> str | None:
    limit = redispatch_no_progress_limit(repo=repo)
    if isinstance(limit, str):
        return f"LIVESPEC_REDISPATCH_POLICY_INVALID: {item.id} cannot be graded: {limit}"
    bodies = comment_bodies(item)
    if isinstance(bodies, str):
        return f"LIVESPEC_REDISPATCH_LEDGER_UNREADABLE: {item.id}: {bodies}"
    recoveries = parse_recovery_comments(bodies=bodies)
    spent = consumed_attempt_ids(bodies=bodies)
    covered = frozenset(
        run_id
        for recovery in recoveries
        if recovery.attempt_id in spent
        for run_id in recovery.prior_run_ids
    )
    attempts = attempts_from_runs(runs=runs, run_payload=run_payload)
    base = _graded(limit=limit, attempts=attempts, covered=covered)
    if base.refusal is None and base.diagnosis is None:
        return None
    for recovery in reversed(recoveries):
        decision = _graded(
            limit=limit,
            attempts=attempts,
            covered=covered,
            recovery=recovery,
            spent=spent,
        )
        if decision.authorized_recovery_attempt_id is not None:
            authorized.append((item.id, decision.authorized_recovery_attempt_id))
            return None
    return _refusal_text(item=item, decision=base, attempts=attempts)


def _graded(
    *,
    limit: int,
    attempts: tuple[CompletedAttempt, ...],
    covered: frozenset[str],
    recovery: RedispatchRecovery | None = None,
    spent: frozenset[str] = frozenset(),
) -> RedispatchProgressDecision:
    """The decision, re-run once per run a consumed diagnosis recovery covers."""
    diagnosed: set[str] = set()
    while True:
        decision = redispatch_progress_decision(
            limit=limit,
            attempts=with_diagnosed(attempts=attempts, run_ids=frozenset(diagnosed)),
            recovery=recovery,
            consumed_recovery_attempt_ids=spent,
        )
        run_id = decision.diagnosis_run_id
        if run_id is None or run_id in diagnosed or run_id not in covered:
            return decision
        diagnosed.add(run_id)


def _refusal_text(
    *, item: WorkItem, decision: RedispatchProgressDecision, attempts: tuple[CompletedAttempt, ...]
) -> str:
    refusal = decision.refusal
    if refusal is not None:
        named = ", ".join(
            f"{run_id} ({cause})"
            for run_id, cause in zip(refusal.run_ids, refusal.causes, strict=True)
        )
        head = (
            f"LIVESPEC_REDISPATCH_NO_PROGRESS: {item.id} is refused before claim: "
            f"{len(refusal.run_ids)} consecutive item-attributable attempts did not advance past "
            f"the prior high-water mark; runs: {named}; high-water milestone: "
            f"{refusal.high_water_milestone}."
        )
        prior = refusal.run_ids
    else:
        history = [attempt.run_id for attempt in attempts if attempt.completed]
        diagnosed = cast("str", decision.diagnosis_run_id)
        prior = tuple(history[: history.index(diagnosed) + 1])
        head = (
            f"LIVESPEC_REDISPATCH_DIAGNOSIS_REQUIRED: {item.id} is refused before claim: "
            f"{decision.diagnosis}."
        )
    flags = " ".join(f"--prior-run {run_id}" for run_id in prior)
    return (
        f"{head} Record a fresh typed causal recovery attempt before another epoch: "
        f"{_RECORD_COMMAND} --item {item.id} --attempt-id <fresh id> {flags} "
        "--diagnosis <measured diagnosis> --operation <executable operation> "
        "--execution-evidence <receipt>. It authorizes exactly one dispatch and does not "
        "change the original required-result deadline."
    )


def _factory_payload(*, repo: Path) -> RunPayloadReader:
    reader = FactoryRunReader(repo=repo)
    return lambda factory, run_id: reader.inspect_payload(factory=factory, run_id=run_id)


def _ledger_bodies(*, repo: Path) -> CommentBodiesReader:
    return lambda item: _comment_bodies(repo=repo, item=item)


def _comment_bodies(*, repo: Path, item: WorkItem) -> Sequence[str] | str:
    comments = read_dispatch_comments(repo=repo, item=item)
    if isinstance(comments, str):
        return comments
    return tuple(comment.text for comment in comments)
