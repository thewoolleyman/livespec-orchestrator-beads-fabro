"""Grade ONE factory run's `inspect` record into the attempts it carries.

Split out of `_acp_factory_hold_evidence`, which keeps the host-wide read --
which factories are asked, which rows are worth an `inspect`, and how the
concurrent reads are merged. Everything here takes the ONE payload already read
and answers what it says: the attempt that FAILED (an observation), the ones
that SUCCEEDED (confirmations), and the observations an operator-clearance run
names as cleared. Nothing here reads a factory or a journal.
"""

from __future__ import annotations

from datetime import datetime

from livespec_orchestrator_beads_fabro.commands._acp_builtin_signatures import (
    builtin_availability_signatures,
)
from livespec_orchestrator_beads_fabro.commands._acp_clearance_records import is_clearance_run
from livespec_orchestrator_beads_fabro.commands._acp_factory_clearance_evidence import (
    recorded_clearance,
)
from livespec_orchestrator_beads_fabro.commands._acp_factory_hold_records import (
    PROVIDER_LIMIT_CAUSE,
    FactoryHoldObservation,
)
from livespec_orchestrator_beads_fabro.commands._acp_factory_success_records import (
    FactorySuccessObservation,
)
from livespec_orchestrator_beads_fabro.commands._acp_failure_text import ends_at_sentence_boundary
from livespec_orchestrator_beads_fabro.commands._dispatcher_run_labels import REPOSITORY_LABEL_KEY
from livespec_orchestrator_beads_fabro.commands._fabro_executed_candidate import (
    executed_candidate_identity,
)
from livespec_orchestrator_beads_fabro.commands._fabro_port_checkpoints import (
    fabro_inspect_checkpoints,
)
from livespec_orchestrator_beads_fabro.commands._fabro_port_node_outcomes import (
    fabro_node_outcomes,
)
from livespec_orchestrator_beads_fabro.commands._fabro_port_records import (
    FabroRunSummary,
    fabro_failure_detail_from_payload,
    fabro_inspect_record,
)
from livespec_orchestrator_beads_fabro.commands._fabro_terminal_evidence import terminal_evidence
from livespec_orchestrator_beads_fabro.commands._fabro_turn_output import succeeded_agent_turns

__all__: list[str] = [
    "cleared_observation_ids",
    "failed_observation",
    "succeeded_confirmations",
]

_SUCCEEDED_STATUS = "succeeded"
_FINAL_OUTPUT_SOURCE = "turn.final_output"


def cleared_observation_ids(
    *, row: FabroRunSummary, payload: object, began_at: datetime | None
) -> frozenset[str]:
    """The observations one OPERATOR-CLEARANCE run's record names as cleared.

    Bounded by the run's START, exactly as the confirmation arm is -- but NOT
    any longer for the same reason, and the difference is worth stating because
    the original premise has been falsified by its own consumer. That premise
    was that a clearance older than `HOLD_INTERVAL` can only retire a record
    which has already expired on its own, and therefore retires nothing that
    decides anything. Since the post-expiry confirmation
    (`_acp_availability_confirmation`) an EXPIRED record is no longer inert: it
    carries an outstanding availability confirmation and GOVERNS selection, so
    such a clearance now does have an effect to be missed.

    The bound is kept anyway, on a cost argument rather than a vacuity one.
    Reading past the window costs one `fabro inspect` per historical clearance
    on EVERY admission evaluation, against a factory that listed 1626 rows for
    this fleet; what missing one costs is a single confirmation turn, since the
    ordinary route to satisfying a post-expiry confirmation is a successful
    attempt and not a clearance at all. That is the conservative direction, and
    the same asymmetry `_acp_availability_confirmation` already reasons from.
    A future editor who finds that trade has changed should widen the window
    here -- the arm is correct, its justification is simply no longer the one
    it was written with.

    Empty is what EVERY non-clearance row answers, and also what a clearance
    run whose record states nothing readable answers. The two are deliberately
    not distinguished: retirement is the destructive direction, so a record
    this read could not recover simply leaves the observation standing.
    """
    if began_at is None or not is_clearance_run(labels=row.labels):
        return frozenset()
    clearance = recorded_clearance(payload=payload)
    if clearance is None:
        return frozenset()
    return frozenset(clearance.observation_ids)


