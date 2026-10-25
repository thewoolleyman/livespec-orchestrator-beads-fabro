"""A hook-refused commit's RECORDED verdict outranks the agent's account of it.

Work-item `bd-ib-k3nmbi`; binds `SPECIFICATION/contracts.md` "The recorded hook
verdict outranks the agent's account of it" (v211) and the Scenario 179 case
"A needs-human ending after a hook-refused commit names the hook's recorded
verdict".

THE FIXTURES TRANSCRIBE MEASURED RECORDS. On run `01M5QNH88NHN68ST28Y80CZJ48`
(`bd-ib-8zyan`, gmktec, Petri, 2026-10-24) the `fabro events --json` stream
carries the implement turn's ACP tool calls as `step.progress.recorded`
envelopes: the node is named on `item.subject.node.name`, and the ACP update
sits at `item.record.body.ev.custom.event.update`. The Green amend's
`tool_call` start carried `rawInput.command`
`mise exec -- git add … && mise exec -- git commit --amend --no-edit`; its
`tool_call_update` completion carried `status: failed`, `rawOutput.exit_code: 1`
and a `rawOutput.formatted_output` holding the lefthook banner
(`lefthook v1.13.6  hook: pre-commit`), the gate's `Failed targets (1):` block
naming `check-types`, and the summary `✗ 03-check-pre-commit (711.40 seconds)`.
The turn's own final text — the stage's `failure_reason` — said "the Green
amend hook did not complete".

THE CONTROLS ARE THE TRAPS THAT RUN RECORDED. The same turn ran a dozen
`ps … | rg 'git commit|lefthook'` inspection calls, each containing the literal
`git commit` and each exiting 0 with no hook banner; the LAST tool call of the
turn was one of them. A reader that took "the latest tool call mentioning
`git commit`" would conclude the latest commit attempt passed. Only a call whose
RECORDED OUTPUT shows a hook ran is a commit attempt this clause governs.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import (
    CommandResult,
    DispatchOutcome,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_fabro_terminal import (
    fabro_run_terminal_outcome,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_hook_verdict import (
    HookVerdict,
    hook_verdict_cause_lines,
    hook_verdict_from_events,
    innermost_cause_label,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_ledger_close import (
    _outcome_payload,  # pyright: ignore[reportPrivateUsage]
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_needs_human_cause import (
    needs_human_cause_body,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_plan import (
    NEEDS_HUMAN_MARKER,
    DispatchPlan,
)
from livespec_orchestrator_beads_fabro.commands._fabro_port import FabroInspectResult
from livespec_orchestrator_beads_fabro.commands._fabro_port_records import (
    fabro_failure_detail_from_payload,
    fabro_status_kind_from_payload,
)

_RUN = "01M5QNH88NHN68ST28Y80CZJ48"
_ITEM = "bd-ib-8zyan"
_AMEND_COMMAND = (
    "mise exec -- git add .claude-plugin/scripts/livespec_orchestrator_beads_fabro/commands/"
    "_dispatcher_dod_judgement_disagreement.py tests/livespec_orchestrator_beads_fabro/"
    "commands/test_dod_judgement_disagreement_controls.py && mise exec -- git commit --amend --no-edit"
)
_INSPECT_COMMAND = (
    "ps -eo pid=,ppid=,stat=,etimes=,args= | rg 'git commit --amend|lefthook|check-per-file' "
    "|| true; git status --short; git log -1 --format='%h%n%s%n%b'"
)
_HOOK_REFUSAL_OUTPUT = (
    "╭──────────────────────────────────────╮\n│ lefthook v1.13.6  hook: pre-commit │\n"
    "╰──────────────────────────────────────╯\n┃  03-check-pre-commit > \n\n"
    "...\n\nFailed targets (1):\n  - check-types\n"
    "error: Recipe `check-skipping` failed on line 477 with exit code 1\n"
    "error: Recipe `check-pre-commit` failed on line 1217 with exit code 1\n\nexit status 1\n"
    "  ────────────────────────────────────\nsummary: (done in 712.37 seconds)\n"
    "✓ 00-install-worktree-pack (0.45 seconds)\n✓ 01-lint-autofix-staged (0.14 seconds)\n"
    "✓ 02-commit-pairs-source-and-test (0.35 seconds)\n✗ 03-check-pre-commit (711.40 seconds)\n"
)
_HOOK_PASS_OUTPUT = (
    "╭──────────────────────────────────────╮\n│ lefthook v1.13.6  hook: pre-commit │\n"
    "╰──────────────────────────────────────╯\nsummary: (done in 640.10 seconds)\n"
    "✓ 03-check-pre-commit (639.80 seconds)\n[fix/x 0123abc] feat: something\n"
)
_INSPECT_OUTPUT = " 166801   14739 Ss         0 /bin/bash -c ps -eo pid=,ppid=,stat=,etimes=,args= | rg 'git commit --amend|lefthook'\n"
_AGENT_TEXT = (
    "LIVESPEC_IMPLEMENT_PARTIAL_PROGRESS: committed Red test f81b470e; staged disagreement "
    "reader and tests are not Green-committed because the Green amend hook did not complete."
)
_TERMINAL_OUTPUT = (
    f"{NEEDS_HUMAN_MARKER}_PRESERVED: refs/heads/needs-human/0209f2cfa52748f199e8383d99147eab\n"
    f"{NEEDS_HUMAN_MARKER}: loop cannot auto-resolve this work-item; run terminated, "
    "work preserved by reference, decision routed to the ledger (blocked / needs-human)\n"
)


def _envelope(*, seq: int, node: str, update: dict[str, object]) -> dict[str, object]:
    """One Petri `step.progress.recorded` envelope carrying an ACP session update."""
    return {
        "run_id": _RUN,
        "stream_seq": seq,
        "kind": "petri",
        "recorded_at": 1792872000000 + seq,
        "item": {
            "subject": {"node": {"id": 3, "name": node, "kind": "attractor/agent"}, "visit": 1},
            "record": {
                "seq": seq,
                "body": {
                    "event": "step.progress.recorded",
                    "ev": {
                        "custom": {
                            "kind": "acp",
                            "node": node,
                            "event": {"method": "session/update", "update": update},
                        }
                    },
                },
            },
        },
    }


def _tool_call(
    *, seq: int, call_id: str, command: str, node: str = "implement"
) -> dict[str, object]:
    return _envelope(
        seq=seq,
        node=node,
        update={
            "sessionUpdate": "tool_call",
            "toolCallId": call_id,
            "status": "in_progress",
            "kind": "execute",
            "title": command,
            "rawInput": {"command": command, "cwd": "/workspace"},
        },
    )


def _tool_done(
    *, seq: int, call_id: str, output: str, exit_code: int, node: str = "implement"
) -> dict[str, object]:
    return _envelope(
        seq=seq,
        node=node,
        update={
            "sessionUpdate": "tool_call_update",
            "toolCallId": call_id,
            "status": "failed" if exit_code else "completed",
            "rawOutput": {"formatted_output": output, "exit_code": exit_code},
            "_meta": {"terminal_exit": {"exit_code": exit_code, "signal": None}},
        },
    )


def _delta(*, seq: int, call_id: str) -> dict[str, object]:
    """A streaming output delta: a `tool_call_update` with no `rawOutput`."""
    return _envelope(
        seq=seq,
        node="implement",
        update={
            "sessionUpdate": "tool_call_update",
            "toolCallId": call_id,
            "_meta": {
                "terminal_output_delta": {"data": "│ lefthook v1.13.6  hook: pre-commit │\n"}
            },
        },
    )


def _measured_stream() -> list[object]:
    """The 8zyan shape: a refused Green amend followed by `rg 'git commit…'` inspections."""
    return [
        _tool_call(
            seq=1,
            call_id="exec-red",
            command="mise exec -- git add tests/x.py && mise exec -- git commit -m 'feat: red'",
        ),
        _tool_done(seq=2, call_id="exec-red", output=_HOOK_PASS_OUTPUT, exit_code=0),
        _tool_call(seq=3, call_id="exec-amend", command=_AMEND_COMMAND),
        _delta(seq=4, call_id="exec-amend"),
        _tool_done(seq=5, call_id="exec-amend", output=_HOOK_REFUSAL_OUTPUT, exit_code=1),
        _tool_call(seq=6, call_id="exec-ps", command=_INSPECT_COMMAND),
        _tool_done(seq=7, call_id="exec-ps", output=_INSPECT_OUTPUT, exit_code=0),
    ]


def test_the_latest_hook_running_commit_attempt_supplies_the_recorded_verdict() -> None:
    verdict = hook_verdict_from_events(events_payload=_measured_stream(), stage="implement@1")
    assert verdict == HookVerdict(node="implement", exit_code=1, failed_targets=("check-types",))


def test_an_inspection_command_mentioning_git_commit_is_not_a_commit_attempt() -> None:
    """CONTROL: the last `git commit`-mentioning call ran `ps | rg`, exit 0, no hook banner."""
    stream = _measured_stream()
    assert hook_verdict_from_events(events_payload=stream, stage="implement@1") is not None
    only_inspections = [stream[0], stream[1], stream[5], stream[6]]
    assert hook_verdict_from_events(events_payload=only_inspections, stage="implement@1") is None


def test_a_later_passing_commit_leaves_no_refusal_to_report() -> None:
    stream = [
        *_measured_stream(),
        _tool_call(
            seq=8, call_id="exec-again", command="mise exec -- git commit --amend --no-edit"
        ),
        _tool_done(seq=9, call_id="exec-again", output=_HOOK_PASS_OUTPUT, exit_code=0),
    ]
    assert hook_verdict_from_events(events_payload=stream, stage="implement@1") is None


def test_another_nodes_refused_commit_is_not_attributed_to_the_stage() -> None:
    stream = [
        _tool_call(seq=1, call_id="exec-fix", command=_AMEND_COMMAND, node="fix"),
        _tool_done(seq=2, call_id="exec-fix", output=_HOOK_REFUSAL_OUTPUT, exit_code=1, node="fix"),
    ]
    assert hook_verdict_from_events(events_payload=stream, stage="implement@1") is None
    assert hook_verdict_from_events(events_payload=stream, stage="fix@2") is not None


def test_a_refusal_naming_no_targets_still_carries_its_exit_status() -> None:
    """A commit-msg hook refusal prints no `Failed targets` block; the exit status is the verdict."""
    output = "╭──╮\n│ lefthook v1.13.6  hook: commit-msg │\n╰──╯\n┃  01-red-green-replay > \ntest-passed-at-red\n✗ 01-red-green-replay (2.85 seconds)\n"
    stream = [
        _tool_call(seq=1, call_id="exec-c", command="mise exec -- git commit -F /tmp/msg"),
        _tool_done(seq=2, call_id="exec-c", output=output, exit_code=1),
    ]
    assert hook_verdict_from_events(events_payload=stream, stage="implement") == HookVerdict(
        node="implement", exit_code=1, failed_targets=()
    )


@pytest.mark.parametrize(
    "payload",
    [
        None,
        {},
        [],
        [{"item": "not a mapping"}],
        [
            {
                "item": {
                    "record": {
                        "body": {
                            "ev": {
                                "custom": {
                                    "kind": "acp",
                                    "event": {
                                        "update": {
                                            "sessionUpdate": "tool_call_update",
                                            "toolCallId": "x",
                                            "rawOutput": {
                                                "exit_code": "1",
                                                "formatted_output": "hook: pre-commit",
                                            },
                                        }
                                    },
                                }
                            }
                        }
                    },
                    "subject": {"node": {"name": "implement"}},
                }
            }
        ],
    ],
)
def test_an_unreadable_stream_or_non_integer_exit_code_records_no_verdict(
    *, payload: object
) -> None:
    assert hook_verdict_from_events(events_payload=payload, stage="implement@1") is None


def test_a_command_carried_only_on_the_title_is_still_read() -> None:
    """Some ACP adapters omit `rawInput`; the start record's `title` carries the command."""
    start = _envelope(
        seq=1,
        node="implement",
        update={"sessionUpdate": "tool_call", "toolCallId": "exec-t", "title": _AMEND_COMMAND},
    )
    done = _tool_done(seq=2, call_id="exec-t", output=_HOOK_REFUSAL_OUTPUT, exit_code=1)
    assert hook_verdict_from_events(events_payload=[start, done], stage="implement") == HookVerdict(
        node="implement", exit_code=1, failed_targets=("check-types",)
    )


