"""The failed run's preserved work, as origin reports it, in the clause's own order.

`SPECIFICATION/contracts.md` section "Factory-configurable ACP fallback priority"
→ "Recovery from the failed run's preserved work" fixes both the preference order
and what a seed must carry: "The Dispatcher MUST prefer the failed run's
successfully preserved terminal tree (the pushed ref a needs-human ending
preserves)... then its observed published head or the corresponding
preserved-publish ref... The seed record MUST name the source run, remote,
immutable commit SHA, and preservation reference."

THREE SOURCES, ASKED IN THAT ORDER, AND EACH ONE STOPS THE SEARCH. The order is
not a tidy ranking: the needs-human ref carries the run's TERMINAL tree, which is
everything the dying run had, while the publish-branch tip carries only what it
had published — so taking the second when the first exists discards work that was
preserved precisely so it would not be lost. The preserved-publish ref of an
EARLIER head ranks below the observed head for the mirror reason, and it is asked
last so the common case pays one round trip rather than three.

WHY EVERY ANSWER IS A COMMIT ORIGIN ITSELF NAMED. "Verified" is the clause's word
and this is what it is made of: the seed's SHA is the object origin reported at a
ref origin reported, never a local object and never a sha this process computed.
A local reading answers a question about this clone's last fetch, which is the
same correction `bd-ib-cewr.4` made to the pre-run push precondition.

WHY AN UNREADABLE REFERENCE IS ITS OWN ANSWER. "An unreadable reference is not
confirmed absence." The two support opposite decisions — one permits a plain
dispatch from the default branch with the loss recorded, the other must wait and
retry — and once the distinction has been collapsed nothing downstream can
recover it: a dispatch from the default branch is exactly how a preserved tree
nobody could read becomes a preserved tree nobody will ever use.

ONE PROPERTY OF THE PUBLISH-BRANCH ARM AN EDITOR MUST NOT INVERT. Its seed names
the preserved-publish ref the RECLAIM creates, not the publish branch itself,
because the reclaim deletes that branch before the run starts — so a seed naming
the branch would fetch a ref that no longer exists by the time the sandbox asks
for it. The reclaim creates the ref, confirms origin carries the head at it, and
only then deletes the branch, which is the "verify preservation before deleting
the publish branch" half of the clause. When that preserve FAILS the reclaim holds
with the branch standing and the ref absent, so the seeded run fails loudly in
preparation rather than running against whatever the clone happens to carry.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandRunner
from livespec_orchestrator_beads_fabro.commands._dispatcher_publish_branch_preserve import (
    PRESERVED_PUBLISH_REF_PREFIX,
    preserved_publish_ref,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_publish_branch_reclaim import (
    PublishBranchUnobservable,
    surviving_publish_branch,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_recovery_routes import RecoverySeed

__all__: list[str] = [
    "NEEDS_HUMAN_REF_PREFIX",
    "SEED_REMOTE",
    "PreservedWorkUnobservable",
    "verified_preserved_seed",
]

# Where a needs-human ending pushes the run's terminal tree. The ref is per RUN
# rather than per item, which is what lets the seed name the source run from the
# ref it was found at rather than from a separate reading that could disagree.
NEEDS_HUMAN_REF_PREFIX = "refs/heads/needs-human"

# The remote every one of these refs is read from and the seed therefore names.
# One constant because the seed record's `remote` field and the `ls-remote`
# argument have to be the same remote, and two spellings of it is how a record
# comes to describe a read that was taken somewhere else.
SEED_REMOTE = "origin"

_GIT_TIMEOUT_SECONDS = 120.0

# `git ls-remote` prints exactly two tab-separated fields per ref.
_LS_REMOTE_FIELDS = 2


@dataclass(frozen=True, kw_only=True)
class PreservedWorkUnobservable:
    """Origin could not be ASKED whether preserved work exists.

    A distinct type rather than `None`, so a caller cannot read "we could not
    look" as "there is nothing there" — the same line the reclaim's own
    `PublishBranchUnobservable` draws, and for the same reason.
    """

    detail: str


def verified_preserved_seed(
    *,
    runner: CommandRunner,
    repo: Path,
    work_item_id: str,
    earlier_run_ids: tuple[str, ...],
) -> RecoverySeed | PreservedWorkUnobservable | None:
    """The seed the failed run's preserved work supports: one, unaskable, or none.

    `None` is CONFIRMED ABSENCE — every source was asked and named nothing — which
    is what permits a plain dispatch from the default branch with the loss
    recorded.
    """
    terminal = _needs_human_seed(runner=runner, repo=repo, earlier_run_ids=earlier_run_ids)
    if terminal is not None:
        return terminal
    published = _published_head_seed(
        runner=runner, repo=repo, work_item_id=work_item_id, earlier_run_ids=earlier_run_ids
    )
    if published is not None:
        return published
    return _earlier_head_seed(
        runner=runner, repo=repo, work_item_id=work_item_id, earlier_run_ids=earlier_run_ids
    )


def _needs_human_seed(
    *, runner: CommandRunner, repo: Path, earlier_run_ids: tuple[str, ...]
) -> RecoverySeed | PreservedWorkUnobservable | None:
    """The terminal tree a needs-human ending preserved, for the newest run naming one.

    ONE `ls-remote` for every identifier the earlier run answers to, because the
    cost of asking about an identifier that was never a run id is a pattern that
    matches nothing, while a call per identifier would be a round trip per
    identifier. The identifiers arrive newest-first — the anchoring record's own
    run leads — so the FIRST one origin answered for is the newest preserved tree.
    """
    if not earlier_run_ids:
        return None
    result = runner.run(
        argv=[
            "git",
            "ls-remote",
            SEED_REMOTE,
            *(f"{NEEDS_HUMAN_REF_PREFIX}/{one}" for one in earlier_run_ids),
        ],
        cwd=repo,
        timeout_seconds=_GIT_TIMEOUT_SECONDS,
    )
    if result.exit_code != 0:
        return PreservedWorkUnobservable(
            detail=(
                f"git ls-remote {SEED_REMOTE} {NEEDS_HUMAN_REF_PREFIX}/<run> exited"
                f" {result.exit_code} for {len(earlier_run_ids)} earlier-run"
                " identifier(s); whether the failed run preserved its terminal tree"
                " could not be established, so no seed was taken and the publish"
                " branch is left exactly as it stands"
            )
        )
    found = _refs_by_name(stdout=result.stdout)
    for one in earlier_run_ids:
        ref = f"{NEEDS_HUMAN_REF_PREFIX}/{one}"
        commit = found.get(ref)
        if commit is not None:
            return RecoverySeed(
                source_run_id=one,
                remote=SEED_REMOTE,
                commit_sha=commit,
                preservation_ref=ref,
            )
    return None


def _published_head_seed(
    *,
    runner: CommandRunner,
    repo: Path,
    work_item_id: str,
    earlier_run_ids: tuple[str, ...],
) -> RecoverySeed | PreservedWorkUnobservable | None:
    """The observed published head, named by the ref the reclaim will preserve it at.

    See the module docstring for why the seed names that ref rather than the
    publish branch it was read off.
    """
    surviving = surviving_publish_branch(runner=runner, repo=repo, work_item_id=work_item_id)
    if isinstance(surviving, PublishBranchUnobservable):
        return PreservedWorkUnobservable(detail=surviving.detail)
    if surviving is None:
        return None
    return RecoverySeed(
        source_run_id=_leading(identifiers=earlier_run_ids),
        remote=SEED_REMOTE,
        commit_sha=surviving.head,
        preservation_ref=preserved_publish_ref(work_item_id=work_item_id, head=surviving.head),
    )


def _earlier_head_seed(
    *,
    runner: CommandRunner,
    repo: Path,
    work_item_id: str,
    earlier_run_ids: tuple[str, ...],
) -> RecoverySeed | PreservedWorkUnobservable | None:
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
        argv=["git", "ls-remote", SEED_REMOTE, pattern],
        cwd=repo,
        timeout_seconds=_GIT_TIMEOUT_SECONDS,
    )
    if result.exit_code != 0:
        return PreservedWorkUnobservable(
            detail=(
                f"git ls-remote {SEED_REMOTE} {pattern} exited {result.exit_code};"
                " whether an earlier reclaim of this item preserved a head could not"
                " be established, so no seed was taken and absence is not confirmed"
            )
        )
    found = _refs_by_name(stdout=result.stdout)
    if not found:
        return None
    ref = sorted(found)[-1]
    return RecoverySeed(
        source_run_id=_leading(identifiers=earlier_run_ids),
        remote=SEED_REMOTE,
        commit_sha=found[ref],
        preservation_ref=ref,
    )


def _refs_by_name(*, stdout: str) -> dict[str, str]:
    """Every ref `ls-remote` named, mapped to the object it reported at it.

    Keyed by the FULL ref, which is what makes the lookups above exact: a prefix
    or suffix test would attribute one run's preserved tree to another, and the
    answer authorizes a checkout.
    """
    named: dict[str, str] = {}
    for line in stdout.splitlines():
        fields = line.split()
        if len(fields) == _LS_REMOTE_FIELDS:
            named[fields[1]] = fields[0]
    return named


def _leading(*, identifiers: tuple[str, ...]) -> str:
    """The newest identifier the earlier run answers to, or the empty string.

    The empty string rather than `None`, because the seed record's `source_run_id`
    is a field an operator reads to find the run on its factory and a record whose
    other three fields are present says more than no record at all. The two arms
    that reach here read a ref that names no run, so there is nothing better to
    offer; the arm that CAN name one — the needs-human ref — takes it from the ref
    itself.
    """
    return identifiers[0] if identifiers else ""
