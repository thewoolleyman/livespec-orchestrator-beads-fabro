"""A successful incident merge reenters normal factory on the same item.

Scenario "a successful incident merge reenters normal factory on the same item"
(bd-ib-riguvj). One case per Definition-of-Done assertion, each driven through
the public repayment surface over an in-memory tenant whose incident chain was
written by the canonical genesis and transition writers.
"""

from __future__ import annotations

import argparse
import json
import os
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest
from livespec_orchestrator_beads_fabro._beads_client import FakeBeadsClient, IssueDraft
from livespec_orchestrator_beads_fabro._incident_authority_payload import decode_attempt
from livespec_orchestrator_beads_fabro._incident_genesis import decode_genesis_request
from livespec_orchestrator_beads_fabro._store_dispatch_claim import (
    CLAIM_TOKEN_METADATA_KEY,
    ClaimStamp,
    claim_stamp_from_record,
    claim_stamp_metadata,
    create_claim_token,
)
from livespec_orchestrator_beads_fabro.commands import _dispatcher_run_checks as run_checks
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine_janitor import (
    JANITOR_REMOVED_ENV_VARS,
    janitor_env_delta,
)
from livespec_orchestrator_beads_fabro.errors import BeadsCommandError
from livespec_orchestrator_beads_fabro.incident_authority import (
    AuthorityRefusal,
    IncidentReading,
    commit_incident_transition,
    publish_incident_genesis,
    read_incident_authority,
)
from livespec_orchestrator_beads_fabro.incident_normal_repayment import (
    INCIDENT_FLAGS,
    REPAYMENT_OWNER,
    MasterCiRun,
    RepaymentEntry,
    advance_repayment,
    enter_repayment,
    incident_flags_delta,
    plan_repayment,
    repayment_brief,
    repayment_operation_id,
    repayment_scope,
    scrub_incident_flags,
    select_incident_pull_request,
    validate_repayment_carrier,
)