@pytest.mark.parametrize(
    ("command", "output", "exit_code"),
    [
        ("mise exec -- git push -u origin HEAD", _HOOK_REFUSAL_OUTPUT, 1),
        (_AMEND_COMMAND, _INSPECT_OUTPUT, 1),
        (_AMEND_COMMAND, _HOOK_REFUSAL_OUTPUT, True),
    ],
)
def test_a_non_commit_a_hookless_output_or_a_boolean_exit_code_is_no_verdict(
    *, command: str, output: str, exit_code: object
) -> None:
    done = _envelope(
        seq=2,
        node="implement",
        update={
            "sessionUpdate": "tool_call_update",
            "toolCallId": "exec-n",
            "rawOutput": {"formatted_output": output, "exit_code": exit_code},
        },
    )
    stream = [_tool_call(seq=1, call_id="exec-n", command=command), done]
    assert hook_verdict_from_events(events_payload=stream, stage="implement") is None


def test_records_that_are_not_tool_calls_are_skipped_and_the_verdict_still_reads() -> None:
    """Non-mapping rows, updates with no call id, and chat chunks sit between the records."""
    chunk = _envelope(
        seq=0,
        node="implement",
        update={"sessionUpdate": "agent_message_chunk", "content": {"type": "text", "text": "hi"}},
    )
    no_id = _envelope(seq=0, node="implement", update={"sessionUpdate": "tool_call_update"})
    stream = ["not a dict", chunk, no_id, *_measured_stream()]
    assert hook_verdict_from_events(events_payload=stream, stage="implement") == HookVerdict(
        node="implement", exit_code=1, failed_targets=("check-types",)
    )


