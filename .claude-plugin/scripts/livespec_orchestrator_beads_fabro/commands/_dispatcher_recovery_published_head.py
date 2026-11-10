"""The published-head sources of the recovery seed: the surviving head and earlier preserved heads.

Split out of `_dispatcher_recovery_preserved` along the cohesion seam of the
sources that read the publish branch or the reclaim's preserved-publish refs,
leaving that module the terminal-tree and checkpoint-failed-tree sources and the
order they are asked in. This module owns its own unobservable answer, as
`_dispatcher_recovery_wip` does, and the caller converts it, so the dependency
runs one way only.

The seed names the preserved-publish ref the RECLAIM creates, never the publish
branch itself: the reclaim deletes that branch before the run starts, so a seed
naming the branch would fetch a ref that no longer exists.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandRunner
from livespec_orchestrator_beads_fabro.commands._dispatcher_needs_human_refs import refs_by_name
from livespec_orchestrator_beads_fabro.commands._dispatcher_publish_branch_preserve import (
    PRESERVED_PUBLISH_REF_PREFIX,
    preserved_publish_ref,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_publish_branch_reclaim import (
    PublishBranchUnobservable,
    surviving_publish_branch,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_recovery_measurements import (
    MEASUREMENT_PRESERVED_WORK,
    MEASUREMENT_PUBLISHING_RUN_UNOBSERVABLE,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_recovery_routes import RecoverySeed
from livespec_orchestrator_beads_fabro.commands._dispatcher_recovery_run_age import (
    published_head_relation,
)

__all__: list[str] = [
    "PublishedHeadUnobservable",
    "earlier_head_seed",
    "leading_identifier",
    "newer_published_head_seed",
    "published_head_seed",
]

_SEED_REMOTE = "origin"
_GIT_TIMEOUT_SECONDS = 120.0


@dataclass(frozen=True, kw_only=True)
class PublishedHeadUnobservable:
    """Origin or the journal could not ANSWER a published-head question.

    A distinct type rather than `None`, so a caller cannot read "we could not
    look" as "there is nothing there".  `measurement` is the stable token the
    recovery-held record names, so an operator sees which read failed.
    """

    detail: str
    measurement: str = MEASUREMENT_PRESERVED_WORK


def newer_published_head_seed(
    *,
    runner: CommandRunner,
    repo: Path,
    work_item_id: str,
    terminal: RecoverySeed,
    records: tuple[dict[str, object], ...],
    publications: tuple[tuple[str, str], ...],
) -> RecoverySeed | PublishedHeadUnobservable | None:
    """Return a head a later run published, or ``None`` when the terminal ref stands.

    A terminal ref normally wins because it is the complete tree the failed run
    preserved.  The journal is the exception's evidence: when it names the
    branch tip as a later run's publication, choosing the older terminal tree
    would discard the item's newer work.  A surviving head that no journal row
    names is NOT a reason to keep the terminal ref: the clause holds the item
    whenever a head and a competing ref both exist and either run cannot be
    established, so the comparison runs for an ordinary published draft too.
    """
    published = published_head_seed(runner=runner, repo=repo, work_item_id=work_item_id)
    if published is None or isinstance(published, PublishedHeadUnobservable):
        return None
    relation = published_head_relation(
        records=records,
        preserved_run_id=terminal.source_run_id,
        published_head=published.commit_sha,
        publications=publications,
    )
    if relation is None:
        return PublishedHeadUnobservable(
            measurement=MEASUREMENT_PUBLISHING_RUN_UNOBSERVABLE,
            detail=(
                "publishing-run-unobservable: the recovery branch head and a"
                " competing preserved ref are both readable, but the journal cannot"
                " attribute one of them to a publishing run; neither tree is reclaimed"
            ),
        )
    return published if relation else None


def published_head_seed(
    *,
    runner: CommandRunner,
    repo: Path,
    work_item_id: str,
    earlier_run_ids: tuple[str, ...] = (),
) -> RecoverySeed | PublishedHeadUnobservable | None:
    """The observed published head, named by the ref the reclaim will preserve it at.

    See the module docstring for why the seed names that ref rather than the
    publish branch it was read off.
    """
    surviving = surviving_publish_branch(runner=runner, repo=repo, work_item_id=work_item_id)
    if isinstance(surviving, PublishBranchUnobservable):
        return PublishedHeadUnobservable(detail=surviving.detail)
    if surviving is None:
        return None
    return RecoverySeed(
        source_run_id=leading_identifier(identifiers=earlier_run_ids),
        remote=_SEED_REMOTE,
        commit_sha=surviving.head,
        preservation_ref=preserved_publish_ref(work_item_id=work_item_id, head=surviving.head),
    )


def earlier_head_seed(
    *,
    runner: CommandRunner,
    repo: Path,
    work_item_id: str,
    earlier_run_ids: tuple[str, ...],
) -> RecoverySeed | PublishedHeadUnobservable | None:
    """A preserved-publish ref an EARLIER reclaim of this item left behind.

    Last in the order, because the clause ranks it below the observed published
    head: such a ref carries a head this item has already moved past. It is still
    preserved work rather than absence, which is the whole reason it is asked at
    all — a dispatch from the default branch "with that loss recorded" would be
    recording a loss that had not happened.

    The ref name ENDS in the head it carries, so `ls-remote`'s own refname
    ordering is the only ordering available and the last line is taken. That is
    arbitrary between two preserved heads and deterministic for one reading,
    which is the most this source can honestly offer: nothing in the ref says
    which of two earlier heads is newer.
    """
    pattern = f"{PRESERVED_PUBLISH_REF_PREFIX}/{work_item_id}/*"
    result = runner.run(
        argv=["git", "ls-remote", _SEED_REMOTE, pattern],
        cwd=repo,
        timeout_seconds=_GIT_TIMEOUT_SECONDS,
    )
    if result.exit_code != 0:
        return PublishedHeadUnobservable(
            detail=(
                f"git ls-remote {_SEED_REMOTE} {pattern} exited {result.exit_code};"
                " whether an earlier reclaim of this item preserved a head could not"
                " be established, so no seed was taken and absence is not confirmed"
            )
        )
    found = refs_by_name(stdout=result.stdout)
    if not found:
        return None
    ref = sorted(found)[-1]
    return RecoverySeed(
        source_run_id=leading_identifier(identifiers=earlier_run_ids),
        remote=_SEED_REMOTE,
        commit_sha=found[ref],
        preservation_ref=ref,
    )


def leading_identifier(*, identifiers: tuple[str, ...]) -> str:
    """The newest identifier the earlier run answers to, or the empty string.

    The empty string rather than `None`, because the seed record's `source_run_id`
    is a field an operator reads to find the run on its factory and a record whose
    other fields are present says more than no record at all. Every arm that
    reaches here read a ref that names no run — the two lower-preference seeds and
    the confirmed absence — so there is nothing better to offer; the arm that CAN
    name one, the needs-human ref, takes it from the ref itself.
    """
    return identifiers[0] if identifiers else ""
