"""Edges of canonical incident entry: malformed records, lost replies and stale readings."""

# EXPEDITED_INCIDENT_RESPONSE flag: bd-ib-dzbwaq
from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest
from livespec_orchestrator_beads_fabro._beads_client import FakeBeadsClient, IssueDraft
from livespec_orchestrator_beads_fabro._incident_authority_payload import (
    TOKEN_TITLE,
    TRANSITION_MARKER,
)
from livespec_orchestrator_beads_fabro._incident_entry import (
    decode_filing_request,
    filing_identity,
    prior_claim,
    prior_claim_valid,
    select_carrier,
)
from livespec_orchestrator_beads_fabro._incident_genesis import (
    GenesisReceipt,
    GenesisRequest,
    decode_genesis_fence,
    decode_genesis_request,
    genesis_fence,
    genesis_fence_reason,
)
from livespec_orchestrator_beads_fabro._store_dispatch_claim import (
    CLAIM_TOKEN_METADATA_KEY,
    create_claim_token,
)
from livespec_orchestrator_beads_fabro.commands import incident_authority as command
from livespec_orchestrator_beads_fabro.effects import _incident_entry_writer as writer
from livespec_orchestrator_beads_fabro.effects import _incident_genesis_recovery as recovery
from livespec_orchestrator_beads_fabro.errors import BeadsCommandError
from livespec_orchestrator_beads_fabro.incident_authority import (
    AuthorityRefusal,
    FilingReceipt,
    IncidentReading,
    file_incident,
    publish_incident_genesis,
    read_incident_authority,
    require_current_generation,
)
from livespec_orchestrator_beads_fabro.types import StoreConfig

REPOSITORY = "owner/repository"
ITEM = "test-incident"
PREFIX = "test"
REF = "refs/heads/incident/test-incident-attempt-1"
PRINCIPAL = "operator:alice"
ROOT = "fake-wisp-8"
SUCCESSOR = "fake-wisp-9"


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
            owner=PRINCIPAL,
            base="a" * 40,
            head="b" * 40,
            pr_number=0,
            landed_commits=[],
            landed_trees=[],
            original_paths=["app.py"],
            deferred_work=["normal-factory-proof"],
            repayment_required=True,
            carrier=dict(
                state="branch-reserved", target_ref=REF, input_parent="a" * 40, staged_tree="c" * 40
            ),
        )
        | changes
    )


def _request(*, claim: str) -> GenesisRequest:
    request = decode_genesis_request(
        text=_json(dict(schema=1, principal=PRINCIPAL, expected_claim=claim, attempt=_attempt())),
        repository=REPOSITORY,
        item_id=ITEM,
        operation_id="operation-1",
    )
    assert request is not None
    return request


def _ledger(*, status: str = "ready") -> tuple[FakeBeadsClient, str]:
    client = FakeBeadsClient()
    client.create_issue(
        draft=IssueDraft(
            issue_id=ITEM,
            issue_type="bug",
            title="incident",
            description="behavior",
            assignee=None,
            created_at="2026-11-06T00:00:00Z",
        )
    )
    token = create_claim_token(client=client)
    client.update_issue(
        issue_id=ITEM,
        status=status,
        metadata={CLAIM_TOKEN_METADATA_KEY: token},
        names_claim_token=True,
    )
    return client, token


def _filing_text(**changes: Any) -> str:
    return _json(
        dict(
            schema=1,
            repository=REPOSITORY,
            principal=PRINCIPAL,
            operation_id="filing-1",
            title="checkout returns 500",
            impact="every order fails",
            scope="payments",
            behavioral_intent="orders complete",
        )
        | changes
    )


def _code(result: object) -> str:
    assert isinstance(result, AuthorityRefusal)
    return result.code


@pytest.mark.parametrize(
    "text",
    [
        "[]",
        _json({"schema": 1}),
        _filing_text(schema="1"),
        _filing_text(schema=2),
        _filing_text(scope=" "),
        json.dumps(json.loads(_filing_text()), indent=1),
    ],
)
def test_a_filing_that_is_not_canonical_and_complete_does_not_decode(text: str) -> None:
    assert decode_filing_request(text=text) is None


@pytest.mark.parametrize(
    "metadata",
    [
        {},
        {"incident_filing": "x"},
        {"incident_filing": {"operation_id": "", "request_digest": "d"}},
        {"incident_filing": {"operation_id": "op"}},
    ],
)
def test_an_item_without_a_complete_filing_record_is_not_a_filed_incident(
    metadata: dict[str, Any],
) -> None:
    assert filing_identity(record={"id": "x", "metadata": metadata}) is None


@pytest.mark.parametrize(
    ("value", "valid"),
    [
        (None, True),
        ("x", False),
        ({"status": "ready"}, False),
        ({"status": 1, "assignee": None, "dispatch_claim": None}, False),
        ({"status": "ready", "assignee": "fabro", "dispatch_claim": {"run_id": "r"}}, True),
    ],
)
def test_a_retained_prior_claim_is_exactly_the_three_facts_entry_records(
    *, value: object, valid: bool
) -> None:
    assert prior_claim_valid(value=value) is valid


