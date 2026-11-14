"""A pool slot's live provider-exhaustion record, attached to its headroom reading.

bd-ib-wx4yha: the provider's rate windows cannot see an organisation spend cap,
so a spend-capped slot whose window resets soonest kept winning the pool
ranking. The Dispatcher's own provider-exhaustion records name the capped
account's credential identity; attaching the live record's expiry to that
slot's reading lets `headroom_skip_kind` pass the slot over.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import replace
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._acp_session_headroom import (
    SessionHeadroomReading,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_provider_exhaustion import (
    live_provider_exhaustions,
)

__all__: list[str] = ["exhausted_identities", "pool_with_exhaustion", "reading_with_exhaustion"]


def exhausted_identities(*, journal_path: Path | None, now_iso: str) -> dict[str, str]:
    """Each credential identity a live provider-exhaustion record names, with its expiry.

    A record carrying no identity is left out: it keeps its vendor-wide coverage
    through the existing exhaustion refusal, and naming no account it cannot say
    which slot to pass over. The walk is the journal tail the refusal reads, so
    this adds no full-journal read. The records come back newest first, so they
    are folded oldest first and the newest record for an identity wins.
    """
    live = live_provider_exhaustions(journal_path=journal_path, now_iso=now_iso)
    return {
        record.credential_identity: record.record_expires_at
        for record in reversed(live)
        if record.credential_identity is not None
    }


def reading_with_exhaustion(
    *, reading: SessionHeadroomReading, exhausted: dict[str, str]
) -> SessionHeadroomReading:
    """The reading, carrying the expiry of a live record that names its identity."""
    return replace(
        reading, provider_exhaustion_expires_at=exhausted.get(reading.credential_identity)
    )


def pool_with_exhaustion(
    *,
    readings: Sequence[tuple[str, SessionHeadroomReading]],
    journal_path: Path | None,
    now_iso: str,
) -> tuple[tuple[str, SessionHeadroomReading], ...]:
    """Each pool slot's reading, carrying the expiry of a live record naming it.

    The journal tail is walked once per admission evaluation, however many
    slots the pool holds.
    """
    exhausted = exhausted_identities(journal_path=journal_path, now_iso=now_iso)
    return tuple(
        (slot, reading_with_exhaustion(reading=reading, exhausted=exhausted))
        for slot, reading in readings
    )
