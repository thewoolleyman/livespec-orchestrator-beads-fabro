"""One incident walked through the real chain, operator action by operator action, to `closed`.

bd-ib-pqz3nw follow-up. The coordinator's identity rule: a cross-repository
interface check compares the identities and transitions the live chain holds,
not just flag names. This test drives ONE in-memory tenant through the
`incident_authority.py` process boundary: genesis, the expedited repair bound
and merged, `enter-repayment`, `advance-repayment` to `repayment-ready` and
`repayment-active`, `bind-repayment-acceptance` and `complete-incident`. It
then reopens the closed incident with `reopen-regression`. Every write goes
through the canonical genesis and transition writers. Each operator action is
called with exactly the identity the chain reports as current, and the test
asserts the attempt, owner, generation and operation that action recorded. The
only fakes are the forge's `gh pr view` and `gh run view` replies and the local
`git fetch`, `git log` and `git grep` reads.
"""

from __future__ import annotations

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
from livespec_orchestrator_beads_fabro._incident_authority_types import IncidentAttempt
from livespec_orchestrator_beads_fabro._incident_carrier import BranchReserved, PrBound
from livespec_orchestrator_beads_fabro._incident_genesis import decode_genesis_request
from livespec_orchestrator_beads_fabro._store_dispatch_claim import (
    CLAIM_TOKEN_METADATA_KEY,
    ClaimStamp,
    claim_stamp_metadata,
    create_claim_token,
)
from livespec_orchestrator_beads_fabro.commands import incident_authority as command
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine_types import CommandResult
from livespec_orchestrator_beads_fabro.incident_authority import (
    AuthorityRefusal,
    IncidentReading,
    commit_incident_transition,
    publish_incident_genesis,
    read_incident_authority,
)
from livespec_orchestrator_beads_fabro.incident_completion import read_incident_standing

REPOSITORY = "owner/repository"
ITEM = "test-incident"
PRINCIPAL = "operator:alice"
REPAIR_REF = "refs/heads/incident/test-incident-attempt-1"
REPAYMENT_BRANCH = "feat/test-incident"
REPAYMENT_REF = "refs/heads/" + REPAYMENT_BRANCH
REPAIR_PR = 7
REPAYMENT_PR = 12
REPAIR_LANDED = "d" * 40
REPAIR_TREE = "e" * 40
PR_HEAD = "8" * 40
REPAYMENT_MERGE = "9" * 40
REPAYMENT_TREE = "5" * 40
BROKEN_MASTER = "f" * 40
ORIGINAL_PATHS = ["app.py"]
DEFERRED = ["normal-factory-proof"]
_IDENTITY = ("attempt_id", "phase", "operation_id", "generation", "owner")


def _json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


@dataclass
class _World:
    """The forge and the local clone as the actions read them."""

    prs: dict[str, dict[str, object]] = field(default_factory=dict)
    runs: dict[str, dict[str, str]] = field(default_factory=dict)
    logs: dict[str, str] = field(default_factory=dict)

    def run(self, *, argv: list[str], **_: object) -> CommandResult:
        if argv[:2] == ["git", "fetch"]:
            return CommandResult(exit_code=0, stdout="", stderr="")
        if argv[:2] == ["git", "grep"]:
            # The repayment removed every marker: no path matches.
            return CommandResult(exit_code=1, stdout="", stderr="")
        if argv[:2] == ["git", "log"]:
            return CommandResult(exit_code=0, stdout=self.logs[argv[-1]] + "\n", stderr="")
        table: dict[str, Any] = self.prs if argv[1] == "pr" else self.runs
        return CommandResult(exit_code=0, stdout=json.dumps(table[argv[3]]), stderr="")


