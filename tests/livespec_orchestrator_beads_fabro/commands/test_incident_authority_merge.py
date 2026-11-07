"""`record-merge`: the named writer of `master-observation`, and what that generation unlocks.

`SPECIFICATION/contracts.md` section "Expedited incident lifecycle" pairs
`master-observation` with "the exact expedited repair carrier merged", and
`reverting` with "a current incident failure". A real chain records its landed
commits nowhere else, so this module also pins the two readers of that
generation: a merged attempt's first failure reopens from it, and the exact
carrier it names keeps its incident receipt.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest
from livespec_orchestrator_beads_fabro._beads_client import FakeBeadsClient, IssueDraft
from livespec_orchestrator_beads_fabro._incident_authority_payload import (
    attempt_record,
    decode_attempt,
)
from livespec_orchestrator_beads_fabro._incident_authority_types import (
    AuthorityRefusal,
    IncidentAttempt,
    IncidentReading,
)
from livespec_orchestrator_beads_fabro._incident_genesis import decode_genesis_request
from livespec_orchestrator_beads_fabro._store_dispatch_claim import (
    CLAIM_TOKEN_METADATA_KEY,
    create_claim_token,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine_types import CommandResult
from livespec_orchestrator_beads_fabro.commands._incident_authority_lifecycle import (
    run_lifecycle_action,
)
from livespec_orchestrator_beads_fabro.commands._incident_authority_merge import record_merge
from livespec_orchestrator_beads_fabro.commands._incident_provenance import (
    matching_incident_receipt,
    receipts_from_history,
)
from livespec_orchestrator_beads_fabro.incident_authority import (
    commit_incident_transition,
    publish_incident_genesis,
    read_incident_authority,
)
from livespec_orchestrator_beads_fabro.incident_completion import read_incident_standing
from livespec_orchestrator_beads_fabro.incident_normal_repayment import RepaymentEntry
from livespec_orchestrator_beads_fabro.incident_regression_recovery import (
    Finding,
    reopen_for_regression,
)

REPOSITORY = "owner/repository"
ITEM = "test-incident"
OWNER = "operator:alice"
BRANCH = "incident/test-incident-attempt-1"
TARGET_REF = "refs/heads/" + BRANCH
PR = 7
PARENT = "a" * 40
HEAD = "b" * 40
STAGED = "c" * 40
FIRST = "d" * 40
SECOND = "e" * 40
TREE_1 = "1" * 40
TREE_2 = "2" * 40
HEADLINES = ("fix: first", "fix: second")
_IDENTITY = ("attempt_id", "phase", "operation_id", "generation", "owner")


def _json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


@dataclass
class _World:
    """The forge's `gh pr view` reply and the local `git fetch` and `git log` reads."""

    pr: dict[str, object] = field(
        default_factory=lambda: {
            "number": PR,
            "state": "MERGED",
            "headRefName": BRANCH,
            "headRefOid": HEAD,
            "mergeCommit": {"oid": SECOND},
            "commits": [{"messageHeadline": line} for line in HEADLINES],
        }
    )
    calls: list[list[str]] = field(default_factory=list)

    def run(self, *, argv: list[str], **_: object) -> CommandResult:
        self.calls.append(argv)
        if argv[:2] == ["git", "fetch"]:
            return CommandResult(exit_code=0, stdout="", stderr="")
        if argv[:2] == ["git", "log"]:
            rows = (
                "\x00".join((SECOND, TREE_2, FIRST, HEADLINES[1])),
                "\x00".join((FIRST, TREE_1, PARENT, HEADLINES[0])),
            )
            return CommandResult(exit_code=0, stdout="\n".join(rows) + "\n", stderr="")
        return CommandResult(exit_code=0, stdout=json.dumps(self.pr), stderr="")


def _read(client: FakeBeadsClient, attempt: IncidentAttempt) -> IncidentReading:
    found = read_incident_authority(
        client=client,
        repository=REPOSITORY,
        item_id=ITEM,
        query={key: getattr(attempt, key) for key in _IDENTITY},
        historical=True,
    )
    assert isinstance(found, IncidentReading)
    return found


def _head(client: FakeBeadsClient) -> IncidentAttempt:
    return read_incident_standing(client=client, item_id=ITEM).history[-1]


