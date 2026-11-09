"""A repair whose expedited PR closed unmerged on a failed fast check opens a corrected attempt.

bd-ib-elq5ry. `SPECIFICATION/contracts.md` section "Carrier identity before and
after PR creation". Each case is driven through the `incident_authority.py`
process boundary (`correct-unmerged-attempt`) over an in-memory tenant whose
chain the canonical genesis and transition writers recorded, with the forge's
`gh pr view` and `gh run view` replies as the only fake effect.
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
from livespec_orchestrator_beads_fabro._incident_genesis import decode_genesis_request
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
from livespec_orchestrator_beads_fabro.incident_regression_recovery import retained_failures

REPOSITORY = "owner/repository"
ITEM = "test-incident"
PRINCIPAL = "operator:alice"
REPAIR_BRANCH = "incident/test-incident-attempt-1"
REPAIR_REF = "refs/heads/" + REPAIR_BRANCH
CORRECTED_REF = "refs/heads/incident/test-incident-attempt-2"
THIRD_REF = "refs/heads/incident/test-incident-attempt-3"
FAILED_HEAD = "b" * 40
FAILED_RUN = "pr-run-5"
FRESH_HEAD = "1" * 40
FRESH_TREE = "2" * 40
RECOVERY_MARKER = "livespec-incident-recovery-v1\n"
_IDENTITY = ("attempt_id", "phase", "operation_id", "generation", "owner")


def _json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


@dataclass
class _Forge:
    """`gh pr view` and `gh run view` as the forge answers them: the one fake effect."""

    prs: dict[str, dict[str, object]] = field(default_factory=dict)
    runs: dict[str, dict[str, object]] = field(default_factory=dict)
    calls: list[list[str]] = field(default_factory=list)

    def run(self, *, argv: list[str], **_: object) -> CommandResult:
        self.calls.append(argv)
        table: dict[str, Any] = self.prs if argv[1] == "pr" else self.runs
        reply = table.get(argv[3])
        if reply is None:
            return CommandResult(exit_code=1, stdout="", stderr="not found")
        return CommandResult(exit_code=0, stdout=json.dumps(reply), stderr="")


@dataclass
class _Tenant:
    client: FakeBeadsClient
    forge: _Forge
    root: Path
    reply: Any = None

    def cli(self, attempt: IncidentAttempt, *payload: str) -> tuple[int, Any]:
        argv = ["correct-unmerged-attempt", "--repo", str(self.root)]
        argv += ["--repository", REPOSITORY, "--item", attempt.item_id]
        argv += ["--attempt", attempt.attempt_id, "--phase", attempt.phase]
        argv += ["--operation", attempt.operation_id, "--generation", str(attempt.generation)]
        argv += ["--owner", attempt.owner, *payload]
        try:
            code = command.main(argv=argv)
        except SystemExit as error:
            code = error.code
        return int(code or 0), self.reply


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
            created_at="2026-11-08T00:00:00Z",
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
            head=FAILED_HEAD,
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
) -> IncidentReading | AuthorityRefusal:
    recorded = json.loads(_json(attempt_record(attempt=observed.attempt)))
    successor = decode_attempt(value=recorded | changes)
    assert successor is not None
    return commit_incident_transition(client=client, observed=observed, successor=successor)


def _advanced(
    client: FakeBeadsClient, observed: IncidentReading, **changes: Any
) -> IncidentReading:
    advanced = _successor(client, observed, **changes)
    assert isinstance(advanced, IncidentReading), advanced
    return advanced


def _reading(client: FakeBeadsClient, attempt: IncidentAttempt) -> IncidentReading:
    reading = read_incident_authority(
        client=client,
        repository=REPOSITORY,
        item_id=ITEM,
        query={key: getattr(attempt, key) for key in _IDENTITY},
        historical=True,
    )
    assert isinstance(reading, IncidentReading), reading
    return reading


def _genesis(state: _Tenant) -> IncidentReading:
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
    client.update_issue(issue_id=ITEM, status="active", assignee=PRINCIPAL)
    genesis = decode_attempt(value=_attempt())
    assert genesis is not None
    return _reading(client, genesis)


def _bound(state: _Tenant) -> IncidentReading:
    """Genesis, then the expedited repair PR #7 bound at the failed head."""
    carrier = dict(_attempt()["carrier"], state="pr-bound", remote_head=FAILED_HEAD)
    return _advanced(
        state.client,
        _genesis(state),
        generation=2,
        operation_id="bind-1",
        pr_number=7,
        carrier=carrier,
    )


