"""WHERE the post-merge janitor's check suite EXECUTES, and how its verdict reads.

`_dispatcher_janitor_venue` answers a different question with a confusingly
similar name: WHICH REF the fresh checkout is made at. This module answers which
MACHINE the check suite then runs on -- the dispatching host, or the
maintainer-owned k3s cluster through the shared delegated gate -- and reads the
chosen venue's verdict back.

THE TWO VENUES ARE NOT SYMMETRICAL IN WHAT THEIR EXIT CODE MEANS, which is the
whole reason this is code rather than one more declared argv. A host-local check
suite exits 0 or non-zero and that IS the verdict. A delegated gate reaches its
answer across a tailnet, an API server, a queue and a pod, so it has THREE
outcomes, not two: the Job completed, the Job failed, or nothing was decided at
all. The third has to stay distinguishable from the second, because a plumbing
fault and a red tree want opposite responses from whoever reads the post-merge
outcome -- and because the ratified post-merge gate may never report green on an
answer it did not obtain.

NO-VERDICT IS RED, NEVER `janitor-env-degraded`. The degraded outcome exists for
a host-environment failure that stopped the janitor from running at all, and it
reports `green` at a distinct stage because the merge is confirmed either way.
That is the wrong shape here: a submitted gate whose verdict was lost is not a
venue that failed to provision, it is a gate that was asked and did not answer,
and the one thing it must not do is let an item close on a reading nobody took.
So every unobservable arm below lands on the SAME red outcome a `Failed` Job
lands on, and says in its own detail that the missing cluster verdict IS the
finding.

THE GATE CLIENT IS INVOKED AS A SUBPROCESS RATHER THAN IMPORTED, and that is a
constraint rather than a preference. `SPECIFICATION/constraints.md` says the
plugin carries no runtime dependency outside its own vendored tree, and the
shared dev-tooling package is NOT vendored: it is a development dependency
resolved into a governed repository's own virtual environment. Measured on this
host, the installed plugin root carries no such environment, and the shebang
wrappers put only the package root and the vendored tree on `sys.path` -- so a
module-level import of the gate client would resolve under this repository's test
run and raise `ModuleNotFoundError` on every real dispatch. Invoking it in the
JANITOR CHECKOUT, which does carry the environment, is the same route the
dispatch-time conformance premises already take, and it reuses the gate's push,
submit, poll and adjudication rather than re-implementing any of them.

THE VERDICT IS READ OFF THE CLIENT'S OWN JSON LOG LINE for the same reason. Its
exit code answers a PUSH question -- it is 0 only when the gate passed AND a
green token was written for the pushed tree -- and the token is the pushing
client's business, not a post-merge gate's. The state word is the machine surface
that client renders JSON expressly to publish, so it is what is read, and an
output carrying no readable state is treated as no verdict at all.

ONE LIMITATION IS ACCEPTED HERE RATHER THAN WORKED AROUND. The delegated gate
pins the diff base its range-scoped members judge to the default branch of this
fleet, as a constant rather than a per-request knob. The janitor venue is
provisioned AT that branch's tip, so the range those members see is empty --
which is exactly what they already saw in a host-local janitor run of the same
checkout, so nothing regresses. Widening the shared package's base to the
governed repository's own declared default branch is that package's change to
make, not this module's.

OFF IS THE STRICT PATH, so every doubt resolves to the host-local venue. Only a
declaration spelling the cluster value exactly selects the cluster; an absent
`janitor` block, an absent key, a value of the wrong type and an unrecognised
word all keep the check suite the repository runs today. That asymmetry is the
mirror of the fail-closed verdict above and lands in the same place: both
defaults reduce to "run the checks", which is the only direction in which a
mistake is merely expensive rather than unsound.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from livespec_orchestrator_beads_fabro.commands._config import dispatcher_block
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine_journal import tail
from livespec_orchestrator_beads_fabro.commands._dispatcher_integration_defaults import (
    JANITOR_CLUSTER_GATE_DEFAULT,
)
from livespec_orchestrator_beads_fabro.effects import JsonParseFailure, parse_json

if TYPE_CHECKING:
    from pathlib import Path

    from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandResult

__all__: list[str] = [
    "CLUSTER_GATE_ARGV",
    "JANITOR_VENUE_CLUSTER_JOB",
    "JANITOR_VENUE_HOST_LOCAL",
    "JANITOR_VENUE_KEY",
    "cluster_janitor_red",
    "cluster_venue_declared",
    "host_janitor_red",
    "janitor_runs_on_the_cluster",
]

# The committed key, spelled as every operator-facing sentence names it, and the
# two venues it selects. The host-local value is named even though it is what
# silence already means: a repository that has deliberately opted OUT should be
# able to say so in its own diff rather than by omission.
JANITOR_VENUE_KEY = "dispatcher.janitor.venue"
JANITOR_VENUE_HOST_LOCAL = "host_local"
JANITOR_VENUE_CLUSTER_JOB = "cluster_job"

# The gate client's argv, re-exported from the one module the
# fleet-toolchain-literal ban admits the shared package's name in, so the engine
# reads the cluster venue's command and its verdict from one place.
CLUSTER_GATE_ARGV: tuple[str, ...] = JANITOR_CLUSTER_GATE_DEFAULT

_JANITOR_BLOCK = "janitor"
_VENUE_FIELD = "venue"

# The two AFFIRMATIVE delegated-gate states, LOCKSTEP WITH the shared
# dev-tooling package's `gate_remote_verdict`. Neither file can see the other,
# and a drifted word is not a syntax error anywhere: it is a PASSED gate read as
# a red one, at post-merge time, on an item whose work has already landed. Both
# are written as equalities against a single word rather than as a set of
# rejected words, so a state the package adds later lands on the no-verdict arm
# by default instead of falling through the gaps of a rejection list.
_GATE_PASSED = "PASSED"
_GATE_FAILED = "FAILED"
_STATE_FIELD = "state"


def cluster_venue_declared(*, block: dict[str, Any]) -> bool:
    """Whether this `dispatcher` block selects the cluster venue, exactly.

    PURE, over a block the caller already read. Every arm that is not the
    cluster word answers no, including a `janitor` node that is not an object:
    the alternative branch runs the repository's own check suite locally, which
    is a real verdict, so resolving a malformed declaration that way costs a
    host-local run rather than a gate nobody has proven on that host.
    """
    janitor = block.get(_JANITOR_BLOCK)
    if not isinstance(janitor, dict):
        return False
    return cast("dict[str, Any]", janitor).get(_VENUE_FIELD) == JANITOR_VENUE_CLUSTER_JOB


def janitor_runs_on_the_cluster(*, cwd: Path) -> bool:
    """Read the governed repository's declared janitor venue off its `.livespec.jsonc`.

    An absent key is an ANSWER -- this repository keeps the host-local venue --
    so it rides the same block reader as every other dispatcher key rather than
    an absent-file path of its own.
    """
    return cluster_venue_declared(block=dispatcher_block(cwd=cwd))


def host_janitor_red(*, result: CommandResult, checkout: Path) -> str | None:
    """The HOST-LOCAL venue's red detail, or `None` when its suite was green.

    `None` is an absence the caller acts on as ordinary control flow -- there is
    no red to report -- which is why there is no green detail here: the green
    post-merge outcome's wording belongs to the flow that closes the gate, and
    is the same sentence whichever venue produced the verdict.
    """
    if result.exit_code == 0:
        return None
    return (
        f"post-merge janitor red in fresh checkout {checkout} "
        f"(kept for diagnosis): {tail(text=result.stderr)}"
    )


def cluster_janitor_red(*, result: CommandResult, checkout: Path) -> str | None:
    """The CLUSTER venue's red detail, or `None` when the gate Job completed.

    The state word decides, never the exit code: a gate that PASSED and could
    not write its green token exits non-zero, and that token authorises a push
    rather than closing a post-merge gate.

    The two non-pass arms are worded apart because their remedies are opposite.
    A `Failed` Job is a RED TREE, and the operator's next move is in the gate's
    own log. Anything else -- the package's no-verdict state, a client that
    never started, an output nothing can be read out of -- is a gate that
    DECIDED NOTHING, and the operator's next move is the cluster. Reporting the
    second as the first sends them to read a verdict that does not exist;
    reporting the first as the second tells them their red tree was plumbing.
    """
    state = _gate_state(text=result.stderr)
    if state == _GATE_PASSED:
        return None
    if state == _GATE_FAILED:
        return (
            f"post-merge janitor RED: the cluster gate Job reported a FAILED verdict for the "
            f"fresh checkout {checkout} (kept for diagnosis): {tail(text=result.stderr)}"
        )
    return (
        f"post-merge janitor RED: the cluster gate reached no verdict for the fresh checkout "
        f"{checkout}, so nothing green may be concluded -- the missing cluster verdict is the "
        f"finding, not the tree: {tail(text=result.stderr)}"
    )


def _gate_state(*, text: str) -> str | None:
    """The state the gate client reported, or `None` for no readable reading.

    Read from the LAST state-bearing line rather than the first. The client logs
    one verdict line per run today, so the two agree; keying on the last is what
    keeps that true if it ever narrates its progress first, because the verdict
    is the thing it says once it knows.
    """
    for line in reversed(text.splitlines()):
        parsed = parse_json(text=line)
        if isinstance(parsed, JsonParseFailure) or not isinstance(parsed, dict):
            continue
        state = cast("dict[str, Any]", parsed).get(_STATE_FIELD)
        if isinstance(state, str):
            return state
    return None
