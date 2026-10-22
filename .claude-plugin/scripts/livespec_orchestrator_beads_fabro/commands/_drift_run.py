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

from livespec_orchestrator_beads_fabro.commands._drift_run_findings import behaviour_statement
from livespec_orchestrator_beads_fabro.commands._drift_run_merges import (
    merge_under_judgement,
    merges_after,
)
from livespec_orchestrator_beads_fabro.spec_reader import read_current_specification

if TYPE_CHECKING:
    from pathlib import Path

    from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandRunner

__all__: list[str] = [
    "CAUSE_JUDGEMENT_UNREADABLE",
    "CAUSE_MERGES_UNREADABLE",
    "CAUSE_MERGE_UNREADABLE",
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

_SPEC_DIRNAME = "SPECIFICATION"


@dataclass(frozen=True, kw_only=True)
class DriftRunSeams:
    """The two impure seams the pass reaches the world through.

    `judge` is the `livespec_runtime.spec_stated.ModelRunner` the shared
    judgement is given, and it is REQUIRED rather than defaulted: a pass that
    defaulted to a working model call would reach a provider from inside any
    test that forgot to supply one, and a pass that defaulted to a stub would
    make forgetting indistinguishable from judging.
    """

    runner: CommandRunner
    judge: spec_stated.ModelRunner


@dataclass(frozen=True, kw_only=True)
class MergeOutcome:
    """What the pass made of ONE merge.

    `verdict` is None precisely when `failure` is populated: either the merge
    could not be read or its judgement could not be parsed, and in both cases
    the merge has not been processed.
    """

    merge: str
    statement: str
    verdict: spec_stated.SpecStatedVerdict | None
    failure: str | None


@dataclass(frozen=True, kw_only=True)
class DriftRunOutcome:
    """One pass over the merges after a frontier.

    `unreadable` names the measurement that stopped the pass before any merge
    was judged, and is None on every pass that enumerated its scope — including
    one whose scope was empty.
    """

    merges: tuple[str, ...]
    judged: tuple[MergeOutcome, ...]
    unreadable: str | None


def run_drift_pass(
    *, project_root: Path, frontier: str | None, seams: DriftRunSeams
) -> DriftRunOutcome:
    """Judge every default-branch merge after `frontier`, oldest first."""
    merges = merges_after(project_root=project_root, runner=seams.runner, since=frontier)
    if merges is None:
        return DriftRunOutcome(merges=(), judged=(), unreadable=CAUSE_MERGES_UNREADABLE)
    spec_tree = read_current_specification(spec_root=project_root / _SPEC_DIRNAME).files
    judged = tuple(
        _judge_one(project_root=project_root, seams=seams, spec_tree=spec_tree, sha=sha)
        for sha in merges
    )
    return DriftRunOutcome(merges=merges, judged=judged, unreadable=None)


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