def test_a_failed_targets_block_that_ends_the_output_is_read_to_its_last_line() -> None:
    output = "│ lefthook v1.13.6  hook: pre-commit │\nFailed targets (2):\n  - check-types\n  - check-lint"
    stream = [
        _tool_call(seq=1, call_id="exec-e", command=_AMEND_COMMAND),
        _tool_done(seq=2, call_id="exec-e", output=output, exit_code=1),
    ]
    verdict = hook_verdict_from_events(events_payload=stream, stage="implement")
    assert verdict is not None
    assert verdict.failed_targets == ("check-types", "check-lint")


def test_a_completion_without_output_text_is_no_verdict() -> None:
    done = _envelope(
        seq=2,
        node="implement",
        update={
            "sessionUpdate": "tool_call_update",
            "toolCallId": "exec-o",
            "rawOutput": {"exit_code": 1},
        },
    )
    stream = [_tool_call(seq=1, call_id="exec-o", command=_AMEND_COMMAND), done]
    assert hook_verdict_from_events(events_payload=stream, stage="implement") is None


def test_the_cause_lines_name_exit_status_and_targets_and_label_a_contradicted_agent_text() -> None:
    verdict = HookVerdict(
        node="implement", exit_code=1, failed_targets=("check-types", "check-lint")
    )
    lines = hook_verdict_cause_lines(verdict=verdict, agent_cause=_AGENT_TEXT)
    joined = "\n".join(lines)
    assert "recorded hook verdict:" in joined
    assert "exit status 1" in joined
    assert "check-types, check-lint" in joined
    assert "agent-reported" in joined
    assert (
        innermost_cause_label(verdict=verdict, agent_cause=_AGENT_TEXT)
        == "innermost cause (agent-reported)"
    )


