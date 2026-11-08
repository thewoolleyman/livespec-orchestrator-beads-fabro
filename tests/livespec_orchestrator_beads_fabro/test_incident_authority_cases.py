"""Current fencing and historical provenance through the real canonical reader."""

# EXPEDITED_INCIDENT_RESPONSE flag: bd-ib-dzbwaq
from __future__ import annotations

import json
from dataclasses import asdict, replace
from pathlib import Path
from typing import Any

import pytest
from livespec_orchestrator_beads_fabro._beads_client import FakeBeadsClient, IssueDraft
from livespec_orchestrator_beads_fabro._incident_authority_payload import (
    GENESIS_MARKER,
    TOKEN_TITLE,
    TRANSITION_MARKER,
    decode_attempt,
    decode_record,
)
from livespec_orchestrator_beads_fabro.effects import _incident_authority_reader as reader
from livespec_orchestrator_beads_fabro.errors import (
    BeadsCommandError,
    BeadsConnectionError,
    BeadsCredentialMissingError,
    BeadsTenantMissingError,
)
from livespec_orchestrator_beads_fabro.incident_authority import (
    AuthorityRefusal,
    IncidentReading,
    commit_incident_transition,
    read_incident_authority,
)

REPOSITORY = "owner/repository"
ITEM = "test-incident"


def _json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _attempt(**changes: Any) -> dict[str, Any]:
    return (
        dict(
            repository=REPOSITORY,
            item_id=ITEM,
            attempt_id="attempt-1",
            phase="repair",
            operation_id="operation-1",
            generation=1,
            owner="operator:alice",
            base="a" * 40,
            head="b" * 40,
            pr_number=7,
            landed_commits=["b" * 40],
            landed_trees=["c" * 40],
            original_paths=["app.py"],
            deferred_work=["normal-factory-proof"],
            repayment_required=True,
        )
        | changes
    )


def _query(attempt: dict[str, Any]) -> dict[str, object]:
    return {k: attempt[k] for k in ("attempt_id", "phase", "operation_id", "generation", "owner")}


def _token(client: FakeBeadsClient) -> str:
    return client.create_no_history_issue(
        title=TOKEN_TITLE, description="Retained immutable incident authority."
    )


def _append(client: FakeBeadsClient, token: str, snapshot: dict[str, Any], **changes: Any) -> str:
    successor = _token(client)
    payload = (
        dict(
            schema=1,
            repository=REPOSITORY,
            item_id=ITEM,
            prior_token_id=token,
            next_token_id=successor,
            attempt=snapshot,
        )
        | changes
    )
    client.close_issue_without_verdict(issue_id=token, reason=TRANSITION_MARKER + _json(payload))
    return successor


def _chain() -> tuple[FakeBeadsClient, str, str]:
    client = FakeBeadsClient()
    client.create_issue(
        draft=IssueDraft(
            issue_id=ITEM,
            issue_type="bug",
            title="incident",
            description="behavior",
            assignee=None,
            created_at="2026-11-04T00:00:00Z",
        )
    )
    root = _token(client)
    client.add_comment(
        issue_id=ITEM,
        body=GENESIS_MARKER
        + _json(dict(schema=1, repository=REPOSITORY, item_id=ITEM, root_token_id=root)),
    )
    return client, root, _append(client, root, _attempt())


def _read(client: FakeBeadsClient, **kwargs: Any) -> IncidentReading | AuthorityRefusal:
    return read_incident_authority(
        client=client, repository=REPOSITORY, item_id=ITEM, query=_query(_attempt()), **kwargs
    )


def test_current_attempt_binds_every_identity_and_the_complete_landed_set() -> None:
    client, root, successor = _chain()
    result = _read(client)
    assert isinstance(result, IncidentReading)
    assert asdict(result.attempt) == _attempt() | {
        "carrier": None,
        "landed_commits": ("b" * 40,),
        "landed_trees": ("c" * 40,),
        "original_paths": ("app.py",),
        "deferred_work": ("normal-factory-proof",),
    }
    assert (result.committed_token_id, result.current_token_id, result.is_current) == (
        root,
        successor,
        True,
    )


