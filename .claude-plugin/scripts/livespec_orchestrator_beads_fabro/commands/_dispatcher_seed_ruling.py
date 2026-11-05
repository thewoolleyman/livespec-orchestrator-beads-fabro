"""Durable operator instructions selecting a released item's recovery seed."""

from __future__ import annotations

from dataclasses import dataclass

__all__: list[str] = [
    "SEED_RULING_MARKER",
    "SeedRuling",
    "latest_unconsumed_seed_ruling",
    "seed_ruling_comment_body",
]

SEED_RULING_MARKER = "livespec-seed-ruling"


@dataclass(frozen=True, kw_only=True)
class SeedRuling:
    """One append-only instruction that can be read from any checkout's ledger."""

    work_item_id: str
    preservation_ref: str
    commit_sha: str
    invoker: str
    reason: str
    instant: str


def seed_ruling_comment_body(
    *,
    work_item_id: str,
    preservation_ref: str,
    commit_sha: str,
    invoker: str,
    reason: str,
    instant: str,
) -> str:
    """Render one append-only ruling with every fact a later reader needs."""
    return "\n".join(
        (
            SEED_RULING_MARKER,
            f"work-item: {work_item_id}",
            f"preservation-ref: {preservation_ref}",
            f"commit-sha: {commit_sha}",
            f"invoker: {invoker}",
            f"reason: {reason}",
            f"instant: {instant}",
        )
    )


def latest_unconsumed_seed_ruling(
    *, comments: tuple[str, ...], consumed_instants: frozenset[str]
) -> SeedRuling | None:
    """Return the newest parseable ruling not already consumed by a launch."""
    rulings = tuple(_ruling_from_comment(comment=one) for one in comments)
    eligible = tuple(
        one for one in rulings if one is not None and one.instant not in consumed_instants
    )
    return eligible[-1] if eligible else None


def _ruling_from_comment(*, comment: str) -> SeedRuling | None:
    """Decode the stable body shape; unrelated or malformed comments are inert."""
    lines = comment.splitlines()
    if not lines or lines[0] != SEED_RULING_MARKER:
        return None
    fields = dict(line.split(": ", 1) for line in lines[1:] if ": " in line)
    required = (
        "work-item",
        "preservation-ref",
        "commit-sha",
        "invoker",
        "reason",
        "instant",
    )
    if any(not isinstance(fields.get(name), str) or not fields[name] for name in required):
        return None
    return SeedRuling(
        work_item_id=fields["work-item"],
        preservation_ref=fields["preservation-ref"],
        commit_sha=fields["commit-sha"],
        invoker=fields["invoker"],
        reason=fields["reason"],
        instant=fields["instant"],
    )
