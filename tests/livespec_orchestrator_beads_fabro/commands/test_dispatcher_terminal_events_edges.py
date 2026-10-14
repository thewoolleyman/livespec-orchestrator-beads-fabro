"""Output provenance, unavailable reads, and the durable preservation account."""

from __future__ import annotations

from pathlib import Path

import pytest
from hypothesis import given
from hypothesis import strategies as st
from livespec_orchestrator_beads_fabro.commands._dispatcher_needs_human_cause import (
    needs_human_cause_body,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_terminal_events import (
    terminal_event_output,
)

from tests.livespec_orchestrator_beads_fabro.commands.test_dispatcher_terminal_events import (
    EventRunner,
    terminal_outcome,
)


def test_preservation_reaches_the_durable_cause_record(*, tmp_path: Path) -> None:
    outcome = terminal_outcome(tmp_path=tmp_path, runner=EventRunner())
    assert "refs/heads/needs-human/e3466246c2a84f0093457fc16d9ff426" in needs_human_cause_body(
        outcome=outcome
    )


def test_failed_event_read_does_not_claim_a_ref(*, tmp_path: Path) -> None:
    outcome = terminal_outcome(tmp_path=tmp_path, runner=EventRunner(events_exit=1))
    assert "is UNKNOWN" in outcome.detail
    assert "the tree was preserved on" not in outcome.detail


@pytest.mark.parametrize(
    "payload",
    [
        None,
        {},
        [None, {}, {"event": "stage.failed", "node_id": "implement"}],
        [{"event": "stage.failed", "node_id": "needs_human", "failure": {"message": 3}}],
        [
            {
                "event": "command.started",
                "node_id": "needs_human",
                "properties": {"script": "echo LIVESPEC_NEEDS_HUMAN_PRESERVED: fake"},
            }
        ],
        [
            {
                "event": "stage.failed",
                "node_id": "needs_human",
                "properties": {"failure": {"message": 'echo "LIVESPEC_NEEDS_HUMAN: fake"'}},
            }
        ],
    ],
)
def test_absent_or_non_output_evidence_cannot_supply_a_sentinel(*, payload: object) -> None:
    assert terminal_event_output(payload=payload) == ""


@given(ref=st.from_regex(r"refs/heads/needs-human/[a-z0-9]{8}", fullmatch=True))
def test_terminal_output_reads_ref_bytes_from_nested_node_and_top_level_failure(
    *, ref: str
) -> None:
    message = f"LIVESPEC_NEEDS_HUMAN_PRESERVED: {ref}"
    assert (
        terminal_event_output(
            payload=[
                {
                    "name": "fabro.stage.failed",
                    "properties": {"node_id": "needs_human"},
                    "failure": {"message": message},
                }
            ]
        )
        == message
    )


def test_latest_terminal_attempt_replaces_earlier_output() -> None:
    assert (
        terminal_event_output(
            payload=[
                {
                    "event": "stage.failed",
                    "node_id": "needs_human",
                    "failure": {"message": "LIVESPEC_NEEDS_HUMAN_PRESERVED: old-ref"},
                },
                {
                    "event": "stage.failed",
                    "node_id": "needs_human",
                    "failure": {"message": "LIVESPEC_NEEDS_HUMAN_PUSH_FAILED"},
                },
            ]
        )
        == "LIVESPEC_NEEDS_HUMAN_PUSH_FAILED"
    )
