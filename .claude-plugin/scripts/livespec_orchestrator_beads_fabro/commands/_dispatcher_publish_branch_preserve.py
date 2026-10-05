"""Copying a surviving publish branch's head onto its own ref, then clearing it.

The MECHANICS of the publish-branch reclaim. `_dispatcher_publish_branch_reclaim`
owns the decision of whether to act and the journal record of what happened;
this module performs the two remote operations and reports which one failed, so
the sequence that makes the act safe lives in one place and is not restated by
any caller.

PRESERVE, THEN CLEAR -- IN THAT ORDER, AND NEVER THE CLEAR ALONE. The dead run's
tip is copied onto a ref of its own under `refs/livespec/preserved-publish/` and
the branch is deleted only once ORIGIN has confirmed that ref. This is the shape
the maintainer's export-then-reap rule takes for a dead factory run: what makes an
irreversible act safe is the durable copy that precedes it, so a preserve that
failed returns a failure and the branch is left standing.

NO SPELLING OF FORCE PUSH APPEARS HERE. The ratified stages clause of
`SPECIFICATION/contracts.md` grants a lease-guarded force push to the `pr` node
ALONE; the preserve is a plain push of a ref nothing else writes, and the clear is
a delete. The capability the graph withheld from `publish_draft` is not reacquired
on its behalf here.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandRunner

__all__: list[str] = [
    "HELD_DELETE_FAILED",
    "HELD_PRESERVE_FAILED",
    "PRESERVED_PUBLISH_REF_PREFIX",
    "PreserveFailure",
    "Reclaimed",
    "SurvivingPublishBranch",
    "preserve_and_clear",
    "preserved_publish_ref",
]

# The namespace the preserved head lives in. Under `refs/livespec/` rather than
# `refs/heads/`, so a preserved head is never a branch: it is not checked out, not
# pushed to by anything, and not a candidate for any branch-hygiene sweep.
PRESERVED_PUBLISH_REF_PREFIX = "refs/livespec/preserved-publish"

# The two reasons these mechanics hold a reclaim, carried on the failure they
# return so the caller's record names the operation that failed rather than a
# generic one.
HELD_PRESERVE_FAILED = "preserve-failed"
HELD_DELETE_FAILED = "delete-failed"

_GIT_TIMEOUT_SECONDS = 120.0


@dataclass(frozen=True, kw_only=True)
class SurvivingPublishBranch:
    """A publish branch origin still carries, and the head it points at."""

    branch: str
    head: str


@dataclass(frozen=True, kw_only=True)
class Reclaimed:
    """The branch is gone and its head is preserved at `preserved_ref`."""

    preserved_ref: str


@dataclass(frozen=True, kw_only=True)
class PreserveFailure:
    """Neither operation completed, or only the preserve did; the branch stands.

    Carries the HOLD REASON as well as the detail, because which operation failed
    is what an operator acts on: a failed preserve means nothing was copied, while
    a failed delete means the head IS preserved and only the branch remains.
    """

    reason: str
    detail: str


def preserved_publish_ref(*, work_item_id: str, head: str) -> str:
    """The ref a dead run's published head is preserved under.

    The HEAD is part of the ref name, which is what makes the preserve a CREATE
    rather than an update: two different dead heads for one item preserve to two
    refs, and a repeat of the same reclaim pushes the same sha to the same ref,
    which origin accepts as already up to date.
    """
    return f"{PRESERVED_PUBLISH_REF_PREFIX}/{work_item_id}/{head}"


def preserve_and_clear(
    *,
    runner: CommandRunner,
    repo: Path,
    work_item_id: str,
    surviving: SurvivingPublishBranch,
) -> Reclaimed | PreserveFailure:
    """Copy the head onto its own ref, then delete the branch it came from."""
    preserved = preserved_publish_ref(work_item_id=work_item_id, head=surviving.head)
    failure = _preserve(runner=runner, repo=repo, surviving=surviving, preserved=preserved)
    if failure is not None:
        return PreserveFailure(reason=HELD_PRESERVE_FAILED, detail=failure)
    deleted = runner.run(
        argv=["git", "push", "origin", "--delete", f"refs/heads/{surviving.branch}"],
        cwd=repo,
        timeout_seconds=_GIT_TIMEOUT_SECONDS,
    )
    if deleted.exit_code != 0:
        return PreserveFailure(
            reason=HELD_DELETE_FAILED,
            detail=(
                f"git push origin --delete refs/heads/{surviving.branch} exited"
                f" {deleted.exit_code}; the head is preserved at {preserved} but the"
                " branch still stands, so publish_draft will still refuse"
            ),
        )
    return Reclaimed(preserved_ref=preserved)


def _preserve(
    *,
    runner: CommandRunner,
    repo: Path,
    surviving: SurvivingPublishBranch,
    preserved: str,
) -> str | None:
    """Copy origin's branch tip onto the preservation ref; a failure detail or None.

    TWO legs, and both are checked, because only the second makes the copy
    DURABLE: the fetch brings the head into this clone, and the push is what puts
    it somewhere a later reader can reach. A caller that checked only the fetch
    would delete the branch whose copy never left the host.
    """
    fetched = runner.run(
        argv=["git", "fetch", "origin", f"+refs/heads/{surviving.branch}:{preserved}"],
        cwd=repo,
        timeout_seconds=_GIT_TIMEOUT_SECONDS,
    )
    if fetched.exit_code != 0:
        return (
            f"git fetch origin +refs/heads/{surviving.branch}:{preserved} exited"
            f" {fetched.exit_code}; the head {surviving.head} was not copied, so the"
            " branch is left standing"
        )
    pushed = runner.run(
        argv=["git", "push", "origin", f"{preserved}:{preserved}"],
        cwd=repo,
        timeout_seconds=_GIT_TIMEOUT_SECONDS,
    )
    if pushed.exit_code != 0:
        return (
            f"git push origin {preserved}:{preserved} exited {pushed.exit_code}; the"
            f" head {surviving.head} is on this host only, so the branch is left"
            " standing"
        )
    return None
