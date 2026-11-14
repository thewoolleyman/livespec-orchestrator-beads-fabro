"""Refusal and reader edges for the drill-close authority action."""

from __future__ import annotations

import json
from argparse import Namespace
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest
from livespec_orchestrator_beads_fabro import incident_drill_close
from livespec_orchestrator_beads_fabro._beads_client import FakeBeadsClient, IssueDraft
from livespec_orchestrator_beads_fabro._incident_authority_payload import (
    GENESIS_MARKER,
    TOKEN_TITLE,
    TRANSITION_MARKER,
)
from livespec_orchestrator_beads_fabro._incident_authority_types import (
    AuthorityRefusal,
    IncidentAttempt,
    IncidentReading,
)
from livespec_orchestrator_beads_fabro._incident_drill_evidence import recorded_drill_evidence
from livespec_orchestrator_beads_fabro._incident_recovery_plan import (
    RECOVERY_MARKER,
    recovery_comment,
)
from livespec_orchestrator_beads_fabro._store_claim_tokens import (
    ClaimChangeResult,
    create_claim_token,
)
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

    def run(self, *, argv: list[str], **kwargs: object) -> CommandResult:
        del argv, kwargs
        return self.result


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


class _EvidenceForge:
    def __init__(self, *, pr: CommandResult, comparison: CommandResult) -> None:
        self.pr = pr
        self.comparison = comparison
        self.comparisons: list[str] = []

    def run(self, *, argv: list[str], **_: object) -> CommandResult:
        if argv[:3] == ["gh", "pr", "view"]:
            return self.pr
        self.comparisons.append(argv[2])
        return self.comparison


def _merged(*, base: str = "incident-scratch/bd-ib-drill-cases") -> CommandResult:
    return CommandResult(
        exit_code=0,
        stdout=encode({"number": 7, "state": "MERGED", "baseRefName": base}),
        stderr="",
    )


def test_drill_close_refuses_incomplete_or_landed_evidence(tmp_path: Path) -> None:
    incomplete_client, incomplete_reading = seed(snapshot=attempt())
    incomplete = close_drill(
        client=incomplete_client,
        reading=incomplete_reading,
        runner=_EvidenceForge(
            pr=CommandResult(exit_code=0, stdout="{}", stderr=""),
            comparison=CommandResult(exit_code=1, stdout="", stderr="unused"),
        ),
        repo=tmp_path,
        repository=REPOSITORY,
    )
    assert isinstance(incomplete, AuthorityRefusal)
    assert incomplete.code == "incident-drill-evidence-unavailable"

    no_carrier = recorded_drill_evidence(
        client=incomplete_client,
        item_id=ITEM,
        history=(
            IncidentAttempt(
                repository=REPOSITORY,
                item_id=ITEM,
                attempt_id="legacy-1",
                phase="reverting",
                operation_id="legacy-1#reverting",
                generation=1,
                owner="operator:alice",
                base="a" * 40,
                head="b" * 40,
                pr_number=7,
                landed_commits=(),
                landed_trees=(),
                original_paths=("app.py",),
                deferred_work=("normal-factory-proof",),
                repayment_required=True,
            ),
        ),
        runner=_EvidenceForge(
            pr=CommandResult(exit_code=1, stdout="", stderr="unused"),
            comparison=CommandResult(exit_code=1, stdout="", stderr="unused"),
        ),
        repo=tmp_path,
        repository=REPOSITORY,
    )
    assert isinstance(no_carrier, AuthorityRefusal)
    assert no_carrier.code == "incident-not-a-recorded-drill"

    landed_client, landed_reading = seed(
        snapshot=attempt(landed_commits=["d" * 40], landed_trees=["e" * 40])
    )
    landed = close_drill(
        client=landed_client,
        reading=landed_reading,
        runner=_EvidenceForge(
            pr=_merged(),
            comparison=CommandResult(exit_code=0, stdout=encode({"behind_by": 0}), stderr=""),
        ),
        repo=tmp_path,
        repository=REPOSITORY,
    )
    assert isinstance(landed, AuthorityRefusal)
    assert (landed.code, "landed commit" in landed.detail) == (
        "incident-not-a-recorded-drill",
        True,
    )


def test_drill_close_refuses_unreadable_or_incomplete_landed_evidence(tmp_path: Path) -> None:
    for comparison in (
        CommandResult(exit_code=1, stdout="", stderr="down"),
        CommandResult(exit_code=0, stdout=encode({"behind_by": -1}), stderr=""),
    ):
        client, reading = seed(snapshot=attempt(landed_commits=["d" * 40], landed_trees=["e" * 40]))
        refused = close_drill(
            client=client,
            reading=reading,
            runner=_EvidenceForge(pr=_merged(), comparison=comparison),
            repo=tmp_path,
            repository=REPOSITORY,
        )
        assert isinstance(refused, AuthorityRefusal)
        assert refused.code == "incident-drill-evidence-unavailable"


