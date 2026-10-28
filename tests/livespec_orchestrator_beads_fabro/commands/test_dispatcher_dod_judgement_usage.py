"""Coverage for host Definition-of-Done candidate input accounting."""

from __future__ import annotations

from livespec_orchestrator_beads_fabro.commands._dispatcher_dod_judgement_usage import (
    INPUT_USAGE_COMPLETE,
    INPUT_USAGE_PARTIAL,
    INPUT_USAGE_UNREPORTED,
    candidate_input_usage,
    candidate_reply,
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


def test_a_request_that_never_reported_input_marks_the_total_partial() -> None:
    """A total missing a request the transcript names is reported as incomplete.

    The marking is what a reader needs to tell a figure that IS the candidate's
    input from one that is merely the part of it the transcript could account
    for, and the two are otherwise indistinguishable: both are a plain integer
    below the bound. Recording the second as `complete` understates the
    candidate's real use, which is the direction that lets a candidate past the
    bound it was measured against.
    """
    usage = candidate_input_usage(
        output="\n".join(
            [
                '{"request_id": "request-one", "usage": {"input_tokens": 40}}',
                '{"request_id": "request-two", "usage": {"output_tokens": 9}}',
            ]
        )
    )

    assert usage.total_tokens == 40
    assert usage.status == INPUT_USAGE_PARTIAL


def test_a_request_reporting_input_on_any_of_its_records_is_counted_whole() -> None:
    """One request spread over several records is complete, not partial.

    The control for the case above, and the one a naive reading fails: a host
    judge announces a request before it can know its usage, so the SAME request
    id arrives first with no counts and later with them. Treating any
    countless record as a gap marks every ordinary transcript partial, which
    would retire the marking by making it mean nothing.
    """
    usage = candidate_input_usage(
        output="\n".join(
            [
                '{"request_id": "request-one", "usage": {"output_tokens": 0}}',
                '{"request_id": "request-one", "usage": {"input_tokens": 40}}',
            ]
        )
    )

    assert usage.total_tokens == 40
    assert usage.status == INPUT_USAGE_COMPLETE


def test_a_claude_stream_s_result_record_is_the_reply() -> None:
    output = "\n".join(
        (
            '{"type": "assistant", "message": {"id": "m", "usage": {"input_tokens": 1}}}',
            '{"type": "result", "result": "first"}',
            '{"type": "result", "result": "the last result wins"}',
        )
    )

    assert candidate_reply(output=output) == "the last result wins"


def test_a_codex_event_stream_s_last_agent_message_is_the_reply() -> None:
    output = "\n".join(
        (
            '{"type": "item.completed", "item": {"type": "reasoning", "text": "thinking"}}',
            '{"type": "item.completed", "item": {"type": "agent_message", "text": "answer"}}',
            '{"type": "turn.completed", "usage": {"input_tokens": 3}}',
        )
    )

    assert candidate_reply(output=output) == "answer"


def test_output_that_carries_no_reply_record_is_returned_unchanged() -> None:
    for output in (
        '{"outcome": "passed"}\n',
        "plain text, not json",
        '{"type": "result", "subtype": "error_max_turns"}',
        '{"type": "item.completed", "item": "not-a-mapping"}',
        '{"type": "item.completed", "item": {"type": "agent_message", "text": 7}}',
        '{"type": "turn.started"}',
    ):
        assert candidate_reply(output=output) == output
