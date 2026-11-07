"""An attributable regression fences repayment and reopens the same incident.

Scenarios "an attributable regression fences repayment and reopens the same
incident" and "a deferred-proof-only finding is repaired without reverting
healthy master" (bd-ib-k5teti). One case per Definition-of-Done assertion, each
driven through the public recovery surface over an in-memory tenant whose
incident chain was written by the canonical genesis, transition and normal
repayment writers.
"""

from __future__ import annotations

import json
from dataclasses import asdict, replace
from typing import Any

import pytest
from livespec_orchestrator_beads_fabro import incident_regression_recovery as recovery_module
from livespec_orchestrator_beads_fabro._beads_client import FakeBeadsClient, IssueDraft
from livespec_orchestrator_beads_fabro._incident_authority_payload import (
    attempt_record,
    decode_attempt,
)
from livespec_orchestrator_beads_fabro._incident_authority_types import IncidentAttempt
from livespec_orchestrator_beads_fabro._incident_genesis import decode_genesis_request
from livespec_orchestrator_beads_fabro._incident_recovery_correction import (
    plan_corrected_attempt,
)
from livespec_orchestrator_beads_fabro._incident_recovery_plan import (
    RECOVERY_MARKER,
    plan_reopen,
)
from livespec_orchestrator_beads_fabro._store_claim_tokens import ClaimChangeResult, change_claim
from livespec_orchestrator_beads_fabro._store_dispatch_claim import (
    CLAIM_TOKEN_METADATA_KEY,
    ClaimStamp,
    claim_stamp_from_record,
    claim_stamp_metadata,
    create_claim_token,
)
from livespec_orchestrator_beads_fabro.incident_authority import (
    AuthorityRefusal,
    IncidentReading,
    commit_incident_transition,
    publish_incident_genesis,
    read_incident_authority,
)
from livespec_orchestrator_beads_fabro.incident_normal_repayment import (
    REPAYMENT_OWNER,
    MasterCiRun,
    RepaymentEntry,
    advance_repayment,
    enter_repayment,
    repayment_scope,
    validate_repayment_carrier,
)
from livespec_orchestrator_beads_fabro.incident_regression_recovery import (
    Correction,
    Finding,
    RecoveryEntry,
    RevertReceipt,
    classify_finding,
    enter_corrected_attempt,
    record_deferred_finding,
    record_revert_receipt,
    recovery_attempts,
    reopen_for_regression,
    require_repayment_current,
    retained_failures,
)

REPOSITORY = "owner/repository"
ITEM = "test-incident"
PRINCIPAL = "operator:alice"
REPAIR_REF = "refs/heads/incident/test-incident-attempt-1"
REPAYMENT_REF = "refs/heads/feat/test-incident"
CORRECTED_REF = "refs/heads/incident/test-incident-attempt-2"
REPAIR_PR = 7
REPAYMENT_PR = 12
MASTER_HEAD = "d" * 40
MASTER_TREE = "e" * 40
BROKEN_MASTER = "f" * 40
FRESH_HEAD = "1" * 40
FRESH_TREE = "2" * 40
GREEN = MasterCiRun(run_id="master-run-1", head=MASTER_HEAD, conclusion="success", complete=True)
FACTORY_DISPATCH = "01DISPATCH"


def _finding(**changes: Any) -> Finding:
    return replace(
        Finding(
            surface="trunk",
            subject="trunk-ci",
            run_id="master-run-9",
            failed_head=BROKEN_MASTER,
            attributed_commit=MASTER_HEAD,
            master_healthy=False,
        ),
        **changes,
    )


def _json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


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
            original_paths=["app.py", "tests/test_app.py"],
            deferred_work=["normal-factory-proof", "spec-debt:scenario-12"],
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


def _ledger() -> tuple[FakeBeadsClient, str]:
    client = FakeBeadsClient()
    _ = client.create_issue(
        draft=IssueDraft(
            issue_id=ITEM,
            issue_type="bug",
            title="incident",
            description="behavior",
            assignee=None,
            created_at="2026-11-05T00:00:00Z",
        )
    )
    token = create_claim_token(client=client)
    client.update_issue(
        issue_id=ITEM,
        status="ready",
        metadata={"rank": "a0", CLAIM_TOKEN_METADATA_KEY: token},
        names_claim_token=True,
    )
    return client, token


