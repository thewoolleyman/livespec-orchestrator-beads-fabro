"""Additional plan timeline coverage."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

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
    current_continuation_ruling,
    plan_record_rate_warnings,
    read_timeline,
)
from livespec_orchestrator_beads_fabro.types import StoreConfig

if TYPE_CHECKING:
    from livespec_orchestrator_beads_fabro.commands._plan_timeline import PlanTimelineSkip


def _config() -> StoreConfig:
    return StoreConfig(
        tenant="livespec-impl-beads",
        prefix="bd-ib",
        server_user="livespec-impl-beads",
        database="livespec-impl-beads",
        bd_path="bd",
        fake=True,
    )


def _result_repo() -> str:
    """The repository identity a required result may name in these fixtures.

    `_config()` carries no `repo_root`, so a plan write resolves its result
    repository against the invoking checkout, whose own directory name is the
    identity the shared authoritative result reader resolves there. A
    placeholder the reader could never resolve is refused at the write
    (`bd-ib-eebjcl`), because every observation of it would be unobservable.
    """
    return Path.cwd().name


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
                "repo": _result_repo(),
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


_ONE_LINE_HAND_AUTHORED = (
    "plan-handoff-entry / author: resumed-session (livespec-overseer, primary checkout) / "
    "2026-09-06: DAEMON-ROW PORTION LANDED and the rest follows."
)
_NONE_ACTION = NextAction(
    kind="none", ref="", text="Nothing is recorded.", required_result=None, budget=None
)


def _plan_epic() -> None:
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


def _valid(*, text: str, created_at: str) -> None:
    _fake().seed_comment(
        issue_id="bd-ib-plan",
        text=f"plan-handoff-entry\nauthor: writer\ntimestamp: {created_at}\n\n{text}",
        author="beads-problems",
        created_at=created_at,
    )


def _hand_authored(*, text: str = _ONE_LINE_HAND_AUTHORED) -> None:
    _fake().seed_comment(
        issue_id="bd-ib-plan",
        text=text,
        author="beads-problems",
        created_at="2026-09-06T16:47:30Z",
    )


def _seed_malformed_between_valid_entries() -> None:
    _plan_epic()
    _valid(text="first", created_at="2026-09-06T10:00:00Z")
    _hand_authored()
    _valid(text="second", created_at="2026-09-06T18:00:00Z")


def test_a_one_line_hand_authored_comment_is_skipped_and_reported_beside_valid_entries() -> None:
    _seed_malformed_between_valid_entries()
    skips: list[PlanTimelineSkip] = []

    entries = read_timeline(config=_config(), epic_id="bd-ib-plan", on_skip=skips.append)

    assert [entry.body for entry in entries] == ["first", "second"]
    [skip] = skips
    assert skip.comment_ref == "bd-ib-plan comment #2"
    assert "missing author line" in skip.reason
    assert "bd-ib-plan comment #2" in skip.message
    assert "missing author line" in skip.message


def test_an_unreported_skip_still_surfaces_on_stderr(capsys: pytest.CaptureFixture[str]) -> None:
    _seed_malformed_between_valid_entries()

    entries = read_timeline(config=_config(), epic_id="bd-ib-plan")

    assert len(entries) == 2
    stderr = capsys.readouterr().err
    assert "bd-ib-plan comment #2" in stderr
    assert "missing author line" in stderr


def test_a_decorated_prefix_is_never_labelled_with_the_other_kind() -> None:
    _plan_epic()
    _hand_authored(
        text=(
            "plan-handoff-entry (shutdown, retired)\n"
            "author: resumed-session\n"
            "timestamp: 2026-09-06T16:47:30Z\n\n"
            "Decorated body."
        )
    )
    skips: list[PlanTimelineSkip] = []

    entries = read_timeline(config=_config(), epic_id="bd-ib-plan", on_skip=skips.append)

    assert [entry for entry in entries if entry.kind == "scope"] == []
    assert entries == ()
    [skip] = skips
    assert skip.comment_ref == "bd-ib-plan comment #1"
    assert "plan-handoff-entry" in skip.reason


def test_a_decorated_scope_prefix_is_skipped_not_read_as_a_handoff() -> None:
    _plan_epic()
    _hand_authored(
        text="plan-scope-event: ruling\nauthor: a\ntimestamp: 2026-09-06T16:47:30Z\n\nbody"
    )
    skips: list[PlanTimelineSkip] = []

    entries = read_timeline(config=_config(), epic_id="bd-ib-plan", on_skip=skips.append)

    assert entries == ()
    assert len(skips) == 1


def test_an_unparseable_header_timestamp_takes_the_comment_created_at_without_a_report() -> None:
    _plan_epic()
    _fake().seed_comment(
        issue_id="bd-ib-plan",
        text="plan-handoff-entry\nauthor: writer\ntimestamp: not-a-time\n\nbody",
        author="beads-problems",
        created_at="2026-08-17T08:37:24Z",
    )
    skips: list[PlanTimelineSkip] = []

    [entry] = read_timeline(config=_config(), epic_id="bd-ib-plan", on_skip=skips.append)

    assert entry.created_at == "2026-08-17T08:37:24Z"
    assert skips == []


def test_append_handoff_rate_warnings_and_continuation_complete_past_a_malformed_comment() -> None:
    _seed_malformed_between_valid_entries()

    refusal = append_handoff(
        config=_config(),
        epic_id="bd-ib-plan",
        body="Appended after the malformed comment.",
        author="factory-test",
        now="2026-09-07T00:00:00Z",
        next_action=_NONE_ACTION,
    )
    entries = read_timeline(config=_config(), epic_id="bd-ib-plan", on_skip=lambda _skip: None)

    assert refusal is None
    assert [entry.body for entry in entries][-1] == "Appended after the malformed comment."
    assert plan_record_rate_warnings(entries=entries) == ()
    assert (
        current_continuation_ruling(
            config=_config(), epic_id="bd-ib-plan", now="2026-09-07T00:00:00Z"
        )
        is None
    )
