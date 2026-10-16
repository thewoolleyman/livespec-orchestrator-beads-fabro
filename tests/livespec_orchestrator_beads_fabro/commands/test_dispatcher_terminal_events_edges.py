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
    routing_stage_failure,
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


def test_unobserved_routing_cause_never_reuses_the_terminal_error(*, tmp_path: Path) -> None:
    outcome = terminal_outcome(tmp_path=tmp_path, runner=EventRunner())
    assert outcome.fabro_failure_cause is None
    assert "no outgoing fail edge" not in outcome.detail
    assert "no outgoing fail edge" not in needs_human_cause_body(outcome=outcome)


def _event(*, node: str, failure: object) -> dict[str, object]:
    return {"event": "stage.failed", "properties": {"node_id": node, "failure": failure}}


def _checkpoint(*, failure: object) -> dict[str, object]:
    return {"node_outcomes": {"implement": {"status": "failed", "failure": failure}}}


@pytest.mark.parametrize("payload", [None, {}, {"checkpoint": {"node_outcomes": []}}])
def test_unreadable_stage_failure_is_unknown(*, payload: object) -> None:
    assert (
        routing_stage_failure(inspect_payload=payload, events_payload=None, stage="implement")
        is None
    )


def test_terminal_is_never_a_routing_cause() -> None:
    assert (
        routing_stage_failure(
            inspect_payload=None,
            events_payload=[_event(node="needs_human", failure={"message": "terminal error"})],
            stage="needs_human",
        )
        is None
    )


def test_checkpoint_cause_wins_over_an_older_event() -> None:
    failure = routing_stage_failure(
        inspect_payload={"checkpoint": _checkpoint(failure={"message": "current cause"})},
        events_payload=[_event(node="implement", failure={"message": "old cause"})],
        stage="implement",
    )
    assert failure is not None
    assert failure.cause == "current cause"


def test_latest_checkpoint_does_not_borrow_an_old_attempt_cause() -> None:
    assert (
        routing_stage_failure(
            inspect_payload={
                "checkpoints": [_checkpoint(failure={"message": "old cause"})],
                "checkpoint": _checkpoint(failure=None),
            },
            events_payload=[],
            stage="implement",
        )
        is None
    )


def test_category_only_checkpoint_survives_an_unreadable_event() -> None:
    failure = routing_stage_failure(
        inspect_payload={"checkpoint": _checkpoint(failure={"category": "deterministic"})},
        events_payload=[_event(node="implement", failure=None)],
        stage="implement",
    )
    assert failure is not None
    assert failure.cause is None
    assert failure.category == "deterministic"


def test_last_failure_event_retains_innermost_cause_and_provider_classification() -> None:
    cause = "You've hit your org's monthly spend limit. Visit claude.ai/settings/usage"
    failure = routing_stage_failure(
        inspect_payload=None,
        events_payload=[
            _event(node="implement", failure={"message": "old failure"}),
            _event(
                node="implement",
                failure={
                    "message": "ACP turn failed",
                    "causes": ["ACP protocol error", cause],
                    "category": "transient_infra",
                    "signature": "implement|transient_infra|acp turn failed",
                },
            ),
            _event(node="needs_human", failure={"message": "terminal error"}),
        ],
        stage="implement",
    )
    assert failure is not None
    assert failure.cause == cause
    assert failure.provider_usage_limit_provider == "anthropic"
    assert failure.provider_usage_limit is True
    assert failure.category == "deterministic"
    assert failure.signature == "implement|deterministic|acp turn failed"


@given(message=st.from_regex(r"missing prerequisite [a-z]{1,20}", fullmatch=True))
def test_unrelated_failures_cannot_replace_the_selected_stage_message(*, message: str) -> None:
    failure = routing_stage_failure(
        inspect_payload=None,
        events_payload=[
            _event(node="implement", failure={"message": message}),
            _event(node="review", failure={"message": "unrelated"}),
            _event(node="needs_human", failure={"message": "terminal error"}),
        ],
        stage="implement",
    )
    assert failure is not None
    assert failure.cause == message