def _successor(
    client: FakeBeadsClient, observed: IncidentReading, **changes: Any
) -> IncidentReading:
    recorded = json.loads(_json(attempt_record(attempt=observed.attempt)))
    successor = decode_attempt(value=recorded | changes)
    assert successor is not None
    advanced = commit_incident_transition(client=client, observed=observed, successor=successor)
    assert isinstance(advanced, IncidentReading), advanced
    return advanced


def _merged_repair(client: FakeBeadsClient, token: str) -> IncidentReading:
    """Genesis, the repair PR bound, then its merge observed on master."""
    request = decode_genesis_request(
        text=_json(dict(schema=1, principal=PRINCIPAL, expected_claim=token, attempt=_attempt())),
        repository=REPOSITORY,
        item_id=ITEM,
        operation_id="operation-1",
    )
    assert request is not None
    assert not isinstance(
        publish_incident_genesis(client=client, request=request, claim_tokens=True),
        AuthorityRefusal,
    )
    query = {k: _attempt()[k] for k in ("attempt_id", "phase", "operation_id", "generation")}
    genesis = read_incident_authority(
        client=client, repository=REPOSITORY, item_id=ITEM, query=query | {"owner": PRINCIPAL}
    )
    assert isinstance(genesis, IncidentReading)
    bound = dict(
        state="pr-bound",
        target_ref=REPAIR_REF,
        input_parent="a" * 40,
        staged_tree="c" * 40,
        remote_head="b" * 40,
    )
    pr_bound = _successor(
        client, genesis, generation=2, operation_id="bind-1", pr_number=REPAIR_PR, carrier=bound
    )
    observed = _successor(
        client,
        pr_bound,
        generation=3,
        operation_id="merge-1",
        phase="master-observation",
        landed_commits=[MASTER_HEAD],
        landed_trees=[MASTER_TREE],
    )
    client.update_issue(issue_id=ITEM, status="active", assignee=PRINCIPAL)
    return observed


def _entry(result: RepaymentEntry | AuthorityRefusal) -> RepaymentEntry:
    assert isinstance(result, RepaymentEntry), result
    return result


def _recovered(result: RecoveryEntry | AuthorityRefusal) -> RecoveryEntry:
    assert isinstance(result, RecoveryEntry), result
    return result


def _code(result: object) -> str:
    assert isinstance(result, AuthorityRefusal), result
    return result.code


def _live_repayment() -> tuple[FakeBeadsClient, IncidentReading, IncidentReading]:
    """The merged repair, then its normal repayment live under one factory claim."""
    client, token = _ledger()
    observed = _merged_repair(client, token)
    admission = _entry(
        enter_repayment(client=client, reading=observed, master_ci=GREEN, target_ref=REPAYMENT_REF)
    )
    client.update_issue(issue_id=ITEM, status="ready")
    ready = _entry(
        advance_repayment(
            client=client,
            reading=admission.reading,
            phase="repayment-ready",
            admission_complete=True,
        )
    )
    stamp = ClaimStamp(
        dispatch_id=FACTORY_DISPATCH,
        dispatching_host="hp",
        run_id="run-1",
        factory_name="petri",
        factory_server="http://petri",
    )
    client.update_issue(
        issue_id=ITEM,
        status="active",
        assignee=REPAYMENT_OWNER,
        metadata=claim_stamp_metadata(stamp=stamp),
    )
    active = _entry(
        advance_repayment(client=client, reading=ready.reading, phase="repayment-active")
    )
    return client, observed, active.reading


def _closed_incident() -> tuple[FakeBeadsClient, IncidentReading, IncidentReading]:
    """The repayment PR merged with its proof, and the incident closed on the same item."""
    client, observed, active = _live_repayment()
    carrier = active.attempt.carrier
    assert carrier is not None
    repaid = dict(
        state="pr-bound",
        target_ref=REPAYMENT_REF,
        input_parent=carrier.input_parent,
        staged_tree=carrier.staged_tree,
        remote_head="9" * 40,
    )
    acceptance = _successor(
        client,
        active,
        generation=active.attempt.generation + 1,
        operation_id=f"{active.attempt.attempt_id}#repayment-acceptance",
        phase="repayment-acceptance",
        head="9" * 40,
        pr_number=REPAYMENT_PR,
        landed_commits=["8" * 40],
        landed_trees=["7" * 40],
        carrier=repaid,
    )
    closed = _successor(
        client,
        acceptance,
        generation=acceptance.attempt.generation + 1,
        operation_id=f"{active.attempt.attempt_id}#closed",
        phase="closed",
    )
    client.update_issue(issue_id=ITEM, status="closed")
    return client, observed, closed


