"""Refusal and reader edges for the drill-close authority action."""

from __future__ import annotations

import json
from argparse import Namespace
from dataclasses import replace
from pathlib import Path
from typing import Any

from livespec_orchestrator_beads_fabro._beads_client import FakeBeadsClient, IssueDraft
from livespec_orchestrator_beads_fabro._incident_authority_payload import (
    GENESIS_MARKER,
    TOKEN_TITLE,
    TRANSITION_MARKER,
)
from livespec_orchestrator_beads_fabro._incident_authority_types import (
    AuthorityRefusal,
    IncidentReading,
)
from livespec_orchestrator_beads_fabro._store_claim_tokens import create_claim_token
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandResult
from livespec_orchestrator_beads_fabro.commands._incident_authority_lifecycle import (
    run_lifecycle_action,
)
from livespec_orchestrator_beads_fabro.commands._incident_provenance import receipts_from_history
from livespec_orchestrator_beads_fabro.incident_authority import (
    commit_incident_transition,
    read_incident_authority,
)
from livespec_orchestrator_beads_fabro.incident_completion import (
    DRILL_CLOSED_OBLIGATION,
    IncidentCompletionEvidence,
    completion_obligations,
)
from livespec_orchestrator_beads_fabro.incident_drill_close import DrillClose, close_drill

REPOSITORY = "owner/repository"
ITEM = "bd-ib-drill-cases"
SCRATCH = "refs/heads/incident-scratch/bd-ib-drill-cases"


