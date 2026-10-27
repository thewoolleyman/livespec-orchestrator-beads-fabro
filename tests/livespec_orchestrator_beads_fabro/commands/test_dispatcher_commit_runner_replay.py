"""A runner-routed commit's verdict is read from the runner's own report.

Work-item `bd-ib-atyefi`; binds `SPECIFICATION/contracts.md` "A commit leg
completes past one tool call" together with "The recorded hook verdict
outranks the agent's account of it". An agent that commits through the sandbox
`livespec-commit-runner.py` leaves a `start` call that prints a run id and a
series of `wait` calls that each print one JSON report, and BOTH exit 0 whatever
the hook decided. The Dispatcher must therefore read the report, drive the
`DetachedCommitRunner` state machine with it, and treat each `start` as a new
attempt -- never the tool call's own exit status.

The event envelopes are the measured Petri `step.progress.recorded` shape the
direct-commit fixtures in `test_dispatcher_hook_verdict.py` transcribe.
"""

from __future__ import annotations

import json

import pytest
from livespec_orchestrator_beads_fabro.commands._dispatcher_hook_verdict import (
    HookVerdict,
    hook_verdict_from_events,
)

_RUNNER = 'python3 "${LIVESPEC_SANDBOX_CLAUDE_PLUGINS_ROOT:-$HOME/.claude/plugins}/livespec-commit-runner.py"'
_START = f"{_RUNNER} start -- mise exec -- git commit --amend --no-edit"
_RUN_ID = "commit-5f0c2a9e41d84b7f9a0e6c3d2b1a0f99"
_SECOND_RUN_ID = "commit-0aa1bb2cc3dd4ee5ff6a7b8c9d0e1f2a"
_REFUSAL_TAIL = (
    "│ lefthook v1.13.6  hook: pre-commit │\n"
    "Failed targets (2):\n  - check-types\n  - check-tests\n"
    "error: Recipe `check-pre-commit` failed on line 1217 with exit code 1\n"
    "✗ 03-check-pre-commit (2727.04 seconds)"
)
_HOOK_REFUSAL_OUTPUT = (
    "│ lefthook v1.13.6  hook: pre-commit │\nFailed targets (1):\n  - check-coverage\n"
)


def _wait(run_id: str) -> str:
    return f"{_RUNNER} wait {run_id} --timeout-seconds 300"


def _report(**fields: object) -> str:
    return json.dumps(fields, sort_keys=True) + "\n"


def _envelope(*, seq: int, update: dict[str, object]) -> dict[str, object]:
    return {
        "run_id": "01M5X4FSXQ5RBSQ79YKQH260QK",
        "stream_seq": seq,
        "kind": "petri",
        "item": {
            "subject": {"node": {"id": 3, "name": "implement", "kind": "attractor/agent"}},
            "record": {
                "seq": seq,
                "body": {
                    "event": "step.progress.recorded",
                    "ev": {
                        "custom": {
                            "kind": "acp",
                            "node": "implement",
                            "event": {"method": "session/update", "update": update},
                        }
                    },
                },
            },
        },
    }


def _call(seq: int, call_id: str, command: str, output: str, exit_code: int = 0) -> list[object]:
    """One tool call's start and completion envelopes."""
    return [
        _envelope(
            seq=seq,
            update={
                "sessionUpdate": "tool_call",
                "toolCallId": call_id,
                "status": "in_progress",
                "kind": "execute",
                "title": command,
                "rawInput": {"command": command, "cwd": "/workspace"},
            },
        ),
        _envelope(
            seq=seq + 1,
            update={
                "sessionUpdate": "tool_call_update",
                "toolCallId": call_id,
                "status": "failed" if exit_code else "completed",
                "rawOutput": {"formatted_output": output, "exit_code": exit_code},
            },
        ),
    ]


def _verdict(*calls: list[object]) -> HookVerdict | None:
    events: list[object] = [envelope for call in calls for envelope in call]
    return hook_verdict_from_events(events_payload=events, stage="050-implement@1")


def test_a_refusal_reported_by_a_later_wait_is_the_recorded_verdict() -> None:
    """The runner's wait exits 0, so only its report can carry the hook's refusal."""
    verdict = _verdict(
        _call(10, "c1", _START, _RUN_ID + "\n"),
        _call(20, "c2", _wait(_RUN_ID), _report(run_id=_RUN_ID, state="running")),
        _call(
            30,
            "c3",
            _wait(_RUN_ID),
            _report(
                run_id=_RUN_ID,
                state="failed",
                hook_ran=True,
                exit_code=1,
                head=None,
                output_tail=_REFUSAL_TAIL,
            ),
        ),
    )

    assert verdict == HookVerdict(
        node="implement", exit_code=1, failed_targets=("check-types", "check-tests")
    )


