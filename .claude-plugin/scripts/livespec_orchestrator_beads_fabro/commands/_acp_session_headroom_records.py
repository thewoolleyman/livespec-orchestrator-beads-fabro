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
from livespec_orchestrator_beads_fabro.commands._acp_session_headroom import SessionHeadroomReading

__all__: list[str] = [
    "SESSION_HEADROOM_STAGE",
    "headroom_refusal_fields",
    "session_headroom_assessment_record",
    "session_headroom_reading_fields",
    "session_headroom_selection_fields",
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
            _skipped_fields(skip=skip) for skip in node.skipped if skip.reason == HEADROOM_SKIP
        ],
    }


def _skipped_fields(*, skip: SkippedCandidate) -> dict[str, object]:
    """One headroom-skipped candidate: who it was, what was read, and the floor."""
    return {
        "availability_key": skip.availability_key,
        "candidate_key": skip.candidate_key,
        "session_headroom_floor_percent": skip.headroom_floor_percent,
        "headroom": (
            None
            if skip.headroom is None
            else session_headroom_reading_fields(reading=skip.headroom)
        ),
    }


def session_headroom_reading_fields(*, reading: SessionHeadroomReading) -> dict[str, object]:
    """One reading's journaled facts, with nulls written rather than omitted.

    The last TWO keys are JOURNAL-ONLY and neither moves an admission decision:
    both exist because the five-hour REMAINING figure the floor decides on
    cannot see the other cliff (`bd-ib-rszkjc`). A credential at 0.95 of its
    seven-day allowance, and one draining 15 points of its five-hour window
    every half hour, both read as ample headroom at the instant of admission --
    and a run keeps its dispatch-time token to the end, so the admission-time
    reading is the only guard an in-flight run has.

    Both are written on EVERY reading, nulls included, for the same reason the
    original five are: an omitted key is what a record from a build predating
    this clause looks like, so a reader could not tell "this figure was
    unmeasurable" from "this record was never asked for it".
    """
    return {
        "credential_identity": reading.credential_identity,
        "utilization_percent": reading.utilization_percent,
        "remaining_percent": reading.remaining_percent,
        "unobservable": reading.unobservable,
        "observed_at": reading.observed_at,
        "seven_day_utilization_percent": reading.seven_day_utilization_percent,
        "five_hour_drain_percent_per_hour": reading.five_hour_drain_percent_per_hour,
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
        node.node: [_skipped_fields(skip=skip) for skip in node.skipped]
        for node in verdict.nodes
        if node.node in verdict.exhausted
        and any(skip.reason == HEADROOM_SKIP for skip in node.skipped)
    }
    if not skipped:
        return {}
    return {
        "session_headroom_floor_percent": floor,
        "session_headroom_assessments": [
            session_headroom_reading_fields(reading=reading)
            for reading in verdict.headroom_assessments
        ],
        "session_headroom_skipped": skipped,
    }