@dataclass
class _Tenant:
    client: FakeBeadsClient
    world: _World
    root: Path
    reply: Any = None

    def act(self, action: str, current: IncidentAttempt, *payload: str) -> IncidentAttempt:
        """Run one action against the chain's current identity; return what it recorded."""
        argv = [action, "--repo", str(self.root), "--repository", REPOSITORY]
        argv += ["--item", current.item_id, "--attempt", current.attempt_id]
        argv += ["--phase", current.phase, "--operation", current.operation_id]
        argv += ["--generation", str(current.generation), "--owner", current.owner]
        code = command.main(argv=[*argv, *payload])
        response = self.reply
        assert code == 0, response
        assert (response["schema"], response["status"]) == (1, "verified")
        recorded = decode_attempt(value=response["result"]["reading"]["attempt"])
        assert recorded is not None
        assert _head(self.client) == recorded, "the reply is the chain's new head"
        return recorded

    def refused(self, action: str, current: IncidentAttempt, *payload: str) -> str:
        argv = [action, "--repo", str(self.root), "--repository", REPOSITORY]
        argv += ["--item", current.item_id, "--attempt", current.attempt_id]
        argv += ["--phase", current.phase, "--operation", current.operation_id]
        argv += ["--generation", str(current.generation), "--owner", current.owner]
        code = command.main(argv=[*argv, *payload])
        assert code == 78, self.reply
        return f"{self.reply['result']['code']}: {self.reply['result']['detail']}"


@pytest.fixture
def tenant(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> _Tenant:
    client = FakeBeadsClient()
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
    state = _Tenant(client=client, world=_World(), root=tmp_path)

    def no_config(**_: object) -> None:
        return None

    def tenant_client(**_: object) -> FakeBeadsClient:
        return client

    monkeypatch.setattr(command, "store_config", no_config)
    monkeypatch.setattr(command, "make_beads_client", tenant_client)
    monkeypatch.setattr(command, "ShellCommandRunner", lambda: state.world)
    real_main = command.main

    def main(*, argv: list[str]) -> int:
        _ = capsys.readouterr()
        try:
            return real_main(argv=argv)
        finally:
            state.reply = json.loads(capsys.readouterr().out)

    monkeypatch.setattr(command, "main", main)
    return state


def _head(client: FakeBeadsClient) -> IncidentAttempt:
    return read_incident_standing(client=client, item_id=ITEM).history[-1]


def _identity(attempt: IncidentAttempt) -> tuple[str, str, str, int, str]:
    return (
        attempt.attempt_id,
        attempt.owner,
        attempt.phase,
        attempt.generation,
        attempt.operation_id,
    )


def _repair(**changes: Any) -> dict[str, Any]:
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
            original_paths=ORIGINAL_PATHS,
            deferred_work=DEFERRED,
            repayment_required=True,
            carrier=dict(
                state="branch-reserved",
                target_ref=REPAIR_REF,
                input_parent="a" * 40,
                staged_tree="c" * 40,
            ),
        )
        | changes
    )


def _host_transition(client: FakeBeadsClient, current: IncidentAttempt, **changes: Any) -> None:
    """A host-side expedited step (PR binding, merge observation) the incident holder records."""
    observed = read_incident_authority(
        client=client,
        repository=REPOSITORY,
        item_id=ITEM,
        query={key: getattr(current, key) for key in _IDENTITY},
    )
    assert isinstance(observed, IncidentReading) and observed.is_current
    record = json.loads(_json(attempt_record(attempt=current)))
    successor = decode_attempt(value=record | {"generation": current.generation + 1} | changes)
    assert successor is not None
    assert isinstance(
        commit_incident_transition(client=client, observed=observed, successor=successor),
        IncidentReading,
    )


def _expedited_merge(client: FakeBeadsClient) -> IncidentAttempt:
    """Genesis, the repair PR bound, then its merge observed: the attempt owing repayment."""
    token = create_claim_token(client=client)
    client.update_issue(
        issue_id=ITEM,
        status="ready",
        metadata={"rank": "a0", CLAIM_TOKEN_METADATA_KEY: token},
        names_claim_token=True,
    )
    request = decode_genesis_request(
        text=_json(dict(schema=1, principal=PRINCIPAL, expected_claim=token, attempt=_repair())),
        repository=REPOSITORY,
        item_id=ITEM,
        operation_id="operation-1",
    )
    assert request is not None
    assert not isinstance(
        publish_incident_genesis(client=client, request=request, claim_tokens=True),
        AuthorityRefusal,
    )
    genesis = _head(client)
    assert _identity(genesis) == ("attempt-1", PRINCIPAL, "repair", 1, "operation-1")
    bound_carrier = dict(_repair()["carrier"], state="pr-bound", remote_head="b" * 40)
    _host_transition(
        client, genesis, operation_id="bind-1", pr_number=REPAIR_PR, carrier=bound_carrier
    )
    _host_transition(
        client,
        _head(client),
        operation_id="merge-1",
        phase="master-observation",
        landed_commits=[REPAIR_LANDED],
        landed_trees=[REPAIR_TREE],
    )
    client.update_issue(issue_id=ITEM, status="active", assignee=PRINCIPAL)
    observed = _head(client)
    assert _identity(observed) == ("attempt-1", PRINCIPAL, "master-observation", 3, "merge-1")
    return observed


