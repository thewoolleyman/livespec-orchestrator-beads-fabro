"""Durable operator instructions selecting a released item's recovery seed."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandRunner
from livespec_orchestrator_beads_fabro.commands._dispatcher_goal import minijinja_openers_in_text

__all__: list[str] = [
    "SEED_RULING_MARKER",
    "SeedRuling",
    "record_verified_seed_ruling",
    "seed_ruling_comment_body",
    "verify_seed_ruling",
]

SEED_RULING_MARKER = "livespec-seed-ruling"
_LS_REMOTE_FIELDS = 2


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


def verify_seed_ruling(*, runner: CommandRunner, repo: Path, ruling: SeedRuling) -> str:
    """Return the ruled SHA, or a durable hold detail when origin disagrees.

    A ruled ref is an immutable instruction only while origin itself still
    advertises the exact object. The detail deliberately includes every fact
    an operator needs to repair a moved or deleted ref without consulting a
    local clone, whose remote-tracking state may be stale.
    """
    result = runner.run(
        argv=["git", "ls-remote", "origin", ruling.preservation_ref],
        cwd=repo,
        timeout_seconds=120.0,
    )
    observed = _observed_commit(stdout=result.stdout, ref=ruling.preservation_ref)
    if observed is not None and observed == ruling.commit_sha:
        return observed
    named = "absent" if observed is None else observed
    return (
        f"ruled seed ref {ruling.preservation_ref} expected {ruling.commit_sha} "
        f"but origin observed {named}"
    )


def record_verified_seed_ruling(
    *,
    ruling: SeedRuling,
    verified_commit: str,
    append_comment: Callable[[str], None],
    append_journal: Callable[[dict[str, object]], None],
) -> str | None:
    """Persist one origin-verified ruling, or return the refusal before any write.

    The journal record omits `invoker`: the journal's append layer stamps it
    once and refuses a record that supplies its own.
    """
    if verified_commit != ruling.commit_sha:
        return (
            f"ruled seed ref {ruling.preservation_ref} expected {ruling.commit_sha} "
            f"but origin observed {verified_commit or 'absent'}"
        )
    body = seed_ruling_comment_body(
        work_item_id=ruling.work_item_id,
        preservation_ref=ruling.preservation_ref,
        commit_sha=ruling.commit_sha,
        invoker=ruling.invoker,
        reason=ruling.reason,
        instant=ruling.instant,
    )
    findings = minijinja_openers_in_text(source="seed ruling", text=body)
    if findings:
        return "template opener present: " + ", ".join(one.opener for one in findings)
    append_comment(body)
    append_journal(
        {
            "stage": "seed-ruling",
            "work_item_id": ruling.work_item_id,
            "preservation_ref": ruling.preservation_ref,
            "commit_sha": ruling.commit_sha,
            "reason": ruling.reason,
            "instant": ruling.instant,
        }
    )
    return None


def _observed_commit(*, stdout: str, ref: str) -> str | None:
    """Read only the requested exact ref from `git ls-remote` output."""
    for line in stdout.splitlines():
        fields = line.split("\t")
        if len(fields) == _LS_REMOTE_FIELDS and fields[1] == ref:
            return fields[0]
    return None