def test_a_fence_retaining_a_malformed_prior_claim_is_not_a_fence() -> None:
    client, token = _ledger()
    fence = genesis_fence(request=_request(claim=token), root_token_id=ROOT, successor=SUCCESSOR)
    row = json.loads(genesis_fence_reason(fence=fence, closed_at="2026-11-06T00:00Z"))
    assert decode_genesis_fence(reason=_json(row)) == fence
    row["incident"]["prior_claim"] = {"status": "ready"}
    assert decode_genesis_fence(reason=_json(row)) is None


def test_a_legacy_attempt_without_a_carrier_cannot_select_one() -> None:
    client, token = _ledger()
    assert isinstance(
        publish_incident_genesis(client=client, request=_request(claim=token), claim_tokens=True),
        GenesisReceipt,
    )
    reading = read_incident_authority(
        client=client,
        repository=REPOSITORY,
        item_id=ITEM,
        query={
            k: _attempt()[k] for k in ("attempt_id", "phase", "operation_id", "generation", "owner")
        },
    )
    assert isinstance(reading, IncidentReading)
    legacy = replace(reading, attempt=replace(reading.attempt, carrier=None))
    assert _code(select_carrier(reading=legacy)) == "incident-carrier-unsupported"


def test_a_filed_item_that_lost_its_claim_token_is_refused_on_retry() -> None:
    client = FakeBeadsClient()
    request = decode_filing_request(text=_filing_text())
    assert request is not None
    receipt = file_incident(client=client, prefix=PREFIX, request=request, claim_tokens=True)
    assert isinstance(receipt, FilingReceipt)
    client.update_issue(
        issue_id=receipt.item_id,
        metadata={CLAIM_TOKEN_METADATA_KEY: " "},
        names_claim_token=True,
    )
    again = file_incident(client=client, prefix=PREFIX, request=request, claim_tokens=True)
    assert (_code(again), again.detail) == ("incident-filing-claim-token-missing", receipt.item_id)