def _enter_and_advance(tenant: _Tenant, observed: IncidentAttempt) -> IncidentAttempt:
    """enter-repayment, then advance-repayment twice: the repayment claimed by a factory run."""
    client, world = tenant.client, tenant.world
    # enter-repayment: the expedited merge's master run is green on its landed commit.
    world.runs["master-run-1"] = dict(
        headSha=REPAIR_LANDED, status="completed", conclusion="success"
    )
    admission = tenant.act(
        "enter-repayment", observed, "--master-run", "master-run-1", "--target-ref", REPAYMENT_REF
    )
    repayment_id = admission.attempt_id
    # The repayment is a NEW attempt identity, owned by the factory, not the incident principal.
    assert repayment_id != observed.attempt_id
    assert _identity(admission) == (
        repayment_id,
        "fabro",
        "repayment-admission",
        4,
        f"{repayment_id}#repayment-admission",
    )
    assert admission.carrier == BranchReserved(
        target_ref=REPAYMENT_REF, input_parent=REPAIR_LANDED, staged_tree=REPAIR_TREE
    )
    assert (admission.pr_number, admission.landed_commits) == (0, ())
    assert client.show_issue(issue_id=ITEM)["status"] == "pending-approval"

    # advance-repayment: ordinary admission approved it, then one factory run claimed it.
    client.update_issue(issue_id=ITEM, status="ready")
    ready = tenant.act(
        "advance-repayment", admission, "--to-phase", "repayment-ready", "--admission-complete"
    )
    assert _identity(ready) == (
        repayment_id,
        "fabro",
        "repayment-ready",
        5,
        f"{repayment_id}#repayment-ready",
    )
    stamp = ClaimStamp(
        dispatch_id="01DISPATCH",
        dispatching_host="hp",
        run_id="run-1",
        factory_name="petri",
        factory_server="http://petri",
    )
    client.update_issue(
        issue_id=ITEM, status="active", assignee="fabro", metadata=claim_stamp_metadata(stamp=stamp)
    )
    active = tenant.act("advance-repayment", ready, "--to-phase", "repayment-active")
    assert _identity(active) == (
        repayment_id,
        "fabro",
        "repayment-active",
        6,
        f"{repayment_id}#repayment-active",
    )
    # advance-repayment cannot bind the PR: it refuses the acceptance phase while the
    # item rests in active, and binds nothing even when it may move.
    assert tenant.refused(
        "advance-repayment", active, "--to-phase", "repayment-acceptance"
    ).startswith("incident-phase-state-mismatch: ")
    return active


def _bind(tenant: _Tenant, active: IncidentAttempt) -> IncidentAttempt:
    """bind-repayment-acceptance once the factory run's repayment PR merged."""
    client, world, repayment_id = tenant.client, tenant.world, active.attempt_id
    # The factory run's repayment PR rebase-merged as one landed commit; ordinary policy
    # moved the item to acceptance.
    world.prs[str(REPAYMENT_PR)] = dict(
        number=REPAYMENT_PR,
        state="MERGED",
        headRefName=REPAYMENT_BRANCH,
        headRefOid=PR_HEAD,
        mergeCommit={"oid": REPAYMENT_MERGE},
        commits=[{"messageHeadline": "fix: repay the incident"}],
    )
    world.logs[REPAYMENT_MERGE] = "\x00".join(
        (REPAYMENT_MERGE, REPAYMENT_TREE, REPAIR_LANDED, "fix: repay the incident")
    )
    client.update_issue(issue_id=ITEM, status="acceptance")
    acceptance = tenant.act("bind-repayment-acceptance", active, "--pr", str(REPAYMENT_PR))
    assert _identity(acceptance) == (
        repayment_id,
        "fabro",
        "repayment-acceptance",
        7,
        f"{repayment_id}#repayment-acceptance",
    )
    assert (acceptance.pr_number, acceptance.head) == (REPAYMENT_PR, PR_HEAD)
    assert (acceptance.landed_commits, acceptance.landed_trees) == (
        (REPAYMENT_MERGE,),
        (REPAYMENT_TREE,),
    )
    # The carrier advanced in place: same reservation, now bound to the merged PR head.
    assert acceptance.carrier == PrBound(
        target_ref=REPAYMENT_REF,
        input_parent=REPAIR_LANDED,
        staged_tree=REPAIR_TREE,
        remote_head=PR_HEAD,
    )
    return acceptance


