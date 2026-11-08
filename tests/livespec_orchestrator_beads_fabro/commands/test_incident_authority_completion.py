"""The incident-authority `complete-incident` action records `closed` only from observed evidence.

bd-ib-pqz3nw. One case per Definition-of-Done assertion, each driven through
the `incident_authority.py` process boundary over an in-memory tenant whose
chain the canonical genesis and transition writers recorded. The forge's pull
request and run views and the local git tree reads are the only fake effects.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import pytest
from livespec_orchestrator_beads_fabro._beads_client import FakeBeadsClient, IssueDraft
from livespec_orchestrator_beads_fabro._incident_authority_payload import decode_attempt
from livespec_orchestrator_beads_fabro._incident_authority_types import IncidentAttempt
from livespec_orchestrator_beads_fabro._incident_genesis import decode_genesis_request
from livespec_orchestrator_beads_fabro._incident_repayment_scope import incident_marker
from livespec_orchestrator_beads_fabro._store_dispatch_claim import (
    CLAIM_TOKEN_METADATA_KEY,
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
REPAYMENT_REF = "refs/heads/feat/test-incident"
REPAIR_PR = 7
REPAYMENT_PR = 12
REPAIR_HEAD = "d" * 40
REPAY_HEAD = "9" * 40
ORIGINAL_PATHS = ("app.py", "tests/test_app.py")
DEFERRED = ("normal-factory-proof", "spec-debt:scenario-12")
MASTER_RUN = "run-9"
OUTSTANDING = "incident-completion-outstanding"
_IDENTITY = ("attempt_id", "phase", "operation_id", "generation", "owner")


def _json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _attestation(**changes: Any) -> str:
    return _json(
        dict(
            manual_outcome=True,
            repaid_debt=list(DEFERRED),
            undisposed_failures=[],
            validated_paths=list(ORIGINAL_PATHS),
        )
        | changes
    )


@dataclass
class _Forge:
    """`gh pr view`, `gh run view`, `git fetch` and `git grep` as the world answers them."""

    prs: dict[str, dict[str, object]] = field(default_factory=dict)
    runs: dict[str, dict[str, str]] = field(default_factory=dict)
    # Head -> the paths whose tree still carries the marker; absent is an unreadable tree.
    trees: dict[str, list[str]] = field(default_factory=dict)
    calls: list[list[str]] = field(default_factory=list)

    def run(self, *, argv: list[str], **_: object) -> CommandResult:
        self.calls.append(argv)
        if argv[:2] == ["git", "fetch"]:
            return CommandResult(exit_code=0, stdout="", stderr="")
        if argv[:2] == ["git", "grep"]:
            return self._grep(head=argv[-2])
        table: dict[str, Any] = self.prs if argv[1] == "pr" else self.runs
        reply = table.get(argv[3])
        if reply is None:
            return CommandResult(exit_code=1, stdout="", stderr=f"{argv[1]} not found")
        return CommandResult(exit_code=0, stdout=json.dumps(reply), stderr="")

    def _grep(self, *, head: str) -> CommandResult:
        paths = self.trees.get(head)
        if paths is None:
            return CommandResult(exit_code=128, stdout="", stderr=f"fatal: bad object {head}")
        out = "".join(f"{head}:{path}\n" for path in paths)
        return CommandResult(exit_code=0 if paths else 1, stdout=out, stderr="")


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

    def complete(self, attempt: IncidentAttempt, attestation: str | None = None):
        return self.cli(
            "complete-incident",
            attempt,
            "--master-run",
            MASTER_RUN,
            "--completion-json",
            _attestation() if attestation is None else attestation,
        )


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


def _expedited_merge(client: FakeBeadsClient) -> IncidentReading:
    """Genesis, the repair PR bound, then its merge observed: only an expedited merge exists."""
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
    first = read_incident_authority(
        client=client,
        repository=REPOSITORY,
        item_id=ITEM,
        query={key: _attempt()[key] for key in _IDENTITY},
        historical=True,
    )
    assert isinstance(first, IncidentReading)
    bound = _advance(
        client, first, operation_id="bind-1", pr_number=REPAIR_PR, carrier=_carrier(ref=REPAIR_REF)
    )
    return _advance(
        client,
        bound,
        operation_id="merge-1",
        phase="master-observation",
        pr_number=REPAIR_PR,
        landed_commits=[REPAIR_HEAD],
        landed_trees=["e" * 40],
        carrier=_carrier(ref=REPAIR_REF),
    )


_REPAID = {"attempt_id": "repayment-1", "owner": "fabro", "base": REPAIR_HEAD, "head": REPAIR_HEAD}


def _repayment_active(client: FakeBeadsClient) -> IncidentReading:
    """The same item's repayment claimed by one factory run, its PR not yet bound."""
    reading = _expedited_merge(client)
    for phase in ("repayment-admission", "repayment-ready", "repayment-active"):
        reading = _advance(
            client,
            reading,
            operation_id=f"repayment-1#{phase}",
            phase=phase,
            carrier=_carrier(ref=REPAYMENT_REF, state="branch-reserved"),
            **_REPAID,
        )
    return reading


