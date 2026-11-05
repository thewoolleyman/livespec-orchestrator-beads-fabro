"""Explicit pre-PR carrier state and the honest incident genesis refusal."""

# EXPEDITED_INCIDENT_RESPONSE flag: bd-ib-dzbwaq
from __future__ import annotations

import json
from dataclasses import asdict, replace
from pathlib import Path
from typing import Any
from unittest.mock import Mock

import pytest
from livespec_orchestrator_beads_fabro._beads_client import FakeBeadsClient, IssueDraft
from livespec_orchestrator_beads_fabro._incident_authority_payload import (
    GENESIS_MARKER,
    TOKEN_TITLE,
    TRANSITION_MARKER,
    decode_attempt,
)
from livespec_orchestrator_beads_fabro._incident_carrier import (
    BranchReserved,
    HeadPublished,
    PrBound,
    carrier_successor_allowed,
    decode_carrier,
)
from livespec_orchestrator_beads_fabro._incident_genesis import (
    decode_genesis_request,
    publish_genesis,
)
from livespec_orchestrator_beads_fabro.commands import incident_authority as command
from livespec_orchestrator_beads_fabro.incident_authority import (
    AuthorityRefusal,
    IncidentReading,
    commit_incident_transition,
    read_incident_authority,
)

REPOSITORY = "owner/repository"
ITEM = "test-incident"
REF = "refs/heads/incident/test-incident-attempt-1"


def _json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _reserved(**changes: Any) -> dict[str, Any]:
    return (
        dict(state="branch-reserved", target_ref=REF, input_parent="a" * 40, staged_tree="c" * 40)
        | changes
    )


def _published(state: str = "head-published", **changes: Any) -> dict[str, Any]:
    return _reserved(state=state, remote_head="b" * 40) | changes


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


def _chain(snapshot: dict[str, Any]) -> FakeBeadsClient:
    client = FakeBeadsClient()
    client.create_issue(
        draft=IssueDraft(
            issue_id=ITEM,
            issue_type="bug",
            title="incident",
            description="behavior",
            assignee=None,
            created_at="2026-11-05T00:00:00Z",
        )
    )
    root = client.create_no_history_issue(title=TOKEN_TITLE, description="authority")
    current = client.create_no_history_issue(title=TOKEN_TITLE, description="authority")
    client.add_comment(
        issue_id=ITEM,
        body=GENESIS_MARKER
        + _json(dict(schema=1, repository=REPOSITORY, item_id=ITEM, root_token_id=root)),
    )
    payload = dict(
        schema=1,
        repository=REPOSITORY,
        item_id=ITEM,
        prior_token_id=root,
        next_token_id=current,
        attempt=snapshot,
    )
    client.close_issue_without_verdict(issue_id=root, reason=TRANSITION_MARKER + _json(payload))
    return client


def _read(client: FakeBeadsClient, snapshot: dict[str, Any]) -> IncidentReading | AuthorityRefusal:
    return read_incident_authority(
        client=client, repository=REPOSITORY, item_id=ITEM, query=_query(snapshot)
    )


def test_a_pre_pr_attempt_names_its_exact_branch_reservation_and_no_pr() -> None:
    reserved = decode_attempt(value=_attempt())
    published = decode_attempt(value=_attempt(carrier=_published()))
    bound = decode_attempt(value=_attempt(pr_number=7, carrier=_published("pr-bound")))
    facts = [
        getattr(reserved, "carrier", None)
        == BranchReserved(target_ref=REF, input_parent="a" * 40, staged_tree="c" * 40),
        getattr(published, "carrier", None)
        == HeadPublished(
            target_ref=REF, input_parent="a" * 40, staged_tree="c" * 40, remote_head="b" * 40
        ),
        getattr(bound, "carrier", None)
        == PrBound(
            target_ref=REF, input_parent="a" * 40, staged_tree="c" * 40, remote_head="b" * 40
        ),
        getattr(reserved, "pr_number", None) == 0,
    ]
    assert all(facts)


@pytest.mark.parametrize(
    "snapshot",
    [
        _attempt(pr_number=7),
        _attempt(carrier=_published("pr-bound")),
        _attempt(pr_number=7, carrier=_published()),
        _attempt(phase="master-observation"),
        _attempt(landed_commits=["b" * 40], landed_trees=["c" * 40]),
        _attempt(pr_number=True, carrier=_published("pr-bound")),
    ],
)
def test_a_pr_number_must_agree_with_the_carrier_state(snapshot: dict[str, Any]) -> None:
    assert decode_attempt(value=snapshot) is None


