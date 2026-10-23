"""What a session-headroom assessment looks like in the dispatch journal.

`SPECIFICATION/contracts.md` section "Dispatcher admission, WIP cap, and
post-merge acceptance": "For each affected work-item and assessed credential,
the Dispatcher MUST journal under section "Control surface and audit" the
opaque non-secret credential identity, the utilization and remaining-headroom
percentages or an explicit unobservable result, and the local observation time.
The journal MUST NOT contain credential values or raw provider responses."

PURE, AND THE ONE PLACE THE RECORD'S KEYS ARE NAMED. The reading projection is
shared by the per-item assessment record and by the refusal surfaces that must
name the same facts, so a second spelling of these keys is how one surface
comes to report `remaining_percent` while another reports `remaining` and no
reader can join them.

EVERY KEY IS WRITTEN ON EVERY READING, NULLS INCLUDED. An omitted key is what a
record from a build predating this clause looks like, so a reader could not tell
"this reading was unobservable" from "this record was never asked". The same
reason puts EVERY filtered node in `node_selections`, including the nodes
headroom did not touch: an absent node is indistinguishable from a node that was
never filtered, and "which nodes did headroom touch" is the question the record
exists to answer.

A SKIPPED ENTRY CARRIES NO HOLD FIELD OF ANY KIND, not even a null one. The
clause says the selection record "MUST NOT represent that skip as an observed
hold", and a `hold_key: null` would still invite a reader to join a headroom
shortfall against the availability-hold ledger, where it matches nothing. So the
projection names the candidate, its reading and the floor, and stops.

THE REFUSAL FIELDS ARE ADDED ONLY WHEN HEADROOM ACTUALLY GOVERNS, and that is a
correctness requirement rather than tidiness. `headroom_refusal_fields` returns
the EMPTY mapping unless some exhausted node was emptied with a headroom skip in
it, so a refusal governed by a typed hold -- where the chain emptied before any
reading was taken -- carries no headroom key. A block stamped on
unconditionally would tell an operator a credential had been assessed when the
filter never reached it, which is the same class of false report as a numeric
sentinel for an unobservable reading.
"""

from __future__ import annotations

from livespec_orchestrator_beads_fabro.commands._acp_candidate_preflight import (
    HEADROOM_SKIP,
    NodePreflight,
    SkippedCandidate,
)
from livespec_orchestrator_beads_fabro.commands._acp_preflight_verdict import AcpPreflightVerdict
from livespec_orchestrator_beads_fabro.commands._acp_session_headroom import (
    SessionHeadroomProjection,
    SessionHeadroomReading,
    SevenDayReading,
)

__all__: list[str] = [
    "SESSION_HEADROOM_STAGE",
    "headroom_refusal_fields",
    "session_headroom_assessment_record",
    "session_headroom_projection_fields",
    "session_headroom_reading_fields",
    "session_headroom_selection_fields",
    "session_headroom_skip_fields",
    "seven_day_reading_fields",
]

# The journal stage one admission evaluation's headroom readings are recorded
# under, for one work-item. Distinct from every refusal stage on purpose: a
# reading is an observation and most readings refuse nothing, so a reader
# filtering for refusals must not sweep up the ordinary admitted case.
SESSION_HEADROOM_STAGE = "acp-session-headroom"


def session_headroom_assessment_record(
    *,
    work_item_id: str,
    floor_percent: int,
    assessments: tuple[SessionHeadroomReading, ...],
    nodes: tuple[NodePreflight, ...] = (),
) -> dict[str, object]:
    """The per-work-item record one admission evaluation's readings produce.

    The floor rides along because the readings alone cannot be interpreted
    without it: the same 35 percent remaining is ample under a floor of 20 and
    short under a floor of 50, and the dial is committed configuration a reader
    of an old journal line cannot recover from the repository as it stands now.
    """
    return {
        "stage": SESSION_HEADROOM_STAGE,
        "work_item_id": work_item_id,
        "session_headroom_floor_percent": floor_percent,
        "assessments": [
            session_headroom_reading_fields(reading=reading) for reading in assessments
        ],
        "node_selections": {
            node.node: session_headroom_selection_fields(node=node) for node in nodes
        },
    }


