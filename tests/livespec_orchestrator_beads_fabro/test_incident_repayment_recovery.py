"""The repayment phase recovery refuses by name before it reads or writes the chain.

bd-ib-wz6bsa. The chain-writing cases, and the bind that follows a recovery,
run through the `incident_authority.py` process boundary in
`commands/test_incident_authority_binding.py`. These cases drive
`recover_repayment_phases` directly over an in-memory ledger row, so each
refusal is pinned to the evidence it reads and none touches the chain.
"""

from __future__ import annotations

from typing import Any

import pytest
from livespec_orchestrator_beads_fabro._beads_client import FakeBeadsClient, IssueDraft
from livespec_orchestrator_beads_fabro._incident_authority_payload import decode_attempt
from livespec_orchestrator_beads_fabro._store_dispatch_claim import (
    ClaimStamp,
    claim_stamp_metadata,
)
from livespec_orchestrator_beads_fabro.incident_authority import (
    AuthorityRefusal,
    IncidentReading,
)
from livespec_orchestrator_beads_fabro.incident_repayment_recovery import (
    RECOVERABLE_STATUSES,
    recover_repayment_phases,
)

ITEM = "test-incident"
COMMITTED_TOKEN = "t-1"
CURRENT_TOKEN = "t-2"


def _reading(*, phase: str) -> IncidentReading:
    attempt = decode_attempt(
        value={
            "repository": "owner/repository",
            "item_id": ITEM,
            "attempt_id": "repayment-1",
            "phase": phase,
            "operation_id": f"repayment-1#{phase}",
            "generation": 4,
            "owner": "fabro",
            "base": "d" * 40,
            "head": "d" * 40,
            "pr_number": 0,
            "landed_commits": [],
            "landed_trees": [],
            "original_paths": ["app.py"],
            "deferred_work": [],
            "repayment_required": True,
            "carrier": {
                "state": "branch-reserved",
                "target_ref": "refs/heads/feat/test-incident",
                "input_parent": "a" * 40,
                "staged_tree": "c" * 40,
            },
        }
    )
    assert attempt is not None
    return IncidentReading(
        attempt=attempt,
        committed_token_id=COMMITTED_TOKEN,
        current_token_id=CURRENT_TOKEN,
        is_current=True,
    )


def _item(*, status: str, assignee: str | None, dispatch_id: str | None) -> FakeBeadsClient:
    client = FakeBeadsClient()
    _ = client.create_issue(
        draft=IssueDraft(
            issue_id=ITEM,
            issue_type="bug",
            title="incident",
            description="behavior",
            assignee=None,
            created_at="2026-11-14T00:00:00Z",
        )
    )
    fields: dict[str, Any] = {"status": status, "assignee": assignee}
    if dispatch_id is not None:
        stamp = ClaimStamp(
            dispatch_id=dispatch_id,
            dispatching_host="vps",
            run_id="01RUN",
            factory_name="petri",
            factory_server="http://petri",
        )
        fields["metadata"] = claim_stamp_metadata(stamp=stamp)
    client.update_issue(issue_id=ITEM, **fields)
    return client


def _code(result: object) -> tuple[str, str]:
    assert isinstance(result, AuthorityRefusal), result
    return result.code, result.detail


def test_only_a_claimed_item_is_recoverable() -> None:
    assert frozenset(("active", "acceptance")) == RECOVERABLE_STATUSES


@pytest.mark.parametrize("phase", ["repayment-active", "repair"])
def test_an_attempt_past_repayment_ready_needs_no_recovery_and_reads_no_ledger_row(
    phase: str,
) -> None:
    # No item exists, so any ledger read would fail; the refusal comes first.
    client = FakeBeadsClient()
    code, detail = _code(recover_repayment_phases(client=client, reading=_reading(phase=phase)))
    assert (code, detail) == ("incident-repayment-recovery-not-needed", phase)


@pytest.mark.parametrize("status", ["pending-approval", "ready", "blocked"])
def test_an_item_ordinary_admission_has_not_claimed_is_premature(status: str) -> None:
    client = _item(status=status, assignee="fabro", dispatch_id="01DISPATCH")
    code, detail = _code(
        recover_repayment_phases(client=client, reading=_reading(phase="repayment-admission"))
    )
    assert code == "incident-repayment-recovery-premature"
    assert status in detail
    assert "advance-repayment" in detail


@pytest.mark.parametrize(
    ("assignee", "dispatch_id"),
    [("fabro", None), ("someone", "01DISPATCH"), ("fabro", "incident:holder")],
)
def test_an_item_without_a_factory_claim_is_refused(assignee: str, dispatch_id: str | None) -> None:
    client = _item(status="acceptance", assignee=assignee, dispatch_id=dispatch_id)
    code, detail = _code(
        recover_repayment_phases(client=client, reading=_reading(phase="repayment-ready"))
    )
    assert (code, detail) == ("incident-repayment-claim-missing", ITEM)
