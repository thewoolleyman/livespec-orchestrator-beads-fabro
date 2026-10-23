"""PERFORMING one availability confirmation turn, bounded, on the factory.

`SPECIFICATION/contracts.md` section "Factory-configurable ACP fallback
priority" -> "Availability is re-confirmed after expiry": "otherwise the probe
MUST be a minimal factory run. The probe sends one fixed minimal prompt. ...
Probe execution MUST be bounded by the committed-configuration-only
`dispatcher.availability_probe_timeout_seconds` (positive integer, default
120), including termination of unfinished probe work."

The IMPURE half of the probe, and the only one that reaches a factory.
`_acp_availability_probe` owns the shape, `_acp_availability_probe_outcome`
grades the ending, `_acp_availability_probe_records` builds the two records,
and this module launches the run, observes it, and hands those three their
inputs. Nothing here decides what an ending MEANS or what a record SAYS, which
is what keeps every one of those decisions exercisable with no factory at all.

THE TURN IS PLACED IN THE FACTORY'S DECLARED ENVIRONMENT, which is the fourth
of the four execution properties the clause names and the only one that is a
property of the SANDBOX rather than of the adapter. `_acp_availability_probe`
argues the first three from `render_adapter`'s byte equality; the "projected
worker credential identity" is whatever the server-catalog environment supplies,
so a target built from the server alone omits `--environment` and lands the turn
in the server's DEFAULT environment, whose credential is not the dispatch's.
Both outcomes of that omission are wrong and neither announces itself: with no
credential there, no healthy provider can ever earn a confirmation and the
post-expiry stall this module exists to end persists unchanged; with one, the
turn confirms a credential identity nobody dispatches with -- the "confirm a
model nobody ran" failure `availability_probe_refusal` turns an in-protocol
candidate away to avoid, arriving through the placement instead of through
`config_options`. The id is the dispatch path's OWN projection
(`factory_environment_id`) rather than a second read, so the probe and a
dispatch to the same factory cannot disagree about where they ran; an unusable
declaration reduces to None here exactly as it does there, which is safe for the
same reason -- `factory_declaration_refusal` has already refused the invocation.

TERMINATION IS PERFORMED BEFORE ANYTHING IS READ, and that ordering is the one
piece of mechanics here worth reading twice. The clause requires the bound to
include "termination of unfinished probe work", so a probe past its bound is
reaped FIRST -- `fabro rm -f`, the same verb the progress watchdog uses -- and
its cost is then reported unobservable. Reading the run before reaping it would
buy one cost figure at the price of leaving an adapter running against a
provider while this Dispatcher spends a round trip asking about it, and a
terminated probe's cost is the one figure nobody acts on: it mints no hold, and
the journal row says plainly that the measurement was interrupted.

A TIMED-OUT LAUNCH IS EXIT 124, which is `ShellCommandRunner`'s own mapping of
a timeout rather than a convention invented here. The constant is exported so
the test that drives the bound names the same value the runner produces instead
of a literal that could drift away from it.

THE RUN ID IS READ OFF A PARTIAL LAUNCH ON PURPOSE. `fabro run` prints the run
id early, so a launch this Dispatcher killed usually still carries one -- and
that id is the only thing that can reap the work. A launch whose id could not
be read reaps nothing, which is reported as `terminated=False` rather than
silently: there is unfinished work on the factory and this Dispatcher cannot
name it, and a record claiming otherwise would be the one lie that matters.

THE PROMPT BOUNDARY IS READ FROM THE EVENT AND NOT FROM A PARSED CHAIN START.
`scan_acp_events` requires `candidate_index` and `primary_generation` before it
will admit an `agent.acp.started`, deliberately, because its own consumer must
not assume which candidate ran. This read asks a strictly weaker question --
did the attempt cross the prompt boundary at all -- which the adapter-launch
clause answers from the event's PRESENCE, so a pre-chain engine's start still
tells a created session from an adapter that exited before the protocol.

TWO REFUSALS RETURN BEFORE ANY RUN EXISTS, and both are the clause's "any other
probe failure": the candidate the probe cannot faithfully run (see
`availability_probe_refusal`), and a repository with no participating factory to
record the confirmation on. The second is not a fallback to a host-side probe:
the clause permits one only when its outcome is "durably observable through the
same authoritative evidence source", and a repository declaring no factory has
no such source -- so there is nowhere for the confirmation to become host-wide
evidence, and running it anyway would spend an allowance for a record no peer
could ever read.
"""

from __future__ import annotations