def session_headroom_selection_fields(*, node: NodePreflight) -> dict[str, object]:
    """One node's selected candidate, and the candidates headroom skipped before it.

    The selected candidate is the FIRST surviving one, which is the per-node
    selection rule itself -- "the first candidate in configured order that ...
    is eligible" -- read off the already-filtered chain rather than re-derived.
    An exhausted node reports nulls, because there is no candidate to name and
    an omitted key would read as a record that never asked.
    """
    selected = node.candidates[0] if node.candidates else None
    identity = None if selected is None else selected.identity
    return {
        "selected_availability_key": None if identity is None else identity.availability_key,
        "selected_candidate_key": None if identity is None else identity.candidate_key,
        "headroom_skipped": [
            session_headroom_skip_fields(skip=skip)
            for skip in node.skipped
            if skip.reason == HEADROOM_SKIP
        ],
    }


def session_headroom_skip_fields(*, skip: SkippedCandidate) -> dict[str, object]:
    """One headroom-skipped candidate: who it was, what was read, and both dials.

    THE KIND IS WHAT NAMES A PROJECTION SKIP AS A PROJECTION SKIP, which the
    clause requires of this very surface. It is written beside BOTH dials rather
    than instead of them: a reader asking why a candidate left the set needs the
    kind to know which test fired and both dials to know what it fired against,
    and the embedded reading carries the credential identity that joins the skip
    to the assessment holding its projection.

    PUBLIC because THREE surfaces must describe one skip identically -- the
    per-node selection fields above, the containment refusal below, and the
    per-node ACP selection record of the fallback-priority clause, which lives
    in `_acp_node_selection` and reaches this projection by name. Each is
    required to name the governing floor and the governing horizon, and a second
    spelling of these keys is how one surface comes to report
    `session_headroom_floor_percent` while another reports `floor` and no reader
    can join them.

    Both DIALS and the kind are carried from the skip rather than resolved here,
    because a projection that read the repository would report the configuration
    as it stands at WRITE time against a skip taken at READ time.
    """
    return {
        "availability_key": skip.availability_key,
        "candidate_key": skip.candidate_key,
        "session_headroom_floor_percent": skip.headroom_floor_percent,
        "session_headroom_horizon_minutes": skip.headroom_horizon_minutes,
        "headroom_skip_kind": skip.headroom_skip_kind,
        "headroom": (
            None
            if skip.headroom is None
            else session_headroom_reading_fields(reading=skip.headroom)
        ),
    }


def session_headroom_reading_fields(*, reading: SessionHeadroomReading) -> dict[str, object]:
    """One reading's journaled facts, with nulls written rather than omitted.

    THE LAST KEY IS A RATE AND NOT A LEVEL, and that is why it is here at all.
    The five-hour REMAINING figure the floor decides on cannot see how fast the
    window is emptying, and a dispatch keeps its dispatch-time credential to
    the end of the run -- so a credential losing 15 points of its allowance
    every half hour reads as ample headroom at the instant of admission and is
    spent well before the run it admitted finishes.

    IT IS WRITTEN ON EVERY READING, NULL INCLUDED, for the same reason the
    original five are, and the reason bites harder here: the rate is not taken
    at all on a reading the floor settled, so an omitted key would make "no
    rate was measured" indistinguishable from "this build does not measure
    rates". And the null is an explicit null rather than a zero, because 0.0 is
    exactly what a credential nobody is spending measures at -- a coerced zero
    would report a measurement nobody took to the one reader using the figure
    to judge whether the floor is adequate.

    THE LAST KEY IS THE ONE FACT THE PROVIDER ASSERTED RATHER THAN THE ONE THIS
    BUILD MEASURED, and its name says so. The clause permits journaling "a reset
    instant the response carries" as "an unverified provider claim" and forbids
    it from changing the projection skip; nothing reads it, and a key spelled
    `resets_at` would sit beside a measured drain rate with nothing to tell a
    reader which of the two anybody checked.

    THE LAST KEY IS THE OTHER WINDOW THE SAME RESPONSE REPORTED, and the clause
    asks for it "beside the five-hour figures" -- so it is one block in this
    entry rather than a record of its own, which is what lets a reader see both
    windows of one credential at one instant without a join.
    """
    return {
        "credential_identity": reading.credential_identity,
        "utilization_percent": reading.utilization_percent,
        "remaining_percent": reading.remaining_percent,
        "unobservable": reading.unobservable,
        "observed_at": reading.observed_at,
        "five_hour_drain_percent_per_hour": reading.five_hour_drain_percent_per_hour,
        "projection": session_headroom_projection_fields(projection=reading.projection),
        "unverified_provider_reset_claim": reading.provider_reset_claim,
        "seven_day": seven_day_reading_fields(reading=reading.seven_day),
    }