def test_an_agent_text_that_does_not_contradict_the_record_keeps_the_plain_label() -> None:
    verdict = HookVerdict(node="implement", exit_code=1, failed_targets=("check-types",))
    cause = "LIVESPEC_IMPLEMENT_PARTIAL_PROGRESS: check-types refused the Green amend; 3 pyright errors remain"
    assert innermost_cause_label(verdict=verdict, agent_cause=cause) == "innermost cause"
    lines = hook_verdict_cause_lines(verdict=verdict, agent_cause=cause)
    assert any("recorded hook verdict:" in line for line in lines)
    assert not any("agent-reported" in line for line in lines)


def test_no_verdict_renders_nothing_and_keeps_the_plain_label() -> None:
    assert hook_verdict_cause_lines(verdict=None, agent_cause=_AGENT_TEXT) == ()
    assert innermost_cause_label(verdict=None, agent_cause=_AGENT_TEXT) == "innermost cause"
    assert (
        innermost_cause_label(
            verdict=HookVerdict(node="implement", exit_code=1, failed_targets=()), agent_cause=None
        )
        == "innermost cause"
    )


def _plan(*, tmp_path: Path) -> DispatchPlan:
    return DispatchPlan(
        repo=tmp_path,
        work_item_id=_ITEM,
        branch=f"feat/{_ITEM}",
        workflow_toml=tmp_path / "workflow.toml",
        goal_file=tmp_path / "goal.txt",
        fabro_bin="fabro",
        fabro_factory_name="petri",
        fabro_factory_server="https://gmktec.example:32276",
        fabro_factory_dev_token=None,
        janitor=None,
        janitor_checkout=tmp_path / ".janitor",
        janitor_core_checkout=tmp_path / ".janitor" / ".livespec-core",
        janitor_core_repo_url="https://github.com/thewoolleyman/livespec.git",
        janitor_core_ref="master",
        review_fix_visit_cap=3,
        merge_on_review_cap_outcome="succeeded",
    )


