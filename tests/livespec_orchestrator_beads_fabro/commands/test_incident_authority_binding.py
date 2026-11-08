"""The incident-authority `bind-repayment-acceptance` action binds the merged repayment PR.

bd-ib-pqz3nw. One case per Definition-of-Done assertion, each driven through
the `incident_authority.py` process boundary over an in-memory tenant whose
chain the canonical genesis and transition writers recorded. The forge's pull
request view and the local git history reads are the only fake effects; the
last case binds, then completes, the same incident end to end.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path
from typing import Any

import pytest
from livespec_orchestrator_beads_fabro._beads_client import FakeBeadsClient, IssueDraft
from livespec_orchestrator_beads_fabro._incident_authority_payload import decode_attempt
from livespec_orchestrator_beads_fabro._incident_authority_types import IncidentAttempt
from livespec_orchestrator_beads_fabro._incident_carrier import PrBound
from livespec_orchestrator_beads_fabro._incident_genesis import decode_genesis_request
from livespec_orchestrator_beads_fabro._store_dispatch_claim import (
    CLAIM_TOKEN_METADATA_KEY,
    create_claim_token,
)
from livespec_orchestrator_beads_fabro.commands import incident_authority as command
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine_types import CommandResult
from livespec_orchestrator_beads_fabro.commands._incident_authority_binding import (
    bind_repayment_acceptance,
)
from livespec_orchestrator_beads_fabro.incident_authority import (
    AuthorityRefusal,
    IncidentReading,
    commit_incident_transition,
    publish_incident_genesis,
    read_incident_authority,
)
from livespec_orchestrator_beads_fabro.incident_completion import read_incident_standing
from livespec_orchestrator_beads_fabro.incident_normal_repayment import RepaymentEntry

REPOSITORY = "owner/repository"
ITEM = "test-incident"
PRINCIPAL = "operator:alice"
REPAIR_REF = "refs/heads/incident/test-incident-attempt-1"
REPAYMENT_BRANCH = "feat/test-incident"
REPAYMENT_REF = "refs/heads/" + REPAYMENT_BRANCH
REPAIR_PR = 7
REPAYMENT_PR = 12
REPAIR_HEAD = "d" * 40
PR_HEAD = "8" * 40
MERGE = "9" * 40
FIRST_LANDED = "7" * 40
FIRST_TREE = "6" * 40
MERGE_TREE = "5" * 40
MASTER_BEFORE = "4" * 40
ORIGINAL_PATHS = ("app.py", "tests/test_app.py")
DEFERRED = ("normal-factory-proof", "spec-debt:scenario-12")
HEADLINES = ("fix: repay the incident", "test: exercise the original paths")
MASTER_RUN = "run-9"
_IDENTITY = ("attempt_id", "phase", "operation_id", "generation", "owner")


def _json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _row(commit: str, tree: str, parents: str, subject: str) -> str:
    return "\x00".join((commit, tree, parents, subject))


# The default branch after a rebase merge: one landed commit per PR commit, tip first.
REBASED_LOG = "\n".join(
    (
        _row(MERGE, MERGE_TREE, FIRST_LANDED, HEADLINES[1]),
        _row(FIRST_LANDED, FIRST_TREE, MASTER_BEFORE, HEADLINES[0]),
    )
)


@dataclass
class _Forge:
    """`gh pr view`, `gh run view`, `git fetch`, `git log` and `git grep` as the world answers."""

    prs: dict[str, dict[str, object]] = field(default_factory=dict)
    runs: dict[str, dict[str, str]] = field(default_factory=dict)
    logs: dict[str, str] = field(default_factory=dict)
    calls: list[list[str]] = field(default_factory=list)

    def run(self, *, argv: list[str], **_: object) -> CommandResult:
        self.calls.append(argv)
        if argv[:2] == ["git", "fetch"]:
            return CommandResult(exit_code=0, stdout="", stderr="")
        if argv[:2] == ["git", "grep"]:
            return CommandResult(exit_code=1, stdout="", stderr="")
        if argv[:2] == ["git", "log"]:
            log = self.logs.get(argv[-1])
            if log is None:
                return CommandResult(exit_code=128, stdout="", stderr="fatal: bad object")
            return CommandResult(exit_code=0, stdout=log + "\n", stderr="")
        table: dict[str, Any] = self.prs if argv[1] == "pr" else self.runs
        reply = table.get(argv[3])
        if reply is None:
            return CommandResult(exit_code=1, stdout="", stderr=f"{argv[1]} not found")
        return CommandResult(exit_code=0, stdout=json.dumps(reply), stderr="")


@dataclass
class _Tenant:
    client: FakeBeadsClient
    forge: _Forge
    root: Path
    reply: Any = None

    def cli(self, action: str, attempt: IncidentAttempt, *payload: str) -> tuple[int, Any]:
        identity = dict(
            item=attempt.item_id,
            attempt=attempt.attempt_id,
            phase=attempt.phase,
            operation=attempt.operation_id,
            generation=str(attempt.generation),
            owner=attempt.owner,
        )
        argv = [action, "--repo", str(self.root), "--repository", REPOSITORY]
        for name, value in identity.items():
            argv += [f"--{name}", value]
        try:
            code = command.main(argv=[*argv, *payload])
        except SystemExit as error:
            code = error.code
        return int(code or 0), self.reply

    def bind(self, attempt: IncidentAttempt, pr: str = str(REPAYMENT_PR)) -> tuple[int, Any]:
        return self.cli("bind-repayment-acceptance", attempt, "--pr", pr)


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
    state = _Tenant(client=client, forge=_Forge(), root=tmp_path)

    def no_config(**_: object) -> None:
        return None

    def tenant_client(**_: object) -> FakeBeadsClient:
        return client

    monkeypatch.setattr(command, "store_config", no_config)
    monkeypatch.setattr(command, "make_beads_client", tenant_client)
    monkeypatch.setattr(command, "ShellCommandRunner", lambda: state.forge)
    real_main = command.main

    def main(*, argv: list[str]) -> int:
        _ = capsys.readouterr()
        try:
            return real_main(argv=argv)
        finally:
            out = capsys.readouterr().out
            lines = out.splitlines()
            state.reply = json.loads(out) if len(lines) == 1 else lines

    monkeypatch.setattr(command, "main", main)
    return state


def _carrier(*, ref: str, state: str = "pr-bound", head: str = "b" * 40) -> dict[str, str]:
    carrier = {"state": state, "target_ref": ref, "input_parent": "a" * 40, "staged_tree": "c" * 40}
    return carrier if state == "branch-reserved" else carrier | {"remote_head": head}


def _attempt(**changes: Any) -> dict[str, Any]:
    return {
        "repository": REPOSITORY,
        "item_id": ITEM,
        "attempt_id": "attempt-1",
        "phase": "repair",
        "operation_id": "operation-1",
        "generation": 1,
        "owner": PRINCIPAL,
        "base": "a" * 40,
        "head": "b" * 40,
        "pr_number": 0,
        "landed_commits": [],
        "landed_trees": [],
        "original_paths": list(ORIGINAL_PATHS),
        "deferred_work": list(DEFERRED),
        "repayment_required": True,
        "carrier": _carrier(ref=REPAIR_REF, state="branch-reserved"),
    } | changes


def _advance(client: FakeBeadsClient, observed: IncidentReading, **changes: Any) -> IncidentReading:
    successor = decode_attempt(
        value=_attempt(generation=observed.attempt.generation + 1, **changes)
    )
    assert successor is not None
    advanced = commit_incident_transition(client=client, observed=observed, successor=successor)
    assert isinstance(advanced, IncidentReading), advanced
    return advanced


def _repayment(
    client: FakeBeadsClient, *, through: str = "repayment-active"
) -> list[IncidentAttempt]:
    """Genesis, the expedited merge, then the repayment walked to `through` with no PR."""
    token = create_claim_token(client=client)
    client.update_issue(
        issue_id=ITEM,
        status="ready",
        metadata={"rank": "a0", CLAIM_TOKEN_METADATA_KEY: token},
        names_claim_token=True,
    )
    request = decode_genesis_request(
        text=_json(dict(schema=1, principal=PRINCIPAL, expected_claim=token, attempt=_attempt())),
        repository=REPOSITORY,
        item_id=ITEM,
        operation_id="operation-1",
    )
    assert request is not None
    receipt = publish_incident_genesis(client=client, request=request, claim_tokens=True)
    assert not isinstance(receipt, AuthorityRefusal)
    reading = read_incident_authority(
        client=client,
        repository=REPOSITORY,
        item_id=ITEM,
        query={key: _attempt()[key] for key in _IDENTITY},
        historical=True,
    )
    assert isinstance(reading, IncidentReading)
    reading = _advance(
        client,
        reading,
        operation_id="bind-1",
        pr_number=REPAIR_PR,
        carrier=_carrier(ref=REPAIR_REF),
    )
    reading = _advance(
        client,
        reading,
        operation_id="merge-1",
        phase="master-observation",
        pr_number=REPAIR_PR,
        landed_commits=[REPAIR_HEAD],
        landed_trees=["e" * 40],
        carrier=_carrier(ref=REPAIR_REF),
    )
    walked: list[IncidentAttempt] = []
    repaid = {
        "attempt_id": "repayment-1",
        "owner": "fabro",
        "base": REPAIR_HEAD,
        "head": REPAIR_HEAD,
    }
    phases = ("repayment-admission", "repayment-ready", "repayment-active")
    for phase in phases[: phases.index(through) + 1]:
        reading = _advance(
            client,
            reading,
            operation_id=f"repayment-1#{phase}",
            phase=phase,
            carrier=_carrier(ref=REPAYMENT_REF, state="branch-reserved"),
            **repaid,
        )
        walked.append(reading.attempt)
    # Ordinary policy moved the item to acceptance once the factory run's PR merged.
    client.update_issue(issue_id=ITEM, status="acceptance")
    return walked


def _merged(world: _Tenant, **changes: object) -> None:
    """The forge reports the repayment PR rebase-merged as two landed commits."""
    world.forge.prs[str(REPAYMENT_PR)] = (
        dict(
            number=REPAYMENT_PR,
            state="MERGED",
            headRefName=REPAYMENT_BRANCH,
            headRefOid=PR_HEAD,
            mergeCommit={"oid": MERGE},
            commits=[{"messageHeadline": line} for line in HEADLINES],
        )
        | changes
    )
    world.forge.logs[MERGE] = REBASED_LOG


def _snapshot(state: _Tenant) -> tuple[object, ...]:
    standing = read_incident_standing(client=state.client, item_id=ITEM)
    return (
        state.client.show_issue(issue_id=ITEM),
        state.client.list_comments(issue_id=ITEM),
        tuple(asdict(attempt) for attempt in standing.history),
    )


def _bound(reply: tuple[int, Any]) -> IncidentAttempt:
    code, response = reply
    assert code == 0, response
    assert (response["schema"], response["status"]) == (1, "verified")
    attempt = decode_attempt(value=response["result"]["reading"]["attempt"])
    assert attempt is not None
    return attempt


def _refused(reply: tuple[int, Any]) -> tuple[str, str]:
    code, response = reply
    assert code == 78, response
    assert (response["schema"], response["status"]) == (1, "refused")
    return response["result"]["code"], response["result"]["detail"]


def test_bind_repayment_acceptance_binds_the_merged_pr_as_the_forge_reports_it(
    tenant: _Tenant,
) -> None:
    active = _repayment(tenant.client)[-1]
    _merged(tenant)
    bound = _bound(tenant.bind(active))
    assert (bound.item_id, bound.attempt_id, bound.phase, bound.generation) == (
        ITEM,
        "repayment-1",
        "repayment-acceptance",
        active.generation + 1,
    )
    assert (bound.pr_number, bound.head) == (REPAYMENT_PR, PR_HEAD)
    assert bound.landed_commits == (FIRST_LANDED, MERGE)
    assert bound.landed_trees == (FIRST_TREE, MERGE_TREE)
    assert bound.carrier == PrBound(
        target_ref=REPAYMENT_REF, input_parent="a" * 40, staged_tree="c" * 40, remote_head=PR_HEAD
    )
    standing = read_incident_standing(client=tenant.client, item_id=ITEM)
    assert asdict(standing.history[-1]) == asdict(bound)
    assert [
        "gh",
        "pr",
        "view",
        str(REPAYMENT_PR),
        "--repo",
        REPOSITORY,
        "--json",
        "number,state,headRefName,headRefOid,mergeCommit,commits",
    ] in tenant.forge.calls
    assert ["git", "fetch", "--quiet", "--no-tags", "origin", MERGE] in tenant.forge.calls


@pytest.mark.parametrize(
    "log",
    [
        # A squash merge lands one commit whose subject is none of the PR's.
        _row(MERGE, MERGE_TREE, MASTER_BEFORE, "Repay the incident (#12)")
        + "\n"
        + _row(MASTER_BEFORE, FIRST_TREE, "3" * 40, "earlier work"),
        # A merge commit lands itself, whatever its second parent carried.
        _row(MERGE, MERGE_TREE, f"{MASTER_BEFORE} {PR_HEAD}", HEADLINES[1])
        + "\n"
        + _row(MASTER_BEFORE, FIRST_TREE, "3" * 40, HEADLINES[0]),
    ],
)
def test_bind_repayment_acceptance_binds_the_merge_commit_alone_for_a_squash_or_merge(
    tenant: _Tenant, log: str
) -> None:
    active = _repayment(tenant.client)[-1]
    _merged(tenant)
    tenant.forge.logs[MERGE] = log
    bound = _bound(tenant.bind(active))
    assert (bound.landed_commits, bound.landed_trees) == ((MERGE,), (MERGE_TREE,))


@pytest.mark.parametrize(
    ("forge", "refusal"),
    [
        ({"state": "OPEN", "mergeCommit": None}, "incident-repayment-pr-unmerged"),
        ({"state": "CLOSED", "mergeCommit": None}, "incident-repayment-pr-unmerged"),
        ({"headRefName": "feat/another-branch"}, "incident-repayment-carrier-mismatch"),
        ({"number": REPAIR_PR}, "incident-repayment-pr-unobservable"),
        ({"headRefOid": "not-a-sha"}, "incident-repayment-pr-unobservable"),
        ({"commits": []}, "incident-repayment-pr-unobservable"),
        ({"commits": [{"messageHeadline": 3}]}, "incident-repayment-pr-unobservable"),
        ({"lost": True}, "incident-repayment-pr-unobservable"),
        ({"log": None}, "incident-repayment-landed-unobservable"),
        (
            {"log": _row("3" * 40, MERGE_TREE, MASTER_BEFORE, "x")},
            "incident-repayment-landed-unobservable",
        ),
        ({"log": "malformed row"}, "incident-repayment-landed-unobservable"),
        (
            {"log": _row(MERGE, "tree", MASTER_BEFORE, "x")},
            "incident-repayment-landed-unobservable",
        ),
    ],
)
def test_bind_repayment_acceptance_refuses_a_pr_the_forge_does_not_report_merged_on_the_carrier(
    tenant: _Tenant, forge: dict[str, object], refusal: str
) -> None:
    active = _repayment(tenant.client)[-1]
    _merged(tenant, **{k: v for k, v in forge.items() if k not in ("lost", "log")})
    if forge.get("lost"):
        del tenant.forge.prs[str(REPAYMENT_PR)]
    if "log" in forge:
        log = forge["log"]
        if log is None:
            del tenant.forge.logs[MERGE]
        else:
            tenant.forge.logs[MERGE] = str(log)
    before = _snapshot(tenant)
    code, detail = _refused(tenant.bind(active))
    assert code == refusal, detail
    assert _snapshot(tenant) == before


def test_bind_repayment_acceptance_refuses_an_attempt_that_is_not_the_current_repayment_active(
    tenant: _Tenant,
) -> None:
    admission, ready = _repayment(tenant.client, through="repayment-ready")
    _merged(tenant)
    before = _snapshot(tenant)
    # The current generation is still repayment-ready: the binding is out of order.
    assert _refused(tenant.bind(ready)) == (
        "incident-repayment-phase-order",
        "repayment-ready -> repayment-acceptance",
    )
    # An earlier generation of the chain is a stale observation.
    assert _refused(tenant.bind(admission))[0] == "incident-repayment-stale-observation"
    assert _snapshot(tenant) == before
    assert not [argv for argv in tenant.forge.calls if argv[:3] == ["gh", "pr", "view"]]


def test_bind_repayment_acceptance_refuses_while_the_item_rests_outside_acceptance(
    tenant: _Tenant,
) -> None:
    active = _repayment(tenant.client)[-1]
    _merged(tenant)
    tenant.client.update_issue(issue_id=ITEM, status="active")
    before = _snapshot(tenant)
    assert _refused(tenant.bind(active)) == (
        "incident-phase-state-mismatch",
        "repayment-acceptance pairs with acceptance, item rests at active",
    )
    assert _snapshot(tenant) == before


@pytest.mark.parametrize("pr", ["0", "-3", "twelve", "012"])
def test_bind_repayment_acceptance_refuses_a_pr_argument_that_is_not_a_pr_number(
    tenant: _Tenant, pr: str
) -> None:
    active = _repayment(tenant.client)[-1]
    _merged(tenant)
    code, detail = _refused(tenant.bind(active, pr))
    assert code == "incident-action-invalid-payload"
    assert detail.startswith("--pr: ")
    assert tenant.forge.calls == []


def test_bind_repayment_acceptance_refuses_an_attempt_with_no_reserved_carrier(
    tenant: _Tenant,
) -> None:
    active = _repayment(tenant.client)[-1]
    reading = read_incident_authority(
        client=tenant.client,
        repository=REPOSITORY,
        item_id=ITEM,
        query={key: getattr(active, key) for key in _IDENTITY},
    )
    assert isinstance(reading, IncidentReading) and reading.is_current
    unreserved = replace(reading, attempt=replace(active, carrier=None))
    refusal = bind_repayment_acceptance(
        client=tenant.client,
        reading=unreserved,
        runner=tenant.forge,
        repo=tenant.root,
        repository=REPOSITORY,
        pr_number=REPAYMENT_PR,
    )
    assert refusal == AuthorityRefusal(
        code="incident-repayment-carrier-mismatch", detail=f"{ITEM}: no reserved carrier"
    )


def test_a_bound_repayment_then_completes_the_incident(tenant: _Tenant) -> None:
    active = _repayment(tenant.client)[-1]
    _merged(tenant)
    bound = _bound(tenant.bind(active))
    tenant.forge.runs[MASTER_RUN] = dict(headSha=MERGE, status="completed", conclusion="success")
    attestation = _json(
        dict(
            manual_outcome=True,
            repaid_debt=list(DEFERRED),
            undisposed_failures=[],
            validated_paths=list(ORIGINAL_PATHS),
        )
    )
    code, response = tenant.cli(
        "complete-incident", bound, "--master-run", MASTER_RUN, "--completion-json", attestation
    )
    assert code == 0, response
    assert response["result"]["reading"]["attempt"]["phase"] == "closed"
    assert read_incident_standing(client=tenant.client, item_id=ITEM).outstanding == ()


def test_bind_repayment_acceptance_records_nothing_against_a_superseded_observation(
    tenant: _Tenant,
) -> None:
    active = _repayment(tenant.client)[-1]
    _merged(tenant)
    observed = read_incident_authority(
        client=tenant.client,
        repository=REPOSITORY,
        item_id=ITEM,
        query={key: getattr(active, key) for key in _IDENTITY},
    )
    assert isinstance(observed, IncidentReading) and observed.is_current
    # Another delivery binds first; the observation taken before it is now stale.
    first = _bound(tenant.bind(active))
    before = _snapshot(tenant)

    def bind() -> RepaymentEntry | AuthorityRefusal:
        return bind_repayment_acceptance(
            client=tenant.client,
            reading=observed,
            runner=tenant.forge,
            repo=tenant.root,
            repository=REPOSITORY,
            pr_number=REPAYMENT_PR,
        )

    # The identical successor again is the recorded generation, and nothing more is written.
    repeated = bind()
    assert not isinstance(repeated, AuthorityRefusal)
    assert asdict(repeated.reading.attempt) == asdict(first)
    assert _snapshot(tenant) == before
    # A different successor against the superseded observation is refused.
    tenant.forge.logs[MERGE] = _row(MERGE, MERGE_TREE, MASTER_BEFORE, "squashed (#12)")
    refusal = bind()
    assert isinstance(refusal, AuthorityRefusal)
    assert refusal.code.startswith("incident-")
    assert _snapshot(tenant) == before


def test_bind_repayment_acceptance_requires_its_pr_argument_and_only_its_own(
    tenant: _Tenant,
) -> None:
    active = _repayment(tenant.client)[-1]
    # Without --pr, or with another action's payload, it is a usage error.
    assert tenant.cli("bind-repayment-acceptance", active)[0] == 2
    assert tenant.cli("advance-repayment", active, "--to-phase", "x", "--pr", "12")[0] == 2
    assert tenant.cli("bind-repayment-acceptance", active, "--pr", "12", "--to-phase", "x")[0] == 2
    assert tenant.forge.calls == []