def encode(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def attempt(**changes: Any) -> dict[str, Any]:
    return {
        "repository": REPOSITORY,
        "item_id": ITEM,
        "attempt_id": "drill-1",
        "phase": "reverting",
        "operation_id": "drill-1#reverting",
        "generation": 1,
        "owner": "operator:alice",
        "base": "a" * 40,
        "head": "b" * 40,
        "pr_number": 7,
        "landed_commits": [],
        "landed_trees": [],
        "original_paths": ["app.py"],
        "deferred_work": ["normal-factory-proof"],
        "repayment_required": True,
        "carrier": {
            "state": "pr-bound",
            "target_ref": SCRATCH,
            "input_parent": "a" * 40,
            "staged_tree": "c" * 40,
            "remote_head": "b" * 40,
        },
    } | changes


def seed(*, snapshot: dict[str, Any]) -> tuple[FakeBeadsClient, IncidentReading]:
    client = FakeBeadsClient()
    _ = client.create_issue(
        draft=IssueDraft(
            issue_id=ITEM,
            issue_type="bug",
            title="drill",
            description="recorded drill",
            assignee="operator:alice",
            created_at="2026-11-13T00:00:00Z",
        )
    )
    root = client.create_no_history_issue(title=TOKEN_TITLE, description="authority root")
    token = client.create_no_history_issue(title=TOKEN_TITLE, description="authority token")
    client.add_comment(
        issue_id=ITEM,
        body=GENESIS_MARKER
        + encode({"schema": 1, "repository": REPOSITORY, "item_id": ITEM, "root_token_id": root}),
    )
    client.close_issue_without_verdict(
        issue_id=root,
        reason=TRANSITION_MARKER
        + encode(
            {
                "schema": 1,
                "repository": REPOSITORY,
                "item_id": ITEM,
                "prior_token_id": root,
                "next_token_id": token,
                "attempt": snapshot,
            }
        ),
    )
    client.update_issue(
        issue_id=ITEM,
        status="active",
        metadata={"dispatch_claim_token": create_claim_token(client=client)},
        names_claim_token=True,
    )
    reading = read_incident_authority(
        client=client,
        repository=REPOSITORY,
        item_id=ITEM,
        query={
            key: snapshot[key]
            for key in ("attempt_id", "phase", "operation_id", "generation", "owner")
        },
    )
    assert isinstance(reading, IncidentReading)
    return client, reading


class _Forge:
    def __init__(self, *, result: CommandResult) -> None:
        self.result = result

    def run(self, *, argv: list[str], **_: object) -> CommandResult:
        if argv[:3] == ["gh", "pr", "view"]:
            return self.result
        raise AssertionError(argv)


def _unchanged(
    *, client: FakeBeadsClient, reading: IncidentReading, before: dict[str, object]
) -> None:
    after = client.show_issue(issue_id=ITEM)
    assert (after["status"], after["assignee"]) == (before["status"], before["assignee"])
    assert reading.attempt.generation == 1


def test_master_based_carrier_is_refused_without_a_write(tmp_path: Path) -> None:
    client, reading = seed(snapshot=attempt())
    before = client.show_issue(issue_id=ITEM)
    refused = close_drill(
        client=client,
        reading=reading,
        runner=_Forge(
            result=CommandResult(
                exit_code=0,
                stdout=encode({"number": 7, "state": "MERGED", "baseRefName": "master"}),
                stderr="",
            )
        ),
        repo=tmp_path,
        repository=REPOSITORY,
    )
    assert isinstance(refused, AuthorityRefusal)
    assert (refused.code, SCRATCH in refused.detail) == (
        "incident-not-a-recorded-drill",
        True,
    )
    _unchanged(client=client, reading=reading, before=before)


def test_missing_carrier_is_refused_without_a_write(tmp_path: Path) -> None:
    client, reading = seed(
        snapshot=attempt(
            phase="repair",
            carrier={
                "state": "branch-reserved",
                "target_ref": SCRATCH,
                "input_parent": "a" * 40,
                "staged_tree": "c" * 40,
            },
            pr_number=0,
        )
    )
    before = client.show_issue(issue_id=ITEM)
    refused = close_drill(
        client=client,
        reading=reading,
        runner=_Forge(result=CommandResult(exit_code=1, stdout="", stderr="must not read forge")),
        repo=tmp_path,
        repository=REPOSITORY,
    )
    assert isinstance(refused, AuthorityRefusal)
    assert refused.code == "incident-not-a-recorded-drill"
    _unchanged(client=client, reading=reading, before=before)


def test_unreadable_forge_evidence_is_refused_without_a_write(tmp_path: Path) -> None:
    client, reading = seed(snapshot=attempt())
    before = client.show_issue(issue_id=ITEM)
    refused = close_drill(
        client=client,
        reading=reading,
        runner=_Forge(result=CommandResult(exit_code=1, stdout="", stderr="down")),
        repo=tmp_path,
        repository=REPOSITORY,
    )
    assert isinstance(refused, AuthorityRefusal)
    assert refused.code == "incident-drill-evidence-unavailable"
    _unchanged(client=client, reading=reading, before=before)


def test_generic_transition_cannot_write_the_drill_close_phase() -> None:
    client, reading = seed(snapshot=attempt())
    successor = replace(
        reading.attempt,
        phase="drill-closed",
        operation_id="drill-1#drill-close",
        generation=2,
        repayment_required=False,
    )
    refused = commit_incident_transition(client=client, observed=reading, successor=successor)
    assert isinstance(refused, AuthorityRefusal)
    assert refused.code == "incident-drill-close-requires-action"


def test_drill_close_is_a_lifecycle_action_and_never_incident_completion(tmp_path: Path) -> None:
    client, reading = seed(snapshot=attempt())
    args = Namespace(action="drill-close", repo=tmp_path, repository=REPOSITORY)
    closed = run_lifecycle_action(
        args=args,
        client=client,
        reading=reading,
        runner=_Forge(
            result=CommandResult(
                exit_code=0,
                stdout=encode(
                    {"number": 7, "state": "MERGED", "baseRefName": "incident-scratch/x"}
                ),
                stderr="",
            )
        ),
    )
    assert isinstance(closed, DrillClose)
    assert closed.reading.attempt.phase == "drill-closed"
    assert completion_obligations(
        history=(closed.reading.attempt,), evidence=IncidentCompletionEvidence()
    ) == (DRILL_CLOSED_OBLIGATION,)
    receipt_attempt = replace(closed.reading.attempt, landed_commits=("c" * 40,))
    assert [
        receipt.repayment_outstanding
        for receipt in receipts_from_history(history=(receipt_attempt,))
    ] == [False]
