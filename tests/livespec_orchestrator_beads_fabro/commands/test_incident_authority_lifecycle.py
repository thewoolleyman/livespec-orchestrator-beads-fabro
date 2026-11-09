"""The incident-authority lifecycle actions drive repayment, reopen and correction.

bd-ib-nabx3u. One case per Definition-of-Done assertion, each driven through the
`incident_authority.py` process boundary over an in-memory tenant whose chain
the canonical genesis and transition writers recorded, with the forge's run
view as the only fake effect.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import pytest
from livespec_orchestrator_beads_fabro._beads_client import FakeBeadsClient, IssueDraft
from livespec_orchestrator_beads_fabro._incident_authority_payload import (
    attempt_record,
    decode_attempt,
)
from livespec_orchestrator_beads_fabro._incident_authority_types import IncidentAttempt
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

REPOSITORY = "owner/repository"
ITEM = "test-incident"
PRINCIPAL = "operator:alice"
REPAIR_REF = "refs/heads/incident/test-incident-attempt-1"
REPAYMENT_REF = "refs/heads/feat/test-incident"
CORRECTED_REF = "refs/heads/incident/test-incident-attempt-2"
MASTER_HEAD = "d" * 40
BROKEN_MASTER = "f" * 40
RECOVERY_MARKER = "livespec-incident-recovery-v1\n"
_IDENTITY = ("attempt_id", "phase", "operation_id", "generation", "owner")


def _json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


@dataclass
class _Forge:
    """`gh run view` as the forge answers it: the one fake effect."""

    runs: dict[str, dict[str, str]] = field(default_factory=dict)
    calls: list[list[str]] = field(default_factory=list)

    def run(self, *, argv: list[str], **_: object) -> CommandResult:
        self.calls.append(argv)
        reply = self.runs.get(argv[3])
        if reply is None:
            return CommandResult(exit_code=1, stdout="", stderr="run not found")
        return CommandResult(exit_code=0, stdout=json.dumps(reply), stderr="")


@dataclass
class _Tenant:
    client: FakeBeadsClient
    forge: _Forge
    root: Path

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

    reply: Any = None


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
    # `raising=False`: before the lifecycle actions exist the seam is absent too.
    monkeypatch.setattr(command, "ShellCommandRunner", lambda: state.forge, raising=False)
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


def _attempt(**changes: Any) -> dict[str, Any]:
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
            original_paths=["app.py"],
            deferred_work=["normal-factory-proof"],
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


def _successor(
    client: FakeBeadsClient, observed: IncidentReading, **changes: Any
) -> IncidentReading:
    recorded = json.loads(_json(attempt_record(attempt=observed.attempt)))
    successor = decode_attempt(value=recorded | changes)
    assert successor is not None
    advanced = commit_incident_transition(client=client, observed=observed, successor=successor)
    assert isinstance(advanced, IncidentReading), advanced
    return advanced


def _genesis_reading(client: FakeBeadsClient) -> IncidentReading:
    query = {key: _attempt()[key] for key in _IDENTITY}
    reading = read_incident_authority(
        client=client, repository=REPOSITORY, item_id=ITEM, query=query, historical=True
    )
    assert isinstance(reading, IncidentReading)
    return reading


def _merged_repair(state: _Tenant) -> IncidentAttempt:
    """Genesis, the repair PR bound, then its merge observed: the attempt owing repayment."""
    client = state.client
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
    bound = dict(_attempt()["carrier"], state="pr-bound", remote_head="b" * 40)
    pr_bound = _successor(
        client,
        _genesis_reading(client),
        generation=2,
        operation_id="bind-1",
        pr_number=7,
        carrier=bound,
    )
    observed = _successor(
        client,
        pr_bound,
        generation=3,
        operation_id="merge-1",
        phase="master-observation",
        landed_commits=[MASTER_HEAD],
        landed_trees=["e" * 40],
    )
    client.update_issue(issue_id=ITEM, status="active", assignee=PRINCIPAL)
    return observed.attempt


def _verified(reply: tuple[int, Any]) -> IncidentAttempt:
    code, response = reply
    assert code == 0, response
    assert response["status"] == "verified"
    assert response["normal_factory_proof"] is False
    assert response["authorizes_current_effects"] is False
    attempt = decode_attempt(value=response["result"]["reading"]["attempt"])
    assert attempt is not None
    return attempt


def _refused(reply: tuple[int, Any]) -> str:
    code, response = reply
    assert code == 78, response
    assert response["status"] == "refused"
    return f"{response['result']['code']}: {response['result']['detail']}"


def _green(state: _Tenant) -> None:
    state.forge.runs["master-run-1"] = dict(
        headSha=MASTER_HEAD, status="completed", conclusion="success"
    )


def _admitted(state: _Tenant) -> tuple[IncidentAttempt, IncidentAttempt]:
    observed = _merged_repair(state)
    _green(state)
    admission = _verified(
        state.cli(
            "enter-repayment",
            observed,
            "--master-run",
            "master-run-1",
            "--target-ref",
            REPAYMENT_REF,
        )
    )
    return observed, admission


def _live_repayment(state: _Tenant) -> tuple[IncidentAttempt, IncidentAttempt]:
    """Admitted, approved by ordinary admission, then claimed by one factory run."""
    observed, admission = _admitted(state)
    state.client.update_issue(issue_id=ITEM, status="ready")
    ready = _verified(
        state.cli(
            "advance-repayment",
            admission,
            "--to-phase",
            "repayment-ready",
            "--admission-complete",
        )
    )
    stamp = ClaimStamp(
        dispatch_id="01DISPATCH",
        dispatching_host="hp",
        run_id="run-1",
        factory_name="petri",
        factory_server="http://petri",
    )
    state.client.update_issue(
        issue_id=ITEM, status="active", assignee="fabro", metadata=claim_stamp_metadata(stamp=stamp)
    )
    active = _verified(state.cli("advance-repayment", ready, "--to-phase", "repayment-active"))
    return observed, active


def _finding(**changes: Any) -> str:
    return _json(
        dict(
            surface="trunk",
            subject="trunk-ci",
            run_id="master-run-9",
            failed_head=BROKEN_MASTER,
            attributed_commit=MASTER_HEAD,
            master_healthy=False,
        )
        | changes
    )


def _reopen(state: _Tenant, current: IncidentAttempt, attributed: IncidentAttempt, finding: str):
    return state.cli(
        "reopen-regression",
        current,
        "--attributed-json",
        _json(attempt_record(attempt=attributed)),
        "--finding-json",
        finding,
        "--principal",
        PRINCIPAL,
    )


def _recovery_kinds(client: FakeBeadsClient) -> list[str]:
    return [
        json.loads(row["text"][len(RECOVERY_MARKER) :])["kind"]
        for row in client.list_comments(issue_id=ITEM)
        if row["text"].startswith(RECOVERY_MARKER)
    ]


def test_enter_repayment_refuses_while_master_ci_is_incomplete_then_records_admission_once_green(
    tenant: _Tenant,
) -> None:
    observed = _merged_repair(tenant)
    enter = ("--master-run", "master-run-1", "--target-ref", REPAYMENT_REF)
    comments = len(tenant.client.list_comments(issue_id=ITEM))
    # The forge cannot report the run: a named refusal, never an assumed result.
    assert _refused(tenant.cli("enter-repayment", observed, *enter)).startswith(
        "incident-repayment-master-ci-unobservable: run master-run-1: run not found"
    )
    tenant.forge.runs["master-run-1"] = dict(
        headSha=MASTER_HEAD, status="in_progress", conclusion=""
    )
    assert _refused(tenant.cli("enter-repayment", observed, *enter)).startswith(
        "incident-repayment-master-ci-outstanding: "
    )
    # Nothing was recorded: the item, its comments and the chain are unchanged.
    assert len(tenant.client.list_comments(issue_id=ITEM)) == comments
    assert tenant.client.show_issue(issue_id=ITEM)["status"] == "active"
    assert tenant.forge.calls[-1] == [
        "gh",
        "run",
        "view",
        "master-run-1",
        "--repo",
        REPOSITORY,
        "--json",
        "headSha,status,conclusion",
    ]
    _green(tenant)
    admission = _verified(tenant.cli("enter-repayment", observed, *enter))
    assert (admission.item_id, admission.phase, admission.generation) == (
        ITEM,
        "repayment-admission",
        observed.generation + 1,
    )
    assert tenant.client.show_issue(issue_id=ITEM)["status"] == "pending-approval"


def test_advance_repayment_moves_the_admitted_repayment_one_phase_and_names_a_refused_phase(
    tenant: _Tenant,
) -> None:
    _, admission = _admitted(tenant)
    tenant.client.update_issue(issue_id=ITEM, status="ready")
    # Ordinary admission must be complete before the item is repayment-ready.
    assert _refused(
        tenant.cli("advance-repayment", admission, "--to-phase", "repayment-ready")
    ).startswith("incident-repayment-admission-incomplete: ")
    # A phase the current one does not permit is refused, naming both phases.
    assert _refused(
        tenant.cli("advance-repayment", admission, "--to-phase", "repayment-acceptance")
    ) == ("incident-repayment-phase-order: repayment-admission -> repayment-acceptance")
    ready = _verified(
        tenant.cli(
            "advance-repayment",
            admission,
            "--to-phase",
            "repayment-ready",
            "--admission-complete",
        )
    )
    assert (ready.item_id, ready.phase, ready.generation) == (
        ITEM,
        "repayment-ready",
        admission.generation + 1,
    )
    enter = ("--master-run", "master-run-1", "--target-ref", REPAYMENT_REF)
    assert tenant.cli("enter-repayment", ready, *enter, "--admission-complete")[0] == 2


@pytest.mark.parametrize("closed", [False, True])
def test_reopen_regression_reopens_the_same_item_into_a_fenced_reverting_generation(
    *, tenant: _Tenant, closed: bool
) -> None:
    observed, current = _live_repayment(tenant)
    if closed:
        reading = read_incident_authority(
            client=tenant.client,
            repository=REPOSITORY,
            item_id=ITEM,
            query={key: getattr(current, key) for key in _IDENTITY},
        )
        assert isinstance(reading, IncidentReading)
        carrier = asdict(current.carrier) if current.carrier is not None else {}
        acceptance = _successor(
            tenant.client,
            reading,
            generation=current.generation + 1,
            operation_id=f"{current.attempt_id}#repayment-acceptance",
            phase="repayment-acceptance",
            head="9" * 40,
            pr_number=12,
            landed_commits=["8" * 40],
            landed_trees=["7" * 40],
            carrier=carrier | dict(state="pr-bound", remote_head="9" * 40),
        )
        current = _successor(
            tenant.client,
            acceptance,
            generation=acceptance.attempt.generation + 1,
            operation_id=f"{current.attempt_id}#closed",
            phase="closed",
        ).attempt
        tenant.client.update_issue(issue_id=ITEM, status="closed")
    reverting = _verified(_reopen(tenant, current, observed, _finding()))
    assert (reverting.item_id, reverting.phase, reverting.generation) == (
        ITEM,
        "reverting",
        current.generation + 1,
    )
    assert reverting.repayment_required is True
    assert (reverting.owner, reverting.pr_number) == (PRINCIPAL, observed.pr_number)
    item = tenant.client.show_issue(issue_id=ITEM)
    assert (item["status"], item["assignee"]) == ("active", PRINCIPAL)
    assert _recovery_kinds(tenant.client) == ["recovery-request"]


def test_record_deferred_finding_owes_the_debt_and_a_reopen_on_it_alone_is_refused(
    tenant: _Tenant,
) -> None:
    observed, active = _live_repayment(tenant)
    deferred = _finding(surface="deferred-proof", run_id="proof-run-3", master_healthy=True)
    owed = _verified(tenant.cli("record-deferred-finding", active, "--finding-json", deferred))
    assert (owed.item_id, owed.phase, owed.generation) == (
        ITEM,
        "repayment-active",
        active.generation + 1,
    )
    assert owed.deferred_work[-1] == "deferred-finding:proof-run-3"
    assert _refused(_reopen(tenant, owed, observed, deferred)) == (
        "incident-finding-deferred-proof-only: "
        "deferred-finding:proof-run-3 is owed by the normal repayment pull request"
    )
    assert _recovery_kinds(tenant.client) == ["deferred-finding"]
    assert tenant.client.show_issue(issue_id=ITEM)["status"] == "active"


def test_correct_attempt_after_a_revert_receipt_opens_a_fresh_attempt_and_refuses_a_reland(
    tenant: _Tenant,
) -> None:
    observed, active = _live_repayment(tenant)
    reverting = _verified(_reopen(tenant, active, observed, _finding()))
    fresh = dict(
        kind="repair",
        evidence_id="repair-commit-2",
        base=BROKEN_MASTER,
        head="1" * 40,
        staged_tree="2" * 40,
    )
    correct = ("--correction-json", _json(fresh), "--target-ref", CORRECTED_REF)
    # A corrected attempt needs the recorded revert receipt first.
    assert _refused(tenant.cli("correct-attempt", reverting, *correct)).startswith(
        "incident-correction-not-eligible: reverting"
    )
    receipt = _json(dict(receipt_id="controller-receipt-1", revert_commit="3" * 40))
    collecting = _verified(
        tenant.cli("record-revert-receipt", reverting, "--revert-receipt-json", receipt)
    )
    assert collecting.phase == "collecting-failures"
    reland = _json(fresh | dict(head=MASTER_HEAD))
    assert _refused(
        tenant.cli(
            "correct-attempt",
            collecting,
            "--correction-json",
            reland,
            "--target-ref",
            CORRECTED_REF,
        )
    ).startswith("incident-correction-unchanged-reland: ")
    corrected = _verified(tenant.cli("correct-attempt", collecting, *correct))
    assert (corrected.item_id, corrected.phase, corrected.generation) == (
        ITEM,
        "repair",
        collecting.generation + 1,
    )
    assert (corrected.head, corrected.pr_number, corrected.repayment_required) == (
        "1" * 40,
        0,
        True,
    )
    assert corrected.carrier is not None and corrected.carrier.target_ref == CORRECTED_REF
    assert _recovery_kinds(tenant.client) == [
        "recovery-request",
        "revert-receipt",
        "corrected-attempt",
    ]


def test_record_rollback_conflict_blocks_the_current_reverting_attempt(
    tenant: _Tenant,
) -> None:
    observed, active = _live_repayment(tenant)
    reverting = _verified(_reopen(tenant, active, observed, _finding()))
    conflict = _json(
        dict(
            receipt="rollback-conflict:action-9:owner:operator:alice:head:" + BROKEN_MASTER,
            release_condition="controller-release:action-9",
        )
    )

    blocked = _verified(
        tenant.cli(
            "record-rollback-conflict",
            reverting,
            "--rollback-conflict-json",
            conflict,
        )
    )

    assert (blocked.phase, blocked.generation, blocked.owner) == (
        "rollback-conflict",
        reverting.generation + 1,
        PRINCIPAL,
    )
    assert (tenant.client.show_issue(issue_id=ITEM)["status"], _recovery_kinds(tenant.client)) == (
        "blocked",
        ["recovery-request", "rollback-conflict"],
    )


def test_rollback_conflict_actions_refuse_invalid_generations_and_resolve_exact_retries(
    tenant: _Tenant,
) -> None:
    module_path = Path(command.__file__).with_name("_incident_rollback_conflict.py")
    assert module_path.is_file()
    observed, active = _live_repayment(tenant)
    reverting = _verified(_reopen(tenant, active, observed, _finding()))
    conflict = _json(
        dict(
            receipt="rollback-conflict:action-9:owner:operator:alice:head:" + BROKEN_MASTER,
            release_condition="controller-release:action-9",
        )
    )
    assert _refused(
        tenant.cli("record-rollback-conflict", active, "--rollback-conflict-json", conflict)
    ) == ("incident-rollback-conflict-not-eligible: repayment-active")
    blocked = _verified(
        tenant.cli("record-rollback-conflict", reverting, "--rollback-conflict-json", conflict)
    )
    assert _refused(
        tenant.cli(
            "record-rollback-conflict",
            reverting,
            "--rollback-conflict-json",
            _json(dict(receipt="different", release_condition="different")),
        )
    ).startswith("incident-generation-stale: ")
    assert (
        _verified(
            tenant.cli("record-rollback-conflict", reverting, "--rollback-conflict-json", conflict)
        )
        == blocked
    )
    unresolved = _json(
        dict(
            release_condition="controller-release:action-9",
            revert_receipt_id="",
            revert_commit="",
        )
    )
    assert (
        _refused(
            tenant.cli(
                "resolve-rollback-conflict",
                blocked,
                "--rollback-resolution-json",
                unresolved.replace("action-9", "action-10"),
            )
        )
        == "incident-rollback-conflict-release-unmet: controller-release:action-10"
    )
    reverting_again = _verified(
        tenant.cli(
            "resolve-rollback-conflict",
            blocked,
            "--rollback-resolution-json",
            unresolved,
        )
    )
    assert (reverting_again.phase, tenant.client.show_issue(issue_id=ITEM)["status"]) == (
        "reverting",
        "active",
    )
    assert (
        _verified(
            tenant.cli(
                "resolve-rollback-conflict",
                blocked,
                "--rollback-resolution-json",
                unresolved,
            )
        )
        == reverting_again
    )


def test_rollback_conflict_resolution_with_a_receipt_collects_failures(tenant: _Tenant) -> None:
    observed, active = _live_repayment(tenant)
    reverting = _verified(_reopen(tenant, active, observed, _finding()))
    blocked = _verified(
        tenant.cli(
            "record-rollback-conflict",
            reverting,
            "--rollback-conflict-json",
            _json(dict(receipt="owned-conflict", release_condition="controller-release:receipt")),
        )
    )
    collecting = _verified(
        tenant.cli(
            "resolve-rollback-conflict",
            blocked,
            "--rollback-resolution-json",
            _json(
                dict(
                    release_condition="controller-release:receipt",
                    revert_receipt_id="controller-receipt-1",
                    revert_commit="3" * 40,
                )
            ),
        )
    )
    assert (collecting.phase, tenant.client.show_issue(issue_id=ITEM)["status"]) == (
        "collecting-failures",
        "active",
    )
    assert _recovery_kinds(tenant.client)[-2:] == ["rollback-conflict", "revert-receipt"]


@pytest.mark.parametrize(
    ("action", "payload"),
    [
        ("enter-repayment", ("--master-run", "master-run-1", "--target-ref", REPAYMENT_REF)),
        ("advance-repayment", ("--to-phase", "repayment-ready")),
        (
            "reopen-regression",
            ("--attributed-json", "{}", "--finding-json", "{}", "--principal", PRINCIPAL),
        ),
        ("record-deferred-finding", ("--finding-json", "{}")),
        ("record-revert-receipt", ("--revert-receipt-json", "{}")),
        ("correct-attempt", ("--correction-json", "{}", "--target-ref", CORRECTED_REF)),
    ],
)
def test_every_lifecycle_action_keeps_the_identity_rule_and_one_json_reply(
    tenant: _Tenant, action: str, payload: tuple[str, ...]
) -> None:
    observed = _merged_repair(tenant)
    # A missing identity argument, or another action's payload, is a usage error.
    try:
        missing = command.main(
            argv=[
                action,
                *("--repo", str(tenant.root), "--repository", REPOSITORY),
                *("--operation", observed.operation_id, "--owner", observed.owner),
                *payload,
            ]
        )
    except SystemExit as error:
        missing = error.code
    assert missing == 2
    assert tenant.cli(action, observed, *payload, "--receipt-id", "hook-1")[0] == 2
    # A refusal is one schema-1 JSON reply naming its code; nothing is written.
    comments = len(tenant.client.list_comments(issue_id=ITEM))
    code, response = tenant.cli(action, observed, *payload)
    assert code == 78, response
    assert (response["schema"], response["status"]) == (1, "refused")
    assert response["result"]["code"].startswith("incident-")
    assert len(tenant.client.list_comments(issue_id=ITEM)) == comments


@pytest.mark.parametrize(
    "finding",
    [
        _json(dict(surface="trunk")),
        json.dumps(json.loads(_finding()), indent=2),
        _finding().replace('"master_healthy":false', '"master_healthy":"false"'),
    ],
)
def test_a_payload_that_is_not_its_canonical_record_is_refused_by_name(
    tenant: _Tenant, finding: str
) -> None:
    observed, active = _live_repayment(tenant)
    for _code, response in (
        tenant.cli("record-deferred-finding", active, "--finding-json", finding),
        _reopen(tenant, active, observed, finding),
    ):
        assert _code == 78, response
        assert response["result"]["code"] == "incident-action-invalid-payload"
        assert response["result"]["detail"].startswith("--finding-json: ")
    assert _recovery_kinds(tenant.client) == []
    assert asdict(active) == asdict(_live_current(tenant, active))


def _live_current(state: _Tenant, attempt: IncidentAttempt) -> IncidentAttempt:
    reading = read_incident_authority(
        client=state.client,
        repository=REPOSITORY,
        item_id=ITEM,
        query={key: getattr(attempt, key) for key in _IDENTITY},
    )
    assert isinstance(reading, IncidentReading) and reading.is_current
    return reading.attempt