def test_historical_provenance_survives_owner_phase_generation_and_environment_changes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, _, successor = _chain()
    _append(
        client,
        successor,
        _attempt(
            generation=2,
            owner="factory:repayment",
            phase="repayment-active",
            operation_id="repay-1",
        ),
    )
    monkeypatch.delenv("EXPEDITED_INCIDENT_RESPONSE", raising=False)
    client.update_issue(issue_id=ITEM, metadata={}, remove_labels=["incident"])
    current = _read(client)
    assert (
        isinstance(current, AuthorityRefusal)
        and current.code == "incident-authority-identity-mismatch"
    )
    historical = _read(client, historical=True)
    assert isinstance(historical, IncidentReading) and historical.is_current is False
    assert historical.attempt.pr_number == 7


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("generation", True),
        ("generation", 0),
        ("pr_number", 0),
        ("repayment_required", 1),
        ("phase", "unknown"),
        ("repository", "wrong"),
        ("head", "bad"),
        ("base", "g" * 40),
        ("owner", " "),
        ("landed_commits", ["bad"]),
        ("landed_trees", []),
        ("original_paths", ["../outside"]),
        ("original_paths", []),
        ("original_paths", ["/absolute"]),
        ("original_paths", ["x/./y"]),
        ("deferred_work", ["duplicate", "duplicate"]),
        ("deferred_work", [1]),
        ("landed_commits", None),
    ],
)
def test_malformed_attempts_never_become_authority(key: str, value: object) -> None:
    assert decode_attempt(value=_attempt(**{key: value})) is None


@pytest.mark.parametrize("value", [None, [], {}, _attempt(extra="field")])
def test_incomplete_or_extended_attempt_schema_is_refused(value: object) -> None:
    assert decode_attempt(value=value) is None


@pytest.mark.parametrize(
    "text",
    [
        None,
        "wrong",
        GENESIS_MARKER + "{",
        GENESIS_MARKER + "[]",
        GENESIS_MARKER + '{"schema":true}',
        GENESIS_MARKER + '{"schema":1,"schema":1}',
    ],
)
def test_unknown_or_noncanonical_record_is_refused(text: object) -> None:
    assert decode_record(text=text, marker=GENESIS_MARKER, keys=frozenset(("schema",))) is None


def test_unreadable_link_reports_unavailable_not_missing_or_normal() -> None:
    client, root, _ = _chain()
    client.delete_issue(issue_id=root)
    result = _read(client)
    assert isinstance(result, AuthorityRefusal) and result.code == "incident-authority-unavailable"


@pytest.mark.parametrize(
    ("changes", "code"),
    [
        ({"repository": "other/repo"}, "incident-authority-invalid-transition"),
        ({"prior_token_id": "wrong"}, "incident-authority-invalid-transition"),
        ({"next_token_id": ""}, "incident-authority-invalid-transition"),
        ({"next_token_id": 4}, "incident-authority-invalid-transition"),
        ({"attempt": {}}, "incident-authority-invalid-attempt"),
        ({"attempt": _attempt(generation=4)}, "incident-authority-invalid-attempt"),
        ({"attempt": _attempt(item_id="other")}, "incident-authority-invalid-attempt"),
    ],
)
def test_forked_or_inconsistent_link_is_refused(changes: dict[str, Any], code: str) -> None:
    client, _, successor = _chain()
    _append(client, successor, _attempt(generation=2), **changes)
    result = _read(client)
    assert isinstance(result, AuthorityRefusal) and result.code == code


def test_cycle_is_refused() -> None:
    client, _, successor = _chain()
    _append(
        client, successor, _attempt(generation=2, operation_id="cycle"), next_token_id=successor
    )
    result = _read(client)
    assert isinstance(result, AuthorityRefusal) and result.code == "incident-authority-cycle"


def test_bounded_history_is_explicit_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    client, _, _ = _chain()
    monkeypatch.setattr(reader, "_MAX_TOKENS", 1)
    result = _read(client)
    assert (
        isinstance(result, AuthorityRefusal) and result.code == "incident-authority-history-limit"
    )


@pytest.mark.parametrize(
    "change",
    [{"owner": "wrong"}, {"generation": True}, {"operation_id": "other"}, {"unexpected": "key"}],
)
def test_current_query_requires_exact_fenced_identity(change: dict[str, object]) -> None:
    client, _, _ = _chain()
    result = read_incident_authority(
        client=client, repository=REPOSITORY, item_id=ITEM, query=_query(_attempt()) | change
    )
    assert (
        isinstance(result, AuthorityRefusal)
        and result.code == "incident-authority-identity-mismatch"
    )


