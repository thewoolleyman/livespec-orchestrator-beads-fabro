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
from livespec_orchestrator_beads_fabro._incident_authority_types import IncidentAttempt
from livespec_orchestrator_beads_fabro._incident_recovery_plan import (
    RECOVERY_MARKER,
    recovery_comment,
)
from livespec_orchestrator_beads_fabro._store_claim_tokens import create_claim_token
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandResult
from livespec_orchestrator_beads_fabro.commands._incident_provenance import receipts_from_history
from livespec_orchestrator_beads_fabro.incident_authority import (
    IncidentReading,
    read_incident_authority,
)
from livespec_orchestrator_beads_fabro.incident_completion import (
    DRILL_CLOSED_OBLIGATION,
    IncidentCompletion,
    IncidentCompletionEvidence,
    complete_incident,
    read_incident_standing,
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


def _drill_closed_attempt() -> IncidentAttempt:
    return IncidentAttempt(
        repository=REPOSITORY,
        item_id=ITEM,
        attempt_id="drill-1",
        phase="drill-closed",
        operation_id="drill-1#drill-close",
        generation=2,
        owner="operator:alice",
        base="a" * 40,
        head="b" * 40,
        pr_number=7,
        landed_commits=("c" * 40,),
        landed_trees=("d" * 40,),
        original_paths=("app.py",),
        deferred_work=("normal-factory-proof",),
        repayment_required=False,
    )


def test_a_drill_closed_chain_receipts_owe_no_repayment() -> None:
    history = (_drill_closed_attempt(),)

    assert [
        receipt.repayment_outstanding for receipt in receipts_from_history(history=history)
    ] == [False]


def test_a_drill_closed_incident_is_never_completed_to_closed(tmp_path: Path) -> None:
    module = importlib.import_module("livespec_orchestrator_beads_fabro.incident_drill_close")
    client, reading = _seed(snapshot=_attempt())
    _ = module.close_drill(
        client=client, reading=reading, runner=_Forge(), repo=tmp_path, repository=REPOSITORY
    )

    standing = read_incident_standing(client=client, item_id=ITEM)
    completion = complete_incident(
        client=client, item_id=ITEM, evidence=IncidentCompletionEvidence()
    )

    assert standing.outstanding == (DRILL_CLOSED_OBLIGATION,)
    assert isinstance(completion, IncidentCompletion)
    assert (completion.recorded, completion.outstanding) == (False, (DRILL_CLOSED_OBLIGATION,))
    assert read_incident_standing(client=client, item_id=ITEM).history[-1].phase == "drill-closed"


class _CompareForge:
    def __init__(self) -> None:
        self.compared: list[str] = []

    def run(self, *, argv: list[str], **_: object) -> CommandResult:
        if argv[:2] == ["gh", "api"]:
            self.compared.append(argv[2])
            return CommandResult(exit_code=0, stdout=_json({"behind_by": 1}), stderr="")
        return _Forge().run(argv=argv)


def test_only_well_formed_revert_receipts_name_a_commit_to_compare(tmp_path: Path) -> None:
    module = importlib.import_module("livespec_orchestrator_beads_fabro.incident_drill_close")
    client, reading = _seed(snapshot=_attempt())
    base = {"schema": 1, "item_id": ITEM, "repayment_owed": True}
    for record in (
        base | {"kind": "recovery-request", "receipt": {"revert_commit": "1" * 40}},
        base | {"kind": "revert-receipt", "receipt": {"receipt_id": "no-commit"}},
        base | {"kind": "revert-receipt", "resolution": "not-a-mapping"},
        base | {"kind": "revert-receipt", "receipt": {"revert_commit": "2" * 40}},
        base | {"kind": "revert-receipt", "resolution": {"revert_commit": "2" * 40}},
    ):
        client.add_comment(issue_id=ITEM, body=recovery_comment(record=record))
    client.add_comment(issue_id=ITEM, body=RECOVERY_MARKER + "[]")
    forge = _CompareForge()

    closed = module.close_drill(
        client=client, reading=reading, runner=forge, repo=tmp_path, repository=REPOSITORY
    )

    assert closed.reading.attempt.phase == "drill-closed"
    assert forge.compared == [f"repos/{REPOSITORY}/compare/{'2' * 40}...master"]


def test_drill_evidence_module_retains_revert_receipt_commits() -> None:
    """The extraction seam retains a revert commit for the fresh forge comparison."""
    evidence = importlib.import_module("livespec_orchestrator_beads_fabro._incident_drill_evidence")
    client, reading = _seed(snapshot=_attempt())
    client.add_comment(
        issue_id=ITEM,
        body=recovery_comment(
            record={
                "schema": 1,
                "kind": "revert-receipt",
                "repository": REPOSITORY,
                "item_id": ITEM,
                "receipt": {"revert_commit": "e" * 40},
            }
        ),
    )

    assert evidence.recorded_commits(client=client, item_id=ITEM, history=(reading.attempt,)) == (
        ("revert", "e" * 40),
    )


def test_drill_evidence_module_retains_rollback_resolution_commit() -> None:
    """A retained rollback-conflict resolution is equally master-reachability evidence."""
    evidence = importlib.import_module("livespec_orchestrator_beads_fabro._incident_drill_evidence")
    client, reading = _seed(snapshot=_attempt())
    client.add_comment(
        issue_id=ITEM,
        body=recovery_comment(
            record={
                "schema": 1,
                "kind": "revert-receipt",
                "repository": REPOSITORY,
                "item_id": ITEM,
                "resolution": {"revert_commit": "f" * 40},
            }
        ),
    )

    assert evidence.recorded_commits(client=client, item_id=ITEM, history=(reading.attempt,)) == (
        ("revert", "f" * 40),
    )


def test_drill_evidence_module_retains_landed_and_revert_commits() -> None:
    """The extraction keeps every master-reachability candidate."""
    evidence = importlib.import_module("livespec_orchestrator_beads_fabro._incident_drill_evidence")
    client, reading = _seed(snapshot=_attempt(landed_commits=["d" * 40], landed_trees=["f" * 40]))
    client.add_comment(
        issue_id=ITEM,
        body=recovery_comment(
            record={
                "schema": 1,
                "kind": "revert-receipt",
                "repository": REPOSITORY,
                "item_id": ITEM,
                "receipt": {"revert_commit": "e" * 40},
            }
        ),
    )

    assert evidence.recorded_commits(client=client, item_id=ITEM, history=(reading.attempt,)) == (
        ("landed", "d" * 40),
        ("revert", "e" * 40),
    )
