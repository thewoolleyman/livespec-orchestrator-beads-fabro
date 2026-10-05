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
failed returns a failure and the branch is left standing. "FAILED" means the head
is not on the ref, which is a weaker claim than "the create call returned
non-zero" -- see `_preserve`, where the difference decides whether a retry of the
failed-delete arm can ever complete.

BOTH OPERATIONS GO THROUGH THE FORGE REFERENCE INTERFACE, AND NEITHER THROUGH
`git push`. The Dispatcher runs from the host's PRIMARY CHECKOUT, which carries
the commit-refuse pre-push hook: it refuses EVERY push with `livespec: refusing
commit/push at primary checkout; use a worktree` and exit 1. A `git push` spelled
here can therefore never succeed on a real dispatching host -- which is exactly
how the first build of this reclaim passed its proof and failed in use, because
that proof ran inside a factory sandbox clone, where the primary-checkout
condition the hook keys on is absent. Measured 2026-10-05 on `bd-ib-pa73qh`: the
reclaim judged the earlier run dead, the preserve push exited 1, the branch was
left standing, and run 01M456V9X8SHX5FASEQCVGYRF5 was then refused at
`publish_draft`, non-fast-forward, exactly as before the fix. The hook is neither
weakened nor bypassed to fix this: the transport moves to the one interface the
hook does not mediate, which is the same correction `bd-ib-cewr.4` made to the
pre-run push precondition for the same reason.

NO SPELLING OF REF REWRITE APPEARS HERE. The ratified stages clause of
`SPECIFICATION/contracts.md` grants a lease-guarded force push to the `pr` node
ALONE; the preserve CREATES a ref nothing else writes, and the clear DELETES the
branch. Neither reaches the forge's reference-UPDATE interface, which is what a
force push spells over this transport, so the capability the graph withheld from
`publish_draft` is not reacquired on its behalf.
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

_FORGE_TIMEOUT_SECONDS = 120.0

# The forge's reference endpoints, addressed through `gh api` so `{owner}` and
# `{repo}` resolve from the repository the command runs in -- which keeps this
# module out of the business of parsing a remote URL to name its own repository.
#
# The READ endpoint is the SINGULAR `git/ref/...`, which resolves one EXACT ref.
# The plural `git/matching-refs/...` form is a PREFIX match, and the preservation
# ref ends in the very sha under question, so a prefix answer could attribute one
# head's preservation to another -- the same reason `surviving_head_from_ls_remote`
# matches on the full ref and nothing looser.
_REFS_ENDPOINT = "/repos/{owner}/{repo}/git/refs"
_REF_ENDPOINT = "/repos/{owner}/{repo}/git/ref"


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
    refs, and a repeat of the same reclaim addresses the same sha at the same ref,
    which is a no-op rather than a rewrite.
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
        argv=_delete_ref_argv(ref=f"refs/heads/{surviving.branch}"),
        cwd=repo,
        timeout_seconds=_FORGE_TIMEOUT_SECONDS,
    )
    if deleted.exit_code != 0:
        return PreserveFailure(
            reason=HELD_DELETE_FAILED,
            detail=(
                f"deleting refs/heads/{surviving.branch} through the forge reference"
                f" interface exited {deleted.exit_code}; the head is preserved at"
                f" {preserved} but the branch still stands, so publish_draft will still"
                " refuse"
            ),
        )
    return Reclaimed(preserved_ref=preserved)


def _ref_path_segment(*, ref: str) -> str:
    """The trailing segment the forge addresses a fully-qualified ref by.

    The endpoints carry the `refs` component in the PATH, so the ref travels
    without it: `refs/heads/feat/x` is addressed as `.../git/refs/heads/feat/x`.
    """
    return ref.removeprefix("refs/")


def _create_ref_argv(*, ref: str, sha: str) -> list[str]:
    """Create `ref` at `sha` on the forge.

    `--raw-field` rather than the typed form, because `gh`'s typed fields coerce a
    value that LOOKS like a number and an all-digit object name is a valid sha --
    which would reach the forge as an integer and be refused for its shape rather
    than for anything about the ref.
    """
    return [
        "gh",
        "api",
        "--method",
        "POST",
        _REFS_ENDPOINT,
        "--raw-field",
        f"ref={ref}",
        "--raw-field",
        f"sha={sha}",
    ]


def _read_ref_argv(*, ref: str) -> list[str]:
    """Ask the forge what object, if any, it carries at `ref`."""
    return [
        "gh",
        "api",
        f"{_REF_ENDPOINT}/{_ref_path_segment(ref=ref)}",
        "--jq",
        ".object.sha",
    ]


def _delete_ref_argv(*, ref: str) -> list[str]:
    """Delete `ref` on the forge."""
    return [
        "gh",
        "api",
        "--method",
        "DELETE",
        f"{_REFS_ENDPOINT}/{_ref_path_segment(ref=ref)}",
    ]


def _forge_ref_head(*, runner: CommandRunner, repo: Path, ref: str) -> str:
    """The sha origin reports at `ref`, or the empty string when it reports none.

    The empty string covers BOTH "origin says there is no such ref" and "origin
    could not be asked", and collapsing them is safe HERE and only here: this
    answer is used to CONFIRM a preserve, so every non-answer must fail to confirm.
    A caller using it to authorize a deletion would need the distinction the
    reclaim's `PublishBranchUnobservable` draws; this one holds either way.
    """
    result = runner.run(
        argv=_read_ref_argv(ref=ref), cwd=repo, timeout_seconds=_FORGE_TIMEOUT_SECONDS
    )
    if result.exit_code != 0:
        return ""
    return result.stdout.strip()


def _preserve(
    *,
    runner: CommandRunner,
    repo: Path,
    surviving: SurvivingPublishBranch,
    preserved: str,
) -> str | None:
    """Put the head on the preservation ref; a failure detail, or None.

    ONE call on the happy path, and it is the DURABLE one: the ref is created on
    origin directly from the sha origin itself reported, so there is no local copy
    to confuse with a remote one. The earlier build fetched the head into this
    clone first and then pushed it, which made the local leg look like half the
    work when it was none of it.

    A REFUSED CREATE IS NOT YET A FAILED PRESERVE, and settling that is what the
    second call is for. The forge refuses a create for a ref that already stands,
    and this ref is NAMED after the head it carries, so the second reclaim of a
    head already preserved meets that refusal on a ref holding exactly the right
    object. That state is reached by the failed-delete arm -- the branch stands and
    the ref is in place -- so a build reading the exit code alone would strand the
    recovery on every retry of precisely the arm that must retry. Only an
    UNCONFIRMED ref holds the reclaim, and the detail names both shas, because an
    operator deciding what to do with the surviving branch has to know which object
    actually survived.
    """
    created = runner.run(
        argv=_create_ref_argv(ref=preserved, sha=surviving.head),
        cwd=repo,
        timeout_seconds=_FORGE_TIMEOUT_SECONDS,
    )
    if created.exit_code == 0:
        return None
    confirmed = _forge_ref_head(runner=runner, repo=repo, ref=preserved)
    if confirmed == surviving.head:
        return None
    return (
        f"creating {preserved} at {surviving.head} through the forge reference"
        f" interface exited {created.exit_code}, and origin reports {confirmed!r} at"
        f" that ref rather than {surviving.head}; the head was not preserved, so the"
        " branch is left standing"
    )
