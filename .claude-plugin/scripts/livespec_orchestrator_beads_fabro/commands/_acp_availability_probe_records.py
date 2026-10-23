"""The RECORDS one confirmation turn leaves behind: a hold, and a journal row.

`SPECIFICATION/contracts.md` section "Factory-configurable ACP fallback
priority" -> "Availability is re-confirmed after expiry": "An eligible refusal
creates a new occurrence-time-scoped hold. Any other probe failure skips that
candidate for the current evaluation, creates no hold, and allows selection to
continue to later eligible candidates." And, in the same section: "A hold MUST
come from an actual candidate attempt: a typed eligible failure classified from
a failed node of a terminal run, whichever terminal the run reached, or a
refused availability confirmation turn ..., which runs the candidate's own
adapter and is therefore an actual attempt. Expiry is computed from occurrence
time and never from ingestion."

PURE, AND THE RECORDS ONLY. Nothing here appends, reads a clock, resolves
configuration or reaches a factory: `_acp_availability_probe_outcome` beside it
graded the ending, and `_acp_availability_probe_run` performs the turn and
hands both the ending and the instant in. That is the same decision/record/
perform split `_acp_failure_classifier` / `_acp_hold_records` /
`_acp_hold_ledger` take one level down, and it is what lets every decision
below be exercised with no provider at all.

THE EVIDENCE KIND IS `candidate-attempt`, AND THAT IS A CONTRACT CLAIM RATHER
THAN A CONVENIENCE. `hold_observation_record` refuses any kind outside its
closed set precisely so that "a credential probe, a catalog read or a
provider's own reset claim" cannot mint a hold -- and the clause that forbids
those is the same one that names a refused confirmation turn an actual attempt,
on the stated ground that it "runs the candidate's own adapter". So a refused
probe is admitted through the existing door rather than by widening the set.
The clause is equally explicit about the OTHER probe: "No hold may come from
... the admission-time credential-usability probe", which is a different
mechanism entirely and reaches none of this.

THE REFUSAL ARM IS THE ONLY ARM. Five of the six endings mint nothing, and the
TIMED-OUT one is the reason this is a lookup on the ending rather than on the
recorded text: a terminated turn's record can carry the provider's last
sentence, so a builder reading the text first mints a hold from a measurement
the Dispatcher interrupted. `probe_ending` already applies that precedence, and
this module trusts the grade instead of re-deriving it -- two accounts of which
endings mint would be two authorities on when an allowance is held.

THE SIGNAL DIFFERS FROM THE TERMINAL-READING ONE IN EXACTLY ONE FIELD, and the
reuse is deliberate. `provider_limit_signal` already decides WHICH observed
channel a recorded cause is, and its own docstring carries the two independent
measurements behind putting it on the protocol MESSAGE; a second account of
that mapping here would be a second authority on whether a signature can ever
match. What a probe knows and a terminal reading does not is that the turn
STARTED: the refusal ending is reachable only through `agent.acp.started`, so
`turn_started` is set rather than left at its conservative default. It changes
no verdict today -- the pre-turn guard fires only when no readable field
carries text, and a refusal by construction carries some -- and it keeps the
signal honest about an attempt whose protocol boundary was measured.

AN UNREADABLE OCCURRENCE INSTANT MINTS NOTHING. `hold_observation_record`
refuses it, because expiry is COMPUTED from occurrence and there is nothing
else to compute one from; this module passes that refusal through as `None`
rather than substituting a clock, which is the one substitution the clause's
"never from ingestion" forbids outright.

THE JOURNAL ROW IS WRITTEN FOR EVERY ENDING, which is the other half of the
same clause -- "Every probe turn is journaled with the candidate identity,
outcome, occurrence time and, where observable, its cost" -- and the breadth is
the part an implementation narrows. A row written only on refusal makes the
measurement that found a provider HEALTHY invisible, which is exactly what an
operator asks while a chain is waiting, and an absent row reads downstream as a
probe nobody ran. So the five endings that mint nothing and the one that
confirms are all recorded, under one stage, with the ending itself as a field.

"WHERE OBSERVABLE" IS A STATEMENT ABOUT THE MEASUREMENT AND NOT ABOUT THE KEY.
The engine reports no cost figure on many runs, so the row carries an explicit
null beside a stated observability flag rather than omitting the key: an
omitted key is what a row from a build predating cost looks like, and the
repository's own cost gate is fail-closed on exactly that distinction. Zero is
a MEASURED figure and reads as observable.

THE ATTEMPT-COST RECORD IS A THIRD RECORD AND NOT A KEY OF THE ROW ABOVE, which
is the one placement decision here worth reading twice. The same section's
"Cost follows every attempt" paragraph says "for every availability
confirmation turn, the Dispatcher MUST journal one attempt-cost record", and
`_dispatcher_cost_sequence`'s per-item fold selects on the attempt-cost STAGE
and the item it names -- so a cost observation carried inside this row's own
stage would be invisible to the one surface that counts it. Both still carry
the figure, deliberately: the row answers "what did this turn do" for an
operator reading the journal by hand, and the record answers "what has this
item spent" for the fold.

IT IS CHARGED TO EXACTLY ONE ITEM, which is the clause's "A shared availability
probe MUST NOT be charged in full to multiple items". A confirmation turn run
inside one item's admission evaluation establishes availability every peer then
benefits from, and nothing downstream divides a charge -- so the record names
the item that spent it and the peers' folds see nothing at all, which is what
keeps one spend from being multiplied by the size of the queue.
"""

