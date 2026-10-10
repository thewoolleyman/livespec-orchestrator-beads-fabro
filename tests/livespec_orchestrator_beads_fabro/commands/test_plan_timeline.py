"""Additional plan timeline coverage."""

from __future__ import annotations

from dataclasses import dataclass

import pytest
from livespec_orchestrator_beads_fabro._beads_client import (
    FakeBeadsClient,
    IssueDraft,
    make_beads_client,
    reset_fake_singleton,
)
from livespec_orchestrator_beads_fabro.commands.plan import (
    NextAction,
    append_handoff,
    read_timeline,
)
from livespec_orchestrator_beads_fabro.types import StoreConfig


@dataclass(frozen=True, kw_only=True)
class _Comment:
    text: str
    author: str | None = None
    created_at: str | None = None
    comment_id: str | None = None


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


def test_timeline_ignores_non_plan_comments() -> None:
    reset_fake_singleton()
    _ = _fake().create_issue(
        draft=IssueDraft(
            issue_id="bd-ib-plan",
            issue_type="epic",
            title="plan",
            description="plan",
            assignee=None,
            created_at="2026-08-11T00:00:00Z",
            metadata={"rank": "a1"},
            labels=["origin:freeform"],
        )
    )

    _fake().seed_comment(issue_id="bd-ib-plan", text="ordinary ledger note")
    append_handoff(
        config=_config(),
        epic_id="bd-ib-plan",
        body="Continue with the scoped child.",
        author="factory-test",
        now="2026-08-11T01:02:03Z",
        next_action=NextAction(
            kind="impl",
            ref="bd-ib-plan.1",
            text="Continue with the scoped child.",
            required_result={
                "repo": "repo",
                "item_status": {"item_id": "bd-ib-plan", "status": "closed"},
            },
            budget={"deadline": "2099-08-11T00:00:00Z", "max_handoffs": 3},
        ),
    )

    [entry] = read_timeline(config=_config(), epic_id="bd-ib-plan")
    assert entry.body == "Continue with the scoped child."


def test_timeline_recovers_missing_header_timestamp_from_comment_record() -> None:
    reset_fake_singleton()
    _ = _fake().create_issue(
        draft=IssueDraft(
            issue_id="bd-ib-plan",
            issue_type="epic",
            title="plan",
            description="plan",
            assignee=None,
            created_at="2026-08-11T00:00:00Z",
            metadata={"rank": "a1"},
            labels=["origin:freeform"],
        )
    )

    _fake().seed_comment(
        issue_id="bd-ib-plan",
        text="plan-handoff-entry\nauthor: peer-session\n\nMalformed but permanent.",
        author="beads-problems",
        created_at="2026-08-21T04:30:00Z",
    )
    append_handoff(
        config=_config(),
        epic_id="bd-ib-plan",
        body="Well-formed later handoff.",
        author="factory-test",
        now="2026-08-21T04:35:00Z",
        next_action=NextAction(
            kind="none",
            ref="",
            text="Nothing is recorded.",
            required_result=None,
            budget=None,
        ),
    )

    entries = read_timeline(config=_config(), epic_id="bd-ib-plan")

    assert [entry.body for entry in entries] == [
        "Malformed but permanent.",
        "Well-formed later handoff.",
    ]
    assert entries[0].created_at == "2026-08-21T04:30:00Z"
    assert entries[0].author == "peer-session"


def test_timeline_recovers_unparseable_header_timestamp_from_comment_record() -> None:
    reset_fake_singleton()
    _ = _fake().create_issue(
        draft=IssueDraft(
            issue_id="bd-ib-plan",
            issue_type="epic",
            title="plan",
            description="plan",
            assignee=None,
            created_at="2026-08-11T00:00:00Z",
            metadata={"rank": "a1"},
            labels=["origin:freeform"],
        )
    )

    _fake().seed_comment(
        issue_id="bd-ib-plan",
        text=(
            "plan-handoff-entry\n"
            "author: plan-archive\n"
            "timestamp: claude-fabro-on-hp@2026-08-17T06:44:56Z\n\n"
            "Archived after review."
        ),
        author="beads-problems",
        created_at="2026-08-17T08:37:24Z",
    )

    [entry] = read_timeline(config=_config(), epic_id="bd-ib-plan")

    assert entry.created_at == "2026-08-17T08:37:24Z"
    assert entry.author == "plan-archive"
    assert entry.body == "Archived after review."


def test_unrecoverable_timeline_parse_error_names_comment_and_expected_header(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from livespec_orchestrator_beads_fabro.commands import _plan_timeline

    def fake_read_comments(
        *,
        path: StoreConfig,
        work_item_id: str,
    ) -> tuple[_Comment, ...]:
        _ = path
        _ = work_item_id
        return (
            _Comment(
                text="plan-handoff-entry\n\nNo author line.",
                created_at=None,
                comment_id="comment-7",
            ),
        )

    monkeypatch.setattr(_plan_timeline, "read_work_item_comments", fake_read_comments)

    with pytest.raises(
        ValueError,
        match=(
            "comment-7.*expected plan timeline header "
            "`plan-handoff-entry\\|plan-scope-event`, `author: `, `timestamp: `"
        ),
    ):
        _ = _plan_timeline.read_timeline(config=_config(), epic_id="bd-ib-plan")