def _completion(tenant: _Tenant) -> tuple[str, ...]:
    """The complete-incident payload; the repayment merge's own master run is green."""
    tenant.world.runs["master-run-2"] = dict(
        headSha=REPAYMENT_MERGE, status="completed", conclusion="success"
    )
    attestation = _json(
        dict(
            manual_outcome=True,
            repaid_debt=DEFERRED,
            undisposed_failures=[],
            validated_paths=ORIGINAL_PATHS,
        )
    )
    return ("--master-run", "master-run-2", "--completion-json", attestation)


def _reopen_closed(
    tenant: _Tenant, *, observed: IncidentAttempt, closed: IncidentAttempt, active: IncidentAttempt
) -> None:
    """reopen-regression on the closed incident; neither action reaches past the reopen."""
    client, repayment_id, completion = tenant.client, active.attempt_id, _completion(tenant)
    # A demonstrated regression reopens the SAME item: the chain's head becomes a
    # recovery generation owned by the incident principal, bound to the expedited PR.
    client.update_issue(issue_id=ITEM, status="closed")
    finding = _json(
        dict(
            surface="trunk",
            subject="trunk-ci",
            run_id="master-run-9",
            failed_head=BROKEN_MASTER,
            attributed_commit=REPAIR_LANDED,
            master_healthy=False,
        )
    )
    reverting = tenant.act(
        "reopen-regression",
        closed,
        *("--attributed-json", _json(attempt_record(attempt=observed))),
        *("--finding-json", finding, "--principal", PRINCIPAL),
    )
    assert reverting.attempt_id != repayment_id
    assert (reverting.owner, reverting.phase, reverting.generation) == (PRINCIPAL, "reverting", 9)
    assert reverting.pr_number == REPAIR_PR
    # complete-incident reads the PR the recovery head binds: the expedited repair PR.
    tenant.world.prs[str(REPAIR_PR)] = dict(number=REPAIR_PR, state="MERGED")
    # Neither action reaches past the reopen with an identity the chain no longer holds:
    # the recovery head owes a fresh normal repayment, and the old repayment is stale.
    assert tenant.refused("complete-incident", reverting, *completion).startswith(
        f"incident-completion-outstanding: {ITEM}: normal-repayment-unmerged:reverting"
    )
    assert tenant.refused(
        "bind-repayment-acceptance", active, "--pr", str(REPAYMENT_PR)
    ).startswith("incident-repayment-stale-observation: ")


def test_one_incident_walks_enter_advance_bind_and_complete_on_the_real_chain(
    tenant: _Tenant,
) -> None:
    client = tenant.client
    observed = _expedited_merge(client)
    active = _enter_and_advance(tenant, observed)
    repayment_id = active.attempt_id
    acceptance = _bind(tenant, active)
    completion = _completion(tenant)
    closed = tenant.act("complete-incident", acceptance, *completion)
    assert _identity(closed) == (repayment_id, "fabro", "closed", 8, f"{repayment_id}#closed")
    assert (closed.pr_number, closed.landed_commits) == (REPAYMENT_PR, (REPAYMENT_MERGE,))
    assert read_incident_standing(client=client, item_id=ITEM).outstanding == ()
    # The walk recorded exactly one generation per action, in order.
    phases = [a.phase for a in read_incident_standing(client=client, item_id=ITEM).history]
    assert phases == [
        "repair",
        "repair",
        "master-observation",
        "repayment-admission",
        "repayment-ready",
        "repayment-active",
        "repayment-acceptance",
        "closed",
    ]
    _reopen_closed(tenant, observed=observed, closed=closed, active=active)
