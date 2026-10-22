"""The per-merge drift pass: enumerate the merges after the frontier, judge each.

The primitive the detection coverage-record contract's "The drift run" bullet
names. Each reconcile pass of the Dispatcher enumerates every default-branch
merge after the recorded frontier, IN MERGE ORDER, and runs the drift pass over
each merge's diff through the shared spec-stated judgement; the post-merge
janitor may call this same primitive after its own merge, and a merge no
janitor saw — a hand merge, a spec pull request, an externally merged pull
request — is processed by the next reconcile pass because the enumerator is the
pass and not the janitor.

THE FRONTIER ARRIVES AS A PARAMETER rather than being read here, and the split
is deliberate. The recorded frontier is the newest COMPLETED drift coverage
point on the committed detection-coverage anchor, which is a ledger read; this
module is the pass over a range, and keeping the ledger out of it is what lets
the whole enumeration-and-judgement order be exercised without a tenant. The
lane that wires this primitive into the reconcile command owns the anchor read
and the records written back to it.

EVERY PER-MERGE FAILURE IS CARRIED, NEVER RAISED, and that is what the
contiguous frontier is built out of. A merge whose diff could not be read, or
whose judgement could not be parsed, is a merge the pass did not process — and
the contract says such a merge "stops the frontier until it is processed with
every finding filed, and a later merge's success MUST NOT advance past it". A
pass that raised on the first unreadable merge would also stop the frontier, by
never recording anything at all; what it would lose is every LATER merge's
finding, which the pass is free to file while the frontier waits.

A READING THAT COULD NOT BE TAKEN IS NOT AN EMPTY SCOPE. `merges_after`
answering None means git did not answer, so the pass reports that measurement
and judges nothing; an empty tuple means the frontier is already the branch
head, which is a complete pass over an empty scope.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from livespec_runtime import spec_stated
from returns.unsafe import unsafe_perform_io

from livespec_orchestrator_beads_fabro.commands._detection_coverage import (
    detection_coverage_anchor,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_journal_file import utc_now_iso
from livespec_orchestrator_beads_fabro.commands._dispatcher_paths import store_config
from livespec_orchestrator_beads_fabro.commands._dispatcher_valves import (
    DEFAULT_DRIFT_PROPOSAL_QUEUE_CAP,
    resolve_drift_proposal_queue_cap,
)
from livespec_orchestrator_beads_fabro.commands._drift_run_disposition import (
    DispositionContext,
    dispose_findings,
)
from livespec_orchestrator_beads_fabro.commands._drift_run_findings import (
    behaviour_statement,
    findings_from_verdict,
)
from livespec_orchestrator_beads_fabro.commands._drift_run_merges import (
    merge_under_judgement,
    merges_after,
)
from livespec_orchestrator_beads_fabro.effects import AttemptFailure, attempt
from livespec_orchestrator_beads_fabro.errors import (
    ConnectionPrefixMissingError,
    LivespecConfigUnreadableError,
)
from livespec_orchestrator_beads_fabro.spec_reader import read_current_specification

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

    from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandRunner
    from livespec_orchestrator_beads_fabro.commands._drift_run_findings import DriftFinding
    from livespec_orchestrator_beads_fabro.types import StoreConfig

__all__: list[str] = [
    "CAUSE_JUDGEMENT_UNREADABLE",
    "CAUSE_MERGES_UNREADABLE",
    "CAUSE_MERGE_UNREADABLE",
    "DRIFT_RUN_AUTHOR",
    "DriftRunOutcome",
    "DriftRunSeams",
    "MergeOutcome",
    "run_drift_pass",
]

# The three measurements this pass can fail to take, each one stable text so a
# reader of the attempt record can tell which instrument stopped it. A merge
# nobody could read and a judgement nobody could parse are different faults
# with different remedies, and both are different from git declining to
# enumerate the range at all.
CAUSE_MERGES_UNREADABLE = "merges-after-frontier-unreadable"
CAUSE_MERGE_UNREADABLE = "merge-unreadable"
CAUSE_JUDGEMENT_UNREADABLE = "judgement-unreadable"

# What a proposal this pass filed records as its author when the caller names
# nobody more specific. The pass is the author, and saying so is what keeps a
# machine-filed proposal legible as one at the human gate.
DRIFT_RUN_AUTHOR = "livespec-orchestrator-beads-fabro:drift-run"

_SPEC_DIRNAME = "SPECIFICATION"


@dataclass(frozen=True, kw_only=True)
class DriftRunSeams:
    """The two impure seams the pass reaches the world through.

    `judge` is the `livespec_runtime.spec_stated.ModelRunner` the shared
    judgement is given, and it is REQUIRED rather than defaulted: a pass that
    defaulted to a working model call would reach a provider from inside any
    test that forgot to supply one, and a pass that defaulted to a stub would
    make forgetting indistinguishable from judging.

    `author` and `now` are what a filed proposal's front matter records about
    who filed it and when. `now` is a seam rather than a direct clock read for
    the ordinary reason: a document whose timestamp moves cannot be compared
    byte for byte. `author` DEFAULTS to the pass itself rather than to nothing,
    because the pass IS the author of what it files — a proposal reaching the
    human gate under no attribution would be indistinguishable from one a
    session wrote by hand. A caller that can name its invoker more precisely
    passes it; the reconcile lane does.
    """

    runner: CommandRunner
    judge: spec_stated.ModelRunner
    author: str = DRIFT_RUN_AUTHOR
    now: Callable[[], str] = utc_now_iso


@dataclass(frozen=True, kw_only=True)
class MergeOutcome:
    """What the pass made of ONE merge.

    `verdict` is None precisely when `failure` is populated: either the merge
    could not be read or its judgement could not be parsed, and in both cases
    the merge has not been processed.

    `findings` are the `partial` or `unstated` behaviours the merge adds;
    `filed` the identities among them that now rest under `proposed_changes/`,
    and `held` those recorded on the detection-coverage anchor because the open
    queue stood at the cap. An identity an EARLIER pass filed or held is in the
    matching tuple too: the frontier rule asks whether every finding of the
    merge IS filed, not whether this pass was the one that filed it.

    A finding in NEITHER tuple is one nothing could dispose of, which is what
    leaves its merge unprocessed.
    """

    merge: str
    statement: str
    verdict: spec_stated.SpecStatedVerdict | None
    failure: str | None
    findings: tuple[DriftFinding, ...] = ()
    filed: tuple[str, ...] = ()
    held: tuple[str, ...] = ()


@dataclass(frozen=True, kw_only=True)
class DriftRunOutcome:
    """One pass over the merges after a frontier.

    `unreadable` names the measurement that stopped the pass before any merge
    was judged, and is None on every pass that enumerated its scope — including
    one whose scope was empty.

    `filed` is every finding identity now resting under `proposed_changes/`
    and `held` every one recorded on the anchor, across every merge of the
    scope and in merge order.
    """

    merges: tuple[str, ...]
    judged: tuple[MergeOutcome, ...]
    unreadable: str | None
    filed: tuple[str, ...] = ()
    held: tuple[str, ...] = ()


def run_drift_pass(
    *, project_root: Path, frontier: str | None, seams: DriftRunSeams
) -> DriftRunOutcome:
    """Judge every default-branch merge after `frontier`, oldest first."""
    merges = merges_after(project_root=project_root, runner=seams.runner, since=frontier)
    if merges is None:
        return DriftRunOutcome(merges=(), judged=(), unreadable=CAUSE_MERGES_UNREADABLE)
    spec_root = project_root / _SPEC_DIRNAME
    spec_tree = read_current_specification(spec_root=spec_root).files
    context = _disposition_context(
        project_root=project_root, spec_root=spec_root, spec_tree=spec_tree, seams=seams
    )
    judged: list[MergeOutcome] = []
    for sha in merges:
        one = _judge_one(project_root=project_root, seams=seams, spec_tree=spec_tree, sha=sha)
        judged.append(_disposed(one=one, context=context))
    return DriftRunOutcome(
        merges=merges,
        judged=tuple(judged),
        unreadable=None,
        filed=tuple(identity for outcome in judged for identity in outcome.filed),
        held=tuple(identity for outcome in judged for identity in outcome.held),
    )


def _disposition_context(
    *,
    project_root: Path,
    spec_root: Path,
    spec_tree: dict[str, str],
    seams: DriftRunSeams,
) -> DispositionContext:
    """The committed inputs one pass disposes its findings against.

    Resolved ONCE per pass rather than per finding, because all four are
    repository properties that cannot change under a pass that holds no lock on
    them — and because re-reading `.livespec.jsonc` per finding would let two
    readings of one file disagree while both looked healthy.
    """
    return DispositionContext(
        spec_root=spec_root,
        spec_tree=spec_tree,
        config=_store_config_or_none(project_root=project_root),
        anchor=detection_coverage_anchor(cwd=project_root),
        cap=unsafe_perform_io(
            resolve_drift_proposal_queue_cap(cwd=project_root).value_or(
                DEFAULT_DRIFT_PROPOSAL_QUEUE_CAP
            )
        ),
        author=seams.author,
        now=seams.now,
    )


def _store_config_or_none(*, project_root: Path) -> StoreConfig | None:
    """This repository's tenant connection, or None when it declares none.

    FAIL-SOFT, because the drift pass's dependence on the tenant is confined to
    the ONE record type it may write there — a held finding — and a repository
    that declares no resolvable connection simply cannot hold. Letting the
    resolver's refusal escape would instead kill the whole pass, including the
    enumeration and judgement of every merge, over a question whose honest
    answer is "this repository cannot hold a finding".
    """
    resolved = attempt(
        action=lambda: store_config(repo=project_root),
        exceptions=(ConnectionPrefixMissingError, LivespecConfigUnreadableError, OSError),
    )
    if isinstance(resolved, AttemptFailure):
        return None
    return resolved


def _disposed(*, one: MergeOutcome, context: DispositionContext) -> MergeOutcome:
    """One judged merge with its findings derived and disposed of.

    A merge the pass could not judge is returned UNCHANGED: there is no verdict
    to derive findings from, and a merge with no findings would otherwise read
    as one whose every finding is filed — which is exactly the reading that
    advances the frontier over an unprocessed merge.
    """
    if one.verdict is None:
        return one
    findings = findings_from_verdict(merge=one.merge, statement=one.statement, verdict=one.verdict)
    disposition = dispose_findings(findings=findings, context=context)
    return MergeOutcome(
        merge=one.merge,
        statement=one.statement,
        verdict=one.verdict,
        failure=one.failure,
        findings=findings,
        filed=disposition.filed,
        held=disposition.held,
    )


def _judge_one(
    *,
    project_root: Path,
    seams: DriftRunSeams,
    spec_tree: dict[str, str],
    sha: str,
) -> MergeOutcome:
    """One merge put to the shared judgement, or the reason it could not be."""
    merge = merge_under_judgement(project_root=project_root, runner=seams.runner, sha=sha)
    if merge is None:
        return MergeOutcome(merge=sha, statement="", verdict=None, failure=CAUSE_MERGE_UNREADABLE)
    statement = behaviour_statement(merge=merge)
    judged = spec_stated.judge(spec_tree=spec_tree, statement=statement, run_model=seams.judge)
    return MergeOutcome(
        merge=sha,
        statement=statement,
        verdict=judged.value_or(None),
        failure=None if judged.value_or(None) is not None else CAUSE_JUDGEMENT_UNREADABLE,
    )
