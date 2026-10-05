"""Clearing a dead run's surviving publish branch, preserving its head first.

A run that dies AFTER publishing its branch leaves that branch on origin, and the
re-dispatch meant to recover it cannot publish: `publish_draft` pushes a plain
fast-forward, the new run's HEAD is not a descendant of the dead run's tip, and
origin refuses it under `LIVESPEC_PUBLISH_DRAFT_PUSH_FAILED`. That sentinel's own
remedy -- clear the stale publish branch and re-dispatch -- is what discards the
dead run's published head, so the single documented recovery costs the proof it
was meant to rescue. Measured 2026-10-05 on `bd-ib-qm4luz`: run
01M44F9E56XCEWZNMVJX4M14Z6 published pull request 2581, captured and verified its
Proof of Done there and was approved, then died at the `pr` stage; re-dispatch
01M44PQW4DAJF5J6N1XQNYVKX3 was refused at `publish_draft`, non-fast-forward. In
the same hour `bd-ib-gp2nt5` needed its publish branch preserved and deleted BY
HAND before a re-dispatch could publish.

WHY THE HOST SIDE DOES THIS AND NOT `publish_draft`. The ratified stages clause of
`SPECIFICATION/contracts.md` grants a lease-guarded force push to the `pr` node
ALONE and says `publish_draft` "MUST NOT rewrite any other ref"; the node's own
comment in the graph records why a force push must not be added there to smooth
this case over. So the branch is cleared BEFORE the run exists, by the one party
that can answer the question the sandbox cannot -- whether the run that pushed
that branch is still alive. `publish_draft` is unchanged and still pushes a plain
fast-forward, which is now the ordinary case for a re-dispatch as well as a first
dispatch.

PRESERVE, THEN CLEAR -- IN THAT ORDER, AND NEVER THE CLEAR ALONE. The dead run's
tip is copied onto a ref of its own under `refs/livespec/preserved-publish/` and
the branch is deleted only once origin has CONFIRMED that ref. This is the shape
the maintainer's export-then-reap rule takes for a dead factory run: what makes an
irreversible act safe is the durable copy that precedes it, so a preserve that
failed leaves the branch standing rather than proceeding. The copy is a plain
push of a ref nothing else writes, so no spelling of force push appears anywhere
in this module -- the capability the graph withheld from `publish_draft` is not
re-acquired here on its behalf.

EVERY ARM THAT CANNOT MEASURE HOLDS, AND SAYS SO. Origin unreachable, a failed
preserve, a failed delete: each leaves the branch alone and journals which
measurement stopped the reclaim. A gauge that proceeded when blinded would turn
`publish_draft`'s honest refusal into a silent ref deletion, and the record it
left would read exactly like a healthy reclaim.
"""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import (
    CommandRunner,
    JournalWriter,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import (
    JournalFile,
    ShellCommandRunner,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_proof_precondition import (
    publish_branch_for,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_reflection_journal import (
    read_journal_records,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_tdd_probe import dispatch_ids_for
from livespec_orchestrator_beads_fabro.commands._run_attribution import journaled_run_ids
from livespec_orchestrator_beads_fabro.types import WorkItem

__all__: list[str] = [
    "HELD_DELETE_FAILED",
    "HELD_ORIGIN_UNOBSERVABLE",
    "HELD_PRESERVE_FAILED",
    "PRESERVED_PUBLISH_REF_PREFIX",
    "PUBLISH_BRANCH_RECLAIM_HELD_STAGE",
    "PUBLISH_BRANCH_RECLAIM_STAGE",
    "PublishBranchUnobservable",
    "SurvivingPublishBranch",
    "journaled_dispatch_ids",
    "preserved_publish_ref",
    "reclaim_stale_publish_branch",
    "reclaim_stale_publish_branches",
    "surviving_head_from_ls_remote",
    "surviving_publish_branch",
]

# The namespace the preserved head lives in. Under `refs/livespec/` rather than
# `refs/heads/`, so a preserved head is never a branch: it is not checked out, not
# pushed to by anything, and not a candidate for any branch-hygiene sweep.
PRESERVED_PUBLISH_REF_PREFIX = "refs/livespec/preserved-publish"

PUBLISH_BRANCH_RECLAIM_STAGE = "publish-branch-reclaim"
PUBLISH_BRANCH_RECLAIM_HELD_STAGE = "publish-branch-reclaim-held"

# The reasons a reclaim was NOT performed. Each names a MEASUREMENT rather than a
# judgment, because the record's whole job is to tell an operator which question
# went unanswered before `publish_draft` refused.
HELD_ORIGIN_UNOBSERVABLE = "origin-unobservable"
HELD_PRESERVE_FAILED = "preserve-failed"
HELD_DELETE_FAILED = "delete-failed"

_GIT_TIMEOUT_SECONDS = 120.0

# `git ls-remote` prints exactly two tab-separated fields per ref, the sha and
# the ref name. Any other count is a line this parse must not read as a ref.
_LS_REMOTE_FIELDS = 2


@dataclass(frozen=True, kw_only=True)
class SurvivingPublishBranch:
    """A publish branch origin still carries, and the head it points at."""

    branch: str
    head: str


@dataclass(frozen=True, kw_only=True)
class PublishBranchUnobservable:
    """Origin could not be ASKED whether the publish branch survives.

    A distinct type rather than a `None`, so a caller cannot treat "unobservable"
    as "absent" -- the same line `verify_pr` draws between `LIVESPEC_PR_NOT_CREATED`
    and `LIVESPEC_PR_NOT_CREATED_CHECK_FAILED`, and for the same reason: "we could
    not look" must never be reported as "there is nothing there".
    """

    detail: str


def journaled_dispatch_ids(*, journal_path: Path, work_item_id: str) -> tuple[str, ...]:
    """Every identifier the dispatch journal names for earlier dispatches of one item.

    The question this answers is "has this item been dispatched before at all",
    and an ABSENT journal reads as "no" rather than raising: a caller holding a
    path that was never written is in the same position as a first dispatch.

    Both plural readers are reused rather than re-derived, for the reason
    `_dispatcher_proof_attribution` records about the same pair -- a hand-rolled
    scan of this file could only come to disagree with them, and the disagreement
    would be invisible because every reading would still be a plausible id.
    """
    records = read_journal_records(journal_path=journal_path)
    return (
        *journaled_run_ids(records=records, work_item_id=work_item_id),
        *dispatch_ids_for(records=records, work_item_id=work_item_id),
    )


def preserved_publish_ref(*, work_item_id: str, head: str) -> str:
    """The ref a dead run's published head is preserved under.

    The HEAD is part of the ref name, which is what makes the preserve a CREATE
    rather than an update: two different dead heads for one item preserve to two
    refs, and a repeat of the same reclaim pushes the same sha to the same ref,
    which origin accepts as already up to date.
    """
    return f"{PRESERVED_PUBLISH_REF_PREFIX}/{work_item_id}/{head}"


def surviving_head_from_ls_remote(*, stdout: str, branch: str) -> str | None:
    """The sha `git ls-remote` reports for one branch, or None when it names none.

    Matched on the FULL ref rather than on any looser form: `refs/heads/feat/x` is
    a prefix of `refs/heads/feat/x-2` and `refs/tags/feat/x` ends the same way, so
    a prefix or suffix test would attribute one item's branch to another item --
    and this answer authorizes a deletion.
    """
    wanted = f"refs/heads/{branch}"
    for line in stdout.splitlines():
        fields = line.split()
        if len(fields) == _LS_REMOTE_FIELDS and fields[1] == wanted:
            return fields[0]
    return None


def surviving_publish_branch(
    *, runner: CommandRunner, repo: Path, work_item_id: str
) -> SurvivingPublishBranch | PublishBranchUnobservable | None:
    """What origin says about this item's publish branch: present, absent, unaskable.

    `ls-remote` ASKS origin rather than reading a local remote-tracking ref, which
    is the same correction `bd-ib-cewr.4` made to the pre-run push precondition: a
    stale local ref answers a question about this clone's last fetch, not about
    what origin carries now.
    """
    branch = publish_branch_for(work_item_id=work_item_id)
    result = runner.run(
        argv=["git", "ls-remote", "origin", f"refs/heads/{branch}"],
        cwd=repo,
        timeout_seconds=_GIT_TIMEOUT_SECONDS,
    )
    if result.exit_code != 0:
        return PublishBranchUnobservable(
            detail=(
                f"git ls-remote origin refs/heads/{branch} exited {result.exit_code};"
                " whether a previous run's publish branch survives could not be"
                " established, so the branch is left exactly as it stands"
            )
        )
    head = surviving_head_from_ls_remote(stdout=result.stdout, branch=branch)
    if head is None:
        return None
    return SurvivingPublishBranch(branch=branch, head=head)


def reclaim_stale_publish_branches(
    *,
    args: argparse.Namespace,
    repo: Path,
    items: Sequence[WorkItem],
    journal: JournalFile,
) -> None:
    """The pre-dispatch walls' entry point: one reclaim per selected candidate.

    PER ITEM, because a publish branch is per item: the drain selects a wave, and
    a wave-level question would leave every candidate but one with its recovery
    still stuck. It takes `items` rather than ids to read like the two gates it
    stands beside in both walls, and it constructs the subprocess seam ONCE for
    the wave rather than per candidate.
    """
    runner = ShellCommandRunner()
    for item in items:
        reclaim_stale_publish_branch(
            args=args,
            repo=repo,
            work_item_id=item.id,
            journal=journal,
            journal_path=journal.path,
            runner=runner,
        )


def reclaim_stale_publish_branch(
    *,
    args: argparse.Namespace,
    repo: Path,
    work_item_id: str,
    journal: JournalWriter,
    journal_path: Path,
    runner: CommandRunner,
) -> None:
    """Preserve and clear a surviving publish branch, or hold and journal why.

    REFUSES NOTHING and returns nothing: a dispatch is never blocked by this
    valve, because every outcome it can reach is either an improvement on
    `publish_draft`'s refusal or that refusal unchanged.

    A FIRST dispatch of an item returns before asking origin anything. Only a
    PREVIOUS dispatch of this item can have left a publish branch behind, so on a
    first dispatch the question has no possible yes -- and a remote probe on a
    path that needs no answer would put a forge outage on the critical path of
    every dispatch this repository makes. That is the same early return the
    proof-assets gate beside it takes for an item carrying no `factory_captured`
    assertion, and it is the reason this valve reads the journal at all.
    """
    _ = args
    if not journaled_dispatch_ids(journal_path=journal_path, work_item_id=work_item_id):
        return
    surviving = surviving_publish_branch(runner=runner, repo=repo, work_item_id=work_item_id)
    if surviving is None:
        return
    if isinstance(surviving, PublishBranchUnobservable):
        _held(
            journal=journal,
            work_item_id=work_item_id,
            reason=HELD_ORIGIN_UNOBSERVABLE,
            detail=surviving.detail,
            branch=None,
            head=None,
        )
        return
    _preserve_and_clear(
        runner=runner,
        repo=repo,
        work_item_id=work_item_id,
        surviving=surviving,
        journal=journal,
    )


def _preserve_and_clear(
    *,
    runner: CommandRunner,
    repo: Path,
    work_item_id: str,
    surviving: SurvivingPublishBranch,
    journal: JournalWriter,
) -> None:
    """Copy the head onto its own ref, then delete the branch it came from."""
    preserved = preserved_publish_ref(work_item_id=work_item_id, head=surviving.head)
    failure = _preserve(runner=runner, repo=repo, surviving=surviving, preserved=preserved)
    if failure is not None:
        _held(
            journal=journal,
            work_item_id=work_item_id,
            reason=HELD_PRESERVE_FAILED,
            detail=failure,
            branch=surviving.branch,
            head=surviving.head,
        )
        return
    deleted = runner.run(
        argv=["git", "push", "origin", "--delete", f"refs/heads/{surviving.branch}"],
        cwd=repo,
        timeout_seconds=_GIT_TIMEOUT_SECONDS,
    )
    if deleted.exit_code != 0:
        _held(
            journal=journal,
            work_item_id=work_item_id,
            reason=HELD_DELETE_FAILED,
            detail=(
                f"git push origin --delete refs/heads/{surviving.branch} exited"
                f" {deleted.exit_code}; the head is preserved at {preserved} but the"
                " branch still stands, so publish_draft will still refuse"
            ),
            branch=surviving.branch,
            head=surviving.head,
        )
        return
    journal.append(
        record={
            "stage": PUBLISH_BRANCH_RECLAIM_STAGE,
            "work_item_id": work_item_id,
            "branch": surviving.branch,
            "head": surviving.head,
            "preserved_ref": preserved,
        }
    )


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
    it somewhere a later reader can reach. A valve that checked only the fetch
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


def _held(
    *,
    journal: JournalWriter,
    work_item_id: str,
    reason: str,
    detail: str,
    branch: str | None,
    head: str | None,
) -> None:
    """Record that no reclaim was performed, and which measurement stopped it."""
    journal.append(
        record={
            "stage": PUBLISH_BRANCH_RECLAIM_HELD_STAGE,
            "work_item_id": work_item_id,
            "reason": reason,
            "detail": detail,
            "branch": branch,
            "head": head,
        }
    )