def seven_day_reading_fields(*, reading: SevenDayReading) -> dict[str, object]:
    """The weekly window's three journaled facts, or its explicit absence.

    NESTED RATHER THAN FLATTENED, and never `None`. A reading always carries a
    weekly result -- the figures, or the explicit unobservable one -- so the
    block is always written, which is what keeps "the provider reported no
    weekly window" apart from "this record was never asked". That second state
    is what a record from a build predating this clause looks like, and it is
    the one an absent key would be indistinguishable from.

    THE FIGURE AND THE STATUS ARE BOTH WRITTEN even where one of them decides
    nothing. The status is the only field the skip reads, so the utilization is
    carried for the reader rather than for the filter: an operator asking why
    an account was refused its week wants the figure the provider reported
    beside the refusal, and a record naming only the refusal cannot be checked
    against the account at all.
    """
    return {
        "utilization_percent": reading.utilization_percent,
        "status": reading.status,
        "unobservable": reading.unobservable,
    }


def session_headroom_projection_fields(
    *, projection: SessionHeadroomProjection | None
) -> dict[str, object] | None:
    """The ONE projection result a reading carries, or an explicit null.

    EXACTLY ONE RESULT, UNDER ONE KEY, which is the clause's own requirement:
    "the journal record MUST additionally carry exactly one projection result".
    Three parallel optional blocks -- a projected one, an unavailable one and a
    not-projected one -- would let a record carry two, and a reader joining on
    whichever it found first would report the wrong one with no way to notice.
    So the result KIND is a field inside the single block, and the figures that
    do not apply to that kind are written as nulls beside it.

    A reading carrying NO projection renders an explicit `null` rather than a
    fourth result value. That is a different claim from any of the three: it
    says this reading was never projected AT ALL, which is what a record from a
    build predating this clause looks like, and what a verdict composed with no
    policy produces. Collapsing it onto `not-projected` would report the three
    conditions the clause enumerates for a reading nothing assessed.

    The drain rate appears BOTH here and as the reading's own sibling key, and
    they cannot diverge because both are rendered from the one reading this
    projection was taken from. The sibling key is what `bd-ib-rszkjc` shipped
    and what the baseline reader joins on; the copy inside the block is what
    makes the result self-contained for a reader grading one projection.
    """
    if projection is None:
        return None
    return {
        "result": projection.result,
        "reason": projection.reason,
        "five_hour_drain_percent_per_hour": projection.five_hour_drain_percent_per_hour,
        "baseline_observed_at": projection.baseline_observed_at,
        "projected_exhaustion_at": projection.projected_exhaustion_at,
        "session_headroom_horizon_minutes": projection.horizon_minutes,
        "projection_skip_applied": projection.skip_applied,
    }


def headroom_refusal_fields(*, verdict: AcpPreflightVerdict) -> dict[str, object]:
    """What a HEADROOM-GOVERNED containment refusal must additionally name.

    Scoped to the EXHAUSTED nodes, because that is what the clause asks for --
    "skipped candidates for the admission-required node lacking an eligible
    candidate" -- and because a node that still holds a candidate refused
    nothing, so naming its skips in a refusal record would point an operator at
    a chain that is working.
    """
    floor = verdict.session_headroom_floor_percent
    if floor is None:
        return {}
    skipped = {
        node.node: [session_headroom_skip_fields(skip=skip) for skip in node.skipped]
        for node in verdict.nodes
        if node.node in verdict.exhausted
        and any(skip.reason == HEADROOM_SKIP for skip in node.skipped)
    }
    if not skipped:
        return {}
    return {
        "session_headroom_floor_percent": floor,
        "session_headroom_horizon_minutes": verdict.session_headroom_horizon_minutes,
        "session_headroom_assessments": [
            session_headroom_reading_fields(reading=reading)
            for reading in verdict.headroom_assessments
        ],
        "session_headroom_skipped": skipped,
    }