from __future__ import annotations

from dataclasses import replace

from livespec_orchestrator_beads_fabro.commands._acp_availability_probe import (
    AVAILABILITY_PROBE_NODE,
)
from livespec_orchestrator_beads_fabro.commands._acp_availability_probe_outcome import (
    PROBE_REFUSED,
    AcpProbeObservation,
    probe_confirms,
    probe_ending,
)
from livespec_orchestrator_beads_fabro.commands._acp_candidate_schema import AcpCandidate
from livespec_orchestrator_beads_fabro.commands._acp_failure_classifier import (
    AcpAvailabilityFailure,
    classify_acp_failure,
)
from livespec_orchestrator_beads_fabro.commands._acp_hold_records import hold_observation_record
from livespec_orchestrator_beads_fabro.commands._dispatcher_cost_attempts import (
    ATTEMPT_COST_CONFIRMATION_TURN,
    attempt_cost_record,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_provider_limit_classify import (
    provider_limit_signal,
)

__all__: list[str] = [
    "PROBE_EVIDENCE_KIND",
    "PROBE_JOURNAL_STAGE",
    "probe_attempt_cost_record",
    "probe_eligible_failure",
    "probe_hold_record",
    "probe_journal_record",
]

# The closed-set evidence kind a refused confirmation turn is admitted under.
# See the module docstring for why it is this one and not a new member.
PROBE_EVIDENCE_KIND = "candidate-attempt"

# The ONE journal stage every confirmation turn is recorded under, whatever it
# ended as. One stage rather than one per ending, so a reader folding the
# journal for "every probe of this account" asks a single question and reads the
# ending off a field -- the same shape `HOLD_STAGE` takes for observations.
PROBE_JOURNAL_STAGE = "acp-availability-confirmation"


def probe_eligible_failure(
    *,
    candidate: AcpCandidate,
    builtin: bool,
    observation: AcpProbeObservation,
    ending: str,
) -> AcpAvailabilityFailure | None:
    """The typed eligible cause this refusal measured, or `None` for every else.

    `None` covers three different things, and none of them is a hold: an ending
    that is not a refusal at all, a refusal whose record carries no sentence to
    classify, and a refusal the signatures do not match -- which keeps its
    existing route and asserts nothing about an allowance.
    """
    if ending != PROBE_REFUSED or observation.failure is None:
        return None
    verdict = classify_acp_failure(
        signal=replace(provider_limit_signal(failure=observation.failure), turn_started=True),
        candidate=candidate,
        builtin=builtin,
    )
    return verdict if isinstance(verdict, AcpAvailabilityFailure) else None


def probe_hold_record(
    *,
    candidate: AcpCandidate,
    builtin: bool,
    observation: AcpProbeObservation,
    occurred_at: str,
    run_reference: str,
    work_item_id: str,
) -> dict[str, object] | None:
    """The appendable observation one refused confirmation turn mints, or `None`.

    The ending is graded HERE from the observation rather than accepted as a
    parameter, so there is exactly one route by which an ending decides whether
    an allowance is held. A caller that has already graded the ending for its
    own journal row passes the observation anyway, and the two readings are the
    same `probe_ending` call -- two accounts of which endings mint would be two
    authorities on when a candidate is skipped for fifteen minutes.

    `run_reference` is the probe's own `factory:run` pair, which is what makes
    the minted `observation_id` STABLE: re-ingesting one probe -- by a
    reconciliation replay, or by a second evaluation in the same window --
    reproduces the identical id and so completes rather than duplicates.
    """
    failure = probe_eligible_failure(
        candidate=candidate,
        builtin=builtin,
        observation=observation,
        ending=probe_ending(observation=observation),
    )
    if failure is None:
        return None
    built = hold_observation_record(
        failure=failure,
        evidence_kind=PROBE_EVIDENCE_KIND,
        evidence_id=f"{run_reference}:{AVAILABILITY_PROBE_NODE}",
        occurred_at=occurred_at,
        work_item_id=work_item_id,
        node=AVAILABILITY_PROBE_NODE,
    )
    return None if isinstance(built, str) else built


def probe_attempt_cost_record(
    *,
    work_item_id: str,
    occurred_at: str,
    factory: str,
    run_id: str | None,
    cost_usd_micros: int | None,
) -> dict[str, object]:
    """The one attempt-cost observation this confirmation turn is recorded as.

    Total: every ending produces one, because a record written only for the
    turn that CONFIRMED makes the spend of every refused, exited, cancelled and
    terminated turn invisible -- and those are the turns a chain waiting out an
    outage actually produces.

    NO ATTEMPT WINDOW IS RECORDED, and that is the honest reading rather than an
    omission. The probe's graph is one adapter-bearing node, its ended-run read
    asks for the node outcome and the whole-run figure, and nothing in it reads
    an event stream for chain starts -- so the run record exposes no per-attempt
    elapsed time to this turn, and inventing an entry from the node id would
    report a measurement nobody took.

    NO CANDIDATE IDENTITY IS TAKEN, unlike the hold record beside it, and the
    asymmetry follows what each record is FOR. A hold is scoped BY the
    entitlement the turn spent, so it cannot be built without one; a charge is
    scoped by the turn's own run and the item it is charged to, and the journal
    row written for the same turn already names the candidate for an operator
    reading the file by hand. Taking an identity here and discarding it would
    read as a field the record carries.
    """
    return attempt_cost_record(
        source=ATTEMPT_COST_CONFIRMATION_TURN,
        work_item_id=work_item_id,
        factory=factory,
        run_id=run_id,
        node_attempt=AVAILABILITY_PROBE_NODE,
        occurred_at=occurred_at,
        windows=(),
        usd_micros=cost_usd_micros,
    )


def probe_journal_record(  # noqa: PLR0913 — kw-only record fields, each one of the four the clause enumerates or one half of the run identity it is recorded against; grouping any pair into a carrier would invent a relationship the row does not have.
    *,
    candidate: AcpCandidate,
    ending: str,
    occurred_at: str,
    factory: str,
    run_id: str | None,
    cost_usd_micros: int | None,
    observation_ids: tuple[str, ...] = (),
) -> dict[str, object]:
    """The one journal row this confirmation turn is recorded as.

    Total: every ending produces a row. `confirmed` is derived through
    `probe_confirms` rather than compared here, so the journal and the filter
    cannot disagree about whether an ending confirmed -- the failure mode being
    a row that reads `confirmed: true` beside a candidate the filter skipped.

    `observation_ids` are the expired records this probe was run to satisfy, and
    they are PROVENANCE rather than a decision. Which records a successful
    confirmation actually satisfies is derived by `retired_by_success` from the
    attempt's own instant, so the row says what the probe was FOR and never
    what it cleared -- a row claiming the latter could not know which records
    expired while the probe ran.

    The identity is rendered field by field rather than as one joined key,
    because a domain hold is scoped by the availability key ALONE and a query
    for "every probe that spent this account" must not have to take a pair
    apart to ask it. An identity-less candidate -- which
    `availability_probe_refusal` refuses before any run exists -- contributes
    nulls rather than an invented entitlement, because a row naming an
    entitlement nobody declared reads host-wide as evidence about it.
    """
    identity = candidate.identity
    return {
        "stage": PROBE_JOURNAL_STAGE,
        "availability_key": None if identity is None else identity.availability_key,
        "candidate_key": None if identity is None else identity.candidate_key,
        "display_name": None if identity is None else identity.display_name,
        "node": AVAILABILITY_PROBE_NODE,
        "outcome": ending,
        "confirmed": probe_confirms(ending=ending),
        "occurred_at": occurred_at,
        "factory": factory,
        "run_id": run_id,
        "cost_usd_micros": cost_usd_micros,
        "cost_observable": cost_usd_micros is not None,
        "satisfies_observation_ids": list(observation_ids),
    }
