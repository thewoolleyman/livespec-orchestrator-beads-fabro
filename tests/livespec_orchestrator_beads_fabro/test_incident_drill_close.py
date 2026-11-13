"""Recorded scratch-branch drills close only through the authority writer.

Scenario: a recorded scratch-branch drill closes through the drill-close action
and a master incident is refused (bd-ib-z7ckf4).
"""

from __future__ import annotations

import importlib
import json
from pathlib import Path
from typing import Any

from livespec_orchestrator_beads_fabro._beads_client import FakeBeadsClient, IssueDraft
from livespec_orchestrator_beads_fabro._incident_authority_payload import (
    GENESIS_MARKER,
    TOKEN_TITLE,
    TRANSITION_MARKER,
)
from livespec_orchestrator_beads_fabro._store_claim_tokens import create_claim_token
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandResult
from livespec_orchestrator_beads_fabro.incident_authority import (
    IncidentReading,
    read_incident_authority,
)

REPOSITORY = "owner/repository"
ITEM = "bd-ib-drill"
_SCRATCH = "refs/heads/incident-scratch/bd-ib-drill"


def _json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _attempt(**changes: Any) -> dict[str, Any]:
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
            "target_ref": _SCRATCH,
            "input_parent": "a" * 40,
            "staged_tree": "c" * 40,
            "remote_head": "b" * 40,
        },
    } | changes


def _seed(*, snapshot: dict[str, Any]) -> tuple[FakeBeadsClient, IncidentReading]:
    client = FakeBeadsClient()
    client.create_issue(
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
        + _json({"schema": 1, "repository": REPOSITORY, "item_id": ITEM, "root_token_id": root}),
    )
    client.close_issue_without_verdict(
        issue_id=root,
        reason=TRANSITION_MARKER
        + _json(
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
    claim = create_claim_token(client=client)
    client.update_issue(
        issue_id=ITEM,
        status="active",
        metadata={"dispatch_claim_token": claim},
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
    def run(self, *, argv: list[str], **_: object) -> CommandResult:
        if argv[:3] == ["gh", "pr", "view"]:
            return CommandResult(
                exit_code=0,
                stdout=_json(
                    {"number": 7, "state": "MERGED", "baseRefName": "incident-scratch/bd-ib-drill"}
                ),
                stderr="",
            )
        raise AssertionError(argv)  # pragma: no cover - fixture contract guard


def test_a_recorded_scratch_branch_drill_closes_done_without_repayment(tmp_path: Path) -> None:
    module_path = (
        Path(__file__).parents[2]
        / ".claude-plugin/scripts/livespec_orchestrator_beads_fabro/incident_drill_close.py"
    )
    assert module_path.is_file()
    module = importlib.import_module("livespec_orchestrator_beads_fabro.incident_drill_close")
    client, reading = _seed(snapshot=_attempt())

    closed = module.close_drill(
        client=client,
        reading=reading,
        runner=_Forge(),
        repo=tmp_path,
        repository=REPOSITORY,
    )

    assert (closed.reading.attempt.phase, closed.lifecycle_state, closed.repayment_outstanding) == (
        "drill-closed",
        "done",
        False,
    )
    assert client.show_issue(issue_id=ITEM)["status"] == "done"
