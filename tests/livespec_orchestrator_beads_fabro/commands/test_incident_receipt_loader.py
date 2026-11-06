"""The production receipt source feeds the provenance gate and audit from the retained chain."""

# EXPEDITED_INCIDENT_RESPONSE flag: bd-ib-y7ryj3
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from livespec_orchestrator_beads_fabro._beads_client import FakeBeadsClient, IssueDraft
from livespec_orchestrator_beads_fabro._incident_authority_payload import (
    GENESIS_MARKER,
    TOKEN_TITLE,
    TRANSITION_MARKER,
)
from livespec_orchestrator_beads_fabro.commands._incident_provenance import IncidentReceipt
from livespec_orchestrator_beads_fabro.commands._incident_receipt_loader import (
    load_retained_receipts,
    read_retained_receipts,
    refusal_text,
)
from livespec_orchestrator_beads_fabro.incident_authority import AuthorityRefusal

_REPOSITORY = "owner/repository"
_OTHER = "owner/other"
_NOT_A_TOKEN = "incident-1"


def _json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _attempt(*, repository: str, item: str, **changes: Any) -> dict[str, Any]:
    return (
        dict(
            repository=repository,
            item_id=item,
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


def _token(client: FakeBeadsClient) -> str:
    return client.create_no_history_issue(title=TOKEN_TITLE, description="retained authority")


def _chain(
    client: FakeBeadsClient, *, repository: str, item: str, attempts: list[dict[str, Any]]
) -> None:
    client.create_issue(
        draft=IssueDraft(
            issue_id=item,
            issue_type="bug",
            title="incident",
            description="behavior",
            assignee=None,
            created_at="2026-11-04T00:00:00Z",
        )
    )
    token = _token(client)
    client.add_comment(
        issue_id=item,
        body=GENESIS_MARKER
        + _json(dict(schema=1, repository=repository, item_id=item, root_token_id=token)),
    )
    for snapshot in attempts:
        successor = _token(client)
        payload = dict(
            schema=1,
            repository=repository,
            item_id=item,
            prior_token_id=token,
            next_token_id=successor,
            attempt=snapshot,
        )
        client.close_issue_without_verdict(
            issue_id=token, reason=TRANSITION_MARKER + _json(payload)
        )
        token = successor


def _receipt(*, item: str = "incident-1") -> IncidentReceipt:
    return IncidentReceipt(
        repository=_REPOSITORY,
        item_id=item,
        phase="repair",
        pr_number=7,
        head_sha="b" * 40,
        landed_commits=("b" * 40,),
        repayment_required=True,
    )


def test_the_retained_repair_attempt_is_loaded_as_an_exact_repayable_receipt() -> None:
    client = FakeBeadsClient()
    _chain(
        client,
        repository=_REPOSITORY,
        item="incident-1",
        attempts=[_attempt(repository=_REPOSITORY, item="incident-1")],
    )
    assert read_retained_receipts(client=client, repository=_REPOSITORY) == (_receipt(),)


def test_history_survives_a_later_repayment_phase_and_yields_only_repair_receipts() -> None:
    client = FakeBeadsClient()
    _chain(
        client,
        repository=_REPOSITORY,
        item="incident-1",
        attempts=[
            _attempt(repository=_REPOSITORY, item="incident-1"),
            _attempt(
                repository=_REPOSITORY,
                item="incident-1",
                attempt_id="attempt-2",
                phase="repayment-ready",
                operation_id="operation-2",
                generation=2,
            ),
        ],
    )
    assert read_retained_receipts(client=client, repository=_REPOSITORY) == (_receipt(),)


def test_another_repositorys_incident_is_not_loaded_for_this_repository() -> None:
    client = FakeBeadsClient()
    _chain(
        client,
        repository=_OTHER,
        item="incident-2",
        attempts=[_attempt(repository=_OTHER, item="incident-2")],
    )
    assert read_retained_receipts(client=client, repository=_REPOSITORY) == ()


def test_an_empty_tenant_loads_no_receipts() -> None:
    assert read_retained_receipts(client=FakeBeadsClient(), repository=_REPOSITORY) == ()


def test_an_invalid_retained_chain_refuses_rather_than_reading_as_no_receipts() -> None:
    client = FakeBeadsClient()
    _chain(
        client,
        repository=_REPOSITORY,
        item="incident-1",
        attempts=[_attempt(repository=_REPOSITORY, item="incident-1")],
    )
    client.create_issue(
        draft=IssueDraft(
            issue_id="incident-3",
            issue_type="bug",
            title="incident",
            description="behavior",
            assignee=None,
            created_at="2026-11-04T00:00:00Z",
        )
    )
    client.add_comment(
        issue_id="incident-3",
        body=GENESIS_MARKER
        + _json(
            dict(schema=1, repository=_REPOSITORY, item_id="incident-3", root_token_id=_NOT_A_TOKEN)
        ),
    )
    result = read_retained_receipts(client=client, repository=_REPOSITORY)
    assert isinstance(result, AuthorityRefusal)
    assert result.code == "incident-authority-invalid-token"


def test_an_unconfigured_ledger_refuses_by_name(tmp_path: Path) -> None:
    result = load_retained_receipts(repo=tmp_path, repository=_REPOSITORY)
    assert isinstance(result, AuthorityRefusal)
    assert result.code == "incident-authority-unavailable"


def test_the_configured_ledger_is_read_for_its_receipts(tmp_path: Path) -> None:
    _ = (tmp_path / ".livespec.jsonc").write_text(
        json.dumps({"livespec-orchestrator-beads-fabro": {"connection": {"prefix": "test"}}}),
        encoding="utf-8",
    )
    assert load_retained_receipts(repo=tmp_path, repository=_REPOSITORY) == ()


def test_the_refusal_text_names_the_cause_and_the_closed_posture() -> None:
    text = refusal_text(
        refusal=AuthorityRefusal(code="incident-authority-unavailable", detail="down")
    )
    assert "incident-authority-unavailable" in text
    assert "down" in text
    assert "refuses" in text
