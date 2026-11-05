"""Incident genesis publishes one first root through the claim-token conditional close."""

# EXPEDITED_INCIDENT_RESPONSE flag: bd-ib-dzbwaq
from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from livespec_orchestrator_beads_fabro._beads_client import FakeBeadsClient, IssueDraft
from livespec_orchestrator_beads_fabro._incident_authority_payload import (
    GENESIS_MARKER,
    TOKEN_TITLE,
    TRANSITION_MARKER,
    decode_attempt,
)
from livespec_orchestrator_beads_fabro._incident_genesis import (
    GenesisReceipt,
    GenesisRequest,
    claim_successor,
    decode_genesis_fence,
    decode_genesis_request,
    genesis_fence,
    genesis_fence_reason,
    request_digest,
)
from livespec_orchestrator_beads_fabro._store_dispatch_claim import (
    CLAIM_TOKEN_METADATA_KEY,
    create_claim_token,
)
from livespec_orchestrator_beads_fabro.commands import incident_authority as command
from livespec_orchestrator_beads_fabro.errors import BeadsCommandError
from livespec_orchestrator_beads_fabro.incident_authority import (
    AuthorityRefusal,
    IncidentReading,
    commit_incident_transition,
    publish_incident_genesis,
    read_incident_authority,
)

REPOSITORY = "owner/repository"
ITEM = "test-incident"
REF = "refs/heads/incident/test-incident-attempt-1"
PRINCIPAL = "operator:alice"
UNREADABLE_ROOT = "fake-wisp-404"
OTHER_ROOT = "other"
SOME_ROOT = "fake-wisp-1"
BLANK_ROOT = "r"


def _json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _reserved(**changes: Any) -> dict[str, Any]:
    return (
        dict(state="branch-reserved", target_ref=REF, input_parent="a" * 40, staged_tree="c" * 40)
        | changes
    )


def _attempt(**changes: Any) -> dict[str, Any]:
    return (
        dict(
            repository=REPOSITORY,
            item_id=ITEM,
            attempt_id="attempt-1",
            phase="repair",
            operation_id="operation-1",
            generation=1,
            owner=PRINCIPAL,
            base="a" * 40,
            head="b" * 40,
            pr_number=0,
            landed_commits=[],
            landed_trees=[],
            original_paths=["app.py"],
            deferred_work=["normal-factory-proof"],
            repayment_required=True,
            carrier=_reserved(),
        )
        | changes
    )


def _query(attempt: dict[str, Any]) -> dict[str, object]:
    return {k: attempt[k] for k in ("attempt_id", "phase", "operation_id", "generation", "owner")}


def _request_text(*, claim: str, principal: str = PRINCIPAL, **changes: Any) -> str:
    return _json(
        dict(schema=1, principal=principal, expected_claim=claim, attempt=_attempt(**changes))
    )


def _request(*, claim: str, principal: str = PRINCIPAL, **changes: Any) -> GenesisRequest:
    operation = changes.get("operation_id", "operation-1")
    request = decode_genesis_request(
        text=_request_text(claim=claim, principal=principal, **changes),
        repository=REPOSITORY,
        item_id=ITEM,
        operation_id=operation,
    )
    assert request is not None
    return request


def _ledger(
    *, status: str = "ready", assignee: str | None = None, with_token: bool = True
) -> tuple[FakeBeadsClient, str]:
    client = FakeBeadsClient()
    client.create_issue(
        draft=IssueDraft(
            issue_id=ITEM,
            issue_type="bug",
            title="incident",
            description="behavior",
            assignee=assignee,
            created_at="2026-11-05T00:00:00Z",
        )
    )
    client.update_issue(issue_id=ITEM, status=status, metadata={"rank": "a0"})
    if not with_token:
        return client, "absent-token"
    token = create_claim_token(client=client)
    client.update_issue(issue_id=ITEM, metadata={"rank": "a0", CLAIM_TOKEN_METADATA_KEY: token})
    return client, token