def _factory_terminal_write(client: FakeBeadsClient) -> str:
    """The superseded run's late terminal write, decided on its own factory stamp."""

    def still_ours(row: dict[str, Any]) -> bool:
        stamp = claim_stamp_from_record(record=row)
        return stamp is not None and stamp.dispatch_id == FACTORY_DISPATCH

    return change_claim(
        client=client,
        work_item_id=ITEM,
        writer="dispatcher-terminal",
        intent="terminal",
        claim_tokens=True,
        status="acceptance",
        still_as_decided=still_ours,
    ).outcome


def _recovery_records(client: FakeBeadsClient) -> list[dict[str, Any]]:
    """Every retained recovery record on the item, decoded, in append order."""
    return [
        json.loads(row["text"][len(RECOVERY_MARKER) :])
        for row in client.list_comments(issue_id=ITEM)
        if row["text"].startswith(RECOVERY_MARKER)
    ]


def _unobservable_claim(**_: object) -> ClaimChangeResult:
    """A lifecycle write whose claim-token outcome could not be read back."""
    return ClaimChangeResult(outcome="claim-unobservable")


def _assert_item_held_by_recovery(client: FakeBeadsClient, reopened: IncidentAttempt) -> None:
    """Back under the incident owner, the factory stamp retained as the prior claim."""
    item = client.show_issue(issue_id=ITEM)
    assert (item["status"], item.get("assignee")) == ("active", PRINCIPAL)
    holder = claim_stamp_from_record(record=item)
    assert holder is not None and holder.dispatch_id == f"incident:{reopened.operation_id}"
    claim = item["metadata"]["incident_claim"]
    assert (claim["operation_id"], claim["generation"], claim["owner"]) == (
        reopened.operation_id,
        reopened.generation,
        PRINCIPAL,
    )
    assert claim["prior_claim"]["dispatch_claim"]["dispatch_id"] == FACTORY_DISPATCH


def _assert_a_closed_incident_reopens_the_same_item() -> None:
    """An already closed incident reopens the same item from its closed generation."""
    closed_client, closed_observed, closed = _closed_incident()
    consumer = _finding(surface="consumer", subject="owner/consumer", run_id="consumer-run-3")
    reopen_closed = _recovered(
        reopen_for_regression(
            client=closed_client,
            reading=closed,
            attributed=closed_observed.attempt,
            finding=consumer,
            owner=PRINCIPAL,
        )
    )
    assert (reopen_closed.reading.attempt.phase, reopen_closed.reading.attempt.generation) == (
        "reverting",
        closed.attempt.generation + 1,
    )
    assert closed_client.show_issue(issue_id=ITEM)["status"] == "active"
    assert retained_failures(client=closed_client, item_id=ITEM) == (consumer,)


def _assert_stale_corrections_refused(
    client: FakeBeadsClient, collecting: IncidentReading, fresh: Correction, finding: Finding
) -> None:
    """An unchanged reland, a reused failing run or no evidence is refused by name."""
    for head in (MASTER_HEAD, BROKEN_MASTER):
        assert _code(
            enter_corrected_attempt(
                client=client,
                reading=collecting,
                correction=replace(fresh, head=head),
                target_ref=CORRECTED_REF,
            )
        ) == ("incident-correction-unchanged-reland")
    reused = replace(fresh, kind="measured-resolution", evidence_id=finding.run_id)
    assert _code(
        enter_corrected_attempt(
            client=client, reading=collecting, correction=reused, target_ref=CORRECTED_REF
        )
    ) == ("incident-correction-unchanged-reland")
    for missing in (replace(fresh, kind="retry"), replace(fresh, evidence_id="")):
        assert _code(
            enter_corrected_attempt(
                client=client,
                reading=collecting,
                correction=missing,
                target_ref=CORRECTED_REF,
            )
        ) == ("incident-correction-evidence-missing")