def _inspect_payload() -> list[object]:
    verdict_line = json.dumps(
        {"outcome": "failed", "failure_reason": _AGENT_TEXT, "definition_of_done_complete": False}
    )
    return [
        {
            "run_id": _RUN,
            "status": {"kind": "failed", "reason": "workflow_error"},
            "stages": {
                "janitor@1": {"handler": "command", "state": "succeeded", "output": ""},
                "implement@1": {
                    "handler": "agent",
                    "state": "failed",
                    "output": f"I implemented part of it.\n\n{verdict_line}\n",
                    "response": "",
                },
                "needs_human@1": {
                    "handler": "command",
                    "state": "failed",
                    "output": _TERMINAL_OUTPUT,
                },
            },
            "checkpoint": {
                "timestamp": "2026-10-24T20:03:39.149Z",
                "current_node": "needs_human",
                "git_commit_sha": "c4bfd246fdd84f46ea13e1a4100c1adb4189cd6a",
            },
            "conclusion": {
                "status": "failed",
                "failure": {
                    "reason": "workflow_error",
                    "detail": {
                        "message": f"script exited with status 1\n{_TERMINAL_OUTPUT}",
                        "category": "deterministic",
                    },
                },
            },
        }
    ]


def _terminal_outcome(*, tmp_path: Path, events: list[object]) -> DispatchOutcome:
    payload = _inspect_payload()
    outcome = fabro_run_terminal_outcome(
        outcome_type=DispatchOutcome,
        plan=_plan(tmp_path=tmp_path),
        run_id=_RUN,
        inspect=FabroInspectResult(
            command=CommandResult(exit_code=0, stdout="", stderr=""),
            payload=payload,
            status_kind=fabro_status_kind_from_payload(payload=payload),
            failure=fabro_failure_detail_from_payload(payload=payload),
            events_payload=events,
        ),
        exit_code=1,
        stderr=_TERMINAL_OUTPUT,
    )
    assert outcome is not None
    return outcome


def test_the_outcome_carries_the_verdict_in_its_own_field_beside_the_agent_text(
    *, tmp_path: Path
) -> None:
    """Assertion 2: the journal's outcome row has the verdict in a field separate from the cause."""
    outcome = _terminal_outcome(tmp_path=tmp_path, events=_measured_stream())
    assert outcome.hook_verdict == HookVerdict(
        node="implement", exit_code=1, failed_targets=("check-types",)
    )
    assert outcome.fabro_failure_cause == _AGENT_TEXT
    payload = _outcome_payload(outcome=outcome)
    assert payload["hook_verdict"] == {
        "node": "implement",
        "exit_code": 1,
        "failed_targets": ("check-types",),
    }
    assert payload["fabro_failure_cause"] == _AGENT_TEXT


def test_the_cause_comment_states_the_recorded_refusal_beside_the_agent_reported_text(
    *, tmp_path: Path
) -> None:
    """Assertions 1 and 3: the durable record names exit status and targets and labels the agent text."""
    body = needs_human_cause_body(
        outcome=_terminal_outcome(tmp_path=tmp_path, events=_measured_stream())
    )
    assert f"innermost cause (agent-reported): {_AGENT_TEXT}" in body
    assert "recorded hook verdict:" in body
    assert "exit status 1" in body
    assert "check-types" in body


def test_an_ending_with_no_recorded_refusal_omits_the_verdict_field(*, tmp_path: Path) -> None:
    outcome = _terminal_outcome(tmp_path=tmp_path, events=None)
    assert outcome.hook_verdict is None
    assert "hook_verdict" not in _outcome_payload(outcome=outcome)
    body = needs_human_cause_body(outcome=outcome)
    assert f"innermost cause: {_AGENT_TEXT}" in body
    assert "recorded hook verdict" not in body