def _publish(
    client: FakeBeadsClient, request: GenesisRequest, clock: Callable[[], float] | None = None
) -> GenesisReceipt | AuthorityRefusal:
    if clock is None:
        return publish_incident_genesis(client=client, request=request, claim_tokens=True)
    return publish_incident_genesis(client=client, request=request, claim_tokens=True, clock=clock)


def _read(client: FakeBeadsClient, **changes: Any) -> IncidentReading | AuthorityRefusal:
    return read_incident_authority(
        client=client, repository=REPOSITORY, item_id=ITEM, query=_query(_attempt(**changes))
    )


def _code(result: object) -> str:
    assert isinstance(result, AuthorityRefusal)
    return result.code


def test_without_the_committed_cutover_genesis_refuses_by_name_and_writes_nothing() -> None:
    client, token = _ledger()
    request = _request(claim=token)
    result = publish_incident_genesis(client=client, request=request, claim_tokens=False)
    assert _code(result) == "incident-genesis-capability-unavailable"
    assert request_digest(request=request) in result.detail
    assert client.list_comments(issue_id=ITEM) == []
    assert client.show_issue(issue_id=token)["status"] == "backlog"
    assert len(client.no_history_issue_ids()) == 1


def test_genesis_wins_the_current_claim_token_and_publishes_one_verified_root() -> None:
    client, token = _ledger()
    request = _request(claim=token)
    receipt = _publish(client, request)
    assert isinstance(receipt, GenesisReceipt)
    assert (receipt.claim_token_id, receipt.recovered) == (token, False)
    assert receipt.request_digest == request_digest(request=request)
    assert receipt.committed_token_id == receipt.root_token_id
    assert receipt.attempt == request.attempt
    closed = client.show_issue(issue_id=token)
    fence = decode_genesis_fence(reason=closed["close_reason"])
    assert fence is not None and closed["status"] == "closed"
    assert (fence.root_token_id, fence.successor, fence.expected_claim) == (
        receipt.root_token_id,
        receipt.successor_claim_token_id,
        token,
    )
    assert claim_successor(reason=closed["close_reason"]) == receipt.successor_claim_token_id
    item = client.show_issue(issue_id=ITEM)
    assert item["metadata"] == {"rank": "a0", CLAIM_TOKEN_METADATA_KEY: fence.successor}
    assert item["status"] == "ready"
    assert "claim-token" in client.show_issue(issue_id=fence.successor)["labels"]
    [comment] = client.list_comments(issue_id=ITEM)
    assert comment["text"] == GENESIS_MARKER + _json(
        dict(
            schema=1,
            repository=REPOSITORY,
            item_id=ITEM,
            root_token_id=receipt.root_token_id,
            claim_token_id=token,
        )
    )
    reading = _read(client)
    assert isinstance(reading, IncidentReading)
    assert (reading.is_current, reading.committed_token_id, reading.current_token_id) == (
        True,
        receipt.root_token_id,
        receipt.current_token_id,
    )
    assert [record["id"] for record in client.list_issues()] == [ITEM]


def test_an_exact_retry_recovers_the_original_root_without_another_token() -> None:
    client, token = _ledger()
    first = _publish(client, _request(claim=token))
    assert isinstance(first, GenesisReceipt)
    minted = client.no_history_issue_ids()
    again = _publish(client, _request(claim=token))
    assert isinstance(again, GenesisReceipt)
    assert again.recovered is True
    assert (again.root_token_id, again.claim_token_id, again.successor_claim_token_id) == (
        first.root_token_id,
        first.claim_token_id,
        first.successor_claim_token_id,
    )
    assert client.no_history_issue_ids() == minted
    assert len(client.list_comments(issue_id=ITEM)) == 1


