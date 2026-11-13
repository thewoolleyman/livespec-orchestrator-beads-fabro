"""Published-head attribution available while a resume is gathered."""

from __future__ import annotations

from collections.abc import Sequence

from livespec_orchestrator_beads_fabro.commands._dispatcher_proof_record import ProofRecord
from livespec_orchestrator_beads_fabro.commands._dispatcher_resume_anchor import (
    FACTORY_RECORD_VERDICTS,
    published_head,
)

__all__: list[str] = ["publications_of"]


def publications_of(*, records: Sequence[ProofRecord]) -> tuple[tuple[str, str], ...]:
    """Each factory-record publication head paired with the run that published it."""
    return tuple(
        (head, record.run_id)
        for record in records
        if record.verdict in FACTORY_RECORD_VERDICTS
        and (head := published_head(body=record.body)) is not None
    )
