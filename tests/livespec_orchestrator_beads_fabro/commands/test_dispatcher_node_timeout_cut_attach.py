"""The cut rides the outcome, journals its hook-over-limit row once, and shows in the cause.

Binds the wiring half of `SPECIFICATION/scenarios.md` Scenario 192 for work-item
``bd-ib-ptnxyg``: the needs-human cause recorded on the item names node-timeout
for a cut and names nothing for an ending that is not one, and the dispatch
journal carries the `hook-over-limit` row for a hook run still executing at the
cut. The negative arms are asserted beside the positive ones because a writer
that named a node-timeout on every needs-human ending would satisfy the positive
arm exactly as a correct one does.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import DispatchOutcome
from livespec_orchestrator_beads_fabro.commands._dispatcher_hook_over_limit import (
    HookOverLimit,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_ledger_close import (
    _outcome_payload,  # pyright: ignore[reportPrivateUsage]
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_needs_human_cause import (
    needs_human_cause_body,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_node_timeout_cut import (
    attach_node_timeout_cut,
    started_commit_run_ids,
)
from livespec_orchestrator_beads_fabro.commands._fabro_causal_stage import (
    AGENT_REQUEST,
    STAGE_FAILURE,
)
from livespec_orchestrator_beads_fabro.commands._node_timeouts import (
    WORKFLOW_DEFAULT_LAYER,
    NodeTimeouts,
)

_RUN = "commit-" + "c" * 32
_TIMED_OUT = "ACP turn timed out after 55 tool call(s) and 840 session update(s)"
_TIMEOUTS = NodeTimeouts(
    configured={"fix": 3600}, stall_seconds=7200, stall_layer=WORKFLOW_DEFAULT_LAYER
)


@dataclass(kw_only=True)
class _Journal:
    records: list[dict[str, object]] = field(default_factory=list)

    def append(self, *, record: dict[str, object]) -> None:
        self.records.append(record)


def _outcome(
    *,
    kind: str | None = STAGE_FAILURE,
    stages: tuple[str, ...] | None = ("fix",),
    cause: str | None = _TIMED_OUT,
    hook_over_limit: HookOverLimit | None = None,
) -> DispatchOutcome:
    return DispatchOutcome(
        work_item_id="bd-ib-ptnxyg",
        status="blocked",
        stage="fabro-run",
        pr_number=None,
        merge_sha=None,
        detail="fix timed out",
        fabro_run_id="01M63WAMHC1G03845AHHFD68S6",
        fabro_failure_cause=cause,
        needs_human_kind=kind,
        needs_human_stages=stages,
        hook_over_limit=hook_over_limit,
    )


def _attach(*, outcome: DispatchOutcome, text: str, journal: _Journal) -> DispatchOutcome:
    return attach_node_timeout_cut(
        outcome=outcome,
        node_timeouts=_TIMEOUTS,
        text=text,
        events_payload=None,
        journal=journal,
    )


def test_a_cut_is_carried_and_its_cause_names_node_timeout_the_node_and_the_run() -> None:
    """Scenario 192: node-timeout, the fix node, its resolved 3600 seconds, the run and state."""
    journal = _Journal()
    text = f"LIVESPEC_NODE_CUT_COMMIT_RUN: run={_RUN} state=passed"

    attached = _attach(outcome=_outcome(), text=text, journal=journal)
    body = needs_human_cause_body(outcome=attached)

    assert "node-timeout" in body
    assert "the fix node" in body
    assert "3600 seconds" in body
    assert f"commit run {_RUN}: passed when preservation began" in body
    assert journal.records == []


def test_a_hook_run_at_the_cut_journals_one_row_and_names_hook_over_limit() -> None:
    """Scenario 192: the row names the fix node, the commit operation and 3600 seconds."""
    journal = _Journal()
    text = "LIVESPEC_NODE_CUT_HOOK_RUN: operation=commit hook_elapsed_ms=295000"

    attached = _attach(outcome=_outcome(), text=text, journal=journal)

    assert journal.records == [
        {
            "work_item_id": "bd-ib-ptnxyg",
            "stage": "hook-over-limit",
            "node": "fix",
            "operation": "commit",
            "limit_seconds": 3600,
            "hook_elapsed_ms": 295000,
        }
    ]
    assert "hook-over-limit" in needs_human_cause_body(outcome=attached)


def test_an_earlier_hook_over_limit_event_is_kept_when_the_cut_saw_no_hook_run() -> None:
    """Scenario 177: the publication event already on the outcome is not displaced."""
    earlier = HookOverLimit(
        node="publish_draft", operation="push", limit_seconds=3600, hook_elapsed_ms=1
    )

    attached = _attach(
        outcome=_outcome(hook_over_limit=earlier), text="nothing", journal=_Journal()
    )

    assert attached.hook_over_limit == earlier
    assert attached.node_timeout_cut is not None


def test_an_ending_that_is_not_a_node_timeout_is_passed_through_untouched() -> None:
    """Scenario 192: no stage, an agent request, or another cause names no cut."""
    journal = _Journal()
    text = f"LIVESPEC_NODE_CUT_COMMIT_RUN: run={_RUN} state=passed"

    for outcome in (
        _outcome(kind=AGENT_REQUEST),
        _outcome(stages=None),
        _outcome(stages=()),
        _outcome(cause="the hook refused"),
        _outcome(cause=None),
    ):
        attached = _attach(outcome=outcome, text=text, journal=journal)
        assert attached is outcome
        assert "node-timeout" not in needs_human_cause_body(outcome=attached)
    assert journal.records == []


def test_the_cut_is_dropped_from_the_journal_outcome_when_absent() -> None:
    """The optional-field drop keeps every other outcome's payload shape unchanged."""
    assert "node_timeout_cut" not in _outcome_payload(outcome=_outcome())
    attached = _attach(outcome=_outcome(), text="x", journal=_Journal())
    assert "node_timeout_cut" in _outcome_payload(outcome=attached)


def _envelope(*, node: str, update: dict[str, object]) -> dict[str, object]:
    return {
        "item": {
            "subject": {"node": {"name": node}},
            "record": {"body": {"ev": {"custom": {"event": {"update": update}}}}},
        }
    }


def test_unreadable_or_foreign_records_name_no_started_run() -> None:
    """Scenario 192: only a runner `start` whose output is a run id names a started run."""
    runner = "python3 /root/.claude/plugins/livespec-commit-runner.py"
    events: list[object] = [
        "not an envelope",
        _envelope(node="fix", update={"sessionUpdate": "agent_message_chunk"}),
        _envelope(
            node="fix",
            update={"sessionUpdate": "tool_call", "toolCallId": "t1", "title": f"{runner} start"},
        ),
        _envelope(
            node="fix",
            update={
                "sessionUpdate": "tool_call_update",
                "toolCallId": "t1",
                "rawOutput": {"formatted_output": "refused: not a run id"},
            },
        ),
        _envelope(
            node="fix",
            update={"sessionUpdate": "tool_call_update", "toolCallId": "t1", "rawOutput": {}},
        ),
        _envelope(
            node="fix",
            update={
                "sessionUpdate": "tool_call_update",
                "toolCallId": "t1",
                "rawOutput": {"formatted_output": _RUN},
            },
        ),
        _envelope(
            node="fix",
            update={
                "sessionUpdate": "tool_call_update",
                "toolCallId": "t1",
                "rawOutput": {"formatted_output": _RUN},
            },
        ),
    ]

    assert started_commit_run_ids(events_payload=events, stage="fix") == (_RUN,)
