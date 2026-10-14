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
"this reading was unobservable" from "this record was never asked".
"""

from __future__ import annotations

from livespec_orchestrator_beads_fabro.commands._acp_session_headroom import SessionHeadroomReading

__all__: list[str] = [
    "SESSION_HEADROOM_STAGE",
    "session_headroom_assessment_record",
    "session_headroom_reading_fields",
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
    }


def session_headroom_reading_fields(*, reading: SessionHeadroomReading) -> dict[str, object]:
    """One reading's five journaled facts, with nulls written rather than omitted."""
    return {
        "credential_identity": reading.credential_identity,
        "utilization_percent": reading.utilization_percent,
        "remaining_percent": reading.remaining_percent,
        "unobservable": reading.unobservable,
        "observed_at": reading.observed_at,
    }