REPOSITORY = "owner/repository"
ITEM = "test-incident"
PRINCIPAL = "operator:alice"
REPAIR_REF = "refs/heads/incident/test-incident-attempt-1"
REPAYMENT_REF = "refs/heads/feat/test-incident"
REPAIR_PR = 7
REPAYMENT_PR = 12
MASTER_HEAD = "d" * 40
MASTER_TREE = "e" * 40
GREEN = MasterCiRun(run_id="master-run-1", head=MASTER_HEAD, conclusion="success", complete=True)


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
    client.create_issue(
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


def _read(client: FakeBeadsClient, attempt: dict[str, Any]) -> IncidentReading:
    query = {k: attempt[k] for k in ("attempt_id", "phase", "operation_id", "generation", "owner")}
    reading = read_incident_authority(
        client=client, repository=REPOSITORY, item_id=ITEM, query=query
    )
    assert isinstance(reading, IncidentReading)
    return reading


def _advance(client: FakeBeadsClient, observed: IncidentReading, **changes: Any) -> IncidentReading:
    successor = decode_attempt(value=_attempt(**changes))
    assert successor is not None
    advanced = commit_incident_transition(client=client, observed=observed, successor=successor)
    assert isinstance(advanced, IncidentReading)
    return advanced


def _merged_repair(client: FakeBeadsClient, token: str) -> IncidentReading:
    """Genesis, the repair PR bound, then its merge observed: the attempt owing repayment."""
    request = decode_genesis_request(
        text=_json(dict(schema=1, principal=PRINCIPAL, expected_claim=token, attempt=_attempt())),
        repository=REPOSITORY,
        item_id=ITEM,
        operation_id="operation-1",
    )
    assert request is not None
    receipt = publish_incident_genesis(client=client, request=request, claim_tokens=True)
    assert not isinstance(receipt, AuthorityRefusal)
    bound = dict(
        state="pr-bound",
        target_ref=REPAIR_REF,
        input_parent="a" * 40,
        staged_tree="c" * 40,
        remote_head="b" * 40,
    )
    pr_bound = _advance(
        client,
        _read(client, _attempt()),
        generation=2,
        operation_id="bind-1",
        pr_number=REPAIR_PR,
        carrier=bound,
    )
    observed = _advance(
        client,
        pr_bound,
        generation=3,
        operation_id="merge-1",
        phase="master-observation",
        pr_number=REPAIR_PR,
        landed_commits=[MASTER_HEAD],
        landed_trees=[MASTER_TREE],
        carrier=bound,
    )
    # The host phase is active under the incident owner, never a factory claim.
    client.update_issue(issue_id=ITEM, status="active", assignee=PRINCIPAL)
    return observed


def _entry(result: RepaymentEntry | AuthorityRefusal) -> RepaymentEntry:
    assert isinstance(result, RepaymentEntry), result
    return result


def _code(result: object) -> str:
    assert isinstance(result, AuthorityRefusal), result
    return result.code


def _stamped_active(client: FakeBeadsClient) -> None:
    """Ordinary admission claimed the item: active, assigned fabro, under a pending stamp."""
    stamp = ClaimStamp(
        dispatch_id="01DISPATCH",
        dispatching_host="hp",
        run_id=None,
        factory_name="petri",
        factory_server="http://petri",
    )
    client.update_issue(
        issue_id=ITEM,
        status="active",
        assignee=REPAYMENT_OWNER,
        metadata=claim_stamp_metadata(stamp=stamp),
    )


def _assert_the_active_phase_needs_a_factory_claim(
    client: FakeBeadsClient, reading: IncidentReading, holder: ClaimStamp
) -> None:
    """An unstamped claim, or the incident holder's stamp, is not a factory claim."""
    client.update_issue(issue_id=ITEM, status="active", assignee=REPAYMENT_OWNER)
    assert _code(advance_repayment(client=client, reading=reading, phase="repayment-active")) == (
        "incident-repayment-claim-missing"
    )
    # An incident holder's stamp is not a factory claim, whoever the item is assigned to.
    client.update_issue(issue_id=ITEM, metadata=claim_stamp_metadata(stamp=holder))
    assert _code(advance_repayment(client=client, reading=reading, phase="repayment-active")) == (
        "incident-repayment-claim-missing"
    )


def test_a_successful_complete_normal_master_run_makes_one_normal_repayment_operation_eligible_after_ordinary_admission() -> (
    None
):
    client, token = _ledger()
    observed = _merged_repair(client, token)
    # Not a merged repair, and master CI not yet a complete success: named obligations.
    stale = replace(observed, is_current=False)
    assert _code(plan_repayment(reading=stale, master_ci=GREEN, target_ref=REPAYMENT_REF)) == (
        "incident-repayment-stale-observation"
    )
    for broken in (
        replace(GREEN, conclusion="failure"),
        replace(GREEN, complete=False),
        replace(GREEN, head="f" * 40),
    ):
        refusal = plan_repayment(reading=observed, master_ci=broken, target_ref=REPAYMENT_REF)
        assert _code(refusal) == "incident-repayment-master-ci-outstanding"
        assert "outstanding obligation" in refusal.detail
    # Canonical entry left the incident holder's stamp on the item in place of a factory claim.
    holder = claim_stamp_from_record(record=client.show_issue(issue_id=ITEM))
    assert holder is not None and (holder.dispatch_id or "").startswith("incident:")
    # A complete success derives ONE repayment operation from the recorded attempt.
    operation_id = repayment_operation_id(attempt=observed.attempt, master_ci=GREEN)
    entry = _entry(
        enter_repayment(client=client, reading=observed, master_ci=GREEN, target_ref=REPAYMENT_REF)
    )
    assert (entry.operation_id, entry.lifecycle_state, entry.recovered) == (
        operation_id,
        "pending-approval",
        False,
    )
    recorded = entry.reading.attempt
    assert (recorded.phase, recorded.generation, recorded.owner, recorded.pr_number) == (
        "repayment-admission",
        4,
        REPAYMENT_OWNER,
        0,
    )
    assert recorded.carrier is not None and recorded.carrier.target_ref == REPAYMENT_REF
    assert (recorded.original_paths, recorded.deferred_work) == (
        observed.attempt.original_paths,
        observed.attempt.deferred_work,
    )
    item = client.show_issue(issue_id=ITEM)
    assert (item["status"], item.get("assignee") or None) == ("pending-approval", None)
    # Returning the item to ordinary admission releases the incident holder's stamp.
    assert claim_stamp_from_record(record=item) is None
    # Ordinary admission is owed before the phase may read as ready.
    assert _code(
        advance_repayment(client=client, reading=entry.reading, phase="repayment-ready")
    ) == ("incident-repayment-admission-incomplete")
    assert (
        _code(
            advance_repayment(
                client=client,
                reading=entry.reading,
                phase="repayment-ready",
                admission_complete=True,
            )
        )
        == "incident-phase-state-mismatch"
    )
    client.update_issue(issue_id=ITEM, status="ready")
    ready = _entry(
        advance_repayment(
            client=client, reading=entry.reading, phase="repayment-ready", admission_complete=True
        )
    )
    assert (ready.reading.attempt.phase, ready.lifecycle_state) == ("repayment-ready", "ready")
    # One fresh factory claim, then the active phase; order and claim are both required.
    assert _code(
        advance_repayment(client=client, reading=ready.reading, phase="repayment-acceptance")
    ) == ("incident-repayment-phase-order")
    _assert_the_active_phase_needs_a_factory_claim(client, ready.reading, holder)
    _stamped_active(client)
    active = _entry(
        advance_repayment(client=client, reading=ready.reading, phase="repayment-active")
    )
    assert (active.reading.attempt.phase, active.reading.attempt.generation) == (
        "repayment-active",
        6,
    )
    assert active.operation_id == operation_id


def test_the_normal_repayment_run_and_pull_request_remove_the_original_marker_while_validating_cumulative_original_incident_paths_evidence_and_deferred_debt() -> (
    None
):
    client, token = _ledger()
    observed = _merged_repair(client, token)
    scope = repayment_scope(attempt=observed.attempt)
    assert (scope.marker, scope.repair_pr_number) == (
        "EXPEDITED_INCIDENT_RESPONSE flag: test-incident",
        REPAIR_PR,
    )
    assert scope.original_paths == ("app.py", "tests/test_app.py")
    assert scope.landed_commits == (MASTER_HEAD,)
    brief = repayment_brief(scope=scope)
    assert "Remove every `EXPEDITED_INCIDENT_RESPONSE flag: test-incident` marker" in brief
    assert "- app.py\n- tests/test_app.py\n" in brief
    assert f"- {MASTER_HEAD}\n" in brief
    assert "- spec-debt:scenario-12\n" in brief
    # Marker removal alone leaves the cumulative scope and debt outstanding, by name.
    only_marker = validate_repayment_carrier(
        scope=scope, marker_paths=(), validated_paths=(), repaid_debt=()
    )
    assert only_marker.outstanding == (
        "original-path-unvalidated:app.py",
        "original-path-unvalidated:tests/test_app.py",
        "deferred-debt-outstanding:normal-factory-proof",
        "deferred-debt-outstanding:spec-debt:scenario-12",
    )
    assert only_marker.complete is False
    still_marked = validate_repayment_carrier(
        scope=scope,
        marker_paths=("tests/test_app.py", "app.py"),
        validated_paths=scope.original_paths,
        repaid_debt=scope.deferred_work,
    )
    assert still_marked.outstanding == (
        "marker-present:app.py",
        "marker-present:tests/test_app.py",
    )
    complete = validate_repayment_carrier(
        scope=scope,
        marker_paths=(),
        validated_paths=("app.py", "tests/test_app.py", "docs/extra.md"),
        repaid_debt=("normal-factory-proof", "spec-debt:scenario-12"),
    )
    assert (complete.outstanding, complete.complete) == ((), True)


def test_normal_repayment_removes_both_incident_flags_before_provider_selection_and_sandbox_hook_and_pull_request_execution_including_malformed_inherited_values(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    assert INCIDENT_FLAGS == ("EXPEDITED_INCIDENT_RESPONSE", "EXPEDITED_INCIDENT_RESPONSE_REVERT")
    # Removal is not parsing: a well-formed, an empty and a malformed value all leave.
    for repair, revert in (("1", "1"), ("", "maybe"), ("yes please", "0")):
        environ = {"PATH": "/usr/bin", "EXPEDITED_INCIDENT_RESPONSE": repair}
        environ["EXPEDITED_INCIDENT_RESPONSE_REVERT"] = revert
        assert scrub_incident_flags(environ=environ) == INCIDENT_FLAGS
        assert environ == {"PATH": "/usr/bin"}
    assert scrub_incident_flags(environ={"EXPEDITED_INCIDENT_RESPONSE_REVERT": "x"}) == (
        "EXPEDITED_INCIDENT_RESPONSE_REVERT",
    )
    assert scrub_incident_flags(environ={}) == ()
    # Every sandbox, hook and gate subprocess the janitor runs removes both as well.
    assert incident_flags_delta() == {
        "EXPEDITED_INCIDENT_RESPONSE": None,
        "EXPEDITED_INCIDENT_RESPONSE_REVERT": None,
    }
    assert set(INCIDENT_FLAGS) <= set(JANITOR_REMOVED_ENV_VARS)
    delta = janitor_env_delta(core_plugin_root="/co/.claude-plugin")
    assert all(delta[name] is None for name in INCIDENT_FLAGS)
    # The dispatch entry scrubs its own process first, before any provider selection,
    # admission or refusal: the invoker refusal here is the earliest existing arm.
    monkeypatch.setenv("EXPEDITED_INCIDENT_RESPONSE", "maybe")
    monkeypatch.setenv("EXPEDITED_INCIDENT_RESPONSE_REVERT", "")
    seen: list[dict[str, str]] = []

    def refuse(*, args: argparse.Namespace, repo: Path) -> str:
        del args, repo
        seen.append({name: os.environ[name] for name in INCIDENT_FLAGS if name in os.environ})
        return "ERROR: refused for the test\n"

    monkeypatch.setattr(run_checks, "require_invoker_refusal", refuse)
    janitor, exit_code = run_checks.dispatch_preamble(args=argparse.Namespace(), repo=tmp_path)
    assert (janitor, exit_code) == (None, 3)
    assert seen == [{}]
    assert all(name not in os.environ for name in INCIDENT_FLAGS)


def test_restart_or_duplicate_delivery_resumes_the_recorded_repayment_operation_instead_of_creating_another_run_or_selecting_the_earlier_repair_carrier() -> (
    None
):
    client, token = _ledger()
    observed = _merged_repair(client, token)
    first = _entry(
        enter_repayment(client=client, reading=observed, master_ci=GREEN, target_ref=REPAYMENT_REF)
    )
    minted = client.no_history_issue_ids()
    # A duplicate delivery recovers the recorded operation: same ids, no new token, no write.
    again = _entry(
        enter_repayment(client=client, reading=observed, master_ci=GREEN, target_ref=REPAYMENT_REF)
    )
    assert (again.recovered, again.operation_id, again.reading.attempt) == (
        True,
        first.operation_id,
        first.reading.attempt,
    )
    assert client.no_history_issue_ids() == minted
    assert client.show_issue(issue_id=ITEM)["status"] == "pending-approval"
    # A restart that re-derives the step after a lost reply recovers it the same way.
    client.update_issue(issue_id=ITEM, status="ready")
    ready = _entry(
        advance_repayment(
            client=client, reading=first.reading, phase="repayment-ready", admission_complete=True
        )
    )
    resumed = _entry(
        advance_repayment(
            client=client, reading=first.reading, phase="repayment-ready", admission_complete=True
        )
    )
    assert (resumed.recovered, resumed.reading.attempt) == (True, ready.reading.attempt)
    # Selection never falls back to the merged repair PR while the repayment is unbound.
    refusal = select_incident_pull_request(reading=ready.reading, candidates=(REPAIR_PR,))
    assert _code(refusal) == "incident-carrier-unbound"
    assert str(REPAIR_PR) in refusal.detail
    # The merged repair, re-read as history, is no longer the current carrier either.
    superseded = read_incident_authority(
        client=client,
        repository=REPOSITORY,
        item_id=ITEM,
        query={
            "attempt_id": "attempt-1",
            "phase": "master-observation",
            "operation_id": "merge-1",
            "generation": 3,
            "owner": PRINCIPAL,
        },
        historical=True,
    )
    assert isinstance(superseded, IncidentReading) and superseded.is_current is False
    assert _code(select_incident_pull_request(reading=superseded, candidates=(REPAIR_PR,))) == (
        "incident-carrier-stale"
    )
    _stamped_active(client)
    active = _entry(
        advance_repayment(client=client, reading=ready.reading, phase="repayment-active")
    )
    carrier = active.reading.attempt.carrier
    assert carrier is not None
    client.update_issue(issue_id=ITEM, status="acceptance")
    bound = _advance(
        client,
        active.reading,
        attempt_id=active.reading.attempt.attempt_id,
        generation=active.reading.attempt.generation + 1,
        operation_id=f"{active.reading.attempt.attempt_id}#repayment-acceptance",
        phase="repayment-acceptance",
        owner=REPAYMENT_OWNER,
        base=MASTER_HEAD,
        head="9" * 40,
        pr_number=REPAYMENT_PR,
        carrier=dict(
            state="pr-bound",
            target_ref=REPAYMENT_REF,
            input_parent=carrier.input_parent,
            staged_tree=carrier.staged_tree,
            remote_head="9" * 40,
        ),
    )
    assert select_incident_pull_request(reading=bound, candidates=(REPAIR_PR, REPAYMENT_PR)) == (
        REPAYMENT_PR
    )
    assert _code(select_incident_pull_request(reading=bound, candidates=(REPAIR_PR,))) == (
        "incident-carrier-not-merged"
    )


def test_an_ineligible_or_stale_repayment_reading_is_refused_by_name_and_records_nothing() -> None:
    """Resume plumbing: an ineligible or stale reading is refused by name and records nothing."""
    client, token = _ledger()
    observed = _merged_repair(client, token)
    # Only a merged repair observed on master owes a repayment; a stale reading records nothing.
    assert _code(
        advance_repayment(
            client=client, reading=replace(observed, is_current=False), phase="repayment-ready"
        )
    ) == ("incident-repayment-stale-observation")
    fresh, fresh_token = _ledger()
    request = decode_genesis_request(
        text=_json(
            dict(schema=1, principal=PRINCIPAL, expected_claim=fresh_token, attempt=_attempt())
        ),
        repository=REPOSITORY,
        item_id=ITEM,
        operation_id="operation-1",
    )
    assert request is not None
    assert not isinstance(
        publish_incident_genesis(client=fresh, request=request, claim_tokens=True),
        AuthorityRefusal,
    )
    unmerged = enter_repayment(
        client=fresh, reading=_read(fresh, _attempt()), master_ci=GREEN, target_ref=REPAYMENT_REF
    )
    assert _code(unmerged) == "incident-repayment-not-eligible"
    # The item still rests where canonical entry put it: active under the incident owner.
    item = fresh.show_issue(issue_id=ITEM)
    assert (item["status"], item.get("assignee")) == ("active", PRINCIPAL)


def test_a_half_landed_repayment_step_completes_on_the_next_delivery_and_an_outage_is_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, token = _ledger()
    observed = _merged_repair(client, token)
    # The item left the host phase before entry: the chain records the generation,
    # the lifecycle write refuses by the protocol's name, and the retry completes it.
    client.update_issue(issue_id=ITEM, status="ready")
    refused = enter_repayment(
        client=client, reading=observed, master_ci=GREEN, target_ref=REPAYMENT_REF
    )
    assert (_code(refused), refused.detail) == (
        "incident-repayment-lifecycle-refused",
        "claim-changed",
    )
    assert client.show_issue(issue_id=ITEM)["status"] == "ready"
    client.update_issue(issue_id=ITEM, status="active", assignee=PRINCIPAL)
    completed = _entry(
        enter_repayment(client=client, reading=observed, master_ci=GREEN, target_ref=REPAYMENT_REF)
    )
    assert (completed.recovered, client.show_issue(issue_id=ITEM)["status"]) == (
        True,
        "pending-approval",
    )
    # A different master run under the stale pre-entry snapshot is a second operation the
    # chain refuses as a stale generation; it never becomes another repayment.
    other_run = replace(GREEN, run_id="master-run-2")
    minted = client.no_history_issue_ids()
    second = enter_repayment(
        client=client, reading=observed, master_ci=other_run, target_ref=REPAYMENT_REF
    )
    assert _code(second) == "incident-generation-stale"
    assert client.no_history_issue_ids() == minted
    # A tenant outage while the chain is read is unavailable at either step, never
    # absence or a blind write.
    client.update_issue(issue_id=ITEM, status="ready")
    show = client.show_issue

    def outage(*, issue_id: str) -> dict[str, Any]:
        if issue_id != ITEM:
            raise BeadsCommandError(command="bd show", exit_code=1, stderr="gone")
        return show(issue_id=issue_id)

    monkeypatch.setattr(client, "show_issue", outage)
    assert (
        _code(
            enter_repayment(
                client=client, reading=observed, master_ci=GREEN, target_ref=REPAYMENT_REF
            )
        )
        == "incident-authority-unavailable"
    )
    assert (
        _code(
            advance_repayment(
                client=client,
                reading=completed.reading,
                phase="repayment-ready",
                admission_complete=True,
            )
        )
        == "incident-authority-unavailable"
    )
    monkeypatch.setattr(client, "show_issue", show)
    assert client.show_issue(issue_id=ITEM)["status"] == "ready"
