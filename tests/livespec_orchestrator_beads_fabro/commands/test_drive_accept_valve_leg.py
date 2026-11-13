"""Unit tests for the accept valve's rendered outstanding-proof legs."""

from __future__ import annotations

from livespec_orchestrator_beads_fabro.commands._drive_accept_valve import (
    HOST_REPLAY_PENDING_ERR,
    HUMAN_ATTESTATION_PENDING_ERR,
)
from livespec_orchestrator_beads_fabro.commands._drive_accept_valve_leg import (
    host_leg,
    human_leg,
)


def test_host_leg_names_its_replay_record_format() -> None:
    leg = host_leg(assertions=("the host assertion",), err=HOST_REPLAY_PENDING_ERR)

    assert leg.err == HOST_REPLAY_PENDING_ERR
    assert leg.awaited == "an independent host replay of"
    assert leg.record_format == (
        "Proof of Done — host_verified — <session identity> — <UTC timestamp>"
    )


def test_human_leg_names_its_attestation_record_format() -> None:
    leg = human_leg(assertions=("the human assertion",), err=HUMAN_ATTESTATION_PENDING_ERR)

    assert leg.err == HUMAN_ATTESTATION_PENDING_ERR
    assert leg.awaited == "human attestation of"
    assert leg.record_format == (
        "Proof of Done — human_attested — <human identity> — <UTC timestamp>"
    )
