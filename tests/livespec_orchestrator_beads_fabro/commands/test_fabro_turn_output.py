"""The recorded output of a run's succeeded agent turns, read off its `inspect` record.

`SPECIFICATION/contracts.md` section "Factory-configurable ACP fallback
priority": a `turn.final_output` signature reads only "an agent node attempt
that the engine recorded as succeeded", and the Dispatcher reads that recorded
output from the run's resolved factory. Only the Petri `stages` map carries a
turn's text, so a record without it yields no turn rather than a guessed one.
"""

from __future__ import annotations

from typing import Any

from livespec_orchestrator_beads_fabro.commands._fabro_turn_output import (
    routing_predecessor_turn,
    succeeded_agent_turns,
)

_REFUSAL = "Selected model is at capacity. Please try a different model."


def _stage(
    *,
    state: str = "succeeded",
    handler: str = "agent",
    response: object = "",
    output: object = None,
) -> dict[str, object]:
    entry: dict[str, object] = {"handler": handler, "state": state, "response": response}
    if output is not None:
        entry["output"] = output
    return entry


def _record(*, stages: object, checkpoint: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    return [
        {
            "run_id": "01M5C0FBAE8FVZK15XN9WHVM6H",
            "stages": stages,
            "checkpoint": {"current_node": "needs_human"} if checkpoint is None else checkpoint,
        }
    ]


def _terminal_stages(*, last: dict[str, object]) -> dict[str, object]:
    return {
        "implement@1": _stage(output="Implemented."),
        "review@2": last,
        "needs_human@1": _stage(state="failed", handler="command", output="parked"),
    }


def test_the_text_is_the_response_when_the_engine_recorded_one() -> None:
    turns = succeeded_agent_turns(
        payload=_record(stages={"review@1": _stage(response="from response", output="from output")})
    )
    assert [(turn.stage, turn.node, turn.output) for turn in turns] == [
        ("review@1", "review", "from response")
    ]


def test_the_text_falls_back_to_output_when_the_response_is_blank() -> None:
    turns = succeeded_agent_turns(
        payload=_record(stages={"review@1": _stage(response="  ", output=_REFUSAL)})
    )
    assert turns[0].output == _REFUSAL


def test_a_turn_with_no_recorded_text_has_none() -> None:
    turns = succeeded_agent_turns(payload=_record(stages={"review@1": _stage()}))
    assert turns[0].output is None


def test_only_the_newest_visit_of_a_node_is_read() -> None:
    stages = {"review@1": _stage(output="first"), "review@2": _stage(output="second")}
    turns = succeeded_agent_turns(payload=_record(stages=stages))
    assert [turn.output for turn in turns] == ["second"]


def test_failed_and_non_agent_stages_are_not_agent_turns() -> None:
    stages = {
        "review@1": _stage(state="failed", output=_REFUSAL),
        "janitor@1": _stage(handler="command", output=_REFUSAL),
    }
    assert succeeded_agent_turns(payload=_record(stages=stages)) == ()


def test_a_record_with_no_stage_map_yields_no_turn() -> None:
    assert succeeded_agent_turns(payload=None) == ()
    assert succeeded_agent_turns(payload=_record(stages=None)) == ()
    assert succeeded_agent_turns(payload=_record(stages=["review@1"])) == ()


def test_checkpoint_outcomes_that_name_no_stage_entry_yield_no_turn() -> None:
    """The pinned engine grades by node id, and records no text for a node to be read from."""
    checkpoint = {
        "current_node": "needs_human",
        "node_outcomes": {"review": {"status": "succeeded"}},
    }
    payload = _record(stages={"review@1": _stage(output=_REFUSAL)}, checkpoint=checkpoint)
    assert succeeded_agent_turns(payload=payload) == ()
    assert routing_predecessor_turn(payload=payload) is None


def test_the_routing_predecessor_is_the_last_stage_before_the_terminal() -> None:
    turn = routing_predecessor_turn(
        payload=_record(stages=_terminal_stages(last=_stage(output=_REFUSAL)))
    )
    assert turn is not None
    assert (turn.stage, turn.node, turn.output) == ("review@2", "review", _REFUSAL)


def test_a_failed_last_stage_is_not_a_routing_predecessor_turn() -> None:
    last = _stage(state="failed", handler="command", output="FAILED")
    assert routing_predecessor_turn(payload=_record(stages=_terminal_stages(last=last))) is None


def test_a_succeeded_non_agent_last_stage_is_not_a_routing_predecessor_turn() -> None:
    last = _stage(handler="command", output=_REFUSAL)
    assert routing_predecessor_turn(payload=_record(stages=_terminal_stages(last=last))) is None


def test_a_run_that_reached_no_terminal_has_no_routing_predecessor() -> None:
    payload = _record(
        stages={"review@1": _stage(output=_REFUSAL)}, checkpoint={"current_node": "review"}
    )
    assert routing_predecessor_turn(payload=payload) is None


def test_a_terminal_reached_with_no_other_stage_has_no_routing_predecessor() -> None:
    stages = {"needs_human@1": _stage(state="failed", handler="command", output="parked")}
    assert routing_predecessor_turn(payload=_record(stages=stages)) is None