@pytest.mark.parametrize(
    "carrier",
    [
        None,
        [],
        {},
        _reserved(state="merged"),
        _reserved(state=7),
        _reserved(extra="field"),
        _published(state="branch-reserved"),
        _reserved(target_ref="incident/branch"),
        _reserved(target_ref="refs/heads/"),
        _reserved(target_ref="refs/heads/a..b"),
        _reserved(target_ref="refs/heads/a//b"),
        _reserved(target_ref="refs/heads//a"),
        _reserved(target_ref="refs/heads/a/"),
        _reserved(target_ref="refs/heads/a.lock"),
        _reserved(target_ref="refs/heads/a b"),
        _reserved(target_ref=7),
        _reserved(input_parent="A" * 40),
        _reserved(staged_tree="c" * 39),
        _published(remote_head="bad"),
    ],
)
def test_an_unknown_or_malformed_carrier_is_not_a_carrier(carrier: object) -> None:
    assert decode_carrier(value=carrier) is None


def test_existing_schema_one_records_without_a_carrier_stay_readable() -> None:
    legacy_pre_pr = {k: v for k, v in _attempt().items() if k != "carrier"}
    legacy_bound = legacy_pre_pr | dict(
        pr_number=7, landed_commits=["b" * 40], landed_trees=["c" * 40]
    )
    explicit_null = legacy_pre_pr | dict(carrier=None)
    decoded = [decode_attempt(value=v) for v in (legacy_pre_pr, legacy_bound, explicit_null)]
    facts = [d is not None and d.carrier is None for d in decoded]
    assert all(facts)


def test_a_stored_unsupported_carrier_is_a_named_refusal_not_normal_fallback() -> None:
    snapshot = _attempt(carrier=_reserved(state="merged"))
    result = _read(_chain(snapshot), snapshot)
    assert isinstance(result, AuthorityRefusal)
    assert result.code == "incident-carrier-unsupported"


def test_the_reader_returns_the_retained_carrier() -> None:
    snapshot = _attempt(carrier=_published())
    result = _read(_chain(snapshot), snapshot)
    assert isinstance(result, IncidentReading)
    assert isinstance(result.attempt.carrier, HeadPublished)
    assert asdict(result.attempt)["carrier"] == _published()


def test_a_transition_advances_a_carrier_but_never_regresses_or_rewrites_it() -> None:
    snapshot = _attempt(carrier=_published())
    client = _chain(snapshot)
    observed = _read(client, snapshot)
    assert isinstance(observed, IncidentReading)
    base = replace(observed.attempt, generation=2, operation_id="operation-2")
    rewritten = HeadPublished(
        target_ref="refs/heads/other",
        input_parent="a" * 40,
        staged_tree="c" * 40,
        remote_head="b" * 40,
    )
    refused = [
        commit_incident_transition(
            client=client, observed=observed, successor=replace(base, carrier=carrier)
        )
        for carrier in (
            None,
            BranchReserved(target_ref=REF, input_parent="a" * 40, staged_tree="c" * 40),
            rewritten,
            HeadPublished(
                target_ref=REF, input_parent="d" * 40, staged_tree="c" * 40, remote_head="b" * 40
            ),
        )
    ]
    advanced = commit_incident_transition(
        client=client,
        observed=observed,
        successor=replace(
            base,
            pr_number=7,
            carrier=PrBound(
                target_ref=REF, input_parent="a" * 40, staged_tree="c" * 40, remote_head="b" * 40
            ),
        ),
    )
    codes = [r.code for r in refused if isinstance(r, AuthorityRefusal)]
    assert codes == ["incident-transition-invalid-successor"] * 4
    assert isinstance(advanced, IncidentReading)
    assert isinstance(advanced.attempt.carrier, PrBound)


def test_successor_rules_for_reservations_and_bound_pr_numbers() -> None:
    reserved = BranchReserved(target_ref=REF, input_parent="a" * 40, staged_tree="c" * 40)
    refreshed = BranchReserved(target_ref=REF, input_parent="d" * 40, staged_tree="e" * 40)
    bound = PrBound(
        target_ref=REF, input_parent="a" * 40, staged_tree="c" * 40, remote_head="b" * 40
    )
    facts = [
        carrier_successor_allowed(before=None, after=reserved, before_pr=0, after_pr=0),
        carrier_successor_allowed(before=reserved, after=refreshed, before_pr=0, after_pr=0),
        carrier_successor_allowed(before=bound, after=bound, before_pr=7, after_pr=7),
        not carrier_successor_allowed(before=bound, after=bound, before_pr=7, after_pr=8),
    ]
    assert all(facts)


