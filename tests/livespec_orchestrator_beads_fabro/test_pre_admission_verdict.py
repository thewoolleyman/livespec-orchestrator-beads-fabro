"""Transport parsing preserves gate findings and treats uncertainty as unavailable."""

import json

import pytest
from hypothesis import given
from hypothesis import strategies as st
from livespec_orchestrator_beads_fabro._pre_admission_verdict import parse_judgement
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandResult
from returns.pipeline import is_successful


@pytest.mark.parametrize(
    "payload",
    [
        {},
        [],
        {"outcome": "failed"},
        {"outcome": "failed", "failure_reason": ""},
        {"outcome": "failed", "failure_reason": 1},
        {"outcome": "failed", "failure_reason": "fix", "remedies": "fix"},
        {"outcome": "failed", "failure_reason": "fix", "remedies": []},
        {"outcome": "failed", "failure_reason": "fix", "remedies": [1]},
        {"outcome": "failed", "failure_reason": "fix", "remedies": [""]},
        {"outcome": "unavailable"},
        {"outcome": "unavailable", "reason": "no spec"},
        {"is_error": True, "result": "provider unavailable"},
    ],
)
def test_unavailable_is_not_a_semantic_hold(*, payload: object) -> None:
    result = parse_judgement(
        response=CommandResult(exit_code=0, stdout=json.dumps(payload), stderr="")
    )
    assert not is_successful(result)
    assert result.failure()


@pytest.mark.parametrize("stdout", ["", "not JSON", "\n\n"])
def test_missing_transport_verdict_is_unavailable(*, stdout: str) -> None:
    assert not is_successful(
        parse_judgement(response=CommandResult(exit_code=0, stdout=stdout, stderr=""))
    )


def test_failed_process_cannot_supply_an_admitting_verdict() -> None:
    result = parse_judgement(
        response=CommandResult(exit_code=124, stdout='{"outcome":"passed"}', stderr="timed out")
    )
    assert not is_successful(result)
    assert "124: timed out" in result.failure()


@pytest.mark.parametrize("enveloped", [False, True])
def test_pass_is_explicit(*, enveloped: bool) -> None:
    text = json.dumps({"outcome": "passed"})
    stdout = json.dumps({"result": f"All assertions are gradeable.\n{text}"}) if enveloped else text
    result = parse_judgement(response=CommandResult(exit_code=0, stdout=stdout, stderr=""))
    assert is_successful(result)
    assert result.unwrap().failure_reason is None
    assert result.unwrap().remedies == ()


@pytest.mark.parametrize("separate_remedies", [False, True])
def test_failure_retains_every_finding_and_remedy(*, separate_remedies: bool) -> None:
    payload: dict[str, object] = {
        "outcome": "failed",
        "failure_reason": "First defect. Second defect.",
    }
    remedies = ["Name the governing scenario.", "Restate the second assertion."]
    if separate_remedies:
        payload["remedies"] = remedies
    result = parse_judgement(
        response=CommandResult(exit_code=0, stdout=json.dumps(payload), stderr="")
    )
    assert is_successful(result)
    assert result.unwrap().failure_reason == payload["failure_reason"]
    assert result.unwrap().remedies == (
        tuple(remedies) if separate_remedies else (payload["failure_reason"],)
    )


def test_codex_uses_the_last_completed_agent_message_not_tool_output() -> None:
    verdict = json.dumps(
        {"outcome": "failed", "failure_reason": "Reference the governing heading."}
    )
    events = [
        {"type": "thread.started"},
        {"type": "item.completed", "item": []},
        {"type": "item.completed", "item": {"type": "agent_message", "text": "Thinking."}},
        {
            "type": "item.completed",
            "item": {"type": "command_execution", "text": '{"outcome":"passed"}'},
        },
        {"type": "item.completed", "item": {"type": "agent_message", "text": verdict}},
        {"type": "turn.completed"},
    ]
    result = parse_judgement(
        response=CommandResult(
            exit_code=0, stdout="\n".join(json.dumps(event) for event in events), stderr=""
        )
    )
    assert is_successful(result)
    assert result.unwrap().failure_reason == "Reference the governing heading."


@given(text=st.text())
def test_arbitrary_output_is_data_not_a_parser_exception(*, text: str) -> None:
    result = parse_judgement(response=CommandResult(exit_code=0, stdout=text, stderr=""))
    assert is_successful(result) or isinstance(result.failure(), str)