def _assert_foreign_records_ignored(client: FakeBeadsClient) -> None:
    """Foreign, malformed and duplicate records count once and retain only real failures."""
    client.seed_comment(issue_id=ITEM, text="an ordinary comment")
    client.seed_comment(issue_id=ITEM, text=RECOVERY_MARKER + "not json")
    foreign = dict(kind="recovery-request", item_id="other-item", retained_failures=[])
    client.seed_comment(issue_id=ITEM, text=RECOVERY_MARKER + _json(foreign))
    odd = dict(kind="recovery-request", item_id=ITEM, retained_failures=["x", {"run_id": "r"}])
    for _ in range(2):
        client.seed_comment(issue_id=ITEM, text=RECOVERY_MARKER + _json(odd))
    unlisted = dict(kind="recovery-request", item_id=ITEM, retained_failures=5)
    client.seed_comment(issue_id=ITEM, text=RECOVERY_MARKER + _json(unlisted))
    assert (
        retained_failures(client=client, item_id=ITEM),
        recovery_attempts(client=client, item_id=ITEM),
    ) == ((), 2)


def test_a_demonstrated_related_master_pull_request_or_consumer_regression_reopens_the_same_incident_item_with_a_new_fenced_generation_and_a_recovery_request() -> (
    None
):
    client, observed, active = _live_repayment()
    finding = _finding()
    # Change evidence must name a landed incident commit; an unrelated failure reopens nothing.
    unrelated = reopen_for_regression(
        client=client,
        reading=active,
        attributed=observed.attempt,
        finding=_finding(attributed_commit="0" * 40),
        owner=PRINCIPAL,
    )
    assert _code(unrelated) == "incident-regression-unattributed"
    assert recovery_attempts(client=client, item_id=ITEM) == 0
    minted = client.no_history_issue_ids()
    entry = _recovered(
        reopen_for_regression(
            client=client,
            reading=active,
            attributed=observed.attempt,
            finding=finding,
            owner=PRINCIPAL,
        )
    )
    reopened = entry.reading.attempt
    # The SAME item, the next fenced generation, bound to the attributed merged carrier.
    assert (reopened.item_id, reopened.phase, reopened.generation, reopened.owner) == (
        ITEM,
        "reverting",
        active.attempt.generation + 1,
        PRINCIPAL,
    )
    assert (reopened.pr_number, reopened.landed_commits) == (REPAIR_PR, (MASTER_HEAD,))
    assert reopened.carrier is not None and reopened.carrier.target_ref == REPAIR_REF
    assert (reopened.repayment_required, reopened.original_paths) == (
        True,
        active.attempt.original_paths,
    )
    assert (entry.reading.is_current, entry.lifecycle_state) == (True, "active")
    # The item is back under the incident owner, the factory's stamp retained as prior.
    _assert_item_held_by_recovery(client, reopened)
    # Recovery is requested on the item, and the original failure is retained.
    assert retained_failures(client=client, item_id=ITEM) == (finding,)
    assert recovery_attempts(client=client, item_id=ITEM) == 1
    requests = _recovery_records(client)
    assert [(r["kind"], r["generation"], r["repayment_owed"]) for r in requests] == [
        ("recovery-request", reopened.generation, True)
    ]
    assert requests[0]["superseded_generation"] == active.attempt.generation
    assert requests[0]["attributed_pr_number"] == REPAIR_PR
    # A duplicate delivery recovers the recorded generation: no token, record or write.
    comments = client.list_comments(issue_id=ITEM)
    tokens = client.no_history_issue_ids()
    assert len(tokens) > len(minted)
    again = _recovered(
        reopen_for_regression(
            client=client,
            reading=active,
            attributed=observed.attempt,
            finding=finding,
            owner=PRINCIPAL,
        )
    )
    assert again.reading.attempt == reopened
    assert (client.no_history_issue_ids(), client.list_comments(issue_id=ITEM)) == (
        tokens,
        comments,
    )
    # A pull-request or consumer failure with the same change evidence is a regression too.
    for surface in ("pull-request", "consumer"):
        disposition = classify_finding(
            finding=_finding(surface=surface), attributed=observed.attempt
        )
        assert not isinstance(disposition, AuthorityRefusal)
        assert disposition.kind == "reopen-recovery"
    # An already closed incident reopens the same item from its closed generation.
    _assert_a_closed_incident_reopens_the_same_item()


