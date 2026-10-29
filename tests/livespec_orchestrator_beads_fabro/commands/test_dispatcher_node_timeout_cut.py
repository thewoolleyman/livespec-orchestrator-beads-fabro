"""A node-timeout cut is named on the ledger with its commit runs and any hook run.

Binds the host side of `SPECIFICATION/scenarios.md` Scenario 192 for work-item
``bd-ib-ptnxyg``:

- "A commit run that passes after the cut is preserved and named" -- the needs-human
  cause names node-timeout, the cut node, its resolved timeout in seconds, and the
  commit run's identity with state passed.
- "A commit run still running when the bounded wait ends is stopped before
  preservation" -- the cause names that run with state no-verdict.
- "An in-turn commit whose hook is still executing at the cut is a hook-over-limit
  event" -- the cut yields the `hook-over-limit` event naming the cut node, the git
  operation and the node's resolved timeout in seconds.

THE NEGATIVE ARMS ARE ASSERTED BESIDE THE POSITIVE ONES. A cut is named only when
the failing stage's recorded cause is a timed-out turn, and a commit run the cut
turn did not start is not named, because the sandbox's run directory also holds
every earlier stage's runs and listing those would attribute them to the cut.
"""

from __future__ import annotations

import importlib
from pathlib import Path
from typing import Any

_MODULE_NAME = "livespec_orchestrator_beads_fabro.commands._dispatcher_node_timeout_cut"
_COMMANDS = (
    Path(__file__).resolve().parents[3]
    / ".claude-plugin"
    / "scripts"
    / "livespec_orchestrator_beads_fabro"
    / "commands"
)
_TIMED_OUT = "ACP turn timed out after 55 tool call(s) and 840 session update(s)"
_RUN_A = "commit-" + "a" * 32
_RUN_B = "commit-" + "b" * 32


def _module() -> Any:
    module_path = _COMMANDS / "_dispatcher_node_timeout_cut.py"
    assert module_path.is_file(), f"{module_path} does not exist yet"
    return importlib.import_module(_MODULE_NAME)


def _cut(*, text: str, started: tuple[str, ...] | None = None, cause: str = _TIMED_OUT) -> Any:
    return _module().node_timeout_cut(
        text=text,
        stage="fix",
        cause=cause,
        timeout_seconds=3600,
        started_run_ids=started,
    )


def _run_line(*, run_id: str, state: str) -> str:
    return f"LIVESPEC_NODE_CUT_COMMIT_RUN: run={run_id} state={state}"


def test_a_passed_commit_run_is_named_with_the_node_and_its_resolved_timeout() -> None:
    """Scenario 192: node-timeout, the fix node, 3600 seconds, the run and `passed`."""
    cut = _cut(text=_run_line(run_id=_RUN_A, state="passed"), started=(_RUN_A,))

    assert cut is not None
    body = "\n".join(_module().node_timeout_cut_cause_lines(cut=cut))
    assert "node-timeout" in body
    assert "fix" in body
    assert "3600" in body
    assert f"{_RUN_A}: passed" in body


def test_a_run_stopped_at_the_bounded_wait_is_named_no_verdict() -> None:
    """Scenario 192: the stopped run is named with state no-verdict."""
    cut = _cut(text=_run_line(run_id=_RUN_A, state="no-verdict"), started=(_RUN_A,))

    assert cut is not None
    assert f"{_RUN_A}: no-verdict" in "\n".join(_module().node_timeout_cut_cause_lines(cut=cut))


def test_a_run_the_cut_turn_did_not_start_is_not_named() -> None:
    """Scenario 192: only each commit run the cut turn had started is named."""
    text = "\n".join(
        (_run_line(run_id=_RUN_A, state="passed"), _run_line(run_id=_RUN_B, state="passed"))
    )
    cut = _cut(text=text, started=(_RUN_B,))

    assert cut is not None
    body = "\n".join(_module().node_timeout_cut_cause_lines(cut=cut))
    assert _RUN_B in body
    assert _RUN_A not in body


