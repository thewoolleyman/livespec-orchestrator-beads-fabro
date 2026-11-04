"""The seam the loop probe drives, and its production wiring.

The loop-probe clause of `SPECIFICATION/contracts.md` requires the probe to run
through the SAME published machinery an ordinary dispatch uses, never a parallel
path. This module is what makes that requirement checkable: the probe talks to
ONE narrow protocol, and the production implementation of that protocol is a
thin composition of the already-published dispatch and reconcile surfaces. A
probe that reached for a private code path would have to change this file to do
it, which is exactly the visibility the clause is after.

The protocol is split into three ORDERED methods rather than one `drive` call
because the confinement contract lives in the SPLIT. `publish` drives the item
to a published change and reports its paths; the probe verifies confinement on
those paths; only then is `merge` called. An escape therefore fails the probe
with `merge` never invoked -- "fails without merging" is a property of the call
graph, not a promise in a docstring.

WHAT THE PRODUCTION WIRING CAN AND CANNOT INTERPOSE ON, stated plainly because
it decides how much the pre-merge leg is worth. The factory's own publish node
opens and merges the pull request, so `publish` can return a change that is
ALREADY merged upstream; `ProbePublish.merge_commit` carries that when it
happens. What the Dispatcher does own is the merge-COMPLETING disposition -- the
post-merge janitor and the acceptance path -- and that is what `merge` performs,
withheld until confinement is verified. The residual case, a change that merged
upstream anyway, is precisely what the post-merge backstop names, which is why
the contract ratifies both legs rather than either alone.
"""

from __future__ import annotations

import argparse
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol, cast

