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

from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, cast

from livespec_orchestrator_beads_fabro.commands._config import dispatcher_block
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine_journal import tail
from livespec_orchestrator_beads_fabro.commands._dispatcher_integration_defaults import (
    JANITOR_CLUSTER_GATE_DEFAULT,
)
from livespec_orchestrator_beads_fabro.effects import JsonParseFailure, parse_json

if TYPE_CHECKING:
    from pathlib import Path

    from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import (
        CommandResult,
        CommandRunner,
    )

__all__: list[str] = [
    "CLUSTER_GATE_ARGV",
    "JANITOR_VENUE_CLUSTER_JOB",
    "JANITOR_VENUE_HOST_LOCAL",
    "JANITOR_VENUE_KEY",
    "cluster_janitor_red",
    "cluster_venue_declared",
    "gate_tree_hash",
    "host_janitor_red",
    "janitor_check_row_fields",
    "janitor_check_started_at",
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

# The `janitor-post-merge` row's own account of the venue, named here beside the
# selection it reports rather than at the journal writer, so the word a row
# carries and the word the selection answered cannot drift.
#
# THE ROW IS WHERE A LATER READER STANDS, and until it carried this field nobody
# stood there. The cluster venue shipped while the row kept saying nothing about
# which machine ran the suite, so two sessions established the venue from
# OUTSIDE the journal -- one from the gate Job's own status in the cluster's
# `gates` namespace plus this module's rule that only `PASSED` reads green, one
# from a canary worktree's `.livespec.jsonc` and the stage's timing. Both
# readings were right and neither survives the run.
#
# Spelled SEPARATELY from `_VENUE_FIELD` above even though the two strings
# agree today: that one is the key a repository WRITES inside its `janitor`
# block, this one is the field a journal row CARRIES, and nothing ties the two
# names together. Folding them into one constant would make a rename of either
# surface silently rename the other.
_ROW_VENUE_FIELD = "venue"
_ROW_STARTED_AT_FIELD = "started_at"
_ROW_GATE_STATE_FIELD = "gate_state"
_ROW_GATE_TREE_HASH_FIELD = "gate_tree_hash"

# The Job identity and timing keys the verdict line MAY carry. Each one present
# on that line is COPIED under the same name with the same value -- a value of
# `null` included, because the gate saying its Job had not started is a
# different fact from a key the line never mentioned -- and each absent one is
# OMITTED.
#
# NONE of them is ever DERIVED here, and the gate's naming convention is
# exactly why that rule needs stating: the Job is `gate-<repository>-<first
# twelve of the tree hash>` in the `gates` namespace, and the row already
# carries that tree hash, so a name could be constructed from what is in hand.
# A constructed name reads on the row exactly like a reported one and is wrong
# whenever the gate did not in fact create that Job -- which is precisely the
# case an operator reads this row to investigate.
_ROW_JOB_FIELDS: tuple[str, ...] = (
    "job_name",
    "namespace",
    "job_started_at",
    "job_finished_at",
)

# The submitted-tree reading, and how long it may take. `HEAD^{tree}` resolves
# the TREE rather than the commit: both render as forty hex characters and both
# look entirely plausible in a journal, but only the tree is the value the gate
# Job's own `livespec.gate/tree-hash` label holds -- so a row carrying the
# commit would send an operator looking for a Job that cannot exist.
_SUBMITTED_TREE_REVISION = "HEAD^{tree}"
_SUBMITTED_TREE_TIMEOUT_SECONDS = 30.0


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
    state = _state_of(line=_verdict_line(text=result.stderr))
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


def janitor_check_started_at() -> str:
    """The instant the check-suite command is about to be launched at.

    Taken by the CALLER, immediately before the launch, and handed to the row
    projection afterwards. It cannot be stamped where the row is built: that
    happens once the command has returned, and the row already carries its own
    append instant, so a start taken there would report every stage as having
    taken no time at all.

    The seconds-precision UTC format is `_dispatcher_io.utc_now_iso`'s, and
    this is a private copy of it rather than an import, because that module
    imports `_dispatcher_engine`, whose own import chain reaches this one --
    so the shared reader cannot be reached from here without closing a cycle.
    `_needs_attention_ready_aging` and `_dispatcher_host_record_post` carry the
    same copy for the same reason.
    """
    return datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def gate_tree_hash(*, runner: CommandRunner, checkout: Path) -> str | None:
    """The full tree hash of the janitor checkout's HEAD: the tree submitted to the gate.

    Read BEFORE the client is launched, because it is the tree the gate is
    being ASKED about -- which is why the row can name it even when no gate Job
    ever started, and why it is the value that lets an operator find, or rule
    out, the Job that ran for it.

    Taken DIRECTLY on the runner rather than through `run_stage`, exactly as
    the venue resolution's own merge-containment probe is: this is a reading
    taken FOR a journal row, and journaling it as a stage of its own would put
    a second row beside the one it belongs to.

    `None` is a reading that could not be TAKEN, and never the empty string:
    an empty string compares as a value, so a row carrying it would report a
    tree hash of nothing rather than the absence of one.
    """
    result = runner.run(
        argv=["git", "-C", str(checkout), "rev-parse", _SUBMITTED_TREE_REVISION],
        cwd=checkout,
        timeout_seconds=_SUBMITTED_TREE_TIMEOUT_SECONDS,
    )
    return result.stdout.strip() or None


def janitor_check_row_fields(
    *, on_the_cluster: bool, result: CommandResult, tree_hash: str | None, started_at: str
) -> dict[str, object]:
    """The `janitor-post-merge` row's venue account, as ONE projection.

    PURE, over the venue the selection already resolved and the check-suite
    command's own result. The venue reported is the RESOLVED one and never the
    declared value: a row echoing the declaration would report `cluster` -- or
    any other unrecognised word -- for a repository whose suite ran on the
    dispatching host, which is exactly the reading the fail-closed selection
    above exists to prevent anyone making.

    ONE projection over both venues rather than a builder each, because the
    row's whole claim is that a reader can tell the two apart from it: a pair of
    builders is how one arm comes to spell a shared field differently from the
    other.

    The HOST-LOCAL arm returns before any gate field, and that omission is
    load-bearing rather than tidy. The cluster arm writes `gate_state` as
    `null` where the client reached no verdict, which is a reading a later
    operator must be able to see; a host-local row carrying the same `null`
    would read as a cluster run whose gate said nothing, so the two states
    would be indistinguishable in exactly the place the field was added to
    distinguish them.
    """
    fields: dict[str, object] = {
        _ROW_VENUE_FIELD: JANITOR_VENUE_CLUSTER_JOB if on_the_cluster else JANITOR_VENUE_HOST_LOCAL,
        _ROW_STARTED_AT_FIELD: started_at,
    }
    if not on_the_cluster:
        return fields
    line = _verdict_line(text=result.stderr)
    fields[_ROW_GATE_STATE_FIELD] = _state_of(line=line)
    fields[_ROW_GATE_TREE_HASH_FIELD] = tree_hash
    # ONE reading of the verdict line serves both the state word and the Job
    # keys, which is the whole reason `_verdict_line` yields the line rather
    # than the state: a second parse would be a second reading nothing proves
    # agrees with the first about the output it describes.
    #
    # An absent line stands in as an EMPTY mapping, which carries no Job key
    # and is not a reading in its own right: a verdict line always holds its
    # own string `state`, so no real one can be empty.
    reported = line or {}
    fields.update({name: reported[name] for name in _ROW_JOB_FIELDS if name in reported})
    return fields


def _verdict_line(*, text: str) -> dict[str, Any] | None:
    """The gate client's VERDICT LINE, parsed, or `None` for no readable reading.

    The verdict line is the LAST standard-error line that parses as a JSON
    object carrying a STRING `state`. Last rather than first: the client logs
    one verdict line per run today, so the two agree, and keying on the last is
    what keeps that true if it ever narrates its progress first, because the
    verdict is the thing it says once it knows.

    The whole LINE is returned rather than just its state word, because the
    row's account and the janitor's verdict are two readings of one line -- and
    the row additionally copies whichever Job keys that line carries. Returning
    the state alone would make the row re-parse the same output to find them,
    which is two readings of one thing where one will do.
    """
    for line in reversed(text.splitlines()):
        parsed = parse_json(text=line)
        if isinstance(parsed, JsonParseFailure) or not isinstance(parsed, dict):
            continue
        fields = cast("dict[str, Any]", parsed)
        if isinstance(fields.get(_STATE_FIELD), str):
            return fields
    return None


def _state_of(*, line: dict[str, Any] | None) -> str | None:
    """The verdict line's state word, or `None` when there was no verdict line.

    A `cast` rather than a second `isinstance`: `_verdict_line` selects a line
    only once its `state` IS a string, so re-testing it here would be a branch
    no input can take and a quiet denial of what that selection guarantees.
    """
    return None if line is None else cast("str", line[_STATE_FIELD])