def _repayment_merged(client: FakeBeadsClient) -> IncidentAttempt:
    """The repayment PR bound and merged: the item rests at `repayment-acceptance`."""
    return _advance(
        client,
        _repayment_active(client),
        operation_id="repayment-1#repayment-acceptance",
        phase="repayment-acceptance",
        pr_number=REPAYMENT_PR,
        landed_commits=[REPAY_HEAD],
        landed_trees=["f" * 40],
        carrier=_carrier(ref=REPAYMENT_REF, head=REPAY_HEAD),
        **(_REPAID | {"head": REPAY_HEAD}),
    ).attempt


def _proven(state: _Tenant) -> None:
    """The forge reports the repayment merged and its master run green; the tree is clean."""
    state.forge.prs[str(REPAYMENT_PR)] = dict(number=REPAYMENT_PR, state="MERGED")
    state.forge.prs[str(REPAIR_PR)] = dict(number=REPAIR_PR, state="MERGED")
    state.forge.runs[MASTER_RUN] = dict(
        headSha=REPAY_HEAD, status="completed", conclusion="success"
    )
    state.forge.trees[REPAY_HEAD] = []


def _snapshot(state: _Tenant) -> tuple[object, ...]:
    """Everything a write could touch: the item, its comments and the incident chain."""
    standing = read_incident_standing(client=state.client, item_id=ITEM)
    return (
        state.client.show_issue(issue_id=ITEM),
        state.client.list_comments(issue_id=ITEM),
        tuple(asdict(attempt) for attempt in standing.history),
    )


def _refused(reply: tuple[int, Any]) -> tuple[str, str]:
    code, response = reply
    assert code == 78, response
    assert (response["schema"], response["status"]) == (1, "refused")
    return response["result"]["code"], response["result"]["detail"]


def test_complete_incident_records_closed_from_forge_observed_repayment_evidence(
    tenant: _Tenant,
) -> None:
    acceptance = _repayment_merged(tenant.client)
    _proven(tenant)
    code, response = tenant.complete(acceptance)
    assert code == 0, response
    assert (response["schema"], response["status"]) == (1, "verified")
    assert response["normal_factory_proof"] is False
    assert response["authorizes_current_effects"] is False
    result = response["result"]
    assert (result["recorded"], result["recovered"], result["outstanding"]) == (True, False, [])
    closed = decode_attempt(value=result["reading"]["attempt"])
    assert closed is not None
    assert (closed.item_id, closed.phase, closed.generation) == (
        ITEM,
        "closed",
        acceptance.generation + 1,
    )
    standing = read_incident_standing(client=tenant.client, item_id=ITEM)
    assert standing.history[-1].phase == "closed"
    assert standing.outstanding == ()
    # The merge and the master result came from the forge, the marker scan from the run head.
    assert [
        "gh",
        "pr",
        "view",
        str(REPAYMENT_PR),
        "--repo",
        REPOSITORY,
        "--json",
        "number,state",
    ] in tenant.forge.calls
    assert [
        "gh",
        "run",
        "view",
        MASTER_RUN,
        "--repo",
        REPOSITORY,
        "--json",
        "headSha,status,conclusion",
    ] in tenant.forge.calls
    grep = next(argv for argv in tenant.forge.calls if argv[:2] == ["git", "grep"])
    assert incident_marker(item_id=ITEM) in grep
    assert grep[-2:] == [REPAY_HEAD, "--"]


