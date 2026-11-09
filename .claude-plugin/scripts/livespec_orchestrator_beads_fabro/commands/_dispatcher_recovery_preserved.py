"""The failed run's preserved work, as origin reports it, in the clause's own order.

`SPECIFICATION/contracts.md` section "Factory-configurable ACP fallback priority"
→ "Recovery from the failed run's preserved work" fixes both the preference order
and what a seed must carry: "The Dispatcher MUST prefer the failed run's
successfully preserved terminal tree (the pushed ref a needs-human ending
preserves)... then its observed published head or the corresponding
preserved-publish ref... The seed record MUST name the source run, remote,
immutable commit SHA, and preservation reference."

FOUR SOURCES, ASKED IN THAT ORDER, AND EACH ONE STOPS THE SEARCH. The order is
not a tidy ranking: the needs-human ref carries the run's TERMINAL tree, which is
everything the dying run had, while the publish-branch tip carries only what it
had published — so taking the second when the first exists discards work that was
preserved precisely so it would not be lost. The preserved-publish ref of an
EARLIER head ranks below the observed head for the mirror reason, and it is asked
last so the common case pays one round trip rather than four.

THE SECOND SOURCE IS THE CHECKPOINT-FAILED RUN'S PUBLISHED TREE, and its rank is
the ratified one: "A tree that nothing else carries is published to a
preservation ref" says that ref "counts as the failed run's successfully
preserved terminal tree, so it MUST be preferred over the run's observed
published head and over any preserved-publish ref of an earlier head". It sits
below the needs-human ref only because the two cannot both exist — a run whose
checkpoint failed never reached the `needs_human` node — so the order between
them decides nothing. That source is also the ONE whose seed does not name the
object at its own ref; see `_preserved_tree_seed` for why it must name the base.

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
from livespec_orchestrator_beads_fabro.commands._dispatcher_needs_human_refs import (
    NeedsHumanRefsUnobservable,
    newest_needs_human_ref,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_publish_branch_preserve import (
    PRESERVED_PUBLISH_REF_PREFIX,
    preserved_publish_ref,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_publish_branch_reclaim import (
    PublishBranchUnobservable,
    surviving_publish_branch,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_recovery_checkpoint import (
    newest_preserved_tree_row,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_recovery_routes import RecoverySeed
from livespec_orchestrator_beads_fabro.commands._dispatcher_recovery_run_age import (
    published_head_relation,
)

__all__: list[str] = [
    "NEEDS_HUMAN_REF_PREFIX",
    "PRESERVED_SOURCE_CHECKPOINT_FAILED_PUBLISHED_TREE",
    "PRESERVED_SOURCE_EARLIER_PRESERVED_PUBLISH_REF",
    "PRESERVED_SOURCE_PUBLISHED_HEAD",
    "PRESERVED_SOURCE_TERMINAL_TREE",
    "SEED_REMOTE",
    "PreservedWorkAbsent",
    "PreservedWorkUnobservable",
    "verified_preserved_seed",
]

# Where a needs-human ending pushes the run's terminal tree. The ref is per RUN
# rather than per item, which is what lets the seed name the source run from the
# ref it was found at rather than from a separate reading that could disagree.
NEEDS_HUMAN_REF_PREFIX = "refs/heads/needs-human"

# The four sources, as the stable tokens a loss record names them by. The clause
# requires a plain dispatch after confirmed absence to record that loss, and the
# row cannot be a MEASUREMENT unless it says which sources were asked: a source
# that answered nothing and a source this build never asked support opposite
# conclusions about whether the work was really lost, and neither is visible from
# the word "absent" on its own.
#
# A source added to the order above takes a token here IN THE SAME CHANGE, and
# the order of these four matches the order they are asked in. A source asked
# under no name is one a loss record stays silent about while reporting the
# absence it concluded — four round trips described as three.
PRESERVED_SOURCE_TERMINAL_TREE = "needs-human-terminal-tree"
PRESERVED_SOURCE_CHECKPOINT_FAILED_PUBLISHED_TREE = "checkpoint-failed-published-tree"
PRESERVED_SOURCE_PUBLISHED_HEAD = "observed-published-head"
PRESERVED_SOURCE_EARLIER_PRESERVED_PUBLISH_REF = "earlier-preserved-publish-ref"

# The remote every one of these refs is read from and the seed therefore names.
# One constant because the seed record's `remote` field and the `ls-remote`
# argument have to be the same remote, and two spellings of it is how a record
# comes to describe a read that was taken somewhere else.
SEED_REMOTE = "origin"

_GIT_TIMEOUT_SECONDS = 120.0

# `git ls-remote` prints exactly two tab-separated fields per ref.
_LS_REMOTE_FIELDS = 2

# The consumer end of `preserved_tree_journal_record`'s own row. Named here
# rather than spelled at the read, for the reason `_dispatcher_preserved_tree_
# base` gives about the staging row: a reader spelling a key differently from
# its writer finds nothing and reports no preserved tree, which at every
# surface is indistinguishable from a run that never published one.


@dataclass(frozen=True, kw_only=True)
class PreservedWorkUnobservable:
    """Origin could not be ASKED whether preserved work exists.

    A distinct type rather than `None`, so a caller cannot read "we could not
    look" as "there is nothing there" — the same line the reclaim's own
    `PublishBranchUnobservable` draws, and for the same reason.
    """

    detail: str


@dataclass(frozen=True, kw_only=True)
class PreservedWorkAbsent:
    """Every source that COULD be asked was asked, and each of them named nothing.

    CONFIRMED ABSENCE — the one answer that permits a plain dispatch from the
    default branch — and a TYPE rather than a bare `None` because the clause
    requires that dispatch to record the loss, and both of these fields are part
    of the loss. `source_run_id` names the run whose tree is being written off,
    which is the identifier an operator looks it up on its factory by.
    `sources_asked` names the sources this reading actually spent a round trip
    on, so a source that answered nothing is distinguishable from one that was
    never asked; it is a list rather than the full set because TWO of the four
    sources are addressed by something an item may not have — the terminal tree
    by a run identifier, the published tree by a journal row naming one — and are
    skipped entirely when it does not, so a record claiming four readings where
    two were taken reports a measurement that did not happen.
    """

    source_run_id: str
    sources_asked: tuple[str, ...]


def verified_preserved_seed(
    *,
    runner: CommandRunner,
    repo: Path,
    work_item_id: str,
    earlier_run_ids: tuple[str, ...],
    journal_records: tuple[dict[str, object], ...],
) -> RecoverySeed | PreservedWorkUnobservable | PreservedWorkAbsent:
    """The seed the failed run's preserved work supports: one, unaskable, or absent.

    THE ASKED-SOURCE LIST IS BUILT HERE, BY THE CODE THAT DOES THE ASKING, which
    is why the two SKIPPABLE sources have their own preconditions up here rather
    than inside the helpers that read them: a second expression of such a
    condition — one deciding whether to ask and one deciding whether to report
    having asked — is free to drift, and the direction it drifts in is a loss
    record naming a round trip nobody took. The terminal ref's precondition moved
    up out of `_needs_human_seed`, and the published tree's row lookup moved up
    out of `_preserved_tree_seed`, for that one reason.

    `journal_records` has NO DEFAULT, for the reason `_dispatcher_sandbox_image_
    source` gives about its own record: a default is how a caller that HAD a
    journal silently reports the answer of one that did not — here, "this item
    has no preserved tree" for an item whose tree was published minutes ago.
    """
    if not earlier_run_ids:
        return PreservedWorkUnobservable(
            detail=(
                f"{PRESERVED_SOURCE_TERMINAL_TREE} could not be asked because no earlier "
                "run identifier was observed from the anchor, dispatch journal, or ledger "
                "claim; preserved work is not confirmed absent and the publish branch is "
                "left exactly as it stands"
            )
        )
    asked: list[str] = [PRESERVED_SOURCE_TERMINAL_TREE]
    preserved = _needs_human_seed(runner=runner, repo=repo, earlier_run_ids=earlier_run_ids)
    # The published tree is named by this item's OWN journal, so with no row
    # naming one there is no ref that source could stand at and the round trip
    # would ask origin about nothing.
    published_tree = newest_preserved_tree_row(records=journal_records, work_item_id=work_item_id)
    if preserved is None and published_tree is not None:
        asked.append(PRESERVED_SOURCE_CHECKPOINT_FAILED_PUBLISHED_TREE)
        preserved = _preserved_tree_seed(runner=runner, repo=repo, named=published_tree)
    if preserved is not None:
        if isinstance(preserved, PreservedWorkUnobservable):
            return preserved
        newer_head = _newer_published_head_seed(
            runner=runner,
            repo=repo,
            work_item_id=work_item_id,
            terminal=preserved,
            records=journal_records,
        )
        return preserved if newer_head is None else newer_head
    asked.append(PRESERVED_SOURCE_PUBLISHED_HEAD)
    published = _published_head_seed(
        runner=runner, repo=repo, work_item_id=work_item_id, earlier_run_ids=earlier_run_ids
    )
    if published is not None:
        return published
    asked.append(PRESERVED_SOURCE_EARLIER_PRESERVED_PUBLISH_REF)
    earlier = _earlier_head_seed(
        runner=runner, repo=repo, work_item_id=work_item_id, earlier_run_ids=earlier_run_ids
    )
    if earlier is not None:
        return earlier
    return PreservedWorkAbsent(
        source_run_id=_leading(identifiers=earlier_run_ids), sources_asked=tuple(asked)
    )


def _needs_human_seed(
    *, runner: CommandRunner, repo: Path, earlier_run_ids: tuple[str, ...]
) -> RecoverySeed | PreservedWorkUnobservable | None:
    """The terminal tree a needs-human ending preserved: the descendant, else the newest.

    ONE `ls-remote` lists the namespace once, then a ref suffix or its tip
    trailers establishes which refs carry one of the identifiers. The choice among
    them is made by ancestry and committer time, never by the order the
    identifiers arrive in, which is oldest-first for an anchorless item.

    Called only for a non-empty identifier list, which its caller establishes for
    the reason that function's docstring gives.
    """
    found = newest_needs_human_ref(
        runner=runner,
        repo=repo,
        run_ids=earlier_run_ids,
        ref_prefix=NEEDS_HUMAN_REF_PREFIX,
        remote=SEED_REMOTE,
        timeout_seconds=_GIT_TIMEOUT_SECONDS,
    )
    if isinstance(found, NeedsHumanRefsUnobservable):
        return PreservedWorkUnobservable(
            detail=(
                f"{found.detail}, so no seed was taken and the publish branch is left"
                " exactly as it stands"
            )
        )
    if found is None:
        return None
    return RecoverySeed(
        source_run_id=found.run_id,
        remote=SEED_REMOTE,
        commit_sha=found.commit_sha,
        preservation_ref=found.ref,
        passed_over_needs_human=found.passed_over,
    )


def _preserved_tree_seed(
    *,
    runner: CommandRunner,
    repo: Path,
    named: tuple[str, str, str],
) -> RecoverySeed | PreservedWorkUnobservable | None:
    """The tree a checkpoint-failed run published, which nothing else carries.

    SECOND IN THE ORDER, AND THAT IS THE CLAUSE'S OWN WORDING: this ref "counts
    as the failed run's successfully preserved terminal tree, so it MUST be
    preferred over the run's observed published head and over any
    preserved-publish ref of an earlier head". It is asked after the needs-human
    ref only because the two are mutually exclusive in practice — a run whose
    checkpoint failed never reached the `needs_human` node, which is the whole
    incident this source exists for — so the order between them decides nothing
    and the cheaper-to-refuse source goes first.

    THE SEED NAMES THE BASE COMMIT AND NOT THE PUBLISHED ONE, which is the one
    thing about this source that must not be "simplified". The published commit
    ran no hook, passed no check suite and carries no Red/Green trailers, so it
    is a recovery artifact rather than a commit to land: the clause requires the
    seed to "record the run's base commit as the seed's immutable commit SHA and
    this ref as its preservation reference, so that checking out the recorded SHA
    and taking the published tree onto it as uncommitted work are one act", and
    to "NOT carry the hookless commit itself". Seeding the published commit would
    put an unchecked commit into a run's history and then into its pull request.

    WHY THE JOURNAL ROW RATHER THAN A REF SCAN. The reclaim's preserved-publish
    refs share this namespace, and nothing in a ref NAME distinguishes the two:
    both end in a forty-character object id. The dispatch's own
    `preserved-tree` row is what knows which ref is a published TREE and, with
    it, the base that tree was taken against — a fact no ref listing carries at
    all. Origin is still ASKED whether the ref stands, so the seed remains a
    commit origin itself named rather than one this journal remembered.

    `named` is that row already resolved — the ref, its base commit and its run —
    rather than the journal to resolve it from, and the lookup sits in the caller
    for the reason that function's docstring gives about its asked-source list.
    """
    ref, base, run_id = named
    result = runner.run(
        argv=["git", "ls-remote", SEED_REMOTE, ref],
        cwd=repo,
        timeout_seconds=_GIT_TIMEOUT_SECONDS,
    )
    if result.exit_code != 0:
        return PreservedWorkUnobservable(
            detail=(
                f"git ls-remote {SEED_REMOTE} {ref} exited {result.exit_code}; whether the"
                " tree this item's checkpoint-failed run published still stands could not"
                " be established, so no seed was taken and absence is not confirmed"
            )
        )
    if ref not in _refs_by_name(stdout=result.stdout):
        return None
    return RecoverySeed(
        source_run_id=run_id,
        remote=SEED_REMOTE,
        commit_sha=base,
        preservation_ref=ref,
    )


def _newer_published_head_seed(
    *,
    runner: CommandRunner,
    repo: Path,
    work_item_id: str,
    terminal: RecoverySeed,
    records: tuple[dict[str, object], ...],
) -> RecoverySeed | PreservedWorkUnobservable | None:
    """Return a head a later dispatch published, or ``None`` when none was recorded.

    A terminal ref normally wins because it is the complete tree the failed run
    preserved.  The journal is the exception's evidence: when it names the
    branch tip as a later run's publication, choosing the older terminal tree
    would discard the item's newer work.  Rows without a published-head field
    predate this measurement, so they leave the established terminal-ref
    behaviour intact rather than manufacturing an attribution from their order.
    """
    if not any(record.get("published_head") is not None for record in records):
        return None
    published = _published_head_seed(
        runner=runner,
        repo=repo,
        work_item_id=work_item_id,
        earlier_run_ids=(),
    )
    if published is None or isinstance(published, PreservedWorkUnobservable):
        return None
    relation = published_head_relation(
        records=records,
        preserved_run_id=terminal.source_run_id,
        published_head=published.commit_sha,
    )
    if relation is None:
        return PreservedWorkUnobservable(
            detail=(
                "publishing-run-unobservable: the recovery branch head and a"
                " competing preserved ref are both readable, but the journal cannot"
                " attribute one of them to a publishing run; neither tree is reclaimed"
            )
        )
    return published if relation else None


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
    other fields are present says more than no record at all. Every arm that
    reaches here read a ref that names no run — the two lower-preference seeds and
    the confirmed absence — so there is nothing better to offer; the arm that CAN
    name one, the needs-human ref, takes it from the ref itself.
    """
    return identifiers[0] if identifiers else ""
