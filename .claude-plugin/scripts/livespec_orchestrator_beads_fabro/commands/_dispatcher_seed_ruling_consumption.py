"""Durably mark the seed ruling a launched run has consumed."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass

from livespec_orchestrator_beads_fabro.commands._dispatcher_ruling_currency import (
    SEED_RULING_CONSUMED_MARKER,
    seed_ruling_matching,
)

__all__: list[str] = [
    "SEED_RULING_CONSUMED_STAGE",
    "SeedRulingConsumption",
    "backfill_seed_ruling_consumptions",
    "backfill_seed_ruling_consumptions_from_ledger",
    "consume_seed_ruling_for_run",
    "record_seed_ruling_consumption",
]

SEED_RULING_CONSUMED_STAGE = "seed-ruling-consumed"
_MARKER = SEED_RULING_CONSUMED_MARKER


@dataclass(frozen=True, kw_only=True)
class SeedRulingConsumption:
    """The immutable identity of one seeded ruling's launched run."""

    work_item_id: str
    preservation_ref: str
    commit_sha: str
    ruling_instant: str
    dispatch_id: str
    run_id: str


@dataclass(frozen=True, kw_only=True)
class _BackfillRun:
    """The journal facts needed to repair one seeded run's missing receipt."""

    item: str
    run_id: str | None
    dispatch_id: str | None
    seed: tuple[str, str] | None


def record_seed_ruling_consumption(
    *,
    append_comment: Callable[[str], None],
    append_journal: Callable[[dict[str, object]], None],
    **facts: str,
) -> None:
    """Write the one ledger and journal receipt for a seeded run's ruling."""
    consumed = SeedRulingConsumption(**facts)
    append_comment(
        _comment_body(
            ruling_instant=consumed.ruling_instant,
            dispatch_id=consumed.dispatch_id,
            run_id=consumed.run_id,
        )
    )
    append_journal(
        {
            "stage": SEED_RULING_CONSUMED_STAGE,
            "work_item_id": consumed.work_item_id,
            "preservation_ref": consumed.preservation_ref,
            "commit_sha": consumed.commit_sha,
            "ruling_instant": consumed.ruling_instant,
            "dispatch_id": consumed.dispatch_id,
            "run_id": consumed.run_id,
        }
    )


def consume_seed_ruling_for_run(
    *,
    comments: Sequence[str],
    append_comment: Callable[[str], None],
    append_journal: Callable[[dict[str, object]], None],
    **facts: str,
) -> None:
    """Record a launched run's receipt only when its seed is a ruled seed."""
    ruling = seed_ruling_matching(
        comments=comments,
        preservation_ref=facts["preservation_ref"],
        commit_sha=facts["commit_sha"],
    )
    if ruling is None or any(
        _already_consumed(comment=comment, instant=ruling.instant) for comment in comments
    ):
        return
    record_seed_ruling_consumption(
        ruling_instant=ruling.instant,
        append_comment=append_comment,
        append_journal=append_journal,
        **facts,
    )


def _comment_body(*, ruling_instant: str, dispatch_id: str, run_id: str) -> str:
    """Render the consumed marker the shared ruling reader recognizes."""
    return "\n".join(
        (
            _MARKER,
            f"ruling-instant: {ruling_instant}",
            f"dispatch-id: {dispatch_id}",
            f"run-id: {run_id}",
        )
    )


def backfill_seed_ruling_consumptions(
    *,
    records: Sequence[Mapping[str, object]],
    comments_for_item: Callable[[str], Sequence[str]],
    append_comment: Callable[[str, str], None],
    append_journal: Callable[[dict[str, object]], None],
) -> None:
    """Backfill a consumed receipt for each seeded run lacking its ledger comment."""
    dispatches: dict[str, str] = {}
    seeds: dict[str, tuple[str, str]] = {}
    for record in records:
        item = _text(record=record, key="work_item_id")
        if item is None:
            continue
        if record.get("stage") == "dispatch-id":
            dispatch = _text(record=record, key="dispatch_id")
            if dispatch is not None:
                dispatches[item] = dispatch
        elif record.get("stage") == "recovery-route" and record.get("route") == "seeded":
            ref = _text(record=record, key="preservation_ref")
            sha = _text(record=record, key="commit_sha")
            if ref is not None and sha is not None:
                seeds[item] = (ref, sha)
        elif record.get("stage") == "fabro-run":
            _backfill_run(
                run=_BackfillRun(
                    item=item,
                    run_id=_text(record=record, key="run_id"),
                    dispatch_id=dispatches.get(item),
                    seed=seeds.get(item),
                ),
                comments_for_item=comments_for_item,
                append_comment=append_comment,
                append_journal=append_journal,
            )


def _backfill_run(
    *,
    run: _BackfillRun,
    comments_for_item: Callable[[str], Sequence[str]],
    append_comment: Callable[[str, str], None],
    append_journal: Callable[[dict[str, object]], None],
) -> None:
    """Write one receipt only when the run and its exact ruled seed are known."""
    if run.run_id is None or run.dispatch_id is None or run.seed is None:
        return
    comments = comments_for_item(run.item)
    ruling = seed_ruling_matching(
        comments=comments, preservation_ref=run.seed[0], commit_sha=run.seed[1]
    )
    if ruling is None or any(
        _already_consumed(comment=one, instant=ruling.instant) for one in comments
    ):
        return
    record_seed_ruling_consumption(
        work_item_id=run.item,
        preservation_ref=run.seed[0],
        commit_sha=run.seed[1],
        ruling_instant=ruling.instant,
        dispatch_id=run.dispatch_id,
        run_id=run.run_id,
        append_comment=lambda body: append_comment(run.item, body),
        append_journal=append_journal,
    )


def backfill_seed_ruling_consumptions_from_ledger(
    *,
    records: Sequence[Mapping[str, object]],
    comments_for_item: Callable[[str], Sequence[str]],
    append_comment: Callable[[str, str], None],
    append_journal: Callable[[dict[str, object]], None],
) -> None:
    """The reconciliation-facing named entry point for receipt repair."""
    backfill_seed_ruling_consumptions(
        records=records,
        comments_for_item=comments_for_item,
        append_comment=append_comment,
        append_journal=append_journal,
    )


def _already_consumed(*, comment: str, instant: str) -> bool:
    """Whether one comment already identifies this ruling's consumption."""
    lines = comment.splitlines()
    return bool(lines and lines[0] == _MARKER and any(instant in line for line in lines[1:]))


def _text(*, record: Mapping[str, object], key: str) -> str | None:
    """A non-empty record string, otherwise no usable identity."""
    value = record.get(key)
    return value if isinstance(value, str) and value else None