@pytest.mark.parametrize(
    ("changes", "code"),
    [
        ({"principal": "operator:bob"}, "incident-operation-conflict"),
        ({"base": "d" * 40}, "incident-operation-conflict"),
        ({"operation_id": "operation-2"}, "incident-genesis-root-exists"),
    ],
)
def test_a_published_root_refuses_a_changed_request_or_another_operation(
    changes: dict[str, Any], code: str
) -> None:
    client, token = _ledger()
    assert isinstance(_publish(client, _request(claim=token)), GenesisReceipt)
    minted = client.no_history_issue_ids()
    assert _code(_publish(client, _request(claim=token, **changes))) == code
    assert client.no_history_issue_ids() == minted


def test_an_unfenced_legacy_root_is_an_existing_root_not_a_recoverable_operation() -> None:
    client, token = _ledger()
    root = client.create_no_history_issue(title=TOKEN_TITLE, description="authority")
    current = client.create_no_history_issue(title=TOKEN_TITLE, description="authority")
    client.add_comment(
        issue_id=ITEM,
        body=GENESIS_MARKER
        + _json(dict(schema=1, repository=REPOSITORY, item_id=ITEM, root_token_id=root)),
    )
    client.close_issue_without_verdict(
        issue_id=root,
        reason=TRANSITION_MARKER
        + _json(
            dict(
                schema=1,
                repository=REPOSITORY,
                item_id=ITEM,
                prior_token_id=root,
                next_token_id=current,
                attempt=_attempt(),
            )
        ),
    )
    assert _code(_publish(client, _request(claim=token))) == "incident-genesis-root-exists"
    client.add_comment(
        issue_id=ITEM,
        body=GENESIS_MARKER
        + _json(dict(schema=1, repository=REPOSITORY, item_id=ITEM, root_token_id=OTHER_ROOT)),
    )
    assert _code(_publish(client, _request(claim=token))) == "incident-authority-ambiguous"


def test_a_live_factory_claim_is_refused_until_the_all_writer_fence_lands() -> None:
    client, token = _ledger(status="active", assignee="fabro")
    result = _publish(client, _request(claim=token))
    assert _code(result) == "incident-factory-fence-unavailable"
    assert client.show_issue(issue_id=token)["status"] == "backlog"
    assert client.list_comments(issue_id=ITEM) == []


def _discarded(client: FakeBeadsClient, token: str) -> None:
    client.close_issue_without_verdict(
        issue_id=token, reason=_json({"kind": "claim-token-discard", "writer": "intake"})
    )


def _transitioned(client: FakeBeadsClient, token: str) -> None:
    client.close_issue_without_verdict(
        issue_id=token,
        reason=_json(
            {
                "kind": "claim-token-transition",
                "writer": "admission",
                "intent": "move-ready-to-active",
                "successor": "fake-wisp-99",
                "closed_at": "2026-11-05T00:00:00+00:00",
            }
        ),
    )


def _deleted(client: FakeBeadsClient, token: str) -> None:
    client.delete_issue(issue_id=token)


@pytest.mark.parametrize(
    ("prepare", "code"),
    [
        (None, "incident-genesis-claim-token-missing"),
        (_discarded, "incident-genesis-claim-token-missing"),
        (_transitioned, "incident-genesis-claim-transition-pending"),
        (_deleted, "incident-genesis-claim-unobservable"),
    ],
)
def test_a_claim_that_is_not_the_item_s_open_current_token_is_refused_by_name(
    prepare: Callable[[FakeBeadsClient, str], None] | None, code: str
) -> None:
    client, token = _ledger(with_token=prepare is not None)
    if prepare is not None:
        prepare(client, token)
    assert _code(_publish(client, _request(claim=token))) == code
    assert client.list_comments(issue_id=ITEM) == []


def test_a_stale_expected_claim_and_a_foreign_item_are_refused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, token = _ledger()
    assert _code(_publish(client, _request(claim="stale"))) == "incident-genesis-claim-mismatch"
    show = client.show_issue
    reads: list[str] = []

    def foreign(*, issue_id: str) -> dict[str, Any]:
        reads.append(issue_id)
        # The reader's own item read passes; the writer's later read answers another item.
        return show(issue_id=issue_id) | ({"id": "other"} if reads.count(ITEM) > 1 else {})

    monkeypatch.setattr(client, "show_issue", foreign)
    assert _code(_publish(client, _request(claim=token))) == "incident-authority-item-mismatch"