import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from livespec_orchestrator_beads_fabro.commands._acp_availability_probe import (
    AVAILABILITY_PROBE_GOAL,
    AVAILABILITY_PROBE_GRAPH_FILE,
    AVAILABILITY_PROBE_MANIFEST,
    AVAILABILITY_PROBE_NODE,
    availability_probe_graph,
    availability_probe_labels,
    availability_probe_refusal,
)
from livespec_orchestrator_beads_fabro.commands._acp_availability_probe_outcome import (
    AcpProbeObservation,
    probe_confirms,
    probe_ending,
)
from livespec_orchestrator_beads_fabro.commands._acp_availability_probe_records import (
    probe_hold_record,
    probe_journal_record,
)
from livespec_orchestrator_beads_fabro.commands._acp_candidate_schema import AcpCandidate
from livespec_orchestrator_beads_fabro.commands._acp_fallback_event_types import ACP_STARTED_EVENT
from livespec_orchestrator_beads_fabro.commands._config import (
    resolve_fabro_bin,
    resolve_fabro_factory,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine_binary_record import (
    engine_binary,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_factory_bin import factory_fabro_bin
from livespec_orchestrator_beads_fabro.commands._dispatcher_factory_environment import (
    factory_environment_id,
)

# The LEAF rather than the `_dispatcher_io` aggregate that re-exports it, for
# the reason `_acp_clearance_factory_record` states beside its own import: the
# aggregate's import closure reaches the ledger resolution this module's caller
# sits inside, and taking it would close the cycle the runner leaf exists to
# break.
from livespec_orchestrator_beads_fabro.commands._dispatcher_shell_runner import (
    ShellCommandRunner,
)
from livespec_orchestrator_beads_fabro.commands._fabro_port import FabroPort, FabroTarget
from livespec_orchestrator_beads_fabro.commands._fabro_port_node_outcomes import (
    fabro_node_outcomes,
    fabro_stage_node,
)
from livespec_orchestrator_beads_fabro.commands._fabro_port_records import (
    fabro_inspect_record,
    fabro_run_summaries_from_payload,
)
from livespec_orchestrator_beads_fabro.commands._fabro_port_types import FabroRunner

__all__: list[str] = [
    "PROBE_LAUNCH_TIMEOUT_EXIT_CODE",
    "AcpAvailabilityProbeResult",
    "run_availability_probe",
]

# `ShellCommandRunner`'s own mapping of a timed-out command. Named here so the
# bound's own test reads the runner's value rather than a literal beside it.
PROBE_LAUNCH_TIMEOUT_EXIT_CODE = 124

# The statuses that are a run CANCELLATION, both spellings the engine uses.
_CANCELLED_STATUS_KINDS: frozenset[str] = frozenset({"cancelled", "canceled"})
_SUCCEEDED_STATUS = "succeeded"

# Generous for one `inspect` or `events` read against a reachable factory, and
# bounded so an unresponsive one leaves the probe unconfirmed instead of
# holding the evaluation open. It is NOT the probe's own bound: that governs
# the TURN, and these are reads about a turn that has already ended.
_READ_TIMEOUT_SECONDS = 60.0


@dataclass(frozen=True, kw_only=True)
class AcpAvailabilityProbeResult:
    """One performed confirmation turn: what it ended as, and what it recorded.

    `terminated` is whether unfinished probe work was actually reaped, and it is
    reported separately from the ending because the two can disagree: a probe
    past its bound whose run id could not be read is `timed-out` and NOT
    terminated, which is unfinished work on a factory that this Dispatcher
    cannot name.

    `hold_record` is the appendable observation an eligible refusal mints and
    `None` for every other ending; `journal_record` is written for all six. The
    caller appends them -- this result carries no journal and no ledger, so the
    one place that decides WHEN a record lands stays the caller's.
    """

    ending: str
    occurred_at: str
    factory: str
    run_id: str | None
    terminated: bool
    hold_record: dict[str, object] | None
    journal_record: dict[str, object]

    @property
    def confirmed(self) -> bool:
        """Whether this turn confirms the candidate's availability."""
        return probe_confirms(ending=self.ending)


def run_availability_probe(  # noqa: PLR0913 — kw-only probe inputs; each is one INDEPENDENT operand of the one turn (which candidate, whose signatures, which item, which records it answers, when, how long, through what), and grouping any pair into a carrier would invent a relationship the turn does not have.
    *,
    repo: Path,
    candidate: AcpCandidate,
    builtin: bool,
    work_item_id: str,
    observation_ids: tuple[str, ...],
    now_iso: str,
    timeout_seconds: int,
    runner: FabroRunner | None = None,
) -> AcpAvailabilityProbeResult | str:
    """Run one confirmation turn for this candidate, or refuse saying why.

    A refusal is the clause's "any other probe failure" -- the candidate is
    skipped for this evaluation, no hold is minted, and selection continues --
    never a hold and never a needs-human decision.

    `now_iso` is the evaluation's own fixed instant and is what the hold's
    expiry is computed from, which is the clause's "Expiry is computed from
    occurrence time and never from ingestion": the probe is performed inside
    one evaluation, so the evaluation's instant IS the occurrence a later read
    must reproduce.
    """
    refusal = availability_probe_refusal(candidate=candidate)
    if refusal is not None:
        return refusal
    target = resolve_fabro_factory(cwd=repo)
    if target.server is None:
        return (
            f"no participating factory to record the confirmation on: factory "
            f"{target.name!r} declares no server, so a successful turn could not "
            f"become host-wide availability evidence"
        )
    command = ShellCommandRunner() if runner is None else runner
    fabro_bin = factory_fabro_bin(factory=target, fallback=resolve_fabro_bin(cwd=repo))
    port = FabroPort(
        fabro_bin=fabro_bin,
        target=FabroTarget(
            server_url=target.server,
            dev_token=target.dev_token,
            environment=factory_environment_id(factory=target),
        ),
        runner=command,
        cwd=repo,
        fabro_version=engine_binary(fabro_bin=fabro_bin, runner=command, cwd=repo).version,
    )
    return _performed(
        port=port,
        factory=target.name,
        candidate=candidate,
        builtin=builtin,
        work_item_id=work_item_id,
        observation_ids=observation_ids,
        now_iso=now_iso,
        timeout_seconds=timeout_seconds,
    )


def _performed(  # noqa: PLR0913 — the same kw-only probe inputs as above plus the opened port; see that function's own note.
    *,
    port: FabroPort,
    factory: str,
    candidate: AcpCandidate,
    builtin: bool,
    work_item_id: str,
    observation_ids: tuple[str, ...],
    now_iso: str,
    timeout_seconds: int,
) -> AcpAvailabilityProbeResult:
    """Launch the turn, observe its ending, and build the records it leaves."""
    launch = _launched(port=port, candidate=candidate, timeout_seconds=timeout_seconds)
    run_id = launch[0]
    timed_out = launch[1] == PROBE_LAUNCH_TIMEOUT_EXIT_CODE
    terminated = _terminated(port=port, run_id=run_id) if timed_out else False
    observation, cost = (
        (_timed_out_observation(), None) if timed_out else _observed(port=port, run_id=run_id)
    )
    ending = probe_ending(observation=observation)
    return AcpAvailabilityProbeResult(
        ending=ending,
        occurred_at=now_iso,
        factory=factory,
        run_id=run_id,
        terminated=terminated,
        hold_record=probe_hold_record(
            candidate=candidate,
            builtin=builtin,
            observation=observation,
            occurred_at=now_iso,
            run_reference=f"{factory}:{run_id}",
            work_item_id=work_item_id,
        ),
        journal_record=probe_journal_record(
            candidate=candidate,
            ending=ending,
            occurred_at=now_iso,
            factory=factory,
            run_id=run_id,
            cost_usd_micros=cost,
            observation_ids=observation_ids,
        ),
    )


def _launched(
    *, port: FabroPort, candidate: AcpCandidate, timeout_seconds: int
) -> tuple[str | None, int]:
    """Materialize the one-run payload, launch it, and report `(run id, exit)`.

    The payload lives in a temporary directory removed as the launch returns: it
    is an argument to one invocation rather than state, and the record it
    produces is on the factory.
    """
    with tempfile.TemporaryDirectory(prefix="livespec-acp-availability-probe-") as staging:
        package = Path(staging)
        graph = package / AVAILABILITY_PROBE_GRAPH_FILE
        _ = graph.write_text(
            availability_probe_graph(candidate=candidate, timeout_seconds=timeout_seconds),
            encoding="utf-8",
        )
        manifest = package / "workflow.toml"
        _ = manifest.write_text(AVAILABILITY_PROBE_MANIFEST, encoding="utf-8")
        goal = package / "goal.md"
        _ = goal.write_text(AVAILABILITY_PROBE_GOAL, encoding="utf-8")
        result = port.run(
            workflow_toml=manifest,
            goal_file=goal,
            inputs=(),
            timeout_seconds=float(timeout_seconds),
            labels=availability_probe_labels(candidate=candidate),
        )
    return (result.run_id, result.command.exit_code)


def _terminated(*, port: FabroPort, run_id: str | None) -> bool:
    """Reap the unfinished probe work, and report whether it was reaped.

    `False` for a launch whose run id could not be read: there is work on the
    factory and nothing here can name it. Reporting it as terminated would be
    the one claim a later reader cannot check.
    """
    if run_id is None:
        return False
    reaped = port.rm(run_id=run_id, timeout_seconds=_READ_TIMEOUT_SECONDS)
    return reaped.command.exit_code == 0


def _timed_out_observation() -> AcpProbeObservation:
    """The observation a terminated probe produces.

    Every field but the bound is False, which is honest rather than
    conservative padding: the run was reaped before it was read, so nothing is
    known about its turn, its session or its recorded failure -- and
    `probe_ending` grades the bound first, so none of those fields can change
    the ending.
    """
    return AcpProbeObservation(
        turn_completed=False,
        acp_started=False,
        cancelled=False,
        timed_out=True,
        failure=None,
    )


def _observed(*, port: FabroPort, run_id: str | None) -> tuple[AcpProbeObservation, int | None]:
    """Read one ended probe run, as `(observation, cost)`.

    A launch whose run id could not be read is observed as a PROCESS EXIT with
    no cost, which is the honest reading: no run was named, so no turn
    completed, no session was recorded and nothing refused anything.
    """
    if run_id is None:
        return (
            AcpProbeObservation(
                turn_completed=False,
                acp_started=False,
                cancelled=False,
                timed_out=False,
                failure=None,
            ),
            None,
        )
    inspected = port.inspect(run_id=run_id, timeout_seconds=_READ_TIMEOUT_SECONDS)
    events = port.events(run_id=run_id, timeout_seconds=_READ_TIMEOUT_SECONDS)
    record = fabro_inspect_record(payload=inspected.payload)
    return (
        AcpProbeObservation(
            turn_completed=_turn_completed(record=record),
            acp_started=_acp_started(payload=events.payload),
            cancelled=(inspected.status_kind or "") in _CANCELLED_STATUS_KINDS,
            timed_out=False,
            failure=inspected.failure,
        ),
        _cost(payload=inspected.payload),
    )


def _turn_completed(*, record: dict[str, Any] | None) -> bool:
    """Whether the factory recorded the probe node's own attempt as SUCCEEDED.

    Keyed through `fabro_stage_node`, so a Petri-era visit-qualified stage key
    (`confirm@1`) and a pinned-engine node id both resolve: comparing the node
    id against the raw key silently matched nothing, which is the one reading
    that would report every successful probe as unconfirmed.
    """
    if record is None:
        return False
    outcomes = fabro_node_outcomes(record=record, checkpoint=_newest_checkpoint(record=record))
    return any(
        fabro_stage_node(stage=stage) == AVAILABILITY_PROBE_NODE
        and outcome.get("status") == _SUCCEEDED_STATUS
        for stage, outcome in outcomes.items()
    )


def _newest_checkpoint(*, record: dict[str, Any]) -> dict[str, Any]:
    """The newest checkpoint this record carries, or an empty one.

    Empty is what sends `fabro_node_outcomes` to the record's own `stages` map,
    which is the Petri-era shape; a pinned-engine record answers from its
    checkpoint instead. One reading serves both.
    """
    raw = record.get("checkpoints")
    if not isinstance(raw, list):
        return {}
    entries: list[dict[str, Any]] = [
        cast("dict[str, Any]", one) for one in cast("list[object]", raw) if isinstance(one, dict)
    ]
    return entries[-1] if entries else {}


def _acp_started(*, payload: object) -> bool:
    """Whether the probe node's attempt crossed the prompt boundary.

    The EVENT's presence is the whole reading, per the module docstring: this
    asks a strictly weaker question than `scan_acp_events` does, so a pre-chain
    engine's start still answers it.
    """
    if not isinstance(payload, list):
        return False
    for entry in cast("list[object]", payload):
        if not isinstance(entry, dict):
            continue
        event = cast("dict[str, Any]", entry)
        node = event.get("node")
        if event.get("type") == ACP_STARTED_EVENT and (
            not isinstance(node, str) or fabro_stage_node(stage=node) == AVAILABILITY_PROBE_NODE
        ):
            return True
    return False


def _cost(*, payload: object) -> int | None:
    """What this probe cost, or `None` when the engine reported no figure.

    Read through the ordinary run-summary parser rather than off the record by
    hand, so a probe's cost and a dispatch's cost come from one reading. `None`
    is the ORDINARY answer on this fleet -- the engine's `total_usd_micros` is
    null on every run of the pinned build -- which is exactly why the clause
    says "where observable" and the journal row states the observability.
    """
    summaries = fabro_run_summaries_from_payload(payload=payload)
    return summaries[0].total_usd_micros if summaries else None
