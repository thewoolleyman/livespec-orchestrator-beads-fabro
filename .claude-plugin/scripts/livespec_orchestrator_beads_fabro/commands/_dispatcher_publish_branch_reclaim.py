"""The pre-dispatch valve that clears a dead run's surviving publish branch.

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

THIS MODULE IS THE DECISION AND THE RECORD. The measurement it decides on lives in
`_dispatcher_publish_branch_liveness` and the two remote operations live in
`_dispatcher_publish_branch_preserve`; each is a separate concern with its own
external system, and keeping them out of here is what lets the decision be read in
one screen.

EVERY ARM THAT CANNOT MEASURE HOLDS, AND SAYS SO. Origin unreachable, the factory
unaskable, a live run, a failed preserve, a failed delete: each leaves the branch
alone and journals which measurement stopped the reclaim. A gauge that proceeded
when blinded would turn `publish_draft`'s honest refusal into a silent ref
deletion, and the record it left would read exactly like a healthy reclaim.
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
from livespec_orchestrator_beads_fabro.commands._dispatcher_publish_branch_liveness import (
    item_run_liveness,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_publish_branch_preserve import (
    PreserveFailure,
    SurvivingPublishBranch,
    preserve_and_clear,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_reflection_journal import (
    read_journal_records,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_tdd_probe import dispatch_ids_for
from livespec_orchestrator_beads_fabro.commands._run_attribution import journaled_run_ids
from livespec_orchestrator_beads_fabro.types import WorkItem

__all__: list[str] = [
    "HELD_ORIGIN_UNOBSERVABLE",
    "PUBLISH_BRANCH_RECLAIM_HELD_STAGE",
    "PUBLISH_BRANCH_RECLAIM_STAGE",
    "PublishBranchUnobservable",
    "journaled_dispatch_ids",
    "reclaim_stale_publish_branch",
    "reclaim_stale_publish_branches",
    "surviving_head_from_ls_remote",
    "surviving_publish_branch",
]

PUBLISH_BRANCH_RECLAIM_STAGE = "publish-branch-reclaim"
PUBLISH_BRANCH_RECLAIM_HELD_STAGE = "publish-branch-reclaim-held"

# The reason an unaskable ORIGIN holds a reclaim. Its two siblings live with the
# measurements that produce them -- the liveness reading and the ref mechanics --
# so each reason is defined where the thing it reports on is decided.
HELD_ORIGIN_UNOBSERVABLE = "origin-unobservable"

_GIT_TIMEOUT_SECONDS = 120.0

# `git ls-remote` prints exactly two tab-separated fields per ref, the sha and
# the ref name. Any other count is a line this parse must not read as a ref.
_LS_REMOTE_FIELDS = 2


@dataclass(frozen=True, kw_only=True)
class PublishBranchUnobservable:
    """Origin could not be ASKED whether the publish branch survives.

    A distinct type rather than a `None`, so a caller cannot treat "unobservable"
    as "absent" -- the same line `verify_pr` draws between `LIVESPEC_PR_NOT_CREATED`
    and `LIVESPEC_PR_NOT_CREATED_CHECK_FAILED`, and for the same reason: "we could
    not look" must never be reported as "there is nothing there".
    """

    detail: str


@dataclass(frozen=True, kw_only=True)
class _Hold:
    """One reason no reclaim was performed, and everything its record names.

    Grouped rather than passed one parameter at a time because they are ONE fact,
    and because every arm must write the SAME key set: an operator reading the
    journal should not have to know which arm fired to know which keys to expect.
    `live_run_ids` is empty on every arm but the live-run hold, and `branch` and
    `head` are absent on the arm that could not establish them.
    """

    reason: str
    detail: str
    branch: str | None = None
    head: str | None = None
    live_run_ids: tuple[str, ...] = ()


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
    if not journaled_dispatch_ids(journal_path=journal_path, work_item_id=work_item_id):
        return
    surviving = surviving_publish_branch(runner=runner, repo=repo, work_item_id=work_item_id)
    if surviving is None:
        return
    if isinstance(surviving, PublishBranchUnobservable):
        _held(
            journal=journal,
            work_item_id=work_item_id,
            hold=_Hold(reason=HELD_ORIGIN_UNOBSERVABLE, detail=surviving.detail),
        )
        return
    liveness = item_run_liveness(
        args=args,
        repo=repo,
        work_item_id=work_item_id,
        journal_path=journal_path,
        runner=runner,
    )
    if not liveness.reclaimable:
        _held(
            journal=journal,
            work_item_id=work_item_id,
            hold=_Hold(
                reason=liveness.held_reason,
                detail=liveness.detail(branch=surviving.branch),
                branch=surviving.branch,
                head=surviving.head,
                live_run_ids=liveness.live_run_ids,
            ),
        )
        return
    _record_reclaim(
        runner=runner,
        repo=repo,
        work_item_id=work_item_id,
        surviving=surviving,
        journal=journal,
    )


def _record_reclaim(
    *,
    runner: CommandRunner,
    repo: Path,
    work_item_id: str,
    surviving: SurvivingPublishBranch,
    journal: JournalWriter,
) -> None:
    """Perform the reclaim and journal its outcome, whichever one it reached."""
    outcome = preserve_and_clear(
        runner=runner, repo=repo, work_item_id=work_item_id, surviving=surviving
    )
    if isinstance(outcome, PreserveFailure):
        _held(
            journal=journal,
            work_item_id=work_item_id,
            hold=_Hold(
                reason=outcome.reason,
                detail=outcome.detail,
                branch=surviving.branch,
                head=surviving.head,
            ),
        )
        return
    journal.append(
        record={
            "stage": PUBLISH_BRANCH_RECLAIM_STAGE,
            "work_item_id": work_item_id,
            "branch": surviving.branch,
            "head": surviving.head,
            "preserved_ref": outcome.preserved_ref,
        }
    )


def _held(*, journal: JournalWriter, work_item_id: str, hold: _Hold) -> None:
    """Record that no reclaim was performed, and which measurement stopped it."""
    journal.append(
        record={
            "stage": PUBLISH_BRANCH_RECLAIM_HELD_STAGE,
            "work_item_id": work_item_id,
            "reason": hold.reason,
            "detail": hold.detail,
            "branch": hold.branch,
            "head": hold.head,
            "live_run_ids": list(hold.live_run_ids),
        }
    )
