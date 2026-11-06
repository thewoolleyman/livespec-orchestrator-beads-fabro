"""The sanctioned claim-token migration pass and the post-cutover refusal.

Scenario 263 of `SPECIFICATION/scenarios.md` states both halves: "An
interrupted migration can be run again" and "After cutover, an item with no
token is refused, not written blind". The cases here drive the pass against
the in-memory tenant, whose close is conditional and whose no-history records
are omitted from the listing exactly as the server's are.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro._beads_client import (
    BeadsRecord,
    FakeBeadsClient,
    IssueDraft,
    make_beads_client,
)
from livespec_orchestrator_beads_fabro._store_claim_token_migration import (
    claim_token_named_by,
    migrate_claim_tokens,
    read_work_item_ids_naming_no_claim_token,
)
from livespec_orchestrator_beads_fabro._store_dispatch_claim import (
    CLAIM_TOKEN_METADATA_KEY,
    change_claim,
    create_claim_token,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_policy_settings import (
    resolve_claim_tokens,
)
from livespec_orchestrator_beads_fabro.errors import BeadsCommandError
from livespec_orchestrator_beads_fabro.types import StoreConfig
from returns.unsafe import unsafe_perform_io


def _config() -> StoreConfig:
    return StoreConfig(
        tenant="livespec-impl-beads",
        prefix="livespec-impl-beads",
        server_user="livespec-impl-beads",
        database="livespec-impl-beads",
        bd_path="bd",
        fake=True,
    )


def _tenant() -> FakeBeadsClient:
    client = make_beads_client(config=_config())
    assert isinstance(client, FakeBeadsClient)
    return client


def _seed(
    client: FakeBeadsClient,
    *,
    item_id: str,
    status: str = "ready",
    token: str | None = None,
) -> None:
    metadata: dict[str, object] = {"rank": "a1"}
    if token is not None:
        metadata[CLAIM_TOKEN_METADATA_KEY] = token
    _ = client.create_issue(
        draft=IssueDraft(
            issue_id=item_id,
            issue_type="task",
            title=f"{item_id} title",
            description="A work item.",
            assignee=None,
            created_at="2026-11-05T00:00:00Z",
            metadata=metadata,
        )
    )
    client.update_issue(issue_id=item_id, status=status)


def _named(client: FakeBeadsClient, *, item_id: str) -> str | None:
    return client.show_issue(issue_id=item_id)["metadata"].get(CLAIM_TOKEN_METADATA_KEY)


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


def _seed_one_item_per_token_standing(client: FakeBeadsClient) -> None:
    """Five items: naming none, a closed token, a discarded token, an open token; one closed."""
    closed_token = create_claim_token(client=client)
    client.close_issue(
        issue_id=closed_token,
        reason=_transition_reason(successor=create_claim_token(client=client)),
    )
    discarded_token = create_claim_token(client=client)
    client.close_issue(
        issue_id=discarded_token,
        reason='{"kind":"claim-token-discard","writer":"loser"}',
    )
    _seed(client, item_id="bd-a-none", status="backlog")
    _seed(client, item_id="bd-b-closed-token", status="active", token=closed_token)
    _seed(client, item_id="bd-c-discarded-token", status="blocked", token=discarded_token)
    _seed(client, item_id="bd-d-open-token", token=create_claim_token(client=client))
    _seed(client, item_id="bd-e-closed-item", status="closed")


def test_pass_names_a_fresh_open_token_on_every_non_closed_item_naming_no_open_token() -> None:
    client = _tenant()
    _seed_one_item_per_token_standing(client)
    untouched = {
        item_id: client.show_issue(issue_id=item_id)
        for item_id in ("bd-d-open-token", "bd-e-closed-item")
    }
    tokens_before = set(client.no_history_issue_ids())

    report = migrate_claim_tokens(client=client, apply=True)

    migrated = ("bd-a-none", "bd-b-closed-token", "bd-c-discarded-token")
    assert tuple(item_id for item_id, _ in report.named) == migrated
    assert report.unchanged == ("bd-d-open-token",)
    assert (report.unnamed, report.held) == ((), ())
    assert (report.applied, report.complete) == (True, True)
    fresh = [_named(client, item_id=item_id) for item_id in migrated]
    assert fresh == [token_id for _, token_id in report.named]
    assert len(set(fresh)) == len(migrated)
    assert set(fresh) == set(client.no_history_issue_ids()) - tokens_before
    for token_id in fresh:
        assert token_id is not None
        token = client.show_issue(issue_id=token_id)
        assert token["status"] != "closed"
        assert "claim-token" in token["labels"]
    for item_id in migrated:
        assert client.show_issue(issue_id=item_id)["metadata"]["rank"] == "a1"
    for item_id, before in untouched.items():
        assert client.show_issue(issue_id=item_id) == before


def test_interrupted_pass_run_again_completes_only_the_remaining_items(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = _tenant()
    item_ids = ("bd-1", "bd-2", "bd-3", "bd-4")
    for item_id in item_ids:
        _seed(client, item_id=item_id)
    original_update = client.update_issue

    def _stop_at_the_third_item(**kwargs: object) -> None:
        if kwargs["issue_id"] == "bd-3":
            raise KeyboardInterrupt
        original_update(**kwargs)

    with monkeypatch.context() as interrupted:
        interrupted.setattr(client, "update_issue", _stop_at_the_third_item)
        with pytest.raises(KeyboardInterrupt):
            _ = migrate_claim_tokens(client=client, apply=True)
    after_interrupt = {item_id: client.show_issue(issue_id=item_id) for item_id in item_ids}
    assert [_named(client, item_id=item_id) is not None for item_id in item_ids] == [
        True,
        True,
        False,
        False,
    ]

    second = migrate_claim_tokens(client=client, apply=True)

    assert second.unchanged == ("bd-1", "bd-2")
    assert tuple(item_id for item_id, _ in second.named) == ("bd-3", "bd-4")
    assert second.complete is True
    for item_id in ("bd-1", "bd-2"):
        assert client.show_issue(issue_id=item_id) == after_interrupt[item_id]
    tokens_after_second = client.no_history_issue_ids()

    third = migrate_claim_tokens(client=client, apply=True)

    assert third.named == ()
    assert third.unchanged == item_ids
    assert third.complete is True
    assert client.no_history_issue_ids() == tokens_after_second


def test_survey_writes_nothing_and_reports_the_items_naming_no_open_token() -> None:
    client = _tenant()
    open_token = create_claim_token(client=client)
    _seed(client, item_id="bd-unnamed")
    _seed(client, item_id="bd-named", token=open_token)
    before = {
        item_id: client.show_issue(issue_id=item_id) for item_id in ("bd-unnamed", "bd-named")
    }

    report = migrate_claim_tokens(client=client, apply=False)

    assert report.applied is False
    assert report.unnamed == ("bd-unnamed",)
    assert report.unchanged == ("bd-named",)
    assert report.named == ()
    assert report.complete is False
    assert client.no_history_issue_ids() == (open_token,)
    for item_id, record in before.items():
        assert client.show_issue(issue_id=item_id) == record


def test_item_whose_named_token_cannot_be_read_is_held_and_never_renamed() -> None:
    client = _tenant()
    _seed(client, item_id="bd-ghost", token="fake-wisp-absent")  # noqa: S106 - a token id

    report = migrate_claim_tokens(client=client, apply=True)

    assert report.held == (("bd-ghost", "claim-token-unobservable"),)
    assert report.named == ()
    assert report.complete is False
    assert _named(client, item_id="bd-ghost") == "fake-wisp-absent"
    assert client.no_history_issue_ids() == ()


def test_failed_item_write_is_held_and_the_pass_settles_the_other_items(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = _tenant()
    _seed(client, item_id="bd-fails")
    _seed(client, item_id="bd-lands")
    original_update = client.update_issue

    def _refuse_one_item(**kwargs: object) -> None:
        if kwargs["issue_id"] == "bd-fails":
            raise BeadsCommandError(command="bd update bd-fails", exit_code=1, stderr="boom")
        original_update(**kwargs)

    monkeypatch.setattr(client, "update_issue", _refuse_one_item)

    report = migrate_claim_tokens(client=client, apply=True)

    assert [item_id for item_id, _ in report.held] == ["bd-fails"]
    assert report.held[0][1].startswith("write-failed: ")
    assert "boom" in report.held[0][1]
    assert [item_id for item_id, _ in report.named] == ["bd-lands"]
    assert report.complete is False
    assert _named(client, item_id="bd-fails") is None
    assert _named(client, item_id="bd-lands") == report.named[0][1]


def test_item_write_that_does_not_read_back_is_held_as_unconfirmed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = _tenant()
    _seed(client, item_id="bd-lost")
    original_update = client.update_issue

    def _lose_the_item_write(**kwargs: object) -> None:
        if kwargs["issue_id"] != "bd-lost":
            original_update(**kwargs)

    monkeypatch.setattr(client, "update_issue", _lose_the_item_write)

    report = migrate_claim_tokens(client=client, apply=True)

    assert report.held == (("bd-lost", "write-unconfirmed"),)
    assert report.named == ()
    assert _named(client, item_id="bd-lost") is None


def test_item_that_names_an_open_token_by_the_time_it_is_re_read_is_left_unchanged(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = _tenant()
    _seed(client, item_id="bd-moved")
    stale_listing = client.list_issues()
    open_token = create_claim_token(client=client)
    client.update_issue(
        issue_id="bd-moved",
        metadata={"rank": "a1", CLAIM_TOKEN_METADATA_KEY: open_token},
        names_claim_token=True,
    )
    monkeypatch.setattr(client, "list_issues", lambda: stale_listing)

    report = migrate_claim_tokens(client=client, apply=True)

    assert report.held == (("bd-moved", "changed-since-listing: names-open-token"),)
    assert report.named == ()
    assert _named(client, item_id="bd-moved") == open_token
    assert client.no_history_issue_ids() == (open_token,)


def test_census_reports_every_non_closed_item_naming_no_token_and_nothing_else(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = _tenant()
    closed_token = create_claim_token(client=client)
    client.close_issue(issue_id=closed_token, reason="superseded")
    _seed(client, item_id="bd-z-unnamed", status="active")
    _seed(client, item_id="bd-a-unnamed", status="backlog")
    _seed(client, item_id="bd-named-open", token=create_claim_token(client=client))
    _seed(client, item_id="bd-named-closed", token=closed_token)
    _seed(client, item_id="bd-closed-item", status="closed")

    assert read_work_item_ids_naming_no_claim_token(path=_config()) == (
        "bd-a-unnamed",
        "bd-z-unnamed",
    )

    listing = client.list_issues()
    monkeypatch.setattr(client, "list_issues", lambda: [{"status": "ready"}, *listing])

    assert read_work_item_ids_naming_no_claim_token(path=_config()) == (
        "bd-a-unnamed",
        "bd-z-unnamed",
    )
    assert migrate_claim_tokens(client=client, apply=False).unnamed == (
        "bd-a-unnamed",
        "bd-named-closed",
        "bd-z-unnamed",
    )


@pytest.mark.parametrize(
    "metadata",
    [
        None,
        {},
        {CLAIM_TOKEN_METADATA_KEY: ""},
        {CLAIM_TOKEN_METADATA_KEY: "   "},
        {CLAIM_TOKEN_METADATA_KEY: 7},
        {CLAIM_TOKEN_METADATA_KEY: "fake-wisp-1"},
        {CLAIM_TOKEN_METADATA_KEY: " fake-wisp-1 "},
    ],
)
def test_census_reports_an_item_exactly_when_the_writer_protocol_refuses_it(
    metadata: dict[str, object] | None,
) -> None:
    client = _tenant()
    live_token = create_claim_token(client=client)
    assert live_token == "fake-wisp-1"
    _seed(client, item_id="bd-item")
    record: BeadsRecord = client.show_issue(issue_id="bd-item")
    record["metadata"] = metadata
    client.update_issue(
        issue_id="bd-item",
        metadata={} if metadata is None else metadata,
        names_claim_token=True,
    )

    refused = (
        change_claim(
            client=client,
            work_item_id="bd-item",
            writer="valve",
            intent="move",
            claim_tokens=True,
            status="blocked",
        ).outcome
        == "claim-token-missing"
    )

    assert (claim_token_named_by(record=record) is None) is refused


def test_after_cutover_a_writer_refuses_an_unnamed_item_until_the_pass_names_a_token(
    tmp_path: Path,
) -> None:
    _ = (tmp_path / ".livespec.jsonc").write_text(
        '{"livespec-orchestrator-beads-fabro":{"dispatcher":{"claim_tokens":true}}}',
        encoding="utf-8",
    )
    committed = unsafe_perform_io(resolve_claim_tokens(cwd=tmp_path).unwrap())
    assert committed is True
    client = _tenant()
    _seed(client, item_id="bd-item", status="ready")
    before = client.show_issue(issue_id="bd-item")

    refused = change_claim(
        client=client,
        work_item_id="bd-item",
        writer="admission",
        intent="admit",
        claim_tokens=committed,
        status="active",
        assignee="fabro",
    )

    assert refused.outcome == "claim-token-missing"
    assert refused.successor_token_id is None
    assert client.show_issue(issue_id="bd-item") == before
    assert client.no_history_issue_ids() == ()

    assert migrate_claim_tokens(client=client, apply=True).complete is True
    first_token = _named(client, item_id="bd-item")
    applied = change_claim(
        client=client,
        work_item_id="bd-item",
        writer="admission",
        intent="admit",
        claim_tokens=committed,
        status="active",
        assignee="fabro",
    )

    assert first_token is not None
    assert applied.outcome == "applied"
    assert client.show_issue(issue_id="bd-item")["status"] == "active"
    assert client.show_issue(issue_id=first_token)["status"] == "closed"
    assert _named(client, item_id="bd-item") == applied.successor_token_id


def _chain_ending_in_a_discarded_token(client: FakeBeadsClient) -> str:
    """A takeover stood down: the item names a closed token whose successor was discarded."""
    named = create_claim_token(client=client)
    discarded = create_claim_token(client=client)
    _seed(client, item_id="bd-item", status="active", token=named)
    client.close_issue(issue_id=named, reason=_transition_reason(successor=discarded))
    client.close_issue(issue_id=discarded, reason='{"kind":"claim-token-discard","writer":"w"}')
    return discarded


def test_pass_recovers_an_item_whose_token_chain_ends_in_a_closed_token() -> None:
    """The pass repairs a chain whose terminal closed token has no successor."""
    client = _tenant()
    taken_over = _chain_ending_in_a_discarded_token(client)
    named = _named(client, item_id="bd-item")
    assert named is not None

    def _release() -> str:
        return change_claim(
            client=client,
            work_item_id="bd-item",
            writer="recovery",
            intent="release",
            claim_tokens=True,
            status="ready",
            clock=lambda: 181.0,
            transition_observations={("bd-item", named, taken_over): 0.0},
        ).outcome

    refused = _release()
    surveyed = migrate_claim_tokens(client=client, apply=False)
    repaired = migrate_claim_tokens(client=client, apply=True)
    applied = _release()

    assert refused == "claim-unobservable"
    assert surveyed.unnamed == ("bd-item",)
    assert [item_id for item_id, _token in repaired.named] == ["bd-item"]
    assert repaired.complete is True
    assert applied == "applied"
    assert client.show_issue(issue_id="bd-item")["status"] == "ready"