def test_losing_the_claim_token_close_discards_only_our_candidates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, token = _ledger()
    close = client.close_issue_without_verdict
    raced = False

    def race(*, issue_id: str, reason: str) -> None:
        nonlocal raced
        if issue_id == token and not raced:
            raced = True
            _transitioned(client, token)
        close(issue_id=issue_id, reason=reason)

    monkeypatch.setattr(client, "close_issue_without_verdict", race)
    result = _publish(client, _request(claim=token))
    assert _code(result) == "incident-genesis-lost-race"
    [successor] = [t for t in client.no_history_issue_ids() if t != token]
    assert client.show_issue(issue_id=successor)["close_reason"] == _json(
        {"kind": "claim-token-discard", "writer": PRINCIPAL}
    )
    assert client.list_comments(issue_id=ITEM) == []
    assert client.show_issue(issue_id=ITEM)["metadata"][CLAIM_TOKEN_METADATA_KEY] == token


def test_an_unobservable_close_keeps_candidates_and_claims_nothing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, token = _ledger()
    monkeypatch.setattr(client, "close_issue_without_verdict", lambda **_kwargs: None)
    assert _code(_publish(client, _request(claim=token))) == "incident-genesis-outcome-unknown"
    assert len(client.no_history_issue_ids()) == 4
    assert client.list_comments(issue_id=ITEM) == []


def test_a_winner_past_its_lease_publishes_nothing() -> None:
    client, token = _ledger()
    ticks = iter([0.0, 120.0])
    result = _publish(client, _request(claim=token), clock=lambda: next(ticks))
    assert _code(result) == "incident-genesis-lease-expired"
    assert client.show_issue(issue_id=result.detail)["status"] == "backlog"
    assert client.list_comments(issue_id=ITEM) == []
    assert client.show_issue(issue_id=ITEM)["metadata"][CLAIM_TOKEN_METADATA_KEY] == token


def _won_unpublished(client: FakeBeadsClient, token: str, request: GenesisRequest) -> str:
    """Our fence won the token, but neither the comment nor the item write landed."""
    root = client.create_no_history_issue(title=TOKEN_TITLE, description="authority")
    current = client.create_no_history_issue(title=TOKEN_TITLE, description="authority")
    successor = create_claim_token(client=client)
    client.close_issue_without_verdict(
        issue_id=root,
        reason=TRANSITION_MARKER
        + _json(
            dict(
                schema=1,
                repository=REPOSITORY,
                item_id=ITEM,
                prior_token_id=root,
                next_token_id=current,
                attempt=_attempt(),
            )
        ),
    )
    fence = genesis_fence(request=request, root_token_id=root, successor=successor)
    client.close_issue_without_verdict(
        issue_id=token, reason=genesis_fence_reason(fence=fence, closed_at="2026-11-05T00:00Z")
    )
    return root


def test_a_won_but_unpublished_close_is_completed_by_the_exact_retry() -> None:
    client, token = _ledger()
    request = _request(claim=token)
    root = _won_unpublished(client, token, request)
    minted = client.no_history_issue_ids()
    assert _code(_publish(client, _request(claim=token, principal="operator:bob"))) == (
        "incident-operation-conflict"
    )
    assert _code(_publish(client, _request(claim=token, operation_id="operation-2"))) == (
        "incident-genesis-claim-transition-pending"
    )
    assert client.list_comments(issue_id=ITEM) == []
    receipt = _publish(client, request)
    assert isinstance(receipt, GenesisReceipt)
    assert (receipt.recovered, receipt.root_token_id, receipt.claim_token_id) == (
        True,
        root,
        token,
    )
    assert client.no_history_issue_ids() == minted
    assert len(client.list_comments(issue_id=ITEM)) == 1
    assert client.show_issue(issue_id=ITEM)["metadata"][CLAIM_TOKEN_METADATA_KEY] == token
    assert isinstance(_read(client), IncidentReading)