@pytest.mark.parametrize(
    ("forge", "obligation"),
    [
        ({"pr": "OPEN"}, f"repayment-merge-unobserved:{REPAYMENT_PR}"),
        (
            {"status": "in_progress", "conclusion": ""},
            f"repayment-master-ci-incomplete:{MASTER_RUN}",
        ),
        ({"conclusion": "failure"}, f"repayment-master-ci-failed:{MASTER_RUN}:failure"),
        ({"conclusion": "cancelled"}, f"repayment-master-ci-cancelled:{MASTER_RUN}"),
        ({"head": REPAIR_HEAD}, f"repayment-master-ci-not-for-repayment:{REPAIR_HEAD}"),
    ],
)
def test_complete_incident_refuses_while_the_repayment_is_unmerged_or_its_master_run_is_not_green(
    tenant: _Tenant, forge: dict[str, str], obligation: str
) -> None:
    acceptance = _repayment_merged(tenant.client)
    _proven(tenant)
    tenant.forge.prs[str(REPAYMENT_PR)]["state"] = forge.get("pr", "MERGED")
    head = forge.get("head", REPAY_HEAD)
    tenant.forge.trees[head] = []
    tenant.forge.runs[MASTER_RUN] = dict(
        headSha=head,
        status=forge.get("status", "completed"),
        conclusion=forge.get("conclusion", "success"),
    )
    before = _snapshot(tenant)
    code, detail = _refused(tenant.complete(acceptance))
    assert code == OUTSTANDING
    assert detail.startswith(f"{ITEM}: ")
    assert obligation in detail.split(": ", 1)[1].split("; ")
    assert _snapshot(tenant) == before


def test_complete_incident_refuses_an_incident_whose_normal_repayment_never_merged(
    tenant: _Tenant,
) -> None:
    active = _repayment_active(tenant.client).attempt
    _proven(tenant)
    before = _snapshot(tenant)
    code, detail = _refused(tenant.complete(active))
    assert code == OUTSTANDING
    assert "normal-repayment-unmerged:repayment-active" in detail
    # The unbound repayment has no PR to read: no pull request view was asked for.
    assert not [argv for argv in tenant.forge.calls if argv[:3] == ["gh", "pr", "view"]]
    assert _snapshot(tenant) == before


def test_complete_incident_refuses_an_expedited_repair_merge_alone(tenant: _Tenant) -> None:
    observed = _expedited_merge(tenant.client).attempt
    _proven(tenant)
    tenant.forge.runs[MASTER_RUN]["headSha"] = REPAIR_HEAD
    tenant.forge.trees[REPAIR_HEAD] = []
    before = _snapshot(tenant)
    code, detail = _refused(tenant.complete(observed))
    assert code == OUTSTANDING
    assert "normal-repayment-unmerged:master-observation" in detail
    assert _snapshot(tenant) == before


@pytest.mark.parametrize(
    ("tree", "obligation"),
    [
        (["tests/test_app.py", "app.py"], "marker-present:app.py"),
        (None, "marker-removal-unobserved"),
    ],
)
def test_complete_incident_refuses_while_the_run_head_tree_carries_or_hides_the_marker(
    tenant: _Tenant, tree: list[str] | None, obligation: str
) -> None:
    acceptance = _repayment_merged(tenant.client)
    _proven(tenant)
    if tree is None:
        del tenant.forge.trees[REPAY_HEAD]
    else:
        tenant.forge.trees[REPAY_HEAD] = tree
    before = _snapshot(tenant)
    code, detail = _refused(tenant.complete(acceptance))
    assert code == OUTSTANDING
    assert obligation in detail
    assert _snapshot(tenant) == before