def test_drill_close_reads_every_retained_revert_commit_once(tmp_path: Path) -> None:
    client, reading = seed(snapshot=attempt())
    base = {"schema": 1, "repository": REPOSITORY, "item_id": ITEM}
    for record in (
        {"kind": "recovery-request"},
        {"kind": "revert-receipt", "receipt": {"receipt_id": "none"}},
        {"kind": "revert-receipt", "resolution": "not-a-mapping"},
        {"kind": "revert-receipt", "receipt": {"revert_commit": "f" * 40}},
        {"kind": "revert-receipt", "resolution": {"revert_commit": "f" * 40}},
    ):
        client.add_comment(issue_id=ITEM, body=recovery_comment(record=base | record))
    client.add_comment(issue_id=ITEM, body="not an authority record")
    client.add_comment(issue_id=ITEM, body=RECOVERY_MARKER + "[]")
    forge = _EvidenceForge(
        pr=_merged(),
        comparison=CommandResult(exit_code=0, stdout=encode({"behind_by": 1}), stderr=""),
    )

    closed = close_drill(
        client=client, reading=reading, runner=forge, repo=tmp_path, repository=REPOSITORY
    )

    assert isinstance(closed, DrillClose)
    assert forge.comparisons == [f"repos/{REPOSITORY}/compare/{'f' * 40}...master"]


def test_drill_close_recovers_its_same_operation_and_refuses_ineligible_phase(
    tmp_path: Path,
) -> None:
    client, reading = seed(snapshot=attempt())
    forge = _EvidenceForge(
        pr=_merged(),
        comparison=CommandResult(exit_code=0, stdout=encode({"behind_by": 2}), stderr=""),
    )
    closed = close_drill(
        client=client, reading=reading, runner=forge, repo=tmp_path, repository=REPOSITORY
    )
    recovered = close_drill(
        client=client, reading=reading, runner=forge, repo=tmp_path, repository=REPOSITORY
    )
    refused_client, refused_reading = seed(snapshot=attempt(phase="closed"))
    refused = close_drill(
        client=refused_client,
        reading=refused_reading,
        runner=forge,
        repo=tmp_path,
        repository=REPOSITORY,
    )

    assert isinstance(closed, DrillClose)
    assert recovered == closed
    assert closed.reading.attempt.operation_id == "drill-1#drill-close"
    assert isinstance(refused, AuthorityRefusal)
    assert refused.code == "incident-not-a-recorded-drill"


def test_drill_close_returns_history_and_lifecycle_fence_refusals(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    client, reading = seed(snapshot=attempt())
    unavailable = AuthorityRefusal(code="incident-authority-unavailable", detail=ITEM)

    def no_history(**_: object) -> AuthorityRefusal:
        return unavailable

    monkeypatch.setattr(incident_drill_close, "read_history", no_history)
    assert (
        close_drill(
            client=client,
            reading=reading,
            runner=_EvidenceForge(
                pr=_merged(),
                comparison=CommandResult(exit_code=1, stdout="", stderr="unused"),
            ),
            repo=tmp_path,
            repository=REPOSITORY,
        )
        == unavailable
    )

    monkeypatch.undo()
    calls = 0

    def stale_after_close(**_: object) -> IncidentReading | AuthorityRefusal:
        nonlocal calls
        calls += 1
        return (
            reading
            if calls == 1
            else AuthorityRefusal(code="incident-generation-stale", detail=ITEM)
        )

    monkeypatch.setattr(incident_drill_close, "require_current_generation", stale_after_close)
    stale = close_drill(
        client=client,
        reading=reading,
        runner=_EvidenceForge(
            pr=_merged(),
            comparison=CommandResult(exit_code=1, stdout="", stderr="unused"),
        ),
        repo=tmp_path,
        repository=REPOSITORY,
    )
    assert isinstance(stale, AuthorityRefusal)
    assert stale.code == "incident-generation-stale"


def test_drill_close_names_a_claim_change_after_authority_transition(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    client, reading = seed(snapshot=attempt())

    def changed_claim(**_: object) -> ClaimChangeResult:
        return ClaimChangeResult(outcome="claim-changed")

    monkeypatch.setattr(incident_drill_close, "change_claim", changed_claim)
    refused = close_drill(
        client=client,
        reading=reading,
        runner=_EvidenceForge(
            pr=_merged(),
            comparison=CommandResult(exit_code=1, stdout="", stderr="unused"),
        ),
        repo=tmp_path,
        repository=REPOSITORY,
    )

    assert isinstance(refused, AuthorityRefusal)
    assert (refused.code, refused.detail) == (
        "incident-drill-close-lifecycle-refused",
        "claim-changed",
    )