def test_a_fence_naming_an_unreadable_root_is_unavailable_not_recovered() -> None:
    client, token = _ledger()
    request = _request(claim=token)
    fence = genesis_fence(request=request, root_token_id=UNREADABLE_ROOT, successor="fake-wisp-5")
    client.close_issue_without_verdict(
        issue_id=token, reason=genesis_fence_reason(fence=fence, closed_at="2026-11-05T00:00Z")
    )
    assert _code(_publish(client, request)) == "incident-authority-unavailable"


def test_a_tenant_outage_is_unavailable_not_absence(monkeypatch: pytest.MonkeyPatch) -> None:
    client, token = _ledger()

    def outage(**_kwargs: str) -> str:
        raise BeadsCommandError(command="bd create", exit_code=1, stderr="gone")

    monkeypatch.setattr(client, "create_no_history_issue", outage)
    assert _code(_publish(client, _request(claim=token))) == "incident-genesis-unavailable"
    assert client.show_issue(issue_id=token)["status"] == "backlog"


def test_the_transition_writer_advances_a_genesis_written_chain() -> None:
    client, token = _ledger()
    assert isinstance(_publish(client, _request(claim=token)), GenesisReceipt)
    observed = _read(client)
    assert isinstance(observed, IncidentReading)
    successor = decode_attempt(
        value=_attempt(
            generation=2,
            operation_id="publish-1",
            carrier=_reserved(state="head-published", remote_head="b" * 40),
        )
    )
    assert successor is not None
    advanced = commit_incident_transition(client=client, observed=observed, successor=successor)
    assert isinstance(advanced, IncidentReading)
    assert (advanced.attempt, advanced.is_current) == (successor, True)
    stale = _read(client)
    assert _code(stale) == "incident-authority-identity-mismatch"


def _cli(action: str, repo: Path, *extra: str) -> list[str]:
    return [
        action,
        *extra,
        "--repo",
        str(repo),
        "--repository",
        REPOSITORY,
        "--item",
        ITEM,
        "--attempt",
        "attempt-1",
        "--phase",
        "repair",
        "--operation",
        "operation-1",
        "--owner",
        PRINCIPAL,
        "--generation",
        "1",
    ]


def _configured(tmp_path: Path, value: str) -> Path:
    _ = (tmp_path / ".livespec.jsonc").write_text(
        '{"livespec-orchestrator-beads-fabro":{"dispatcher":{"claim_tokens":' + value + "}}}",
        encoding="utf-8",
    )
    return tmp_path