def failed_observation(
    *, factory: str, row: FabroRunSummary, payload: object, occurred_at: str
) -> FactoryHoldObservation | None:
    """One failed run's typed availability attempt, or `None` when it is not one.

    `None` covers both ways this is not evidence about a provider, and they
    stay un-surfaced because neither is a failure to measure: a failure the
    cause chain does not classify as a ceiling, and a failing node the run
    recorded no entitlement for -- which is the conservative legacy posture an
    identity-less adapter keeps, where there is no entitlement a typed record
    could be scoped by.
    """
    failure = fabro_failure_detail_from_payload(payload=payload)
    if failure is None or not failure.provider_usage_limit:
        return None
    evidence = terminal_evidence(payload=payload)
    executed = executed_candidate_identity(
        labels=row.labels, node=None if evidence is None else evidence.current_predecessor
    )
    if executed is None:
        return None
    return FactoryHoldObservation(
        factory=factory,
        repository=row.labels.get(REPOSITORY_LABEL_KEY),
        run_id=row.run_id,
        node_attempt=executed.node,
        availability_key=executed.availability_key,
        candidate_key=executed.candidate_key,
        cause=PROVIDER_LIMIT_CAUSE,
        occurred_at=occurred_at,
    )


def succeeded_confirmations(
    *, factory: str, row: FabroRunSummary, payload: object, started_at: str
) -> tuple[FactorySuccessObservation, ...]:
    """Every SUCCEEDED node attempt one run's record carries, as confirmations.

    The grading is the port's own `fabro_node_outcomes`, which resolves BOTH
    inputs the two engines write -- the newest checkpoint's `node_outcomes`,
    else the record's own top-level `stages` map, visit-collapsed. A second
    reading here would make this and `failed_observation` above disagree about
    whether one record is readable at all.

    A succeeded node the run recorded NO entitlement for yields nothing, which
    is the same conservative legacy posture `failed_observation` keeps one function
    up: an identity-less adapter names no allowance, so its success confirms no
    allowance either. An unusable payload yields nothing for the same reason it
    yields no observation -- the record was read, and what it says is that it
    establishes no attempt.

    A SUCCEEDED AGENT TURN THAT ENDS WITH A MEASURED REFUSAL YIELDS NOTHING
    EITHER: "A provider refusal booked as a successful turn is a failed attempt",
    which "MUST NOT count as a successful completion" under the retirement rule.
    """
    record = fabro_inspect_record(payload=payload)
    if record is None:
        return ()
    checkpoints = fabro_inspect_checkpoints(record=record)
    outcomes = fabro_node_outcomes(record=record, checkpoint=checkpoints[-1] if checkpoints else {})
    turn_output = {turn.stage: turn.output for turn in succeeded_agent_turns(payload=payload)}
    confirmations: list[FactorySuccessObservation] = []
    for stage, outcome in outcomes.items():
        if outcome.get("status") != _SUCCEEDED_STATUS:
            continue
        executed = executed_candidate_identity(labels=row.labels, node=stage)
        if executed is None or _booked_refusal(
            output=turn_output.get(stage), availability_key=executed.availability_key
        ):
            continue
        confirmations.append(
            FactorySuccessObservation(
                factory=factory,
                repository=row.labels.get(REPOSITORY_LABEL_KEY),
                run_id=row.run_id,
                node_attempt=executed.node,
                availability_key=executed.availability_key,
                candidate_key=executed.candidate_key,
                started_at=started_at,
            )
        )
    return tuple(confirmations)


def _booked_refusal(*, output: str | None, availability_key: str) -> bool:
    """Whether a succeeded turn's output ends with a measured refusal of its domain.

    Such an attempt "is not a successful completion" and so confirms nothing:
    it is the candidate's FAILED attempt, and counting it would let the hold it
    mints be retired by the very run that minted it.

    THE BUILT-IN TABLE IS THE ONLY ONE CONSULTED, keyed by the run's recorded
    availability key. A peer repository's own declared `turn.final_output`
    signatures are configuration this repository does not hold, and a key
    spelling is not evidence of provenance -- so a repository naming its own key
    "codex" has a success withheld that was in fact a success. That is the
    conservative direction: retirement is the destructive one, and a withheld
    confirmation costs at most one later success.
    """
    if output is None:
        return False
    return any(
        signature.source == _FINAL_OUTPUT_SOURCE
        and signature.final_text is not None
        and ends_at_sentence_boundary(tail=signature.final_text, text=output)
        for signature in builtin_availability_signatures(availability_key=availability_key)
    )
