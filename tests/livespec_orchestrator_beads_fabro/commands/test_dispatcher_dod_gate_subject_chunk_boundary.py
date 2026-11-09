"""A chunk boundary never splits a multi-byte character of the judgement subject."""

from __future__ import annotations

from livespec_orchestrator_beads_fabro.commands._dispatcher_dod_gate_subject import (
    dod_gate_subject_prepare_steps_block,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_prepare_payload import (
    MAX_PAYLOAD_VALUE_BYTES,
)

from tests.prepare_step_support import steps_in


def test_a_character_straddling_the_chunk_boundary_moves_whole_into_the_next_chunk() -> None:
    subject = "a" * (MAX_PAYLOAD_VALUE_BYTES - 1) + "é" + "tail"

    steps = steps_in(block=dod_gate_subject_prepare_steps_block(subject=subject))
    chunks = [next(iter(step.env.values())) for step in steps]

    assert len(chunks) == 2
    assert chunks[0] == "a" * (MAX_PAYLOAD_VALUE_BYTES - 1)
    assert chunks[1] == "étail"
    assert "".join(chunks) == subject