def test_a_commit_still_running_when_the_turn_ends_is_no_refusal() -> None:
    """A `running` report is an observation, not a failed commit."""
    verdict = _verdict(
        _call(10, "c1", _START, _RUN_ID + "\n"),
        _call(20, "c2", _wait(_RUN_ID), _report(run_id=_RUN_ID, state="running")),
    )

    assert verdict is None


def test_a_later_start_supersedes_an_earlier_refusal() -> None:
    """The latest attempt is the one whose verdict counts, and it has none yet."""
    verdict = _verdict(
        _call(
            10,
            "c1",
            _wait(_RUN_ID),
            _report(
                run_id=_RUN_ID,
                state="failed",
                hook_ran=True,
                exit_code=1,
                output_tail=_REFUSAL_TAIL,
            ),
        ),
        _call(20, "c2", _START, _SECOND_RUN_ID + "\n"),
    )

    assert verdict is None


def test_a_wait_whose_start_is_not_on_the_record_still_reports_its_refusal() -> None:
    """The report alone carries the verdict, so a lost start does not hide it."""
    verdict = _verdict(
        _call(
            10,
            "c1",
            _wait(_RUN_ID),
            _report(
                run_id=_RUN_ID,
                state="failed",
                hook_ran=True,
                exit_code=2,
                output_tail="hook: commit-msg",
            ),
        ),
    )

    assert verdict == HookVerdict(node="implement", exit_code=2, failed_targets=())


def test_a_commit_that_ended_without_a_verdict_reports_no_refusal() -> None:
    """`no-verdict` is not a commit and not a hook refusal either."""
    verdict = _verdict(
        _call(10, "c1", _START, _RUN_ID + "\n"),
        _call(
            20,
            "c2",
            _wait(_RUN_ID),
            _report(run_id=_RUN_ID, state="no-verdict", exit_code=None, output_tail=""),
        ),
    )

    assert verdict is None


def test_a_failed_report_without_an_exit_status_is_read_as_no_verdict() -> None:
    """A terminal report that recorded no exit status cannot name a refusal's status."""
    verdict = _verdict(
        _call(
            10,
            "c1",
            _wait(_RUN_ID),
            _report(
                run_id=_RUN_ID,
                state="failed",
                hook_ran=True,
                exit_code=None,
                output_tail=_REFUSAL_TAIL,
            ),
        ),
    )

    assert verdict is None


def test_a_passed_report_after_an_earlier_refusal_reports_no_refusal() -> None:
    """A passing latest attempt is not a refusal, whatever an earlier attempt did."""
    verdict = _verdict(
        _call(10, "c1", "mise exec -- git commit --amend --no-edit", _HOOK_REFUSAL_OUTPUT, 1),
        _call(20, "c2", _START, _RUN_ID + "\n"),
        _call(
            30,
            "c3",
            _wait(_RUN_ID),
            _report(run_id=_RUN_ID, state="passed", exit_code=0, head="0123abc", output_tail=""),
        ),
    )

    assert verdict is None


def test_runner_calls_that_carry_no_report_leave_the_latest_verdict_alone() -> None:
    """A refused start, an empty start and unreadable waits are not commit attempts."""
    verdict = _verdict(
        _call(10, "c1", "mise exec -- git commit --amend --no-edit", _HOOK_REFUSAL_OUTPUT, 1),
        _call(20, "c2", _START, "livespec commit runner: commit run x is still running\n", 2),
        _call(30, "c3", _START, ""),
        _call(40, "c4", _wait(_RUN_ID), "livespec commit runner: no commit run recorded\n", 2),
        _call(50, "c5", _wait(_RUN_ID), "{not json\n"),
        _call(60, "c6", _wait(_RUN_ID), _report(state="failed")),
    )

    assert verdict == HookVerdict(node="implement", exit_code=1, failed_targets=("check-coverage",))


def test_a_replayed_wait_observes_the_record_once_and_never_sleeps() -> None:
    """Each recorded report is the observation, so the replay clock refuses to sleep."""
    from livespec_orchestrator_beads_fabro.commands._dispatcher_commit_runner_replay import (
        _ReplayClock,  # pyright: ignore[reportPrivateUsage]
    )

    with pytest.raises(RuntimeError, match="never sleeps"):
        _ReplayClock().sleep(seconds=1.0)


def test_a_failed_commit_that_ran_no_hook_is_not_a_hook_refusal() -> None:
    """Nothing staged, or a bad message: the commit failed, but no hook refused it."""
    verdict = _verdict(
        _call(10, "c1", _START, _RUN_ID + "\n"),
        _call(
            20,
            "c2",
            _wait(_RUN_ID),
            _report(
                run_id=_RUN_ID,
                state="failed",
                hook_ran=False,
                exit_code=1,
                output_tail="nothing to commit, working tree clean",
            ),
        ),
    )

    assert verdict is None