def _closed_after_failure(state: _Tenant, **pr: object) -> None:
    """The forge: PR #7 closed unmerged at the failed head, run 5 failed on that head."""
    state.forge.prs["7"] = (
        dict(number=7, state="CLOSED", headRefName=REPAIR_BRANCH, headRefOid=FAILED_HEAD) | pr
    )
    state.forge.runs[FAILED_RUN] = dict(
        headSha=FAILED_HEAD, status="completed", conclusion="failure"
    )


def _correction(**changes: str) -> str:
    return _json(
        dict(
            kind="repair",
            evidence_id="lloc-split-commit",
            base="a" * 40,
            head=FRESH_HEAD,
            staged_tree=FRESH_TREE,
        )
        | changes
    )


def _correct(
    state: _Tenant, attempt: IncidentAttempt, *, correction: str, target: str = CORRECTED_REF
) -> tuple[int, Any]:
    return state.cli(
        attempt,
        "--failed-run",
        FAILED_RUN,
        "--correction-json",
        correction,
        "--target-ref",
        target,
    )


def _verified(reply: tuple[int, Any]) -> IncidentAttempt:
    code, response = reply
    assert code == 0, response
    assert (response["status"], response["normal_factory_proof"]) == ("verified", False)
    attempt = decode_attempt(value=response["result"]["reading"]["attempt"])
    assert attempt is not None
    return attempt


def _refused(reply: tuple[int, Any]) -> str:
    code, response = reply
    assert code == 78, response
    assert response["status"] == "refused"
    return response["result"]["code"]


def _records(client: FakeBeadsClient) -> list[dict[str, Any]]:
    return [
        json.loads(row["text"][len(RECOVERY_MARKER) :])
        for row in client.list_comments(issue_id=ITEM)
        if row["text"].startswith(RECOVERY_MARKER)
    ]


def _current(state: _Tenant, attempt: IncidentAttempt) -> IncidentReading:
    reading = read_incident_authority(
        client=state.client,
        repository=REPOSITORY,
        item_id=ITEM,
        query={key: getattr(attempt, key) for key in _IDENTITY},
    )
    assert isinstance(reading, IncidentReading), reading
    return reading


def test_a_repair_whose_expedited_pr_closed_unmerged_after_a_failed_fast_check_opens_a_corrected_attempt_retaining_the_failed_run(
    tenant: _Tenant,
) -> None:
    bound = _bound(tenant)
    _closed_after_failure(tenant)
    corrected = _verified(_correct(tenant, bound.attempt, correction=_correction()))
    # The same item, the next generation, a new attempt on its own fresh branch.
    assert (corrected.item_id, corrected.phase, corrected.generation) == (ITEM, "repair", 3)
    assert corrected.attempt_id != bound.attempt.attempt_id
    assert (corrected.pr_number, corrected.head, corrected.repayment_required) == (
        0,
        FRESH_HEAD,
        True,
    )
    assert attempt_record(attempt=corrected)["carrier"] == dict(
        state="branch-reserved",
        target_ref=CORRECTED_REF,
        input_parent="a" * 40,
        staged_tree=FRESH_TREE,
    )
    assert _current(tenant, corrected).is_current
    # The failed bound attempt stays in the history exactly as recorded.
    assert _reading(tenant.client, bound.attempt).attempt == bound.attempt
    # The forge was read for the chain's own PR and the operator's named run.
    assert [argv[1:4] for argv in tenant.forge.calls] == [
        ["pr", "view", "7"],
        ["run", "view", FAILED_RUN],
    ]
    # The failed run is retained as the corrected attempt's failure evidence.
    (record,) = _records(tenant.client)
    failure = dict(
        surface="pull-request",
        subject="pull-request#7",
        run_id=FAILED_RUN,
        failed_head=FAILED_HEAD,
        attributed_commit=FAILED_HEAD,
        master_healthy=True,
    )
    assert (record["kind"], record["source"], record["closed_pr_number"]) == (
        "corrected-attempt",
        "unmerged-pull-request",
        7,
    )
    assert (record["superseded_attempt_id"], record["superseded_generation"]) == ("attempt-1", 2)
    assert record["retained_failures"] == [failure]
    assert record["repayment_owed"] is True
    assert [f.run_id for f in retained_failures(client=tenant.client, item_id=ITEM)] == [FAILED_RUN]