def test_complete_incident_names_every_attestation_gap_and_records_nothing(
    tenant: _Tenant,
) -> None:
    acceptance = _repayment_merged(tenant.client)
    _proven(tenant)
    before = _snapshot(tenant)
    gaps = _attestation(
        manual_outcome=False,
        validated_paths=["app.py"],
        repaid_debt=["normal-factory-proof"],
        undisposed_failures=["consumer-ci"],
    )
    code, detail = _refused(tenant.complete(acceptance, gaps))
    assert code == OUTSTANDING
    named = detail.split(": ", 1)[1].split("; ")
    assert named == [
        "original-path-unvalidated:tests/test_app.py",
        "deferred-debt-outstanding:spec-debt:scenario-12",
        "manual-outcome-missing",
        "related-failure-undisposed:consumer-ci",
    ]
    assert _snapshot(tenant) == before


@pytest.mark.parametrize(
    ("lost", "refusal"),
    [
        ("pr", "incident-completion-repayment-pr-unobservable"),
        ("pr-reply", "incident-completion-repayment-pr-unobservable"),
        ("run", "incident-repayment-master-ci-unobservable"),
    ],
)
def test_complete_incident_refuses_a_repayment_the_forge_cannot_report(
    tenant: _Tenant, lost: str, refusal: str
) -> None:
    acceptance = _repayment_merged(tenant.client)
    _proven(tenant)
    if lost == "pr":
        del tenant.forge.prs[str(REPAYMENT_PR)]
    elif lost == "pr-reply":
        tenant.forge.prs[str(REPAYMENT_PR)] = dict(state="MERGED")
    else:
        del tenant.forge.runs[MASTER_RUN]
    before = _snapshot(tenant)
    code, _detail = _refused(tenant.complete(acceptance))
    assert code == refusal
    assert _snapshot(tenant) == before


def test_complete_incident_repeated_after_closed_recovers_and_writes_nothing(
    tenant: _Tenant,
) -> None:
    acceptance = _repayment_merged(tenant.client)
    _proven(tenant)
    first = tenant.complete(acceptance)
    assert first[0] == 0, first[1]
    after = _snapshot(tenant)
    code, response = tenant.complete(acceptance)
    assert code == 0, response
    result = response["result"]
    assert (result["recorded"], result["recovered"], result["reading"]) == (True, True, None)
    assert _snapshot(tenant) == after


@pytest.mark.parametrize(
    "attestation",
    [
        "[]",
        json.dumps(json.loads(_attestation()), indent=2),
        _attestation(manual_outcome="true"),
        _attestation(validated_paths="app.py"),
        _attestation(repaid_debt=[1]),
        _json(dict(manual_outcome=True)),
    ],
)
def test_a_completion_attestation_that_is_not_its_canonical_record_is_refused_by_name(
    tenant: _Tenant, attestation: str
) -> None:
    acceptance = _repayment_merged(tenant.client)
    _proven(tenant)
    before = _snapshot(tenant)
    code, detail = _refused(tenant.complete(acceptance, attestation))
    assert code == "incident-action-invalid-payload"
    assert detail.startswith("--completion-json: ")
    assert _snapshot(tenant) == before
    # Nothing was read from the forge for a payload that never decoded.
    assert tenant.forge.calls == []


def test_complete_incident_payloads_are_required_and_valid_only_for_their_actions(
    tenant: _Tenant,
) -> None:
    acceptance = _repayment_merged(tenant.client)
    # Without the master run named, or with another action's payload, it is a usage error.
    assert tenant.cli("complete-incident", acceptance, "--completion-json", _attestation())[0] == 2
    assert (
        tenant.cli(
            "advance-repayment",
            acceptance,
            "--to-phase",
            "repayment-acceptance",
            "--completion-json",
            _attestation(),
        )[0]
        == 2
    )
    assert (
        tenant.cli(
            "complete-incident",
            acceptance,
            *("--master-run", MASTER_RUN, "--completion-json", _attestation()),
            *("--target-ref", REPAYMENT_REF),
        )[0]
        == 2
    )