from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandRunner
from livespec_orchestrator_beads_fabro.commands._dispatcher_journal_tail import (
    journal_tail_records,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_step_ids import STEP_IDS

__all__: list[str] = [
    "ACCEPTANCE_STAGE",
    "DispatchProbeCycle",
    "ProbeCycle",
    "ProbeMerge",
    "ProbeObservation",
    "ProbePublish",
    "changed_paths_argv",
    "journal_records",
    "merged_paths_argv",
    "observed_acceptance",
    "observed_step_outcomes",
    "parse_paths",
    "probe_publish_branch",
]

ACCEPTANCE_STAGE = "acceptance-ai-pass"

_GIT_TIMEOUT_SECONDS = 120.0
_UNOBSERVED_VERDICT = "<no acceptance verdict journaled>"


@dataclass(frozen=True, kw_only=True)
class ProbePublish:
    """The published change, read BEFORE the merge disposition is completed.

    `readable` is separate from an empty `paths` tuple on purpose: a change set
    that could not be read is not a change set that touched nothing, and the
    residue contract's refusal to conflate unavailability with emptiness applies
    with equal force here.
    """

    branch: str
    paths: tuple[str, ...]
    merge_commit: str | None = None
    readable: bool = True
    detail: str = ""


@dataclass(frozen=True, kw_only=True)
class ProbeMerge:
    """What the merge-completing disposition did with the verified change."""

    merged: bool
    merge_commit: str | None = None
    merged_paths: tuple[str, ...] = ()
    detail: str = ""


@dataclass(frozen=True, kw_only=True)
class ProbeObservation:
    """The post-merge facts the probe's remaining stage assertions read."""

    step_outcomes: tuple[Mapping[str, object], ...]
    verdict: str
    absent_evidence: tuple[str, ...]
    item_status: str


class ProbeCycle(Protocol):
    """The published machinery the probe drives, one method per ordered stage.

    `item_status` is separate from `observe` because the failure leg needs it at
    stages `observe` has not been reached from. The contract requires a failed
    probe to report the item's CURRENT lifecycle state -- left wherever the
    ordinary machinery put it, never auto-closed and never hidden -- and a
    report that could only be produced after a full observation would go silent
    exactly when the operator most needs it.
    """

    def publish(self, *, work_item_id: str) -> ProbePublish: ...

    def merge(self, *, published: ProbePublish) -> ProbeMerge: ...

    def observe(self, *, work_item_id: str) -> ProbeObservation: ...

    def item_status(self, *, work_item_id: str) -> str: ...


def probe_publish_branch(*, work_item_id: str) -> str:
    """The publish branch the phase graph pushes, by the repo's own convention."""
    return f"feat/{work_item_id}"


def changed_paths_argv(*, default_branch: str, branch: str) -> list[str]:
    """The argv reading a published branch's changed paths against the default branch."""
    return ["git", "diff", "--name-only", f"origin/{default_branch}...origin/{branch}"]


def merged_paths_argv(*, merge_commit: str) -> list[str]:
    """The argv reading the paths one merged commit introduced."""
    return ["git", "show", "--name-only", "--pretty=format:", merge_commit]


def parse_paths(*, stdout: str) -> tuple[str, ...]:
    """The non-empty path lines of a git name-only listing."""
    return tuple(line.strip() for line in stdout.splitlines() if line.strip())


def journal_records(*, journal_path: Path) -> tuple[Mapping[str, object], ...]:
    """Every parseable JSONL record in the dispatch journal; absent means none.

    A line whose bytes are not text is skipped like any other unparseable line,
    which is the shape a truncated or interleaved append actually produces.
    """
    return journal_tail_records(journal_path=journal_path)


def observed_step_outcomes(
    *, records: Sequence[Mapping[str, object]]
) -> tuple[Mapping[str, object], ...]:
    """Every journaled record naming a step of the closed preflight/post-merge vocabulary.

    Keyed on the STEP identifier rather than on a stage name: the vocabulary is
    the ratified surface, and a reader keyed on stage names would silently miss
    a step whose stage was renamed.
    """
    return tuple(record for record in records if record.get("step") in STEP_IDS)


def observed_acceptance(*, records: Sequence[Mapping[str, object]]) -> tuple[str, tuple[str, ...]]:
    """The newest journaled acceptance verdict and the evidence it could not observe."""
    passes = [record for record in records if record.get("stage") == ACCEPTANCE_STAGE]
    if not passes:
        return (_UNOBSERVED_VERDICT, (_UNOBSERVED_VERDICT,))
    newest = passes[-1]
    absent = newest.get("absent_evidence")
    listed = cast("list[Any]", absent) if isinstance(absent, list) else []
    return (str(newest.get("verdict", _UNOBSERVED_VERDICT)), tuple(str(one) for one in listed))


@dataclass(frozen=True, kw_only=True)
class DispatchProbeCycle:
    """The production cycle: the published dispatch and reconcile surfaces, in order.

    `drive` and `complete` are the two published entry points, injected rather
    than imported at the call site so the hermetic tier can exercise the
    ordering without ever reaching the live Dispatcher.
    """

    args: argparse.Namespace
    repo: Path
    runner: CommandRunner
    journal_path: Path
    default_branch: str
    drive: Callable[..., int]
    complete: Callable[..., int]
    item_status_lookup: Callable[..., str]

    def publish(self, *, work_item_id: str) -> ProbePublish:
        """Drive the item to a published change and read its paths before merging."""
        branch = probe_publish_branch(work_item_id=work_item_id)
        _ = self.drive(args=self.args)
        result = self.runner.run(
            argv=changed_paths_argv(default_branch=self.default_branch, branch=branch),
            cwd=self.repo,
            timeout_seconds=_GIT_TIMEOUT_SECONDS,
        )
        if result.exit_code != 0:
            return ProbePublish(
                branch=branch,
                paths=(),
                readable=False,
                detail=f"git diff exited {result.exit_code}: {result.stderr.strip()}",
            )
        return ProbePublish(branch=branch, paths=parse_paths(stdout=result.stdout))

    def merge(self, *, published: ProbePublish) -> ProbeMerge:
        """Complete the merge disposition for a change already verified as confined."""
        exit_code = self.complete(args=self.args)
        if exit_code != 0:
            return ProbeMerge(
                merged=False,
                detail=f"the merge-completing disposition exited {exit_code}",
            )
        return ProbeMerge(
            merged=True,
            merge_commit=published.merge_commit,
            merged_paths=published.paths,
        )

    def observe(self, *, work_item_id: str) -> ProbeObservation:
        """Read the cycle's journaled step outcomes, verdict, and terminal state."""
        records = journal_records(journal_path=self.journal_path)
        verdict, absent = observed_acceptance(records=records)
        return ProbeObservation(
            step_outcomes=observed_step_outcomes(records=records),
            verdict=verdict,
            absent_evidence=absent,
            item_status=self.item_status(work_item_id=work_item_id),
        )

    def item_status(self, *, work_item_id: str) -> str:
        """The designated item's current lifecycle state, for the failure leg."""
        return self.item_status_lookup(work_item_id=work_item_id)