def _transition(
    client: FakeBeadsClient, current: IncidentAttempt, **changes: Any
) -> IncidentAttempt:
    record = json.loads(_json(attempt_record(attempt=current)))
    successor = decode_attempt(value=record | {"generation": current.generation + 1} | changes)
    assert successor is not None
    committed = commit_incident_transition(
        client=client, observed=_read(client, current), successor=successor
    )
    assert isinstance(committed, IncidentReading)
    return committed.attempt


def _genesis(client: FakeBeadsClient) -> IncidentAttempt:
    _ = client.create_issue(
        draft=IssueDraft(
            issue_id=ITEM,
            issue_type="bug",
            title="incident",
            description="behavior",
            assignee=None,
            created_at="2026-11-07T00:00:00Z",
        )
    )
    token = create_claim_token(client=client)
    client.update_issue(
        issue_id=ITEM,
        status="ready",
        metadata={"rank": "a0", CLAIM_TOKEN_METADATA_KEY: token},
        names_claim_token=True,
    )
    attempt = {
        "repository": REPOSITORY,
        "item_id": ITEM,
        "attempt_id": "attempt-1",
        "phase": "repair",
        "operation_id": "operation-1",
        "generation": 1,
        "owner": OWNER,
        "base": PARENT,
        "head": HEAD,
        "pr_number": 0,
        "landed_commits": [],
        "landed_trees": [],
        "original_paths": ["app.py"],
        "deferred_work": ["normal-factory-proof"],
        "repayment_required": True,
        "carrier": {
            "state": "branch-reserved",
            "target_ref": TARGET_REF,
            "input_parent": PARENT,
            "staged_tree": STAGED,
        },
    }
    request = decode_genesis_request(
        text=_json({"schema": 1, "principal": OWNER, "expected_claim": token, "attempt": attempt}),
        repository=REPOSITORY,
        item_id=ITEM,
        operation_id="operation-1",
    )
    assert request is not None
    assert not isinstance(
        publish_incident_genesis(client=client, request=request, claim_tokens=True),
        AuthorityRefusal,
    )
    return _head(client)


def _bound(client: FakeBeadsClient) -> IncidentAttempt:
    """A real chain's shape when the merge happens: a `pr-bound` repair with nothing landed."""
    carrier = {
        "state": "pr-bound",
        "target_ref": TARGET_REF,
        "input_parent": PARENT,
        "staged_tree": STAGED,
        "remote_head": HEAD,
    }
    return _transition(
        client, _genesis(client), operation_id="bind-1", pr_number=PR, carrier=carrier
    )


def _merged(client: FakeBeadsClient) -> IncidentAttempt:
    """The generation record-merge writes, committed through the writer it uses."""
    return _transition(
        client,
        _bound(client),
        phase="master-observation",
        operation_id="attempt-1#master-observation",
        landed_commits=[FIRST, SECOND],
        landed_trees=[TREE_1, TREE_2],
    )


def _record(client: FakeBeadsClient, attempt: IncidentAttempt, world: _World) -> Any:
    return record_merge(
        client=client,
        reading=_read(client, attempt),
        runner=world,
        repo=Path("/repo"),
        repository=REPOSITORY,
    )


def test_record_merge_records_the_landed_identities_the_forge_and_git_report() -> None:
    client, world = FakeBeadsClient(), _World()
    bound = _bound(client)
    entry = _record(client, bound, world)
    assert isinstance(entry, RepaymentEntry), entry
    recorded = entry.reading.attempt
    assert recorded == _head(client)
    assert (entry.lifecycle_state, entry.recovered, entry.operation_id) == (
        "active",
        False,
        "attempt-1",
    )
    assert (recorded.phase, recorded.generation, recorded.operation_id) == (
        "master-observation",
        bound.generation + 1,
        "attempt-1#master-observation",
    )
    assert (recorded.landed_commits, recorded.landed_trees) == ((FIRST, SECOND), (TREE_1, TREE_2))
    # The attempt, head and carrier it merged under survive, for a later attribution.
    assert (recorded.attempt_id, recorded.head, recorded.carrier, recorded.pr_number) == (
        bound.attempt_id,
        HEAD,
        bound.carrier,
        PR,
    )
    # The chain names the PR; no caller supplies it.
    assert world.calls[0][:3] == ["gh", "pr", "view"]
    assert world.calls[0][3] == str(PR)