def test_a_superseded_repayment_operation_refuses_merge_proof_and_closure_side_effects_against_the_corrected_incident_attempt() -> (
    None
):
    client, observed, active = _live_repayment()
    # While it is current, the repayment's own effects pass the gate.
    assert require_repayment_current(client=client, observed=active, effect="merge") == active
    _ = _recovered(
        reopen_for_regression(
            client=client,
            reading=active,
            attributed=observed.attempt,
            finding=_finding(),
            owner=PRINCIPAL,
        )
    )
    for effect in ("merge", "proof", "closure"):
        refusal = require_repayment_current(client=client, observed=active, effect=effect)
        assert isinstance(refusal, AuthorityRefusal)
        assert refusal.code == "incident-repayment-superseded"
        assert refusal.detail.startswith(f"{ITEM}: {effect} refused")
    # The stale repayment cannot write its acceptance or closure into the chain either.
    stale_close = commit_incident_transition(
        client=client,
        observed=active,
        successor=replace(
            active.attempt,
            operation_id=f"{active.attempt.attempt_id}#late",
            generation=active.attempt.generation + 1,
        ),
    )
    assert _code(stale_close) == "incident-generation-stale"
    # Nor can the superseded run's late terminal write land on the item.
    assert _factory_terminal_write(client) == "claim-changed"
    assert client.show_issue(issue_id=ITEM)["status"] == "active"
    # A stale observation that is not a repayment keeps the generic stale refusal.
    assert _code(require_repayment_current(client=client, observed=observed, effect="proof")) == (
        "incident-generation-stale"
    )


def test_a_defect_isolated_to_deferred_factory_proof_is_repaired_in_the_normal_repayment_pull_request_while_an_otherwise_healthy_master_merge_remains_in_place() -> (
    None
):
    client, observed, active = _live_repayment()
    deferred = _finding(surface="deferred-proof", subject="factory-proof", run_id="proof-run-4")
    deferred = replace(deferred, master_healthy=True)
    disposition = classify_finding(finding=deferred, attributed=observed.attempt)
    assert not isinstance(disposition, AuthorityRefusal)
    assert (disposition.kind, disposition.obligation) == (
        "repair-in-repayment",
        "deferred-finding:proof-run-4",
    )
    # It never reopens or reverts the successful merge.
    refused = reopen_for_regression(
        client=client,
        reading=active,
        attributed=observed.attempt,
        finding=deferred,
        owner=PRINCIPAL,
    )
    assert _code(refused) == "incident-finding-deferred-proof-only"
    assert require_repayment_current(client=client, observed=active, effect="merge") == active
    # It is owed by the live repayment pull request, under normal validation.
    owed = _recovered(record_deferred_finding(client=client, reading=active, finding=deferred))
    attempt = owed.reading.attempt
    assert (attempt.phase, attempt.generation, attempt.pr_number) == (
        "repayment-active",
        active.attempt.generation + 1,
        0,
    )
    assert attempt.deferred_work[-1] == "deferred-finding:proof-run-4"
    item = client.show_issue(issue_id=ITEM)
    stamp = claim_stamp_from_record(record=item)
    assert (item["status"], item.get("assignee")) == ("active", REPAYMENT_OWNER)
    assert stamp is not None and stamp.dispatch_id == FACTORY_DISPATCH
    assert recovery_attempts(client=client, item_id=ITEM) == 0
    scope = repayment_scope(attempt=attempt)
    original_debt = ("normal-factory-proof", "spec-debt:scenario-12")
    unrepaired = validate_repayment_carrier(
        scope=scope,
        marker_paths=(),
        validated_paths=scope.original_paths,
        repaid_debt=original_debt,
    )
    assert unrepaired.outstanding == ("deferred-debt-outstanding:deferred-finding:proof-run-4",)
    repaired = validate_repayment_carrier(
        scope=scope,
        marker_paths=(),
        validated_paths=scope.original_paths,
        repaid_debt=(*original_debt, "deferred-finding:proof-run-4"),
    )
    assert repaired.complete is True
    # Not isolated (master unhealthy), or a master/PR/consumer failure: not repayment debt.
    assert _code(
        record_deferred_finding(
            client=client, reading=owed.reading, finding=replace(deferred, master_healthy=False)
        )
    ) == ("incident-finding-not-isolated")
    assert _code(
        record_deferred_finding(client=client, reading=owed.reading, finding=_finding())
    ) == ("incident-finding-requires-recovery")
    # Only a live repayment owes it; a merged repair awaiting repayment does not.
    assert _code(record_deferred_finding(client=client, reading=observed, finding=deferred)) == (
        "incident-finding-repayment-not-live"
    )