def test_a_started_run_the_sandbox_never_reported_is_named_unobserved() -> None:
    """Scenario 192: a run the sandbox did not report is named, never invented as passed."""
    cut = _cut(text="no sentinel at all", started=(_RUN_A,))

    assert cut is not None
    assert f"{_RUN_A}: unobserved" in "\n".join(_module().node_timeout_cut_cause_lines(cut=cut))


def test_no_cut_is_named_when_the_stage_did_not_time_out() -> None:
    """Scenario 192: a stage that failed for another cause is not a node-timeout."""
    text = _run_line(run_id=_RUN_A, state="passed")

    assert _cut(text=text, started=(_RUN_A,), cause="the hook refused") is None
    assert _cut(text=text, started=(_RUN_A,), cause="") is None


def test_an_in_turn_hook_run_at_the_cut_is_a_hook_over_limit_event() -> None:
    """Scenario 192: the event names the cut node, the operation and the node's timeout."""
    text = "LIVESPEC_NODE_CUT_HOOK_RUN: operation=commit hook_elapsed_ms=295000"
    cut = _cut(text=text, started=())

    assert cut is not None
    event = cut.hook_over_limit
    assert event is not None
    assert (event.node, event.operation, event.limit_seconds, event.hook_elapsed_ms) == (
        "fix",
        "commit",
        3600,
        295000,
    )


def test_no_hook_run_observed_is_no_hook_over_limit_event() -> None:
    """Scenario 192: a cut that found no hook run executing yields no event."""
    cut = _cut(text=_run_line(run_id=_RUN_A, state="passed"), started=(_RUN_A,))

    assert cut is not None
    assert cut.hook_over_limit is None


def test_the_started_run_ids_are_read_from_the_cut_stages_recorded_runner_calls() -> None:
    """Scenario 192: a run id is what the stage's own `start` call printed."""
    module = _module()
    runner = "python3 /root/.claude/plugins/livespec-commit-runner.py"
    events = [
        _tool_call(seq=1, call_id="c1", node="fix", command=f"{runner} start -- git commit -m x"),
        _tool_done(seq=2, call_id="c1", node="fix", output=_RUN_A + "\n"),
        _tool_call(seq=3, call_id="c2", node="implement", command=f"{runner} start -- git commit"),
        _tool_done(seq=4, call_id="c2", node="implement", output=_RUN_B + "\n"),
        _tool_call(seq=5, call_id="c3", node="fix", command=f"{runner} wait {_RUN_A} --x 1"),
        _tool_done(seq=6, call_id="c3", node="fix", output='{"state": "running"}'),
    ]

    assert module.started_commit_run_ids(events_payload=events, stage="fix@1") == (_RUN_A,)
    assert module.started_commit_run_ids(events_payload=events, stage="review_fix") == ()
    assert module.started_commit_run_ids(events_payload=None, stage="fix") is None


def _envelope(*, seq: int, node: str, update: dict[str, object]) -> dict[str, object]:
    return {
        "stream_seq": seq,
        "item": {
            "subject": {"node": {"name": node}},
            "record": {
                "body": {
                    "ev": {"custom": {"event": {"update": update}}},
                }
            },
        },
    }


def _tool_call(*, seq: int, call_id: str, node: str, command: str) -> dict[str, object]:
    return _envelope(
        seq=seq,
        node=node,
        update={
            "sessionUpdate": "tool_call",
            "toolCallId": call_id,
            "rawInput": {"command": command},
        },
    )


def _tool_done(*, seq: int, call_id: str, node: str, output: str) -> dict[str, object]:
    return _envelope(
        seq=seq,
        node=node,
        update={
            "sessionUpdate": "tool_call_update",
            "toolCallId": call_id,
            "rawOutput": {"formatted_output": output, "exit_code": 0},
        },
    )
