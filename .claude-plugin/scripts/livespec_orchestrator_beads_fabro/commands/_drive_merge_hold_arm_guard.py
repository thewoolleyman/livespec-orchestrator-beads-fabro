"""What a merge-hold RELEASE must establish before it arms a pull request.

`_drive_merge_hold_valve` owns the valve — the label, the two directions and the
one forge write each performs. This owns the question the release has to answer
first, which v145's "Scripted publication and proof-head integrity" clause added:
the host-side hold release is the ONE arming that happens outside a run, so it
"MUST NOT arm while a run of the item is live, and it MUST arm only a pull
request whose current head is named by the latest `verified` or
`carried_forward` record of the item's latest run".

WHY THAT IS A SEPARATE CONCERN FROM THE VALVE. Inside a run the arming is
head-bound at the forge (`gh pr merge --match-head-commit`) and only `pr`
performs it, after the publication-head program has established the proof
identity. A release has neither: a person asks, possibly days later, and the
forge offers no conditional arming for a strategy chosen then. So the two
measurements this module takes are what stand in for the run's own guards, and
they are a different kind of work from writing a label.

WHAT EACH MEASUREMENT PREVENTS, because the two are not interchangeable.

A LIVE RUN is the race the clause closes first. A run of the item that reaches
`pr_refresh` DISARMS the pull request and rebases it, so an arming written while
that run is alive is either undone (the harmless outcome) or survives into a
rebased head the run then pushes — and an armed pull request whose checks are
green merges on the forge's own schedule, so the forge lands a tree no record
names. There is no ordering a release can choose that avoids this; the only safe
answer is not to arm while a run is alive.

AN UNPROVED HEAD is the slower version of the same loss. The pull request's head
moves for reasons a release cannot see — a refresh of an earlier run, a push an
operator made by hand — and the record that proved a tree names the head it ran
on. Arming a head no `verified` or `carried_forward` record names merges a tree
nothing graded, and the merge reads exactly like any other green merge.

EVERY ARM THAT CANNOT MEASURE REFUSES, which is the direction this fleet's
gauges fail in and the reason the clause says "naming the measurement that
failed". A `fabro ps` that did not answer cannot establish that no run is live;
an unreadable comment payload cannot establish which head was proved. A gauge
that armed when blinded would turn the refusal into a merge, and the record it
left would read exactly like a healthy release.

THE ENGINE AND FORGE ARE REACHED THROUGH THE VALVE'S OWN RUNNER, adapted to the
`CommandRunner` shape the port and the record reader take. One seam for the whole
action is load-bearing rather than tidy: a guard reading a forge of its own could
refuse against one pull request while the valve armed another, and neither record
would show it.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from subprocess import run
from typing import Protocol, cast

from livespec_orchestrator_beads_fabro.commands._config import (
    resolve_fabro_bin,
    resolve_fabro_factory,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine_types import CommandResult
from livespec_orchestrator_beads_fabro.commands._dispatcher_factory_bin import factory_fabro_bin
from livespec_orchestrator_beads_fabro.commands._dispatcher_proof_evidence import (
    read_pull_request_records,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_publication_head import (
    PROOF_HEAD_ANCHOR_VERDICTS,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_publish_branch_liveness import (
    ItemRunLiveness,
    live_run_ids_for_item,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_reflection_journal import (
    read_journal_records,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_resume_anchor import published_head
from livespec_orchestrator_beads_fabro.commands._drive_reject_valve import HumanValveRunner
from livespec_orchestrator_beads_fabro.commands._fabro_port import FabroPort, FabroTarget
from livespec_orchestrator_beads_fabro.commands._run_attribution import journaled_run_ids

__all__: list[str] = [
    "ARM_REFUSAL_LIVE_RUN",
    "ARM_REFUSAL_UNPROVED_HEAD",
    "ArmRefusal",
    "MergeHoldCommandRun",
    "arm_refusal_for_release",
]

# The two valve error codes a guarded release can return. Each NAMES the
# measurement that stopped it rather than ranking it, per the repository rule
# that an option set is never labelled as numbered tiers -- and they are
# separate because the remedies are: a live run is waited out, while an unproved
# head is a pull request whose proof has to be re-established by a dispatch.
ARM_REFUSAL_LIVE_RUN = "live-run"
ARM_REFUSAL_UNPROVED_HEAD = "unproved-head"

_PS_TIMEOUT_SECONDS = 60.0
_GH_TIMEOUT_SECONDS = 300.0
_JOURNAL_SUBPATH = ("tmp", "fabro-dispatch-journal.jsonl")


class MergeHoldCommandRun(Protocol):
    """The slice of a completed command the merge-hold surfaces read.

    Declared HERE, in the lower of the two modules, and imported by the valve
    rather than restated there: both read the same three members off the same
    injected runner, and two declarations of one shape is how the valve's
    refusal prose and this guard's measurements come to disagree about what a
    runner answered.
    """

    @property
    def returncode(self) -> int: ...

    @property
    def stdout(self) -> str: ...

    @property
    def stderr(self) -> str: ...


@dataclass(frozen=True, kw_only=True)
class ArmRefusal:
    """One reason a release may not arm, with the message an operator reads.

    `error` is the valve's machine-readable code and `message` is the prose. Both
    rather than one, for the reason every other valve refusal here carries both:
    the code is what a caller routes on and the prose is what names the
    measurement, and deriving either from the other loses the half it is not.
    """

    error: str
    message: str


def arm_refusal_for_release(
    *,
    repo: Path,
    work_item_id: str,
    pr_number: int,
    pr_head: str | None,
    runner: HumanValveRunner | None,
) -> ArmRefusal | None:
    """Why this release may not arm pull request `pr_number`, or `None` when it may.

    The liveness reading comes FIRST because it is the question whose answer can
    make the second one moot: a live run is about to move the head this guard
    would otherwise compare against, so a head comparison taken beside a live run
    is a measurement of a value that is already changing.

    `pr_head` is the head the valve's OWN pull-request view read, threaded down
    rather than re-read here. A second read could answer differently for the same
    pull request in the same action, and nothing in the record would say which
    reading the arming was justified by -- the same resolve-once rule the
    integration contract states.
    """
    command_runner = _ValveCommandRunner(runner=runner, cwd=repo)
    liveness = _item_run_liveness(repo=repo, work_item_id=work_item_id, runner=command_runner)
    if not liveness.observed:
        return ArmRefusal(
            error=ARM_REFUSAL_LIVE_RUN,
            message=(
                f"set-merge-hold:off refused: `fabro ps` did not answer for the configured "
                f"factory, so whether a run of {work_item_id} is still live could not be "
                f"established. Arming pull request #{pr_number} on an unmeasured liveness "
                "answer would let the forge merge a head a live run is about to rewrite, so "
                "the hold stands and the pull request is left unarmed."
            ),
        )
    if liveness.live_run_ids:
        return ArmRefusal(
            error=ARM_REFUSAL_LIVE_RUN,
            message=(
                f"set-merge-hold:off refused: {', '.join(liveness.live_run_ids)} is still "
                f"non-terminal on the configured factory, so a run of {work_item_id} is live "
                f"and its own pr_refresh disarms and rebases pull request #{pr_number}. The "
                "hold stands and the pull request is left unarmed; release it once the run "
                "has ended."
            ),
        )
    return _head_refusal(
        repo=repo,
        work_item_id=work_item_id,
        pr_number=pr_number,
        pr_head=pr_head,
        runner=command_runner,
    )


def _head_refusal(
    *,
    repo: Path,
    work_item_id: str,
    pr_number: int,
    pr_head: str | None,
    runner: _ValveCommandRunner,
) -> ArmRefusal | None:
    """Why the pull request's CURRENT head is not one this release may arm.

    Three absences share one refusal code and are worded apart, because the code
    is what the caller routes on while the prose is the only thing that says which
    reading was missing: the forge could not report the head, it carries no
    anchoring record, or the anchoring record names no single head. A fourth arm
    is the one positive negative -- a head that WAS read and differs.
    """
    if pr_head is None:
        return _unproved(
            pr_number=pr_number,
            detail=(
                "the forge did not report the pull request's current head, so whether it is "
                "the head a verified or carried_forward record names could not be measured"
            ),
        )
    records = read_pull_request_records(repo=repo, pr_number=pr_number, runner=runner)
    if records is None:
        return _unproved(
            pr_number=pr_number,
            detail=(
                "the forge could not be asked for the Proof of Done records on it, so the "
                "head the latest verified or carried_forward record names could not be read"
            ),
        )
    anchors = [one for one in records if one.verdict in PROOF_HEAD_ANCHOR_VERDICTS]
    if not anchors:
        return _unproved(
            pr_number=pr_number,
            detail=(
                "it carries no verified or carried_forward Proof of Done record, so no record "
                f"names a head {work_item_id} may be merged at"
            ),
        )
    # The LATEST anchor, by position, is the item's latest run's answer: a
    # `carried_forward` record supersedes the verified record it carries, and a
    # later run's record is appended after an earlier run's, so reading per
    # verdict would let an older run's head win a chain of carry-forwards.
    proved = published_head(body=anchors[-1].body)
    if proved is None:
        return _unproved(
            pr_number=pr_number,
            detail=(
                f"its latest {anchors[-1].verdict} Proof of Done record names no single full "
                "publish-branch head, so the tree it proved cannot be established"
            ),
        )
    if proved != pr_head:
        return _unproved(
            pr_number=pr_number,
            detail=(
                f"it is at {pr_head} while its latest {anchors[-1].verdict} Proof of Done "
                f"record names {proved}, so the head it carries is one no record of this "
                "item's latest run proved"
            ),
        )
    return None


def _unproved(*, pr_number: int, detail: str) -> ArmRefusal:
    return ArmRefusal(
        error=ARM_REFUSAL_UNPROVED_HEAD,
        message=(
            f"set-merge-hold:off refused: pull request #{pr_number} may not be armed because "
            f"{detail}. The hold stands and the pull request is left unarmed."
        ),
    )


def _item_run_liveness(
    *, repo: Path, work_item_id: str, runner: _ValveCommandRunner
) -> ItemRunLiveness:
    """Ask the configured factory which runs of this item are still non-terminal.

    The SAME reading the publish-branch reclaim takes, through the same
    attribution helper, so "still alive" means one thing across the two surfaces
    that act on it. The factory is resolved from the repository's own
    configuration rather than from a dispatch's argv, because a valve is invoked
    by a person and carries no dispatch.
    """
    factory = resolve_fabro_factory(cwd=repo, factory=None)
    ps = FabroPort(
        fabro_bin=factory_fabro_bin(factory=factory, fallback=resolve_fabro_bin(cwd=repo)),
        target=FabroTarget(server_url=factory.server, dev_token=factory.dev_token),
        runner=runner,
        cwd=repo,
    ).ps(timeout_seconds=_PS_TIMEOUT_SECONDS)
    if ps.command.exit_code != 0:
        return ItemRunLiveness(live_run_ids=(), observed=False)
    return ItemRunLiveness(
        live_run_ids=live_run_ids_for_item(
            runs=ps.runs,
            journaled=journaled_run_ids(
                records=read_journal_records(journal_path=repo.joinpath(*_JOURNAL_SUBPATH)),
                work_item_id=work_item_id,
            ),
            work_item_id=work_item_id,
        ),
        observed=True,
    )


@dataclass(frozen=True, kw_only=True)
class _ValveCommandRunner:
    """The valve's own runner, in the `CommandRunner` shape the port and reader take.

    An ADAPTER rather than a second seam: the engine port and the record reader
    both ask for `run(argv=, cwd=, timeout_seconds=)`, while a human valve's
    runner is handed `(argv, cwd)` and nothing else. Threading the valve's runner
    through this is what keeps one action reading one forge and one factory.

    `timeout_seconds` is accepted and DROPPED, because a valve runner has no
    timeout to apply and inventing one here would impose a bound the valve's own
    direct `subprocess.run` does not carry.
    """

    runner: HumanValveRunner | None
    cwd: Path

    def run(
        self,
        *,
        argv: list[str],
        cwd: Path,
        timeout_seconds: float,
        env: Mapping[str, str | None] | None = None,
        stdin: int | None = None,
    ) -> CommandResult:
        """Run `argv`, returning the completed result; never raises for a non-zero exit."""
        _ = (timeout_seconds, env, stdin)
        if self.runner is None:
            done = run(argv, check=False, cwd=cwd, text=True, capture_output=True)  # noqa: S603
            return _result(answered=cast("MergeHoldCommandRun", done))
        return _result(answered=cast("MergeHoldCommandRun", self.runner(argv=tuple(argv), cwd=cwd)))


def _result(*, answered: MergeHoldCommandRun) -> CommandResult:
    """One completed command in the shape the port and the record reader take."""
    return CommandResult(
        exit_code=answered.returncode, stdout=answered.stdout, stderr=answered.stderr
    )