def test_a_corrected_expedited_attempt_retains_original_failed_ci_evidence_and_requires_fresh_repair_or_measured_resolution_evidence_while_final_normal_repayment_stays_owed() -> (
    None
):
    client, observed, active = _live_repayment()
    finding = _finding()
    reverting = _recovered(
        reopen_for_regression(
            client=client,
            reading=active,
            attributed=observed.attempt,
            finding=finding,
            owner=PRINCIPAL,
        )
    ).reading
    fresh = Correction(
        kind="repair",
        evidence_id="repair-commit-2",
        base=BROKEN_MASTER,
        head=FRESH_HEAD,
        staged_tree=FRESH_TREE,
    )
    # A corrected attempt needs the completed revert first.
    assert _code(
        enter_corrected_attempt(
            client=client, reading=reverting, correction=fresh, target_ref=CORRECTED_REF
        )
    ) == ("incident-correction-not-eligible")
    receipt = RevertReceipt(receipt_id="controller-receipt-1", revert_commit="3" * 40)
    collecting = _recovered(
        record_revert_receipt(client=client, reading=reverting, receipt=receipt)
    )
    assert (collecting.reading.attempt.phase, collecting.reading.attempt.generation) == (
        "collecting-failures",
        reverting.attempt.generation + 1,
    )
    assert _code(
        record_revert_receipt(client=client, reading=collecting.reading, receipt=receipt)
    ) == ("incident-revert-not-eligible")
    # An unchanged reland, a reused failing run or no evidence is refused by name.
    _assert_stale_corrections_refused(client, collecting.reading, fresh, finding)
    # Measured resolution may keep the original head when its evidence is fresh.
    measured = replace(
        fresh, kind="measured-resolution", evidence_id="master-run-10", head=MASTER_HEAD
    )
    planned = plan_corrected_attempt(
        reading=collecting.reading,
        retained=(finding,),
        correction=measured,
        target_ref=CORRECTED_REF,
    )
    assert not isinstance(planned, AuthorityRefusal)
    assert planned.attempt.head == MASTER_HEAD
    # Without the retained original failures there is nothing to correct against.
    assert _code(
        plan_corrected_attempt(
            reading=collecting.reading, retained=(), correction=fresh, target_ref=CORRECTED_REF
        )
    ) == ("incident-correction-failures-missing")
    corrected = _recovered(
        enter_corrected_attempt(
            client=client, reading=collecting.reading, correction=fresh, target_ref=CORRECTED_REF
        )
    )
    attempt = corrected.reading.attempt
    assert (attempt.item_id, attempt.phase, attempt.generation, attempt.pr_number) == (
        ITEM,
        "repair",
        collecting.reading.attempt.generation + 1,
        0,
    )
    assert (attempt.base, attempt.head, attempt.landed_commits) == (BROKEN_MASTER, FRESH_HEAD, ())
    assert attempt.carrier is not None and attempt.carrier.target_ref == CORRECTED_REF
    # Final normal repayment stays owed with its debt; the original failure is retained.
    assert attempt.repayment_required is True
    assert attempt.deferred_work == active.attempt.deferred_work
    assert retained_failures(client=client, item_id=ITEM) == (finding,)
    records = _recovery_records(client)
    assert [r["kind"] for r in records] == [
        "recovery-request",
        "revert-receipt",
        "corrected-attempt",
    ]
    assert records[1]["receipt"] == asdict(receipt)
    assert records[2]["retained_failures"] == [asdict(finding)]
    assert records[2]["correction"] == asdict(fresh)
    assert all(r["repayment_owed"] is True for r in records)
    assert recovery_attempts(client=client, item_id=ITEM) == 1