def _genesis_text(**changes: Any) -> str:
    request = (
        dict(
            schema=1,
            principal="operator:alice",
            expected_claim="unclaimed",
            attempt=_attempt(),
        )
        | changes
    )
    return _json(request)


def test_genesis_refuses_with_the_named_capability_error_and_binds_the_request() -> None:
    request = decode_genesis_request(
        text=_genesis_text(), repository=REPOSITORY, item_id=ITEM, operation_id="operation-1"
    )
    assert request is not None
    first = publish_genesis(request=request)
    again = publish_genesis(request=request)
    assert first.code == "incident-genesis-capability-unavailable"
    assert first == again
    assert ITEM in first.detail


@pytest.mark.parametrize(
    "text",
    [
        "{",
        "[]",
        _genesis_text(schema=2),
        _genesis_text(schema=True),
        _genesis_text(extra="field"),
        _genesis_text(principal=" "),
        _genesis_text(principal=7),
        _genesis_text(expected_claim=""),
        _genesis_text(attempt=_attempt(generation=2)),
        _genesis_text(attempt=_attempt(item_id="other-item")),
        _genesis_text(attempt=_attempt(repository="other/repository")),
        _genesis_text(attempt=_attempt(operation_id="operation-2")),
        _genesis_text(attempt=_attempt(carrier=_published())),
        _genesis_text(attempt={k: v for k, v in _attempt().items() if k != "carrier"}),
        _genesis_text(attempt=_attempt(phase="reverting")),
        _genesis_text().replace(":", ": ", 1),
    ],
)
def test_genesis_rejects_requests_that_are_not_one_exact_initial_snapshot(text: str) -> None:
    assert (
        decode_genesis_request(
            text=text, repository=REPOSITORY, item_id=ITEM, operation_id="operation-1"
        )
        is None
    )


def _cli(action: str, *extra: str) -> list[str]:
    return [
        action,
        *extra,
        "--repo",
        str(Path.cwd()),
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
        "operator:alice",
        "--generation",
        "1",
    ]


@pytest.mark.parametrize(
    ("text", "code"),
    [
        (_genesis_text(), "incident-genesis-capability-unavailable"),
        (_genesis_text(attempt=_attempt(owner="operator:bob")), "incident-genesis-invalid-request"),
        ("{", "incident-genesis-invalid-request"),
    ],
)
def test_the_genesis_verb_touches_no_ledger_and_exits_78(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], text: str, code: str
) -> None:
    factory = Mock(return_value=FakeBeadsClient())
    monkeypatch.setattr(command, "make_beads_client", factory)
    monkeypatch.setattr(command, "store_config", Mock(return_value=None))
    status = command.main(argv=_cli("publish-genesis", "--genesis-json", text))
    reply = json.loads(capsys.readouterr().out)
    assert (status, reply["status"], reply["result"]["code"]) == (78, "refused", code)
    assert reply["authorizes_current_effects"] is False
    assert factory.call_count == 0


@pytest.mark.parametrize(
    "argv",
    [
        _cli("publish-genesis"),
        _cli("read-current", "--genesis-json", _genesis_text()),
    ],
)
def test_genesis_json_belongs_to_the_genesis_verb_alone(argv: list[str]) -> None:
    with pytest.raises(SystemExit):
        command.main(argv=argv)


def test_a_cli_successor_with_an_unsupported_carrier_is_named(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    snapshot = _attempt(carrier=_published())
    client = _chain(snapshot)
    monkeypatch.setattr(command, "make_beads_client", Mock(return_value=client))
    monkeypatch.setattr(command, "store_config", Mock(return_value=None))
    successor = _json(
        _attempt(generation=2, operation_id="operation-2", carrier=_reserved(state="merged"))
    )
    argv = _cli("commit-transition", "--successor-json", successor)
    status = command.main(argv=argv)
    reply = json.loads(capsys.readouterr().out)
    assert (status, reply["result"]["code"]) == (78, "incident-carrier-unsupported")