def test_a_second_unmerged_correction_still_refuses_a_reland_of_the_first_failed_head(
    tenant: _Tenant,
) -> None:
    bound = _bound(tenant)
    _closed_after_failure(tenant)
    first = _verified(_correct(tenant, bound.attempt, correction=_correction()))
    # The corrected attempt's own PR #8 is bound, fails run 6 and is closed unmerged.
    rebound = _advanced(
        tenant.client,
        _current(tenant, first),
        generation=4,
        operation_id="bind-2",
        pr_number=8,
        carrier=dict(
            state="pr-bound",
            target_ref=CORRECTED_REF,
            input_parent="a" * 40,
            staged_tree=FRESH_TREE,
            remote_head=FRESH_HEAD,
        ),
    )
    tenant.forge.prs["8"] = dict(
        number=8,
        state="CLOSED",
        headRefName=CORRECTED_REF.removeprefix("refs/heads/"),
        headRefOid=FRESH_HEAD,
    )
    tenant.forge.runs["pr-run-6"] = dict(
        headSha=FRESH_HEAD, status="completed", conclusion="failure"
    )

    def again(**changes: str) -> tuple[int, Any]:
        return tenant.cli(
            rebound.attempt,
            "--failed-run",
            "pr-run-6",
            "--correction-json",
            _correction(**({"evidence_id": "second-fix"} | changes)),
            "--target-ref",
            THIRD_REF,
        )

    assert _refused(again(head=FAILED_HEAD)) == "incident-correction-unchanged-reland"
    assert _refused(again(evidence_id=FAILED_RUN)) == "incident-correction-unchanged-reland"
    second = _verified(again(head="3" * 40))
    assert (second.generation, second.pr_number) == (5, 0)
    runs = [f.run_id for f in retained_failures(client=tenant.client, item_id=ITEM)]
    assert runs == [FAILED_RUN, "pr-run-6"]


@pytest.mark.parametrize(
    ("pr", "run", "code"),
    [
        (dict(state="OPEN"), {}, "incident-correction-pr-not-closed-unmerged"),
        (dict(state="MERGED"), {}, "incident-correction-pr-not-closed-unmerged"),
        (dict(number=9), {}, "incident-correction-pr-not-closed-unmerged"),
        (dict(headRefOid="9" * 40), {}, "incident-correction-carrier-mismatch"),
        (dict(headRefName="incident/other"), {}, "incident-correction-carrier-mismatch"),
        ({}, dict(conclusion="success"), "incident-correction-run-not-failed-on-head"),
        ({}, dict(conclusion="cancelled"), "incident-correction-run-not-failed-on-head"),
        (
            {},
            dict(status="in_progress", conclusion=""),
            "incident-correction-run-not-failed-on-head",
        ),
        ({}, dict(headSha="9" * 40), "incident-correction-run-not-failed-on-head"),
        (dict(state=None), {}, "incident-correction-pr-unobservable"),
        ({}, dict(headSha=None), "incident-correction-run-unobservable"),
    ],
)
def test_a_corrected_attempt_from_an_unmerged_pr_is_refused_when_the_forge_does_not_show_it_closed_unmerged_after_a_failed_run_on_its_head(
    tenant: _Tenant, pr: dict[str, object], run: dict[str, object], code: str
) -> None:
    bound = _bound(tenant)
    _closed_after_failure(tenant)
    tenant.forge.prs["7"] |= pr
    tenant.forge.runs[FAILED_RUN] = {
        key: value
        for key, value in (tenant.forge.runs[FAILED_RUN] | run).items()
        if value is not None
    }
    tenant.forge.prs["7"] = {k: v for k, v in tenant.forge.prs["7"].items() if v is not None}
    comments = len(tenant.client.list_comments(issue_id=ITEM))
    assert _refused(_correct(tenant, bound.attempt, correction=_correction())) == code
    # Nothing is written: no generation and no recovery record.
    assert _current(tenant, bound.attempt).is_current
    assert len(tenant.client.list_comments(issue_id=ITEM)) == comments


