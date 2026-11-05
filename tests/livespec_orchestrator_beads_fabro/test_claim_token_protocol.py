"""The claim-token guarded item-write primitive."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro import _store_claim_tokens as claim_tokens
from livespec_orchestrator_beads_fabro._beads_client import FakeBeadsClient, IssueDraft
from livespec_orchestrator_beads_fabro._store_dispatch_claim import (
    CLAIM_TOKEN_METADATA_KEY,
    change_claim,
    create_claim_token,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_policy_settings import (
    resolve_claim_tokens,
)
from livespec_orchestrator_beads_fabro.commands._drive_config_schema import config_key_by_name
from livespec_orchestrator_beads_fabro.commands._plan_epoch_tokens import TokenReading
from returns.unsafe import unsafe_perform_io

_ITEM_ID = "bd-ib-claim-token"


def _client_with_current_token() -> tuple[FakeBeadsClient, str]:
    client = FakeBeadsClient()
    _ = client.create_issue(
        draft=IssueDraft(
            issue_id=_ITEM_ID,
            issue_type="task",
            title="A dispatched slice",
            description="Implement the slice.",
            assignee="fabro",
            created_at="2026-11-05T00:00:00Z",
        )
    )
    client.update_issue(issue_id=_ITEM_ID, status="active")
    token = create_claim_token(client=client)
    client.update_issue(issue_id=_ITEM_ID, metadata={CLAIM_TOKEN_METADATA_KEY: token})
    return client, token


def _transition_reason(*, successor: str) -> str:
    return json.dumps(
        {
            "kind": "claim-token-transition",
            "writer": "crashed-writer",
            "intent": "old-intent",
            "successor": successor,
            "closed_at": "2026-11-05T00:00:00+00:00",
        },
        separators=(",", ":"),
        sort_keys=True,
    )


def test_enabled_winner_names_a_fresh_successor_in_the_same_item_write() -> None:
    client, old_token = _client_with_current_token()

    outcome = change_claim(
        client=client,
        work_item_id=_ITEM_ID,
        writer="admission",
        intent="move-ready-to-active",
        claim_tokens=True,
        status="blocked",
        metadata={"writer_note": "admitted"},
    )

    assert outcome.outcome == "applied"
    assert outcome.successor_token_id is not None
    item = client.show_issue(issue_id=_ITEM_ID)
    assert item["status"] == "blocked"
    assert item["metadata"]["writer_note"] == "admitted"
    assert item["metadata"][CLAIM_TOKEN_METADATA_KEY] == outcome.successor_token_id
    assert client.show_issue(issue_id=old_token)["close_reason"] is not None
    successor = client.show_issue(issue_id=outcome.successor_token_id)
    assert "claim-token" in successor["labels"]
    assert all(record["id"] != outcome.successor_token_id for record in client.list_issues())
    assert client.children(parent_id=_ITEM_ID) == []


def test_loser_and_unobservable_writer_leave_the_item_untouched_and_discard_successors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, token = _client_with_current_token()
    original_close = client.close_issue_without_verdict

    def _lose(*, issue_id: str, reason: str) -> None:
        if issue_id == token:
            original_close(issue_id=issue_id, reason="other writer won")
        original_close(issue_id=issue_id, reason=reason)

    monkeypatch.setattr(client, "close_issue_without_verdict", _lose)
    loser = change_claim(
        client=client,
        work_item_id=_ITEM_ID,
        writer="recovery",
        intent="release",
        claim_tokens=True,
        status="ready",
    )

    assert loser.outcome == "claim-changed"
    assert client.show_issue(issue_id=_ITEM_ID)["status"] == "active"
    assert all(
        client.show_issue(issue_id=token_id)["status"] == "closed"
        for token_id in client.no_history_issue_ids()
        if token_id != token
    )


def test_unreadable_close_reason_and_expired_lease_write_nothing() -> None:
    client, token = _client_with_current_token()
    original_show = client.show_issue

    def _unreadable(*, issue_id: str) -> dict[str, object]:
        record = original_show(issue_id=issue_id)
        if issue_id == token and record["status"] == "closed":
            record["close_reason"] = None
        return record

    client.show_issue = _unreadable
    unreadable = change_claim(
        client=client,
        work_item_id=_ITEM_ID,
        writer="valve",
        intent="move",
        claim_tokens=True,
        status="ready",
    )
    assert unreadable.outcome == "claim-unobservable"
    assert original_show(issue_id=_ITEM_ID)["status"] == "active"


def test_expired_lease_leaves_the_successor_open() -> None:
    client, _ = _client_with_current_token()
    readings = iter((0.0, 121.0))

    outcome = change_claim(
        client=client,
        work_item_id=_ITEM_ID,
        writer="terminal",
        intent="complete",
        claim_tokens=True,
        status="ready",
        clock=lambda: next(readings),
    )

    assert outcome.outcome == "claim-lease-expired"
    assert outcome.successor_token_id is not None
    assert client.show_issue(issue_id=_ITEM_ID)["status"] == "active"
    assert client.show_issue(issue_id=outcome.successor_token_id)["status"] != "closed"


def test_closed_unapplied_transition_waits_then_takes_over_and_stands_down_if_it_lands(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, old_token = _client_with_current_token()
    stranded_successor = create_claim_token(client=client)
    client.close_issue(issue_id=old_token, reason=_transition_reason(successor=stranded_successor))
    observations: dict[tuple[str, str, str], float] = {}
    now = [0.0]

    pending = change_claim(
        client=client,
        work_item_id=_ITEM_ID,
        writer="recovery",
        intent="release",
        claim_tokens=True,
        status="ready",
        clock=lambda: now[0],
        transition_observations=observations,
    )
    assert pending.outcome == "claim-transition-pending"

    original_close = client.close_issue_without_verdict

    def _land_original(*, issue_id: str, reason: str) -> None:
        original_close(issue_id=issue_id, reason=reason)
        if issue_id == stranded_successor:
            client.update_issue(
                issue_id=_ITEM_ID,
                metadata={CLAIM_TOKEN_METADATA_KEY: stranded_successor},
            )

    monkeypatch.setattr(client, "close_issue_without_verdict", _land_original)
    now[0] = 200.0
    takeover = change_claim(
        client=client,
        work_item_id=_ITEM_ID,
        writer="recovery",
        intent="release",
        claim_tokens=True,
        status="ready",
        clock=lambda: now[0],
        transition_observations=observations,
    )

    assert takeover.outcome == "claim-changed"
    assert client.show_issue(issue_id=_ITEM_ID)["metadata"][CLAIM_TOKEN_METADATA_KEY] == (
        stranded_successor
    )


def test_enabled_protocol_refuses_an_item_with_no_current_token() -> None:
    client, token = _client_with_current_token()
    client.update_issue(issue_id=_ITEM_ID, metadata={})

    outcome = change_claim(
        client=client,
        work_item_id=_ITEM_ID,
        writer="admission",
        intent="admit",
        claim_tokens=True,
        status="ready",
    )

    assert outcome.outcome == "claim-token-missing"
    assert client.show_issue(issue_id=_ITEM_ID)["status"] == "active"
    assert client.no_history_issue_ids() == (token,)


def test_transition_takeover_applies_after_wait_when_the_original_write_never_lands() -> None:
    client, old_token = _client_with_current_token()
    stranded_successor = create_claim_token(client=client)
    client.close_issue(issue_id=old_token, reason=_transition_reason(successor=stranded_successor))
    observations: dict[tuple[str, str, str], float] = {}
    now = [0.0]

    assert (
        change_claim(
            client=client,
            work_item_id=_ITEM_ID,
            writer="recovery",
            intent="release",
            claim_tokens=True,
            status="ready",
            clock=lambda: now[0],
            transition_observations=observations,
        ).outcome
        == "claim-transition-pending"
    )
    now[0] = 181.0
    outcome = change_claim(
        client=client,
        work_item_id=_ITEM_ID,
        writer="recovery",
        intent="release",
        claim_tokens=True,
        status="ready",
        clock=lambda: now[0],
        transition_observations=observations,
    )

    assert outcome.outcome == "applied"
    assert client.show_issue(issue_id=_ITEM_ID)["status"] == "ready"


def test_transition_takeover_stands_down_when_the_item_names_the_stranded_successor(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, old_token = _client_with_current_token()
    stranded_successor = create_claim_token(client=client)
    client.close_issue(issue_id=old_token, reason=_transition_reason(successor=stranded_successor))
    original_show = client.show_issue
    item_reads = [0]

    def _name_successor_after_first_read(*, issue_id: str) -> dict[str, object]:
        if issue_id == _ITEM_ID:
            item_reads[0] += 1
            if item_reads[0] == 2:
                client.update_issue(
                    issue_id=_ITEM_ID,
                    metadata={CLAIM_TOKEN_METADATA_KEY: stranded_successor},
                )
        return original_show(issue_id=issue_id)

    monkeypatch.setattr(client, "show_issue", _name_successor_after_first_read)

    outcome = change_claim(
        client=client,
        work_item_id=_ITEM_ID,
        writer="recovery",
        intent="release",
        claim_tokens=True,
        clock=lambda: 181.0,
        transition_observations={(_ITEM_ID, old_token, stranded_successor): 0.0},
    )

    assert outcome.outcome == "claim-changed"


def test_transition_takeover_stands_down_when_the_close_reason_changes_on_reread(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, old_token = _client_with_current_token()
    stranded_successor = create_claim_token(client=client)
    client.close_issue(issue_id=old_token, reason=_transition_reason(successor=stranded_successor))
    observations: dict[tuple[str, str, str], float] = {}
    now = [0.0]
    _ = change_claim(
        client=client,
        work_item_id=_ITEM_ID,
        writer="recovery",
        intent="release",
        claim_tokens=True,
        clock=lambda: now[0],
        transition_observations=observations,
    )
    original_reading = claim_tokens.token_reading
    reads = [0]

    def _changed_on_reread(*, client: FakeBeadsClient, token_id: str) -> TokenReading:
        reads[0] += 1
        if reads[0] == 2:
            return TokenReading(present=True, closed=True, close_reason="changed")
        return original_reading(client=client, token_id=token_id)

    monkeypatch.setattr(claim_tokens, "token_reading", _changed_on_reread)
    now[0] = 181.0
    outcome = change_claim(
        client=client,
        work_item_id=_ITEM_ID,
        writer="recovery",
        intent="release",
        claim_tokens=True,
        clock=lambda: now[0],
        transition_observations=observations,
    )

    assert outcome.outcome == "claim-changed"


@pytest.mark.parametrize("reason", [("not-json",), ("[]",), ('{"kind":"other"}',)])
def test_invalid_transition_reason_is_unobservable(reason: tuple[str]) -> None:
    client, old_token = _client_with_current_token()
    client.close_issue(issue_id=old_token, reason=reason[0])

    outcome = change_claim(
        client=client,
        work_item_id=_ITEM_ID,
        writer="recovery",
        intent="release",
        claim_tokens=True,
    )

    assert outcome.outcome == "claim-unobservable"


def test_claim_tokens_is_committed_only_boolean_with_a_false_default(tmp_path: Path) -> None:
    configured = tmp_path / ".livespec.jsonc"
    _ = configured.write_text(
        '{"livespec-orchestrator-beads-fabro":{"dispatcher":{"claim_tokens":true}}}',
        encoding="utf-8",
    )

    assert unsafe_perform_io(resolve_claim_tokens(cwd=tmp_path).unwrap()) is True
    assert unsafe_perform_io(resolve_claim_tokens(cwd=tmp_path / "absent").unwrap()) is False
    assert config_key_by_name(key="claim_tokens") is None