def test_changed_generation_during_read_is_refused_before_effect(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, _, successor = _chain()
    show = client.show_issue
    reads = 0

    def race(*, issue_id: str) -> dict[str, Any]:
        nonlocal reads
        if issue_id == successor:
            reads += 1
            if reads == 2:
                _append(client, successor, _attempt(generation=2))
        return show(issue_id=issue_id)

    monkeypatch.setattr(client, "show_issue", race)
    result = _read(client)
    assert isinstance(result, AuthorityRefusal) and result.code == "incident-authority-changed"


@pytest.mark.parametrize(
    "body",
    [
        GENESIS_MARKER + "{",
        GENESIS_MARKER
        + _json(dict(schema=1, repository="other/repo", item_id=ITEM, root_token_id=ITEM)),
        GENESIS_MARKER
        + _json(dict(schema=1, repository=REPOSITORY, item_id=ITEM, root_token_id="")),
        GENESIS_MARKER
        + _json(dict(schema=1, repository=REPOSITORY, item_id=ITEM, root_token_id=7)),
    ],
)
def test_invalid_genesis_fails_closed(body: str) -> None:
    client, _, _ = _chain()
    client.add_comment(issue_id=ITEM, body=body)
    result = _read(client)
    assert isinstance(result, AuthorityRefusal)
    assert result.code == "incident-authority-invalid-genesis"


def test_duplicate_root_is_idempotent_but_two_roots_refuse() -> None:
    client, root, _ = _chain()
    record = dict(schema=1, repository=REPOSITORY, item_id=ITEM, root_token_id=root)
    client.add_comment(issue_id=ITEM, body="unrelated comment")
    client.add_comment(issue_id=ITEM, body=GENESIS_MARKER + _json(record))
    assert isinstance(_read(client), IncidentReading)
    record["root_token_id"] = _token(client)
    client.add_comment(issue_id=ITEM, body=GENESIS_MARKER + _json(record))
    result = _read(client)
    assert isinstance(result, AuthorityRefusal)
    assert result.code == "incident-authority-ambiguous"


@pytest.mark.parametrize("status", ["active", "ready"])
def test_invalid_token_state_is_not_current(status: str) -> None:
    client, _, successor = _chain()
    client.update_issue(issue_id=successor, status=status)
    result = _read(client)
    assert isinstance(result, AuthorityRefusal)
    assert result.code == "incident-authority-invalid-token-state"


def test_wrong_token_identity_refuses(monkeypatch: pytest.MonkeyPatch) -> None:
    client, root, _ = _chain()
    show = client.show_issue

    def wrong(*, issue_id: str) -> dict[str, Any]:
        return show(issue_id=issue_id) | ({"title": "foreign token"} if issue_id == root else {})

    monkeypatch.setattr(client, "show_issue", wrong)
    result = _read(client)
    assert isinstance(result, AuthorityRefusal)
    assert result.code == "incident-authority-invalid-token"


def test_source_cannot_return_another_item(monkeypatch: pytest.MonkeyPatch) -> None:
    client, _, _ = _chain()
    show = client.show_issue

    def wrong(*, issue_id: str) -> dict[str, Any]:
        return show(issue_id=issue_id) | ({"id": "foreign"} if issue_id == ITEM else {})

    monkeypatch.setattr(client, "show_issue", wrong)
    result = _read(client)
    assert isinstance(result, AuthorityRefusal)
    assert result.code == "incident-authority-item-mismatch"


def test_empty_chain_has_no_attempt() -> None:
    client, root, _ = _chain()
    client.update_issue(issue_id=root, status="backlog")
    result = _read(client)
    assert isinstance(result, AuthorityRefusal)
    assert result.code == "incident-authority-identity-mismatch"


def test_missing_transition_reason_is_refused() -> None:
    client, _, successor = _chain()
    client.close_issue_without_verdict(issue_id=successor, reason="ordinary close")
    result = _read(client)
    assert isinstance(result, AuthorityRefusal)
    assert result.code == "incident-authority-invalid-transition"


def test_server_conditional_transition_and_retry_preserve_one_effect() -> None:
    client, _, _ = _chain()
    before = _read(client)
    assert isinstance(before, IncidentReading)
    next_attempt = replace(before.attempt, generation=2, operation_id="next", owner="operator:bob")
    committed = commit_incident_transition(client=client, observed=before, successor=next_attempt)
    assert isinstance(committed, IncidentReading)
    assert committed.attempt == next_attempt
    count = len(client.no_history_issue_ids())
    recovered = commit_incident_transition(client=client, observed=before, successor=next_attempt)
    assert recovered == committed
    assert len(client.no_history_issue_ids()) == count
    third = replace(next_attempt, generation=3, operation_id="third")
    assert isinstance(
        commit_incident_transition(client=client, observed=committed, successor=third),
        IncidentReading,
    )
    historical = commit_incident_transition(client=client, observed=before, successor=next_attempt)
    assert isinstance(historical, IncidentReading)
    assert historical.attempt == next_attempt
    assert not historical.is_current


@pytest.mark.parametrize(
    "changes",
    [
        {"generation": 0},
        {"generation": 4},
        {"phase": "bad"},
        {"original_paths": ("other.py",)},
        {"repository": "other/repo"},
        {"item_id": "other"},
        {"operation_id": "operation-1"},
    ],
)
def test_invalid_successor_changes_no_authority(changes: dict[str, Any]) -> None:
    client, _, _ = _chain()
    before = _read(client)
    assert isinstance(before, IncidentReading)
    count = len(client.no_history_issue_ids())
    successor = (
        replace(before.attempt, generation=2, operation_id="next", **changes)
        if not ({"generation", "operation_id"} & set(changes))
        else replace(before.attempt, **(dict(generation=2, operation_id="next") | changes))
    )
    result = commit_incident_transition(client=client, observed=before, successor=successor)
    assert isinstance(result, AuthorityRefusal)
    assert result.code == "incident-transition-invalid-successor"
    assert len(client.no_history_issue_ids()) == count


def test_forged_observation_cannot_choose_another_token() -> None:
    client, _, _ = _chain()
    before = _read(client)
    assert isinstance(before, IncidentReading)
    forged = replace(before, current_token_id=before.attempt.item_id)
    result = commit_incident_transition(
        client=client,
        observed=forged,
        successor=replace(before.attempt, generation=2, operation_id="next"),
    )
    assert isinstance(result, AuthorityRefusal)
    assert result.code == "incident-generation-stale"


def test_same_operation_with_conflicting_payload_is_refused() -> None:
    client, _, _ = _chain()
    before = _read(client)
    assert isinstance(before, IncidentReading)
    successor = replace(before.attempt, generation=2, operation_id="next")
    assert isinstance(
        commit_incident_transition(client=client, observed=before, successor=successor),
        IncidentReading,
    )
    result = commit_incident_transition(
        client=client, observed=before, successor=replace(successor, head="d" * 40)
    )
    assert isinstance(result, AuthorityRefusal)
    assert result.code == "incident-transition-operation-conflict"
    stale = commit_incident_transition(
        client=client, observed=before, successor=replace(successor, operation_id="different")
    )
    assert isinstance(stale, AuthorityRefusal)
    assert stale.code == "incident-generation-stale"


def test_losing_a_server_close_discards_only_our_unlinked_candidate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, _, current = _chain()
    before = _read(client)
    assert isinstance(before, IncidentReading)
    close = client.close_issue_without_verdict
    raced = False

    def race(*, issue_id: str, reason: str) -> None:
        nonlocal raced
        if issue_id == current and not raced:
            raced = True
            _append(client, current, _attempt(generation=2, operation_id="winner"))
        close(issue_id=issue_id, reason=reason)

    monkeypatch.setattr(client, "close_issue_without_verdict", race)
    result = commit_incident_transition(
        client=client,
        observed=before,
        successor=replace(before.attempt, generation=2, operation_id="loser"),
    )
    assert isinstance(result, AuthorityRefusal)
    assert result.code == "incident-transition-lost-race"
    assert len(client.no_history_issue_ids()) == 3


def test_unknown_close_keeps_candidate_and_does_not_claim_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, _, _ = _chain()
    before = _read(client)
    assert isinstance(before, IncidentReading)
    monkeypatch.setattr(client, "close_issue_without_verdict", lambda **_kwargs: None)
    result = commit_incident_transition(
        client=client,
        observed=before,
        successor=replace(before.attempt, generation=2, operation_id="next"),
    )
    assert isinstance(result, AuthorityRefusal)
    assert result.code == "incident-transition-outcome-unknown"
    assert len(client.no_history_issue_ids()) == 3


def test_unreadable_winning_close_preserves_candidate_for_exact_retry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from livespec_orchestrator_beads_fabro.errors import BeadsMappingError

    client, _, current = _chain()
    before = _read(client)
    assert isinstance(before, IncidentReading)
    show = client.show_issue

    def unreadable(*, issue_id: str) -> dict[str, Any]:
        row = show(issue_id=issue_id)
        if issue_id == current and row["status"] == "closed":
            raise BeadsMappingError(record_id=issue_id, detail="readback unavailable")
        return row

    successor = replace(before.attempt, generation=2, operation_id="next")
    monkeypatch.setattr(client, "show_issue", unreadable)
    result = commit_incident_transition(client=client, observed=before, successor=successor)
    assert isinstance(result, AuthorityRefusal)
    assert result.code == "incident-transition-unavailable"
    assert len(client.no_history_issue_ids()) == 3
    monkeypatch.setattr(client, "show_issue", show)
    recovered = commit_incident_transition(client=client, observed=before, successor=successor)
    assert isinstance(recovered, IncidentReading)
    assert recovered.attempt == successor
    assert len(client.no_history_issue_ids()) == 3


def test_reusing_an_immutable_operation_id_in_later_generation_is_refused() -> None:
    client, _, current = _chain()
    _append(client, current, _attempt(generation=2))
    result = _read(client)
    assert isinstance(result, AuthorityRefusal)
    assert result.code == "incident-authority-reused-operation"


def test_distinct_landed_commits_can_share_a_tree_without_losing_the_complete_set() -> None:
    decoded = decode_attempt(
        value=_attempt(landed_commits=["b" * 40, "d" * 40], landed_trees=["c" * 40, "c" * 40])
    )
    assert decoded is not None
    assert decoded.landed_trees == ("c" * 40, "c" * 40)
    assert decode_attempt(value=_attempt(original_paths=["."])) is None


def test_writer_refuses_historical_operation_reuse_before_closing_another_token() -> None:
    client, _, _ = _chain()
    before = _read(client)
    assert isinstance(before, IncidentReading)
    next_attempt = replace(before.attempt, generation=2, operation_id="next")
    second = commit_incident_transition(client=client, observed=before, successor=next_attempt)
    assert isinstance(second, IncidentReading)
    count = len(client.no_history_issue_ids())
    result = commit_incident_transition(
        client=client,
        observed=second,
        successor=replace(second.attempt, generation=3, operation_id=before.attempt.operation_id),
    )
    assert isinstance(result, AuthorityRefusal)
    assert result.code == "incident-transition-operation-reused"
    assert len(client.no_history_issue_ids()) == count
    assert isinstance(
        read_incident_authority(
            client=client,
            repository=REPOSITORY,
            item_id=ITEM,
            query=_query(dict(asdict(second.attempt))),
        ),
        IncidentReading,
    )


@pytest.mark.parametrize(
    "error",
    [
        BeadsCommandError(command="bd", exit_code=1, stderr="transport"),
        BeadsConnectionError(detail="server unreachable"),
        BeadsCredentialMissingError(variable="BEADS_DOLT_PASSWORD"),
        BeadsTenantMissingError(tenant="fixture"),
    ],
)
def test_expected_tenant_failures_remain_named_at_the_public_process_boundary(
    error: Exception,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    from livespec_orchestrator_beads_fabro.commands import incident_authority as command

    client, _, _ = _chain()

    def unavailable(*, issue_id: str) -> list[dict[str, Any]]:
        assert issue_id == ITEM
        raise error

    monkeypatch.setattr(client, "list_comments", unavailable)
    monkeypatch.setattr(command, "store_config", lambda **_kwargs: None)
    monkeypatch.setattr(command, "make_beads_client", lambda **_kwargs: client)
    argv = [
        "read-current",
        "--repo",
        str(tmp_path),
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
        "--generation",
        "1",
        "--owner",
        "operator:alice",
    ]
    assert command.main(argv=argv) == 78
    reply = json.loads(capsys.readouterr().out)
    assert reply["result"]["code"] == "incident-authority-unavailable"
    assert reply["authorizes_current_effects"] is False


@pytest.mark.parametrize(
    "error",
    [
        BeadsConnectionError(detail="server unreachable"),
        BeadsCredentialMissingError(variable="BEADS_DOLT_PASSWORD"),
        BeadsTenantMissingError(tenant="fixture"),
    ],
)
def test_transition_create_outage_cannot_publish_or_lose_a_claim(
    error: Exception, monkeypatch: pytest.MonkeyPatch
) -> None:
    client, _, _ = _chain()
    before = _read(client)
    assert isinstance(before, IncidentReading)
    count = len(client.no_history_issue_ids())

    def unavailable(*, title: str, description: str) -> str:
        assert title and description
        raise error

    monkeypatch.setattr(client, "create_no_history_issue", unavailable)
    result = commit_incident_transition(
        client=client,
        observed=before,
        successor=replace(before.attempt, generation=2, operation_id="next"),
    )
    assert isinstance(result, AuthorityRefusal)
    assert result.code == "incident-transition-unavailable"
    assert len(client.no_history_issue_ids()) == count