def test_the_process_boundary_publishes_then_reads_current_and_commits_over_the_chain(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    client, token = _ledger()
    monkeypatch.setattr(command, "store_config", lambda **_kwargs: None)
    monkeypatch.setattr(command, "make_beads_client", lambda **_kwargs: client)
    repo = _configured(tmp_path, "true")
    text = _request_text(claim=token)
    status = command.main(argv=_cli("publish-genesis", repo, "--genesis-json", text))
    published = json.loads(capsys.readouterr().out)
    assert (status, published["status"], published["authorizes_current_effects"]) == (
        0,
        "verified",
        False,
    )
    assert published["result"]["claim_token_id"] == token
    assert published["result"]["attempt"] == _attempt()
    assert command.main(argv=_cli("read-current", repo)) == 0
    current = json.loads(capsys.readouterr().out)
    assert (current["status"], current["authorizes_current_effects"]) == ("verified", True)
    assert current["result"]["is_current"] is True
    assert current["result"]["committed_token_id"] == published["result"]["root_token_id"]
    successor = _json(
        _attempt(
            generation=2,
            operation_id="publish-1",
            carrier=_reserved(state="head-published", remote_head="b" * 40),
        )
    )
    assert command.main(argv=_cli("commit-transition", repo, "--successor-json", successor)) == 0
    assert json.loads(capsys.readouterr().out)["result"]["attempt"]["generation"] == 2


def test_the_process_boundary_refuses_an_unreadable_cutover_setting(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    client, token = _ledger()
    monkeypatch.setattr(command, "make_beads_client", lambda **_kwargs: client)
    repo = _configured(tmp_path, '"yes"')
    text = _request_text(claim=token)
    status = command.main(argv=_cli("publish-genesis", repo, "--genesis-json", text))
    reply = json.loads(capsys.readouterr().out)
    assert (status, reply["result"]["code"]) == (78, "incident-genesis-capability-unavailable")
    assert "unreadable" in reply["result"]["detail"]
    assert client.show_issue(issue_id=token)["status"] == "backlog"


def _reopened(_client: FakeBeadsClient, _token: str) -> None:
    return None


def _fenced_elsewhere(client: FakeBeadsClient, token: str) -> None:
    fence = genesis_fence(
        request=_request(claim=token), root_token_id=UNREADABLE_ROOT, successor="fake-wisp-5"
    )
    client.close_issue_without_verdict(
        issue_id=token, reason=genesis_fence_reason(fence=fence, closed_at="2026-11-05T00:00Z")
    )


@pytest.mark.parametrize("corrupt", [_reopened, _transitioned, _fenced_elsewhere])
def test_a_fenced_genesis_record_holds_only_when_its_claim_token_close_names_it(
    corrupt: Callable[[FakeBeadsClient, str], None],
) -> None:
    client, token = _ledger()
    receipt = _publish(client, _request(claim=token))
    assert isinstance(receipt, GenesisReceipt)
    assert isinstance(_read(client), IncidentReading)
    client.delete_issue(issue_id=token)
    _ = client.create_issue(
        draft=IssueDraft(
            issue_id=token,
            issue_type="task",
            title="livespec dispatch claim token",
            description="reopened",
            assignee=None,
            created_at="2026-11-05T00:00:00Z",
        )
    )
    corrupt(client, token)
    assert _code(_read(client)) == "incident-authority-invalid-genesis"


def test_an_empty_claim_token_id_on_a_genesis_record_is_invalid() -> None:
    client, _ = _ledger()
    client.add_comment(
        issue_id=ITEM,
        body=GENESIS_MARKER
        + _json(
            dict(
                schema=1,
                repository=REPOSITORY,
                item_id=ITEM,
                root_token_id=BLANK_ROOT,
                claim_token_id="",
            )
        ),
    )
    assert _code(_read(client)) == "incident-authority-invalid-genesis"


def _fence_reason(**changes: Any) -> str:
    fence = genesis_fence(
        request=_request(claim="t1"), root_token_id=SOME_ROOT, successor="fake-wisp-3"
    )
    row = json.loads(genesis_fence_reason(fence=fence, closed_at="2026-11-05T00:00Z"))
    return _json(row | changes)


@pytest.mark.parametrize(
    "reason",
    [
        None,
        "{",
        "[]",
        _fence_reason(kind="other"),
        _fence_reason(successor=""),
        _fence_reason(intent="move-ready-to-active"),
        _fence_reason(incident="x"),
        _fence_reason(incident=json.loads(_fence_reason())["incident"] | {"extra": "1"}),
        _fence_reason(incident=json.loads(_fence_reason())["incident"] | {"schema": 2}),
        _fence_reason(incident=json.loads(_fence_reason())["incident"] | {"principal": " "}),
    ],
)
def test_foreign_or_malformed_close_reasons_are_never_a_genesis_fence(reason: object) -> None:
    assert decode_genesis_fence(reason=reason) is None


def test_the_successor_a_closed_claim_token_names_is_read_under_any_intent() -> None:
    assert claim_successor(reason=_fence_reason()) == "fake-wisp-3"
    assert claim_successor(reason=_fence_reason(intent="move-ready-to-active")) == "fake-wisp-3"
    assert claim_successor(reason=_fence_reason(kind="other")) is None
    assert claim_successor(reason=7) is None
