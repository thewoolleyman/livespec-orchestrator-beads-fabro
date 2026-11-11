"""The preserved ref of one rank in the recovery order: needs-human, else checkpoint-failed tree.

Split out of `_dispatcher_recovery_preserved` along the cohesion seam of the
sources that publish a ref at a run's ENDING, leaving that module the order the
ranks are asked in. The caller hands in the refs that belong to ONE rank — the
latest run's, or every earlier run's — and this module chooses among them, takes
the checkpoint-failed tree when no needs-human ref stands, and applies the
run-age bound against the observed published head.

This module owns its own unobservable answer, as `_dispatcher_recovery_wip` and
`_dispatcher_recovery_published_head` do, and the caller converts it, so the
dependency runs one way only. It is generic over the remote and the ref prefix,
which the caller supplies, so the two constants stay defined where the seed
record's own fields are.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandRunner
from livespec_orchestrator_beads_fabro.commands._dispatcher_needs_human_refs import (
    NeedsHumanRef,
    NeedsHumanRefsUnobservable,
    refs_by_name,
    select_needs_human_ref,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_recovery_measurements import (
    MEASUREMENT_PRESERVED_WORK,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_recovery_published_head import (
    PublishedHeadEquivalent,
    PublishedHeadUnobservable,
    RecoveryPublicationHistory,
    newer_published_head_seed,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_recovery_routes import RecoverySeed

__all__: list[str] = [
    "RankedRefUnobservable",
    "Ranking",
    "listing",
    "ranked_ref",
]

_GIT_TIMEOUT_SECONDS = 120.0


@dataclass(frozen=True, kw_only=True)
class RankedRefUnobservable:
    """Origin or the journal could not ANSWER which ref of this rank to take.

    A distinct type rather than `None`, so a caller cannot read "we could not
    look" as "there is nothing there".  `measurement` is the stable token the
    recovery-held record names.
    """

    detail: str
    measurement: str = MEASUREMENT_PRESERVED_WORK


@dataclass(frozen=True, kw_only=True)
class Ranking:
    """What every ranked-ref comparison reads: origin, the journal, and the carrying refs."""

    runner: CommandRunner
    repo: Path
    remote: str
    ref_prefix: str
    work_item_id: str
    journal_records: tuple[dict[str, object], ...]
    publications: tuple[tuple[str, str], ...]
    earlier_run_ids: tuple[str, ...]
    carrying: list[NeedsHumanRef]


def ranked_ref(
    *,
    ranking: Ranking,
    refs: list[NeedsHumanRef],
    tree: tuple[str, str, str] | None,
    run_ids: tuple[str, ...],
) -> RecoverySeed | RankedRefUnobservable | None:
    """The preserved ref (needs-human, else checkpoint-failed tree) after the head comparison.

    `refs` and `tree` are the candidates of ONE rank in the order: the refs a set
    of runs published at their endings. A surviving published head by a later run
    outranks the ref; see `newer_published_head_seed`.
    """
    preserved: RecoverySeed | RankedRefUnobservable | None = None
    if refs:
        chosen = select_needs_human_ref(
            runner=ranking.runner,
            repo=ranking.repo,
            carrying=refs,
            ref_prefix=ranking.ref_prefix,
            run_ids=run_ids,
            timeout_seconds=_GIT_TIMEOUT_SECONDS,
        )
        if isinstance(chosen, NeedsHumanRefsUnobservable):
            return RankedRefUnobservable(
                detail=(
                    f"{chosen.detail}, so no seed was taken and the publish branch is left"
                    " exactly as it stands"
                )
            )
        preserved = RecoverySeed(
            source_run_id=chosen.run_id,
            remote=ranking.remote,
            commit_sha=chosen.commit_sha,
            preservation_ref=chosen.ref,
            preservation_tip_sha=chosen.commit_sha,
        )
    elif tree is not None:
        preserved = _preserved_tree_seed(ranking=ranking, named=tree)
    if preserved is None or isinstance(preserved, RankedRefUnobservable):
        return preserved
    newer_head = newer_published_head_seed(
        runner=ranking.runner,
        repo=ranking.repo,
        work_item_id=ranking.work_item_id,
        terminal=preserved,
        history=RecoveryPublicationHistory(
            records=ranking.journal_records,
            publications=ranking.publications,
            earlier_run_ids=ranking.earlier_run_ids,
        ),
    )
    if isinstance(newer_head, PublishedHeadUnobservable):
        return RankedRefUnobservable(detail=newer_head.detail, measurement=newer_head.measurement)
    if isinstance(newer_head, PublishedHeadEquivalent):
        return listing(
            seed=newer_head.seed,
            carrying=[one for one in ranking.carrying if one.ref != newer_head.competing_ref],
        )
    return listing(seed=preserved if newer_head is None else newer_head, carrying=ranking.carrying)


def listing(*, seed: RecoverySeed, carrying: list[NeedsHumanRef]) -> RecoverySeed:
    """The seed with every carrying needs-human ref it did not take listed as passed over.

    The clause lists "every carrying ref the route did not take", whichever source
    the route took, so the listing is attached here rather than by each source.
    """
    return replace(
        seed,
        passed_over_needs_human=tuple(
            (one.ref, one.commit_sha) for one in carrying if one.ref != seed.preservation_ref
        ),
    )


def _preserved_tree_seed(
    *,
    ranking: Ranking,
    named: tuple[str, str, str],
) -> RecoverySeed | RankedRefUnobservable | None:
    """The tree a checkpoint-failed run published, which nothing else carries.

    SECOND WITHIN ITS RANK, AND THAT IS THE CLAUSE'S OWN WORDING: this ref "counts
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
    result = ranking.runner.run(
        argv=["git", "ls-remote", ranking.remote, ref],
        cwd=ranking.repo,
        timeout_seconds=_GIT_TIMEOUT_SECONDS,
    )
    if result.exit_code != 0:
        return RankedRefUnobservable(
            detail=(
                f"git ls-remote {ranking.remote} {ref} exited {result.exit_code}; whether the"
                " tree this item's checkpoint-failed run published still stands could not"
                " be established, so no seed was taken and absence is not confirmed"
            )
        )
    if ref not in refs_by_name(stdout=result.stdout):
        return None
    return RecoverySeed(
        source_run_id=run_id,
        remote=ranking.remote,
        commit_sha=base,
        preservation_ref=ref,
        preservation_tip_sha=refs_by_name(stdout=result.stdout)[ref],
    )
