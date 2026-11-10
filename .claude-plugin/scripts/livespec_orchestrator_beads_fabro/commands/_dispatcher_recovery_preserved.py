"""The failed run's preserved work, as origin reports it, in the clause's own order.

`SPECIFICATION/contracts.md` section "Factory-configurable ACP fallback priority"
→ "Recovery from the failed run's preserved work" fixes both the preference order
and what a seed must carry: "The Dispatcher MUST prefer the failed run's
successfully preserved terminal tree (the pushed ref a needs-human ending
preserves)... then its observed published head or the corresponding
preserved-publish ref... The seed record MUST name the source run, remote,
immutable commit SHA, and preservation reference."

SOURCES, ASKED IN THIS ORDER, AND EACH ONE STOPS THE SEARCH. The order is not a
tidy ranking: it is the clause's, and `test_dispatcher_recovery_seed_precedence`
holds every pair of it in one table.

1. A needs-human ref, or a checkpoint-failed preservation ref, of the LATEST run:
   it carries the run's TERMINAL tree, which is everything the dying run had.
2. The latest run's highest-numbered work-in-progress ref: the run's latest
   settled capture, which "MUST be preferred over the observed published head and
   over every preservation ref of an earlier run of the item".
3. A needs-human ref or preservation ref of an EARLIER run, which outranks the
   observed published head only when its run is the head's run or a later one.
4. The observed published head.
5. The preserved-publish ref of an EARLIER head, asked last so the common case
   pays one round trip rather than four.

THE REFS ARE PARTITIONED BY THE RUN THEY CARRY, NOT TAKEN AS ONE POOL. Listing
every earlier run's ref and taking the newest before the capture was asked is the
regression this ordering repairs: the older tree it chose is a plausible, well-formed
seed that restores older work than the latest run's capture holds.

THE CHECKPOINT-FAILED RUN'S PUBLISHED TREE shares the first rank with the
needs-human ref, and its rank is the ratified one: "A tree that nothing else
carries is published to a preservation ref" says that ref "counts as the failed run's successfully
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
    NeedsHumanRef,
    NeedsHumanRefsUnobservable,
    NeedsHumanScope,
    carrying_needs_human_refs,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_recovery_checkpoint import (
    newest_preserved_tree_row,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_recovery_measurements import (
    MEASUREMENT_PRESERVED_WORK,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_recovery_published_head import (
    PublishedHeadUnobservable,
    earlier_head_seed,
    leading_identifier,
    published_head_seed,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_recovery_ranked_ref import (
    RankedRefUnobservable,
    Ranking,
    listing,
    ranked_ref,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_recovery_routes import RecoverySeed
from livespec_orchestrator_beads_fabro.commands._dispatcher_recovery_run_age import foreign_run_ids
from livespec_orchestrator_beads_fabro.commands._dispatcher_recovery_wip import (
    WipRefUnobservable,
    verified_latest_wip_seed,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_tdd_probe import dispatch_id_for
from livespec_orchestrator_beads_fabro.commands._run_attribution import newest_journaled_run_id

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


@dataclass(frozen=True, kw_only=True)
class PreservedWorkUnobservable:
    """Origin could not be ASKED whether preserved work exists.

    A distinct type rather than `None`, so a caller cannot read "we could not
    look" as "there is nothing there" — the same line the reclaim's own
    `PublishBranchUnobservable` draws, and for the same reason.  `measurement`
    is the token the recovery-held record names for the read that failed.
    """

    detail: str
    measurement: str = MEASUREMENT_PRESERVED_WORK


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
    publications: tuple[tuple[str, str], ...] = (),
) -> RecoverySeed | PreservedWorkUnobservable | PreservedWorkAbsent:
    """The seed the failed run's preserved work supports: one, unaskable, or absent.

    THE ASKED-SOURCE LIST IS BUILT HERE, BY THE CODE THAT DOES THE ASKING, which
    is why the two SKIPPABLE sources have their own preconditions up here rather
    than inside the helpers that read them: a second expression of such a
    condition — one deciding whether to ask and one deciding whether to report
    having asked — is free to drift, and the direction it drifts in is a loss
    record naming a round trip nobody took. The terminal ref's precondition and the
    published tree's row lookup both sit up here, rather than inside the helpers
    that read them, for that one reason.

    `journal_records` has NO DEFAULT, for the reason `_dispatcher_sandbox_image_
    source` gives about its own record: a default is how a caller that HAD a
    journal silently reports the answer of one that did not — here, "this item
    has no preserved tree" for an item whose tree was published minutes ago.
    """
    latest = newest_journaled_run_id(
        records=journal_records, work_item_id=work_item_id
    ) or leading_identifier(identifiers=earlier_run_ids)
    if not earlier_run_ids:
        return PreservedWorkUnobservable(
            detail=(
                f"{PRESERVED_SOURCE_TERMINAL_TREE} could not be asked because no earlier "
                "run identifier was observed from the anchor, dispatch journal, or ledger "
                "claim; preserved work is not confirmed absent and the publish branch is "
                "left exactly as it stands"
            )
        )
    dispatch_id = dispatch_id_for(records=journal_records, work_item_id=work_item_id)
    run_ids = tuple(dict.fromkeys((*earlier_run_ids, *filter(None, (dispatch_id,)))))
    latest_ids = tuple(dict.fromkeys(filter(None, (latest, dispatch_id))))
    carrying = carrying_needs_human_refs(
        runner=runner,
        repo=repo,
        scope=NeedsHumanScope(
            run_ids=run_ids,
            foreign_run_ids=foreign_run_ids(
                records=journal_records, work_item_id=work_item_id, own=run_ids
            ),
        ),
        ref_prefix=NEEDS_HUMAN_REF_PREFIX,
        remote=SEED_REMOTE,
        timeout_seconds=_GIT_TIMEOUT_SECONDS,
    )
    if isinstance(carrying, NeedsHumanRefsUnobservable):
        return PreservedWorkUnobservable(
            detail=(
                f"{carrying.detail}, so no seed was taken and the publish branch is left"
                " exactly as it stands"
            )
        )
    # The published tree is named by this item's OWN journal, so with no row
    # naming one there is no ref that source could stand at and the round trip
    # would ask origin about nothing.
    tree_row = newest_preserved_tree_row(records=journal_records, work_item_id=work_item_id)
    ranking = Ranking(
        runner=runner,
        repo=repo,
        remote=SEED_REMOTE,
        ref_prefix=NEEDS_HUMAN_REF_PREFIX,
        work_item_id=work_item_id,
        journal_records=journal_records,
        publications=publications,
        carrying=carrying,
    )
    found = _seed_in_order(
        ranking=ranking,
        tree_row=tree_row,
        latest=latest,
        latest_ids=latest_ids,
        run_ids=run_ids,
        earlier_run_ids=earlier_run_ids,
    )
    if found is not None:
        return found
    return PreservedWorkAbsent(
        source_run_id=leading_identifier(identifiers=earlier_run_ids),
        sources_asked=(
            PRESERVED_SOURCE_TERMINAL_TREE,
            *((PRESERVED_SOURCE_CHECKPOINT_FAILED_PUBLISHED_TREE,) if tree_row else ()),
            PRESERVED_SOURCE_PUBLISHED_HEAD,
            PRESERVED_SOURCE_EARLIER_PRESERVED_PUBLISH_REF,
        ),
    )


def _seed_in_order(
    *,
    ranking: Ranking,
    tree_row: tuple[str, str, str] | None,
    latest: str,
    latest_ids: tuple[str, ...],
    run_ids: tuple[str, ...],
    earlier_run_ids: tuple[str, ...],
) -> RecoverySeed | PreservedWorkUnobservable | None:
    """The first source in the clause's order that answers, or `None` when none does.

    The order IS the clause's: a ref published at the latest run's own ending, then
    that run's latest capture, then an earlier run's ref (bounded by run age
    against the head), then the head itself, then a preserved head an earlier
    reclaim left. A ref belongs to the latest run by the run it carries (and a
    tree row by the run it names), never by being the newest ref listed: reading
    every earlier run's ref first is how an older tree came to outrank the
    capture.
    """
    latest_tree = tree_row if tree_row is not None and tree_row[2] in latest_ids else None
    earlier_tree = tree_row if tree_row is not None and tree_row[2] not in latest_ids else None
    ranked = _ranked(
        ranking=ranking,
        refs=[one for one in ranking.carrying if one.run_id in latest_ids],
        tree=latest_tree,
        run_ids=latest_ids,
    )
    if ranked is not None:
        return ranked
    wip = verified_latest_wip_seed(
        runner=ranking.runner,
        repo=ranking.repo,
        work_item_id=ranking.work_item_id,
        run_id=latest or None,
    )
    if wip is not None:
        return (
            PreservedWorkUnobservable(detail=wip.detail)
            if isinstance(wip, WipRefUnobservable)
            else listing(seed=wip, carrying=ranking.carrying)
        )
    ranked = _ranked(
        ranking=ranking,
        refs=[one for one in ranking.carrying if one.run_id not in latest_ids],
        tree=earlier_tree,
        run_ids=run_ids,
    )
    if ranked is not None:
        return ranked
    heads = _as_preserved(
        seed=published_head_seed(
            runner=ranking.runner,
            repo=ranking.repo,
            work_item_id=ranking.work_item_id,
            earlier_run_ids=earlier_run_ids,
        )
    ) or _as_preserved(
        seed=earlier_head_seed(
            runner=ranking.runner,
            repo=ranking.repo,
            work_item_id=ranking.work_item_id,
            earlier_run_ids=earlier_run_ids,
        )
    )
    return None if heads is None else _listed(seed=heads, carrying=ranking.carrying)


def _ranked(
    *,
    ranking: Ranking,
    refs: list[NeedsHumanRef],
    tree: tuple[str, str, str] | None,
    run_ids: tuple[str, ...],
) -> RecoverySeed | PreservedWorkUnobservable | None:
    """One rank's ref in this module's unobservable type; see `ranked_ref`."""
    found = ranked_ref(ranking=ranking, refs=refs, tree=tree, run_ids=run_ids)
    if isinstance(found, RankedRefUnobservable):
        return PreservedWorkUnobservable(detail=found.detail, measurement=found.measurement)
    return found


def _listed(
    *, seed: RecoverySeed | PreservedWorkUnobservable, carrying: list[NeedsHumanRef]
) -> RecoverySeed | PreservedWorkUnobservable:
    """The seed with its passed-over needs-human refs listed; an unobservable passes through."""
    if isinstance(seed, PreservedWorkUnobservable):
        return seed
    return listing(seed=seed, carrying=carrying)


def _as_preserved(
    *, seed: RecoverySeed | PublishedHeadUnobservable | None
) -> RecoverySeed | PreservedWorkUnobservable | None:
    """The published-head module's answer, in this module's unobservable type."""
    if isinstance(seed, PublishedHeadUnobservable):
        return PreservedWorkUnobservable(detail=seed.detail, measurement=seed.measurement)
    return seed