def test_an_unreadable_pr_or_run_reply_is_refused_by_name(tenant: _Tenant) -> None:
    bound = _bound(tenant)
    pr_missing = _refused(_correct(tenant, bound.attempt, correction=_correction()))
    _closed_after_failure(tenant)
    del tenant.forge.runs[FAILED_RUN]
    run_missing = _refused(_correct(tenant, bound.attempt, correction=_correction()))
    assert (pr_missing, run_missing) == (
        "incident-correction-pr-unobservable",
        "incident-correction-run-unobservable",
    )
    assert _current(tenant, bound.attempt).is_current


@pytest.mark.parametrize(
    ("correction", "target", "code"),
    [
        (_correction(head=FAILED_HEAD), CORRECTED_REF, "incident-correction-unchanged-reland"),
        (
            _correction(evidence_id=FAILED_RUN),
            CORRECTED_REF,
            "incident-correction-unchanged-reland",
        ),
        (_correction(kind="retry"), CORRECTED_REF, "incident-correction-evidence-missing"),
        (_correction(), REPAIR_REF, "incident-correction-target-reused"),
        ("{}", CORRECTED_REF, "incident-action-invalid-payload"),
    ],
)
def test_an_unmerged_correction_needs_fresh_evidence_on_a_new_branch(
    tenant: _Tenant, correction: str, target: str, code: str
) -> None:
    bound = _bound(tenant)
    _closed_after_failure(tenant)
    assert _refused(_correct(tenant, bound.attempt, correction=correction, target=target)) == code
    assert _current(tenant, bound.attempt).is_current
    assert _records(tenant.client) == []


def test_only_the_current_pr_bound_repair_is_eligible_and_the_forge_is_not_read_otherwise(
    tenant: _Tenant,
) -> None:
    genesis = _genesis(tenant)
    _closed_after_failure(tenant)
    unbound = _refused(_correct(tenant, genesis.attempt, correction=_correction()))
    bound = _advanced(
        tenant.client,
        genesis,
        generation=2,
        operation_id="bind-1",
        pr_number=7,
        carrier=dict(_attempt()["carrier"], state="pr-bound", remote_head=FAILED_HEAD),
    )
    stale = _refused(_correct(tenant, genesis.attempt, correction=_correction()))
    merged = _advanced(
        tenant.client,
        bound,
        generation=3,
        operation_id="merge-1",
        phase="master-observation",
        landed_commits=[FAILED_HEAD],
        landed_trees=["e" * 40],
    )
    after_merge = _refused(_correct(tenant, merged.attempt, correction=_correction()))
    assert (unbound, stale, after_merge) == ("incident-correction-not-eligible",) * 3
    assert tenant.forge.calls == []
    # The action keeps the shared identity rule and owns its own payload flags.
    assert tenant.cli(bound.attempt, "--correction-json", _correction())[0] == 2


def test_the_transition_writer_accepts_the_unmerged_correction_only_as_a_new_attempt_on_a_new_ref(
    tenant: _Tenant,
) -> None:
    bound = _bound(tenant)
    fresh = dict(
        state="branch-reserved",
        target_ref=CORRECTED_REF,
        input_parent="a" * 40,
        staged_tree=FRESH_TREE,
    )
    common: dict[str, Any] = dict(
        generation=3, operation_id="correction-1#repair", pr_number=0, head=FRESH_HEAD
    )
    # A rewrite of the bound carrier back to a reservation on its own ref is refused.
    same_ref = _successor(
        tenant.client,
        bound,
        attempt_id="correction-1",
        carrier=dict(fresh, target_ref=REPAIR_REF),
        **common,
    )
    # A new ref under the failed attempt's own id is no new attempt.
    same_attempt = _successor(tenant.client, bound, carrier=fresh, **common)
    refusals = [
        result.code if isinstance(result, AuthorityRefusal) else result
        for result in (same_ref, same_attempt)
    ]
    assert refusals == ["incident-transition-invalid-successor"] * 2
    accepted = _successor(tenant.client, bound, attempt_id="correction-1", carrier=fresh, **common)
    assert isinstance(accepted, IncidentReading), accepted
    assert (accepted.attempt.phase, accepted.attempt.generation) == ("repair", 3)
