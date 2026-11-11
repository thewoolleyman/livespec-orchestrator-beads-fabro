"""Durably mark the seed ruling a launched run has consumed."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

__all__: list[str] = [
    "SEED_RULING_CONSUMED_STAGE",
    "SeedRulingConsumption",
    "record_seed_ruling_consumption",
]

SEED_RULING_CONSUMED_STAGE = "seed-ruling-consumed"
_MARKER = "livespec-seed-ruling-consumed"


@dataclass(frozen=True, kw_only=True)
class SeedRulingConsumption:
    """The immutable identity of one seeded ruling's launched run."""

    work_item_id: str
    preservation_ref: str
    commit_sha: str
    ruling_instant: str
    dispatch_id: str
    run_id: str


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