def test_a_create_that_named_no_token_refuses_rather_than_filing_an_unwritable_item(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = FakeBeadsClient()
    request = decode_filing_request(text=_filing_text())
    assert request is not None

    def bare(*, client: FakeBeadsClient, draft: IssueDraft, names_token: bool) -> None:
        del names_token
        _ = client.create_issue(draft=draft)

    monkeypatch.setattr(writer, "create_issue_naming_first_claim_token", bare)
    assert _code(
        file_incident(client=client, prefix=PREFIX, request=request, claim_tokens=True)
    ) == ("incident-filing-claim-token-missing")


def test_a_tenant_outage_during_filing_is_unavailable_not_absence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = FakeBeadsClient()
    request = decode_filing_request(text=_filing_text())
    assert request is not None

    def outage() -> list[dict[str, Any]]:
        raise BeadsCommandError(command="bd list", exit_code=1, stderr="gone")

    monkeypatch.setattr(client, "list_issues", outage)
    assert _code(
        file_incident(client=client, prefix=PREFIX, request=request, claim_tokens=True)
    ) == ("incident-filing-unavailable")


def test_the_generation_gate_passes_other_refusals_through_and_never_invents_a_history() -> None:
    client, token = _ledger()
    assert isinstance(
        publish_incident_genesis(client=client, request=_request(claim=token), claim_tokens=True),
        GenesisReceipt,
    )
    reading = read_incident_authority(
        client=client,
        repository=REPOSITORY,
        item_id=ITEM,
        query={
            k: _attempt()[k] for k in ("attempt_id", "phase", "operation_id", "generation", "owner")
        },
    )
    assert isinstance(reading, IncidentReading)
    never = replace(reading, attempt=replace(reading.attempt, attempt_id="attempt-9"))
    assert _code(require_current_generation(client=client, observed=never)) == (
        "incident-authority-identity-mismatch"
    )
    elsewhere = replace(reading, attempt=replace(reading.attempt, item_id="other"))
    assert _code(require_current_generation(client=client, observed=elsewhere)) == (
        "incident-authority-unavailable"
    )


def test_a_recovered_root_whose_prior_claim_moved_on_reports_the_fence_lost() -> None:
    client, token = _ledger()
    request = _request(claim=token)
    item = client.show_issue(issue_id=ITEM)
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
    fence = genesis_fence(
        request=request,
        root_token_id=root,
        successor=successor,
        prior_claim=prior_claim(record=item),
    )
    client.close_issue_without_verdict(
        issue_id=token, reason=genesis_fence_reason(fence=fence, closed_at="2026-11-06T00:00Z")
    )
    # Another writer moved the row before this entry's lost takeover was remade.
    client.update_issue(issue_id=ITEM, status="acceptance")
    observations = {(ITEM, token, successor): 0.0}
    result = publish_incident_genesis(
        client=client,
        request=request,
        claim_tokens=True,
        clock=lambda: 200.0,
        observations=observations,
    )
    assert _code(result) == "incident-genesis-fence-lost"
    assert "claim-changed" in result.detail
    assert client.show_issue(issue_id=ITEM)["status"] == "acceptance"


def _cli(action: str, repo: Path, *extra: str) -> list[str]:
    return [
        action,
        *extra,
        "--repo",
        str(repo),
        "--repository",
        REPOSITORY,
        "--operation",
        "operation-1",
        "--owner",
        PRINCIPAL,
    ]


def _config(tmp_path: Path, value: str) -> StoreConfig:
    _ = (tmp_path / ".livespec.jsonc").write_text(
        '{"livespec-orchestrator-beads-fabro":{"dispatcher":{"claim_tokens":' + value + "}}}",
        encoding="utf-8",
    )
    return StoreConfig(
        tenant=PREFIX,
        prefix=PREFIX,
        server_user=PREFIX,
        database=PREFIX,
        bd_path="bd",
        fake=True,
        repo_root=tmp_path,
    )


@pytest.mark.parametrize(
    "argv",
    [
        ["file-incident", "--filing-json", "{}", "--item", ITEM],
        ["read-current", "--item", ITEM, "--attempt", "attempt-1", "--phase", "repair"],
    ],
)
def test_the_item_identity_belongs_to_every_action_but_a_filing(
    argv: list[str], tmp_path: Path
) -> None:
    with pytest.raises(SystemExit):
        _ = command.main(argv=_cli(argv[0], tmp_path, *argv[1:]))


def test_a_filing_refuses_an_unreadable_cutover_and_the_off_cutover_by_name(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    client = FakeBeadsClient()
    monkeypatch.setattr(command, "make_beads_client", lambda **_kwargs: client)
    text = _filing_text(operation_id="operation-1")
    unreadable_config = _config(tmp_path, '"yes"')
    monkeypatch.setattr(command, "store_config", lambda **_kwargs: unreadable_config)
    assert command.main(argv=_cli("file-incident", tmp_path, "--filing-json", text)) == 78
    unreadable = json.loads(capsys.readouterr().out)["result"]
    assert (unreadable["code"], "unreadable" in unreadable["detail"]) == (
        "incident-genesis-capability-unavailable",
        True,
    )
    off_config = _config(tmp_path, "false")
    monkeypatch.setattr(command, "store_config", lambda **_kwargs: off_config)
    assert command.main(argv=_cli("file-incident", tmp_path, "--filing-json", text)) == 78
    off = json.loads(capsys.readouterr().out)["result"]
    assert (off["code"], "no item was filed" in off["detail"]) == (
        "incident-genesis-capability-unavailable",
        True,
    )
    assert client.list_issues() == []


def test_a_one_shot_entry_waits_out_a_pending_transition_once_before_its_retry(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    client, token = _ledger()
    request = _request(claim=token)
    root = client.create_no_history_issue(title=TOKEN_TITLE, description="authority")
    current = client.create_no_history_issue(title=TOKEN_TITLE, description="authority")
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
    fence = genesis_fence(
        request=request,
        root_token_id=root,
        successor=create_claim_token(client=client),
        prior_claim=prior_claim(record=client.show_issue(issue_id=ITEM)),
    )
    client.close_issue_without_verdict(
        issue_id=token, reason=genesis_fence_reason(fence=fence, closed_at="2026-11-06T00:00Z")
    )
    waits: list[str] = []

    class _Wait:
        def wait_out(self) -> None:
            waits.append("waited")

    monkeypatch.setattr(command, "TakeoverWait", _Wait)
    monkeypatch.setattr(recovery, "TRANSITION_OBSERVATIONS", {})
    config = _config(tmp_path, "true")
    monkeypatch.setattr(command, "store_config", lambda **_kwargs: config)
    monkeypatch.setattr(command, "make_beads_client", lambda **_kwargs: client)
    genesis_json = _json(
        dict(schema=1, principal=PRINCIPAL, expected_claim=token, attempt=_attempt())
    )
    status = command.main(
        argv=[
            *_cli("publish-genesis", tmp_path, "--genesis-json", genesis_json),
            "--item",
            ITEM,
            "--attempt",
            "attempt-1",
            "--phase",
            "repair",
            "--generation",
            "1",
        ]
    )
    reply = json.loads(capsys.readouterr().out)
    # On the real clock the wait returned at once, so the retry is still pending.
    assert (status, reply["result"]["code"], waits) == (
        78,
        "incident-genesis-claim-transition-pending",
        ["waited"],
    )
    assert client.show_issue(issue_id=ITEM)["metadata"][CLAIM_TOKEN_METADATA_KEY] == token


def test_a_second_operation_files_its_own_item_beside_an_earlier_one() -> None:
    client = FakeBeadsClient()
    first = decode_filing_request(text=_filing_text())
    second = decode_filing_request(text=_filing_text(operation_id="filing-2", title="other"))
    assert first is not None and second is not None
    one = file_incident(client=client, prefix=PREFIX, request=first, claim_tokens=True)
    two = file_incident(client=client, prefix=PREFIX, request=second, claim_tokens=True)
    assert isinstance(one, FilingReceipt) and isinstance(two, FilingReceipt)
    assert one.item_id != two.item_id and two.recovered is False
    assert len(client.list_issues()) == 2