def test_an_exact_retry_recovers_the_recorded_generation_and_writes_nothing() -> None:
    client, world = FakeBeadsClient(), _World()
    bound = _bound(client)
    first = _record(client, bound, world)
    assert isinstance(first, RepaymentEntry)
    retried = _record(client, bound, world)
    assert isinstance(retried, RepaymentEntry)
    assert retried.recovered is True
    assert retried.reading.attempt == first.reading.attempt == _head(client)


def test_a_superseded_observation_records_nothing() -> None:
    client, world = FakeBeadsClient(), _World()
    bound = _bound(client)
    moved = _transition(client, bound, operation_id="bind-2")
    refused = _record(client, bound, world)
    assert isinstance(refused, AuthorityRefusal)
    assert _head(client) == moved


@pytest.mark.parametrize(
    ("change", "code"),
    [
        ({"state": "OPEN", "mergeCommit": None}, "incident-merge-pr-unmerged"),
        ({"number": 8}, "incident-merge-pr-unobservable"),
        ({"headRefName": "incident/other"}, "incident-merge-carrier-mismatch"),
        ({"headRefOid": "f" * 40}, "incident-merge-carrier-mismatch"),
    ],
)
def test_the_forge_decides_whether_the_carrier_merged(change: dict[str, object], code: str) -> None:
    client, world = FakeBeadsClient(), _World()
    bound = _bound(client)
    world.pr |= change
    refused = _record(client, bound, world)
    assert isinstance(refused, AuthorityRefusal)
    assert refused.code == code
    assert _head(client) == bound


def test_only_a_pr_bound_repair_can_record_a_merge_and_only_while_it_rests_active() -> None:
    client, world = FakeBeadsClient(), _World()
    genesis = _genesis(client)
    unbound = _record(client, genesis, world)
    assert isinstance(unbound, AuthorityRefusal)
    assert unbound.code == "incident-merge-phase-order"
    other = FakeBeadsClient()
    merged = _merged(other)
    repeated = _record(other, merged, world)
    assert isinstance(repeated, AuthorityRefusal)
    assert repeated.code == "incident-merge-phase-order"
    resting = FakeBeadsClient()
    bound = _bound(resting)
    resting.update_issue(issue_id=ITEM, status="blocked")
    mismatch = _record(resting, bound, world)
    assert isinstance(mismatch, AuthorityRefusal)
    assert mismatch.code == "incident-phase-state-mismatch"
    assert world.calls == [], "no refusal before the forge read spends a forge read"


def test_the_action_is_reachable_through_the_lifecycle_dispatch() -> None:
    client, world = FakeBeadsClient(), _World()
    bound = _bound(client)
    args = argparse.Namespace(action="record-merge", repo=Path("/repo"), repository=REPOSITORY)
    entry = run_lifecycle_action(
        args=args, client=client, reading=_read(client, bound), runner=world
    )
    assert isinstance(entry, RepaymentEntry), entry
    assert entry.reading.attempt.phase == "master-observation"


def test_a_merged_attempts_first_master_failure_reopens_into_reverting() -> None:
    client = FakeBeadsClient()
    merged = _merged(client)
    finding = Finding(
        surface="trunk",
        subject="check-metadata-batch",
        run_id="9001",
        failed_head=SECOND,
        attributed_commit=SECOND,
        master_healthy=False,
    )
    entry = reopen_for_regression(
        client=client,
        reading=_read(client, merged),
        attributed=merged,
        finding=finding,
        owner=OWNER,
    )
    assert not isinstance(entry, AuthorityRefusal), entry
    reverting = entry.reading.attempt
    assert (reverting.phase, reverting.generation) == ("reverting", merged.generation + 1)
    assert reverting.landed_commits == merged.landed_commits
    assert reverting.head == HEAD
    assert client.show_issue(issue_id=ITEM)["status"] == "active"


def test_the_merged_carrier_keeps_its_incident_receipt_on_a_real_chain() -> None:
    """The only generation of a green expedited merge that names its landed commits."""
    client = FakeBeadsClient()
    merged = _merged(client)
    history = read_incident_standing(client=client, item_id=ITEM).history
    receipt = matching_incident_receipt(
        receipts=receipts_from_history(history=history),
        repository=REPOSITORY,
        pr_number=PR,
        head_sha=HEAD,
        landed_commits=merged.landed_commits,
    )
    assert receipt is not None
    assert receipt.item_id == ITEM