def test_recovery_refuses_forged_stale_or_half_landed_inputs_by_name(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Edges: caller bytes, stale readings, foreign records and a half-landed reopen."""
    client, observed, active = _live_repayment()
    # An attributed attempt the chain never retained, or one altered in transit.
    unknown = replace(observed.attempt, attempt_id="attempt-9")
    assert _code(
        reopen_for_regression(
            client=client, reading=active, attributed=unknown, finding=_finding(), owner=PRINCIPAL
        )
    ) == ("incident-authority-identity-mismatch")
    forged = replace(observed.attempt, landed_commits=("0" * 40,))
    assert _code(
        reopen_for_regression(
            client=client, reading=active, attributed=forged, finding=_finding(), owner=PRINCIPAL
        )
    ) == ("incident-reopen-attribution-mismatch")
    # Pure planning refusals: stale, ineligible phase, unbound attribution, unknown surface.
    assert _code(
        plan_reopen(
            reading=replace(active, is_current=False),
            attributed=observed.attempt,
            finding=_finding(),
            owner=PRINCIPAL,
        )
    ) == ("incident-reopen-stale-observation")
    assert _code(
        plan_reopen(
            reading=replace(observed, attempt=replace(observed.attempt, phase="repair")),
            attributed=observed.attempt,
            finding=_finding(),
            owner=PRINCIPAL,
        )
    ) == ("incident-reopen-not-eligible")
    assert _code(
        plan_reopen(reading=active, attributed=active.attempt, finding=_finding(), owner=PRINCIPAL)
    ) == ("incident-reopen-attribution-mismatch")
    assert _code(
        plan_reopen(
            reading=active,
            attributed=observed.attempt,
            finding=_finding(surface="nightly"),
            owner=PRINCIPAL,
        )
    ) == ("incident-finding-surface-unknown")
    # Foreign, malformed and duplicate records count once and retain only real failures.
    _assert_foreign_records_ignored(client)
    # A half-landed reopen: the chain recorded the generation, the lifecycle write did not land.
    real_change_claim = recovery_module.change_claim
    monkeypatch.setattr(recovery_module, "change_claim", _unobservable_claim)
    half = reopen_for_regression(
        client=client,
        reading=active,
        attributed=observed.attempt,
        finding=_finding(),
        owner=PRINCIPAL,
    )
    assert isinstance(half, AuthorityRefusal)
    assert (half.code, half.detail) == ("incident-reopen-lifecycle-refused", "claim-unobservable")
    monkeypatch.setattr(recovery_module, "change_claim", real_change_claim)
    # A stale repayment step after the reopen is refused before any chain write.
    assert _code(
        record_deferred_finding(
            client=client,
            reading=active,
            finding=_finding(surface="deferred-proof", master_healthy=True),
        )
    ) == ("incident-generation-stale")
    # Once the chain has moved past it, a retried reopen no longer takes the item.
    plan = plan_reopen(
        reading=active, attributed=observed.attempt, finding=_finding(), owner=PRINCIPAL
    )
    assert not isinstance(plan, AuthorityRefusal)
    reverting = read_incident_authority(
        client=client,
        repository=REPOSITORY,
        item_id=ITEM,
        query={
            key: getattr(plan.attempt, key)
            for key in ("attempt_id", "phase", "operation_id", "generation", "owner")
        },
    )
    assert isinstance(reverting, IncidentReading)
    _ = _recovered(
        record_revert_receipt(
            client=client,
            reading=reverting,
            receipt=RevertReceipt(receipt_id="controller-receipt-1", revert_commit="3" * 40),
        )
    )
    retried = reopen_for_regression(
        client=client,
        reading=active,
        attributed=observed.attempt,
        finding=_finding(),
        owner=PRINCIPAL,
    )
    assert _code(retried) == "incident-generation-stale"
    assert client.show_issue(issue_id=ITEM).get("assignee") == REPAYMENT_OWNER
