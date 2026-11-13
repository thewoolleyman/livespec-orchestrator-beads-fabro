"""The outstanding-proof leg rendered by the accept valve's refusals."""

from __future__ import annotations

from dataclasses import dataclass

from livespec_orchestrator_beads_fabro.commands._dispatcher_proof_record import (
    PROOF_RECORD_TITLE,
    VERDICT_HOST_VERIFIED,
    VERDICT_HUMAN_ATTESTED,
)

__all__: list[str] = ["OutstandingLeg", "host_leg", "human_leg"]


@dataclass(frozen=True, kw_only=True)
class OutstandingLeg:
    """One leg still owed, the assertions it covers, and the record that clears it."""

    err: str
    assertions: tuple[str, ...]
    record_format: str
    awaited: str


def host_leg(*, assertions: tuple[str, ...], err: str) -> OutstandingLeg:
    """Describe the host replay the valve is still awaiting."""
    return OutstandingLeg(
        err=err,
        assertions=assertions,
        record_format=(
            f"{PROOF_RECORD_TITLE} — {VERDICT_HOST_VERIFIED} — <session identity> — <UTC timestamp>"
        ),
        awaited="an independent host replay of",
    )


def human_leg(*, assertions: tuple[str, ...], err: str) -> OutstandingLeg:
    """Describe the human attestation the valve is still awaiting."""
    return OutstandingLeg(
        err=err,
        assertions=assertions,
        record_format=(
            f"{PROOF_RECORD_TITLE} — {VERDICT_HUMAN_ATTESTED} — <human identity> — <UTC timestamp>"
        ),
        awaited="human attestation of",
    )
