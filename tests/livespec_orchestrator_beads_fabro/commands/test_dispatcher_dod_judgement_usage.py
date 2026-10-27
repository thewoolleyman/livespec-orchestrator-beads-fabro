"""Coverage for host Definition-of-Done candidate input accounting."""

from __future__ import annotations

from livespec_orchestrator_beads_fabro.commands._dispatcher_dod_judgement_usage import (
    INPUT_USAGE_COMPLETE,
    INPUT_USAGE_UNREPORTED,
    candidate_input_usage,
)


def test_an_unnamed_total_is_an_aggregate_not_an_additional_request() -> None:
    usage = candidate_input_usage(
        output='{"usage": {"input_tokens": 12}}\n{"usage": {"input_tokens": 9}}'
    )

    assert usage.total_tokens == 12
    assert usage.status == INPUT_USAGE_COMPLETE


def test_missing_or_invalid_usage_is_explicitly_unreported() -> None:
    usage = candidate_input_usage(output='not-json\n[]\n{"usage": {"input_tokens": -1}}')

    assert usage.total_tokens is None
    assert usage.status == INPUT_USAGE_UNREPORTED


def test_message_shaped_usage_uses_the_nested_request_identifier() -> None:
    usage = candidate_input_usage(
        output='{"message": {"id": "request-one", "usage": {"input_tokens": 7}}}'
    )

    assert usage.total_tokens == 7
    assert usage.status == INPUT_USAGE_COMPLETE


def test_a_request_usage_with_no_input_counts_is_not_a_total() -> None:
    usage = candidate_input_usage(
        output='{"request_id": "request-one", "usage": {"output_tokens": 7}}'
    )

    assert usage.total_tokens is None
    assert usage.status == INPUT_USAGE_UNREPORTED
