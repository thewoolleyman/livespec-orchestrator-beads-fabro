"""The unattended marker, and the prose next-action probe the resume no longer reads.

`resume_directive` moved to `_plan_next_action.py` when the typed `next_action`
metadata became the resume authority; its coverage lives in
`test_plan_next_action.py`. What stays here is the session-marker read and the
handoff self-sufficiency findings, which still probe the prose a person reads.
"""

from __future__ import annotations

from livespec_orchestrator_beads_fabro._beads_client import (
    FakeBeadsClient,
    IssueDraft,
    make_beads_client,
    reset_fake_singleton,
)
from livespec_orchestrator_beads_fabro.commands import _plan_timeline
from livespec_orchestrator_beads_fabro.commands._plan_timeline import (
    UNATTENDED_ENV_VAR,
    is_unattended_session,
)
from livespec_orchestrator_beads_fabro.commands.plan import (
    NextAction,
    PlanTimelineEntry,
    append_handoff,
    read_timeline,
    record_scope_event,
    recorded_next_actions,
)
from livespec_orchestrator_beads_fabro.types import StoreConfig

_HANDOFF_ONE_ACTION = (
    "Thread reopened after a context-threshold restart.\n"
    "\n"
    "NEXT ACTION (exactly one): implement bd-ib-idgwyk.1.\n"
)


def _config() -> StoreConfig:
    return StoreConfig(
        tenant="livespec-impl-beads",
        prefix="bd-ib",
        server_user="livespec-impl-beads",
        database="livespec-impl-beads",
        bd_path="bd",
        fake=True,
    )


def _fake() -> FakeBeadsClient:
    client = make_beads_client(config=_config())
    assert isinstance(client, FakeBeadsClient)
    return client


def _seed_epic(*, epic_id: str) -> None:
    reset_fake_singleton()
    _ = _fake().create_issue(
        draft=IssueDraft(
            issue_id=epic_id,
            issue_type="epic",
            title="plan",
            description="plan",
            assignee=None,
            created_at="2026-08-20T00:00:00Z",
            metadata={"rank": "a1"},
            labels=["origin:freeform"],
        )
    )


def _entry(*, kind: str, body: str) -> PlanTimelineEntry:
    return PlanTimelineEntry(
        kind=kind,
        body=body,
        author="unattended-plan-operation-plan",
        created_at="2026-08-20T00:00:00Z",
    )


def test_unattended_marker_is_read_from_the_session_environment() -> None:
    assert is_unattended_session(env={UNATTENDED_ENV_VAR: "1"})
    assert is_unattended_session(env={UNATTENDED_ENV_VAR: " TRUE "})
    assert is_unattended_session(env={UNATTENDED_ENV_VAR: "yes"})
    assert is_unattended_session(env={UNATTENDED_ENV_VAR: "on"})
    assert not is_unattended_session(env={UNATTENDED_ENV_VAR: "0"})
    assert not is_unattended_session(env={UNATTENDED_ENV_VAR: ""})
    assert not is_unattended_session(env={})


def test_recorded_next_actions_reads_the_marker_line() -> None:
    assert recorded_next_actions(body=_HANDOFF_ONE_ACTION) == ("implement bd-ib-idgwyk.1.",)


def test_recorded_next_actions_reads_every_marker_line() -> None:
    body = "NEXT ACTION: implement bd-ib-idgwyk.1.\n- next action: file bd-ib-idgwyk.5.\n"

    assert recorded_next_actions(body=body) == (
        "implement bd-ib-idgwyk.1.",
        "file bd-ib-idgwyk.5.",
    )


def test_recorded_next_actions_ignores_a_marker_that_names_nothing() -> None:
    assert recorded_next_actions(body="NEXT ACTION\nNEXT ACTION:   \nprose about the plan.\n") == ()


def test_handoff_timeline_verifier_accepts_a_self_sufficient_newest_handoff() -> None:
    assert hasattr(_plan_timeline, "handoff_timeline_findings")
    findings = _plan_timeline.handoff_timeline_findings(
        entries=(
            _entry(
                kind="handoff",
                body="Current state is recorded.\n\nNext action: implement bd-ib-c2sasn.",
            ),
        )
    )

    assert findings == ()


def test_handoff_timeline_verifier_rejects_heading_only_next_action_markers() -> None:
    assert hasattr(_plan_timeline, "handoff_timeline_findings")
    for body in (
        "Working state cites bd-ib-qfv9.1.\n\n== NEXT ACTION ==\nImplement it.",
        "Working state cites bd-ib-qfv9.1.\n\n== EXACTLY ONE NEXT ACTION ==\nImplement it.",
    ):
        findings = _plan_timeline.handoff_timeline_findings(
            entries=(_entry(kind="handoff", body=body),)
        )

        assert findings == ("newest handoff records 0 next actions, not exactly one",)


def test_handoff_timeline_verifier_rejects_newest_handoff_without_work_item_id() -> None:
    assert hasattr(_plan_timeline, "handoff_timeline_findings")
    findings = _plan_timeline.handoff_timeline_findings(
        entries=(
            _entry(
                kind="handoff",
                body="Current state is recorded.\n\nNext action: keep driving the plan.",
            ),
        )
    )

    assert findings == ("newest handoff names no work-item id",)


def test_handoff_timeline_verifier_rejects_empty_or_unattributed_entries() -> None:
    assert hasattr(_plan_timeline, "handoff_timeline_findings")
    findings = _plan_timeline.handoff_timeline_findings(
        entries=(
            PlanTimelineEntry(kind="scope", body="", author="", created_at="2026-08-20T00:00:00Z"),
        )
    )

    assert findings == (
        "timeline entry 1 is empty",
        "timeline entry 1 is unattributed",
        "no handoff entry on the plan timeline",
    )


def test_read_timeline_labels_each_entry_with_its_kind() -> None:
    _seed_epic(epic_id="bd-ib-plan")
    record_scope_event(
        config=_config(),
        epic_id="bd-ib-plan",
        requirements=("bd-ib-plan.1",),
        deferrals=("nothing",),
        author="unattended-plan-operation-plan",
        now="2026-08-20T00:00:00Z",
    )
    append_handoff(
        config=_config(),
        epic_id="bd-ib-plan",
        body=_HANDOFF_ONE_ACTION,
        author="unattended-plan-operation-plan",
        now="2026-08-20T00:00:01Z",
        next_action=NextAction(
            kind="impl",
            ref="bd-ib-idgwyk.1",
            text="Implement bd-ib-idgwyk.1 through the factory.",
            required_result={
                "repo": "repo",
                "item_status": {"item_id": "bd-ib-plan", "status": "closed"},
            },
            budget={"deadline": "2099-08-20T00:00:00Z", "max_handoffs": 3},
        ),
    )

    entries = read_timeline(config=_config(), epic_id="bd-ib-plan")

    assert [entry.kind for entry in entries] == ["scope", "handoff"]
