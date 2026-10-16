"""WHERE the post-merge janitor's check suite RUNS: this host, or the cluster.

`_dispatcher_janitor_venue` answers which REF the fresh checkout is made at.
This answers the orthogonal question of which MACHINE the check suite then runs
on, and it is a different kind of decision: the ref is a property of the merge,
while the venue is a property of the repository's own configuration and of the
cluster the maintainer runs. The two change for different reasons, which is why
they are separate modules rather than one.

THE CLUSTER MECHANISM IS REUSED, NOT RE-IMPLEMENTED. The delegated pre-push
gate already pushes a tree to the gates mirror, renders a Job, submits it into
the `gates` namespace through the credential wrapper, waits for a terminal
condition, streams the pod logs back and renders a three-state verdict. The
janitor needs exactly that, against the janitor checkout instead of against a
pushing worktree, so it asks for exactly that -- and nothing here knows what a
mirror, a namespace or a Job condition is.

THE GATE IS INVOKED, NOT IMPORTED, AND THAT IS FORCED RATHER THAN PREFERRED.
The implementation brief asked for the library call. It cannot be one: this
plugin declares NO runtime dependencies and ships its own vendored runtime, and
a dispatch runs as `python3 dispatcher.py` under the ambient interpreter, which
resolves none of the shared dev-tooling package (measured in a sandbox clone of
this repository: `import livespec_dev_tooling` raises `ModuleNotFoundError`
under `/usr/bin/python3`, and the pinned package is a `[dependency-groups] dev`
member installed only into the project venv). An imported gate would therefore
reach no cluster from any real dispatch while passing every unit test, which is
the worst available failure: a janitor that reports red on every merge for a
reason nothing in the code says. So the gate is reached through its OWN entry
point, in the gated checkout's own environment, exactly as this repository's
three conformance premises reach that package.

WHAT THE BRIEF'S INSTRUCTION WAS PROTECTING IS KEPT. Its reason for rejecting
the CLI was that an exit code collapses a red tree and a lost cluster into one
number, and the two want opposite responses. They are not collapsed here,
because the gate's entry point does not only exit -- it renders its verdict as a
structured line carrying `state` and `detail`, and that is what is read. The
exit code is deliberately NOT read: a gate that PASSED but could not write the
push-specific green token exits non-zero, and that token is a fact about a push
this janitor is not making.

EVERY NON-PASS IS RED, INCLUDING EVERY WAY THE CLUSTER CAN SAY NOTHING. The
host-local janitor has a `janitor-env-degraded` outcome that is GREEN -- the
merge is confirmed on the remote and what failed was host provisioning -- and
that shape must never reach this path. A cluster that returned no verdict has
not gated the merged tree, so reporting it green would publish a gate nobody
ran; it is red. A host that cannot read the gates credential, a mirror push
that was refused, a Job that never reached a terminal condition and an entry
point that could not even be invoked all arrive here identically, which is
correct: each of them is the cluster saying nothing.

THE GATE DIFFS AGAINST THIS FLEET'S DEFAULT BRANCH, WHICH IS A LIMITATION RATHER
THAN A CHOICE. Eight members of the gated aggregate judge a commit RANGE, and
the shared client resolves that range's base from a single constant it does not
expose as a per-request knob. This repository's default branch is that constant,
so the janitor's range is the one it would have judged locally. An adopter whose
default branch differs would get a gate about a range its repository does not
use -- so widening that constant belongs to the dev-tooling package that owns
it, and until then this venue is not one such a repository should select.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, cast

from returns.pipeline import is_successful
from returns.unsafe import unsafe_perform_io

from livespec_orchestrator_beads_fabro.commands._dispatcher_engine_journal import (
    StageJournalOptions,
    run_stage,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_integration_defaults import (
    CLUSTER_JANITOR_GATE_ARGV,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_policy_settings import (
    read_dispatcher_config_value,
)
from livespec_orchestrator_beads_fabro.effects import parse_json

if TYPE_CHECKING:
    from pathlib import Path

    from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import (
        CommandResult,
        CommandRunner,
        DispatchOutcome,
        JournalWriter,
    )
    from livespec_orchestrator_beads_fabro.commands._dispatcher_plan import DispatchPlan, PrView

__all__: list[str] = [
    "CLUSTER_GATE_STAGE",
    "CLUSTER_JOB_VENUE",
    "GATE_FAILED",
    "GATE_NO_VERDICT",
    "GATE_PASSED",
    "HOST_PROCESS_VENUE",
    "ClusterJanitorVerdict",
    "cluster_janitor_red",
    "janitor_runs_on_cluster",
]

# The two venues, each NAMING WHAT IT IS rather than ranking a tier: the check
# suite runs as a process on this host, or as a Job on the cluster.
HOST_PROCESS_VENUE = "host_process"
CLUSTER_JOB_VENUE = "cluster_job"

_JANITOR_GATE_VENUE_KEY = "janitor_gate_venue"

# The journal stage the cluster gate runs under. DISTINCT from the host-local
# `janitor-post-merge` rather than a reuse of it, because the two stages are
# answered by different machines and a reader of the dispatch journal has no
# other way to tell which one gated a merge.
CLUSTER_GATE_STAGE = "janitor-post-merge-cluster"

# The three states the delegated gate renders, IN LOCKSTEP with the shared
# dev-tooling package's own constants. They cross a process boundary as text, so
# they are spelled here rather than imported -- the package is not resolvable
# from a dispatch's interpreter, which is the whole reason the gate is invoked
# rather than imported. A test pins these three against the package's own.
GATE_PASSED = "PASSED"
GATE_FAILED = "FAILED"
GATE_NO_VERDICT = "NO_VERDICT"

_GATE_STATES = frozenset((GATE_PASSED, GATE_FAILED, GATE_NO_VERDICT))

# The gate has the whole check suite plus cluster scheduling to get through, so
# it is given the ceiling the host-local suite had rather than a tighter one:
# a janitor killed by its own caller reports nothing, which is the one outcome
# this venue may not produce silently.
_GATE_TIMEOUT_SECONDS = 3600.0

_UNREADABLE_GATE_OUTPUT = "the cluster gate rendered no verdict line this janitor could read"


@dataclass(frozen=True, kw_only=True)
class ClusterJanitorVerdict:
    """What the cluster said about the merged tree, and why.

    `state` is the gate's OWN answer, carried verbatim, and `detail` is the
    reason an operator acts on. They are kept apart because the state decides
    what the janitor does and the detail decides where the operator looks, and
    collapsing them would make a lost cluster and a red tree read alike.
    """

    state: str
    detail: str


def janitor_runs_on_cluster(*, cwd: Path) -> bool:
    """Whether `cwd`'s committed configuration sends its janitor to the cluster.

    OFF IS THE STRICT PATH, so every doubt resolves to it. Only the literal
    `cluster_job` selects the cluster; an absent key, an unknown value, a value
    of the wrong type and a `.livespec.jsonc` that cannot be parsed all keep the
    host-local check suite. That asymmetry is the one that costs least when it
    is wrong: a repository that should have delegated merely runs its own checks
    where it always did, while the opposite default would send a repository
    nobody configured at a cluster it has no credential for and turn every one
    of its merges red.
    """
    configured = read_dispatcher_config_value(cwd=cwd, key=_JANITOR_GATE_VENUE_KEY)
    if not is_successful(configured):
        return False
    return unsafe_perform_io(configured.unwrap()) == CLUSTER_JOB_VENUE


def cluster_janitor_red(
    *,
    outcome_type: type[DispatchOutcome],
    plan: DispatchPlan,
    runner: CommandRunner,
    journal: JournalWriter,
    merged: PrView,
) -> DispatchOutcome | None:
    """Gate the merged tree on the cluster; `None` means the Job passed.

    `None` rather than a green outcome, because the janitor is not the last
    thing the post-merge flow does: the fresh checkout still has to be removed,
    and a venue that returned its own green would either skip that or duplicate
    it. The caller owns the green; this owns every way of not reaching one.
    """
    result = run_stage(
        runner=runner,
        journal=journal,
        plan=plan,
        stage=CLUSTER_GATE_STAGE,
        command=(
            list(CLUSTER_JANITOR_GATE_ARGV),
            plan.janitor_checkout,
            _GATE_TIMEOUT_SECONDS,
            None,
        ),
        # Covered by the same retention clause the host-local suite is: the
        # verdict line is bounded, while the pod logs that say WHICH check went
        # red ride the same streams and disappear with the checkout.
        journal_options=StageJournalOptions(retention=plan.janitor_retention),
    )
    verdict = _gate_verdict(result=result)
    if verdict.state == GATE_PASSED:
        return None
    return outcome_type(
        work_item_id=plan.work_item_id,
        status="failed",
        stage=CLUSTER_GATE_STAGE,
        pr_number=merged.number,
        merge_sha=merged.merge_sha,
        detail=_red_detail(plan=plan, verdict=verdict),
    )


def _red_detail(*, plan: DispatchPlan, verdict: ClusterJanitorVerdict) -> str:
    """The operator's line for a merge the cluster did not pass.

    Nothing here is ever green: a merge the cluster did not pass has not been
    gated, whichever way the cluster declined to pass it.
    """
    return (
        f"post-merge janitor red: the cluster gate Job reported {verdict.state} on the merged "
        f"tree in {plan.janitor_checkout}: {verdict.detail}"
    )


def _gate_verdict(*, result: CommandResult) -> ClusterJanitorVerdict:
    """Read the gate's own verdict out of what its invocation rendered.

    BOTH STREAMS ARE SEARCHED, and the LAST recognised line wins. The gate
    streams the Job's pod logs to its caller before it renders its verdict, so
    the verdict is one line among many and is the last of them; and a pod log
    that happens to be structured JSON is not a verdict, which is why a line
    counts only when its `state` is one of the three the gate renders.

    An invocation that rendered no such line reached no verdict -- the entry
    point was not resolvable, the process died, the output was truncated -- so
    it lands on the same state a lost cluster does. The exit code is never
    consulted: a PASSED gate whose push-specific green token could not be
    written exits non-zero, and that token is a fact about a push this janitor
    is not making.
    """
    for line in reversed((result.stdout + "\n" + result.stderr).splitlines()):
        parsed = parse_json(text=line)
        if not isinstance(parsed, dict):
            continue
        rendered = _verdict_from_record(record=cast("dict[str, object]", parsed))
        if rendered is not None:
            return rendered
    return ClusterJanitorVerdict(state=GATE_NO_VERDICT, detail=_UNREADABLE_GATE_OUTPUT)


def _verdict_from_record(*, record: dict[str, object]) -> ClusterJanitorVerdict | None:
    """One structured line as a verdict, or `None` when it is not one."""
    state = record.get("state")
    if not isinstance(state, str) or state not in _GATE_STATES:
        return None
    detail = record.get("detail")
    return ClusterJanitorVerdict(
        state=state, detail=detail if isinstance(detail, str) else "the gate gave no detail"
    )
