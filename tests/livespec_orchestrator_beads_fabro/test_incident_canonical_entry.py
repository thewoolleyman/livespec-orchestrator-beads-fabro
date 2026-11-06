"""Canonical incident entry keeps one item and fences the factory claim (bd-ib-dzbwaq).

One case per Definition-of-Done bullet, each on public surfaces over the
in-memory tenant with the claim-token cutover committed.
"""

# EXPEDITED_INCIDENT_RESPONSE flag: bd-ib-dzbwaq
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from livespec_orchestrator_beads_fabro._beads_client import FakeBeadsClient, IssueDraft
from livespec_orchestrator_beads_fabro._incident_authority_payload import decode_attempt
from livespec_orchestrator_beads_fabro._incident_genesis import (
    GenesisReceipt,
    GenesisRequest,
    claim_successor,
    decode_genesis_fence,
    decode_genesis_request,
)
from livespec_orchestrator_beads_fabro._store_dispatch_claim import (
    CLAIM_TOKEN_METADATA_KEY,
    ClaimStamp,
    change_claim,
    claim_stamp_from_record,
    claim_stamp_metadata,
    create_claim_token,
)
from livespec_orchestrator_beads_fabro.commands import incident_authority as command
from livespec_orchestrator_beads_fabro.commands._dispatcher_claim_guard import (
    claimed_by_run,
    learning_run,
    status_is,
)
from livespec_orchestrator_beads_fabro.incident_authority import (
    AuthorityRefusal,
    CarrierSelection,
    FilingReceipt,
    IncidentReading,
    carrier_selection,
    commit_incident_transition,
    decode_filing_request,
    file_incident,
    incident_claim_decided,
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
OLD_DISPATCH = "dispatch-7"
OLD_RUN = "01RUN7"
ENTRY_MARKER = "livespec-incident-entry-v1\n"
INCIDENT_CLAIM_KEY = "incident_claim"


def _json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _reserved(**changes: Any) -> dict[str, Any]:
    return (
        dict(state="branch-reserved", target_ref=REF, input_parent="a" * 40, staged_tree="c" * 40)
        | changes
    )


def _attempt(item_id: str = ITEM, **changes: Any) -> dict[str, Any]:
    return (
        dict(
            repository=REPOSITORY,
            item_id=item_id,
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


def _request(*, claim: str, item_id: str = ITEM, **changes: Any) -> GenesisRequest:
    text = _json(
        dict(
            schema=1,
            principal=PRINCIPAL,
            expected_claim=claim,
            attempt=_attempt(item_id, **changes),
        )
    )
    request = decode_genesis_request(
        text=text, repository=REPOSITORY, item_id=item_id, operation_id="operation-1"
    )
    assert request is not None
    return request


def _old_stamp() -> ClaimStamp:
    return ClaimStamp(
        dispatch_id=OLD_DISPATCH,
        dispatching_host="vmi",
        run_id=OLD_RUN,
        factory_name="petri",
        factory_server="https://petri.example",
    )


def _ledger(*, status: str, assignee: str | None, stamped: bool) -> tuple[FakeBeadsClient, str]:
    client = FakeBeadsClient()
    client.create_issue(
        draft=IssueDraft(
            issue_id=ITEM,
            issue_type="bug",
            title="incident",
            description="behavior",
            assignee=assignee,
            created_at="2026-11-06T00:00:00Z",
            labels=["intake:triaged"],
        )
    )
    token = create_claim_token(client=client)
    metadata: dict[str, Any] = {"rank": "a0", CLAIM_TOKEN_METADATA_KEY: token}
    if stamped:
        metadata.update(claim_stamp_metadata(stamp=_old_stamp()))
    client.update_issue(issue_id=ITEM, status=status, metadata=metadata, names_claim_token=True)
    return client, token


def _read(client: FakeBeadsClient, item_id: str = ITEM, **changes: Any) -> IncidentReading:
    reading = read_incident_authority(
        client=client,
        repository=REPOSITORY,
        item_id=item_id,
        query=_query(_attempt(item_id, **changes)),
    )
    assert isinstance(reading, IncidentReading)
    return reading


def _code(result: object) -> str:
    assert isinstance(result, AuthorityRefusal)
    return result.code


def _filing_text(**changes: Any) -> str:
    return _json(
        dict(
            schema=1,
            repository=REPOSITORY,
            principal=PRINCIPAL,
            operation_id="filing-1",
            title="checkout returns 500 on every order",
            impact="every order fails at payment",
            scope="payments service, release 4.2",
            behavioral_intent="an order completes again on the released build",
        )
        | changes
    )


def _file(client: FakeBeadsClient, text: str, *, claim_tokens: bool = True) -> object:
    request = decode_filing_request(text=text)
    assert request is not None
    return file_incident(client=client, prefix=PREFIX, request=request, claim_tokens=claim_tokens)


def test_an_authorized_entry_files_one_identified_item_once_and_records_deferred_admission() -> (
    None
):
    client = FakeBeadsClient()
    assert _code(_file(client, _filing_text(), claim_tokens=False)) == (
        "incident-genesis-capability-unavailable"
    )
    assert client.list_issues() == []
    receipt = _file(client, _filing_text())
    assert isinstance(receipt, FilingReceipt)
    assert receipt.item_id.startswith(PREFIX + "-") and receipt.recovered is False
    item = client.show_issue(issue_id=receipt.item_id)
    assert (item["status"], item["title"]) == ("backlog", "checkout returns 500 on every order")
    assert item["metadata"][CLAIM_TOKEN_METADATA_KEY] == receipt.claim_token_id
    assert item["metadata"]["incident_filing"]["operation_id"] == "filing-1"
    assert "incident:entry" in item["labels"]
    for field in ("every order fails at payment", "payments service", "completes again"):
        assert field in item["description"]
    [comment] = client.list_comments(issue_id=receipt.item_id)
    assert comment["text"].startswith(ENTRY_MARKER)
    record = json.loads(comment["text"][len(ENTRY_MARKER) :])
    assert (record["item_id"], record["operation_id"]) == (receipt.item_id, "filing-1")
    assert record["deferred_to_repayment"] == ["ordinary-admission", "spec-debt"]
    again = _file(client, _filing_text())
    assert isinstance(again, FilingReceipt)
    assert (again.item_id, again.claim_token_id, again.recovered) == (
        receipt.item_id,
        receipt.claim_token_id,
        True,
    )
    assert _code(_file(client, _filing_text(impact="only one region"))) == (
        "incident-operation-conflict"
    )
    assert [row["id"] for row in client.list_issues()] == [receipt.item_id]
    entered = publish_incident_genesis(
        client=client,
        request=_request(claim=receipt.claim_token_id, item_id=receipt.item_id),
        claim_tokens=True,
    )
    assert isinstance(entered, GenesisReceipt)
    assert [row["id"] for row in client.list_issues()] == [receipt.item_id]
    assert _read(client, receipt.item_id).is_current is True


def test_entry_over_a_live_factory_claim_fences_it_through_the_claim_token_and_keeps_history() -> (
    None
):
    client, token = _ledger(status="active", assignee="fabro", stamped=True)
    receipt = publish_incident_genesis(
        client=client, request=_request(claim=token), claim_tokens=True
    )
    assert isinstance(receipt, GenesisReceipt)
    item = client.show_issue(issue_id=ITEM)
    assert (item["status"], item["assignee"]) == ("active", PRINCIPAL)
    assert item["metadata"][CLAIM_TOKEN_METADATA_KEY] == receipt.successor_claim_token_id
    claim = item["metadata"][INCIDENT_CLAIM_KEY]
    assert (claim["operation_id"], claim["generation"], claim["owner"]) == (
        "operation-1",
        1,
        PRINCIPAL,
    )
    assert claim["prior_claim"] == {
        "status": "active",
        "assignee": "fabro",
        "dispatch_claim": claim_stamp_metadata(stamp=_old_stamp())["dispatch_claim"],
    }
    assert claim["factory_cancel"] == "unobserved"
    assert claim["deferred_to_repayment"] == ["ordinary-admission", "spec-debt"]
    stamp = claim_stamp_from_record(record=item)
    assert stamp is not None and stamp.pending is False
    assert (stamp.dispatch_id, stamp.run_id) == (
        "incident:operation-1",
        "incident:" + receipt.root_token_id,
    )
    closed = client.show_issue(issue_id=token)
    fence = decode_genesis_fence(reason=closed["close_reason"])
    assert fence is not None and fence.prior_claim == claim["prior_claim"]
    assert claim_successor(reason=closed["close_reason"]) == receipt.successor_claim_token_id
    assert _read(client).is_current is True
    late_writers = {
        "terminal": claimed_by_run(assignee="fabro", run_id=OLD_RUN, unstamped_ok=True),
        "run-stamp": learning_run(dispatch_id=OLD_DISPATCH, run_id=OLD_RUN),
        "recovery": claimed_by_run(assignee="fabro", run_id=OLD_RUN),
        "admission": status_is(status="ready"),
    }
    for writer, decided in late_writers.items():
        result = change_claim(
            client=client,
            work_item_id=ITEM,
            writer=writer,
            intent="late-factory-write",
            claim_tokens=True,
            status="acceptance",
            still_as_decided=decided,
        )
        assert result.outcome == "claim-changed", writer
    after = client.show_issue(issue_id=ITEM)
    assert (after["status"], after["assignee"]) == ("active", PRINCIPAL)
    assert after["metadata"][CLAIM_TOKEN_METADATA_KEY] == receipt.successor_claim_token_id
    assert client.show_issue(issue_id=receipt.successor_claim_token_id)["status"] == "backlog"


def test_a_queued_item_is_taken_off_the_admission_path_by_the_same_transition() -> None:
    client, token = _ledger(status="ready", assignee=None, stamped=False)
    receipt = publish_incident_genesis(
        client=client, request=_request(claim=token), claim_tokens=True
    )
    assert isinstance(receipt, GenesisReceipt)
    item = client.show_issue(issue_id=ITEM)
    assert (item["status"], item["assignee"]) == ("active", PRINCIPAL)
    assert item["metadata"][INCIDENT_CLAIM_KEY]["prior_claim"] == {
        "status": "ready",
        "assignee": None,
        "dispatch_claim": None,
    }
    admitted = change_claim(
        client=client,
        work_item_id=ITEM,
        writer="dispatcher-admission",
        intent="move-ready-to-active",
        claim_tokens=True,
        status="active",
        assignee="fabro",
        still_as_decided=status_is(status="ready"),
    )
    assert admitted.outcome == "claim-changed"
    assert client.show_issue(issue_id=ITEM)["assignee"] == PRINCIPAL


def _advance(client: FakeBeadsClient, observed: IncidentReading, **changes: Any) -> IncidentReading:
    successor = decode_attempt(value=_attempt(**changes))
    assert successor is not None
    advanced = commit_incident_transition(client=client, observed=observed, successor=successor)
    assert isinstance(advanced, IncidentReading)
    return advanced


def test_claim_recovery_branch_and_pull_request_selection_bind_the_exact_current_carrier() -> None:
    client, token = _ledger(status="ready", assignee=None, stamped=False)
    assert isinstance(
        publish_incident_genesis(client=client, request=_request(claim=token), claim_tokens=True),
        GenesisReceipt,
    )
    reserved = _read(client)
    selection = carrier_selection(client=client, reading=reserved)
    assert selection == CarrierSelection(
        state="branch-reserved", target_ref=REF, remote_head=None, pr_number=None
    )
    decided = incident_claim_decided(operation_id="operation-1", generation=1, owner=PRINCIPAL)
    held = change_claim(
        client=client,
        work_item_id=ITEM,
        writer=PRINCIPAL,
        intent="incident-host-write",
        claim_tokens=True,
        add_labels=["incident:repair"],
        still_as_decided=decided,
    )
    assert held.outcome == "applied"
    assert "incident:repair" in client.show_issue(issue_id=ITEM)["labels"]
    for wrong in (
        incident_claim_decided(operation_id="operation-2", generation=1, owner=PRINCIPAL),
        incident_claim_decided(operation_id="operation-1", generation=2, owner=PRINCIPAL),
        incident_claim_decided(operation_id="operation-1", generation=1, owner="operator:bob"),
    ):
        refused = change_claim(
            client=client,
            work_item_id=ITEM,
            writer=PRINCIPAL,
            intent="incident-host-write",
            claim_tokens=True,
            add_labels=["incident:stale"],
            still_as_decided=wrong,
        )
        assert refused.outcome == "claim-changed"
    assert "incident:stale" not in client.show_issue(issue_id=ITEM)["labels"]
    published = _advance(
        client,
        reserved,
        generation=2,
        operation_id="publish-1",
        carrier=_reserved(state="head-published", remote_head="b" * 40),
    )
    assert carrier_selection(client=client, reading=published) == CarrierSelection(
        state="head-published", target_ref=REF, remote_head="b" * 40, pr_number=None
    )
    bound = _advance(
        client,
        published,
        generation=3,
        operation_id="bind-1",
        pr_number=7,
        carrier=_reserved(state="pr-bound", remote_head="b" * 40),
    )
    assert carrier_selection(client=client, reading=bound) == CarrierSelection(
        state="pr-bound", target_ref=REF, remote_head="b" * 40, pr_number=7
    )
    assert _code(carrier_selection(client=client, reading=published)) == "incident-generation-stale"
    assert _code(carrier_selection(client=client, reading=reserved)) == "incident-generation-stale"


def test_a_stale_generation_is_refused_by_name_before_proof_claim_or_completion() -> None:
    client, token = _ledger(status="ready", assignee=None, stamped=False)
    assert isinstance(
        publish_incident_genesis(client=client, request=_request(claim=token), claim_tokens=True),
        GenesisReceipt,
    )
    first = _read(client)
    assert require_current_generation(client=client, observed=first) == first
    second = _advance(
        client,
        first,
        generation=2,
        operation_id="publish-1",
        carrier=_reserved(state="head-published", remote_head="b" * 40),
    )
    stale = require_current_generation(client=client, observed=first)
    assert (_code(stale), stale.detail) == ("incident-generation-stale", ITEM)
    assert require_current_generation(client=client, observed=second) == second
    completion = decode_attempt(
        value=_attempt(
            generation=2,
            operation_id="complete-1",
            carrier=_reserved(state="head-published", remote_head="b" * 40),
        )
    )
    assert completion is not None
    assert _code(
        commit_incident_transition(client=client, observed=first, successor=completion)
    ) == ("incident-generation-stale")
    transferred = change_claim(
        client=client,
        work_item_id=ITEM,
        writer="repayment",
        intent="return-to-factory",
        claim_tokens=True,
        metadata={
            INCIDENT_CLAIM_KEY: client.show_issue(issue_id=ITEM)["metadata"][INCIDENT_CLAIM_KEY]
            | {"generation": 2, "owner": "factory"}
        },
        still_as_decided=incident_claim_decided(
            operation_id="operation-1", generation=1, owner=PRINCIPAL
        ),
    )
    assert transferred.outcome == "applied"
    consumed = change_claim(
        client=client,
        work_item_id=ITEM,
        writer=PRINCIPAL,
        intent="incident-proof",
        claim_tokens=True,
        add_labels=["incident:proof"],
        still_as_decided=incident_claim_decided(
            operation_id="operation-1", generation=1, owner=PRINCIPAL
        ),
    )
    assert consumed.outcome == "claim-changed"
    assert "incident:proof" not in client.show_issue(issue_id=ITEM)["labels"]


def _cli(action: str, repo: Path, *extra: str) -> list[str]:
    return [
        action,
        *extra,
        "--repo",
        str(repo),
        "--repository",
        REPOSITORY,
        "--operation",
        "filing-1",
        "--owner",
        PRINCIPAL,
    ]


def test_the_process_boundary_files_an_incident_and_reports_its_identity(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    client = FakeBeadsClient()
    _ = (tmp_path / ".livespec.jsonc").write_text(
        '{"livespec-orchestrator-beads-fabro":{"dispatcher":{"claim_tokens":true}}}',
        encoding="utf-8",
    )
    config = StoreConfig(
        tenant=PREFIX,
        prefix=PREFIX,
        server_user=PREFIX,
        database=PREFIX,
        bd_path="bd",
        fake=True,
        repo_root=tmp_path,
    )
    monkeypatch.setattr(command, "store_config", lambda **_kwargs: config)
    monkeypatch.setattr(command, "make_beads_client", lambda **_kwargs: client)
    status = command.main(argv=_cli("file-incident", tmp_path, "--filing-json", _filing_text()))
    reply = json.loads(capsys.readouterr().out)
    assert (status, reply["status"], reply["authorizes_current_effects"]) == (0, "verified", False)
    item_id = reply["result"]["item_id"]
    assert client.show_issue(issue_id=item_id)["status"] == "backlog"
    assert (
        reply["result"]["claim_token_id"]
        == (client.show_issue(issue_id=item_id)["metadata"][CLAIM_TOKEN_METADATA_KEY])
    )
    mismatched = command.main(
        argv=_cli("file-incident", tmp_path, "--filing-json", _filing_text(principal="x"))
    )
    assert (mismatched, json.loads(capsys.readouterr().out)["result"]["code"]) == (
        78,
        "incident-filing-invalid-request",
    )
