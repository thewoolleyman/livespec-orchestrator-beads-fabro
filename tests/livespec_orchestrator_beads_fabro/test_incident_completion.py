"""Incident completion requires final normal proof rather than an old repair merge.

Scenario "incident completion requires final normal proof rather than an old
repair merge" (bd-ib-mnny4v). One case per Definition-of-Done assertion, each
driven through the public acceptance and closure surfaces over the in-memory
tenant, whose incident chain is written by the canonical genesis and transition
writers. Each case computes its facts first and asserts them together last.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any
from unittest.mock import Mock

import pytest
from livespec_orchestrator_beads_fabro import incident_completion
from livespec_orchestrator_beads_fabro._beads_client import (
    FakeBeadsClient,
    fake_singleton,
    reset_fake_singleton,
)
from livespec_orchestrator_beads_fabro._incident_authority_payload import (
    GENESIS_MARKER,
    TOKEN_TITLE,
    decode_attempt,
)
from livespec_orchestrator_beads_fabro._incident_genesis import decode_genesis_request
from livespec_orchestrator_beads_fabro._store_dispatch_claim import (
    CLAIM_TOKEN_METADATA_KEY,
    create_claim_token,
)
from livespec_orchestrator_beads_fabro.commands import (
    _dispatcher_completion,
    _dispatcher_incident_closure,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_acceptance_ai import (
    MERGED_DIFF_LEG,
    run_acceptance_pass,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_acceptance_diff import (
    read_merged_diff,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import (
    CommandResult,
    DispatchOutcome,
)
from livespec_orchestrator_beads_fabro.commands._drive_accept_valve import accept_item
from livespec_orchestrator_beads_fabro.commands.close_work_item import (
    close_with_resolution,
    main,
)
from livespec_orchestrator_beads_fabro.errors import (
    BeadsCommandError,
    IncidentClosureRefusedError,
)
from livespec_orchestrator_beads_fabro.incident_authority import (
    AuthorityRefusal,
    IncidentReading,
    commit_incident_transition,
    publish_incident_genesis,
    read_incident_authority,
)
from livespec_orchestrator_beads_fabro.incident_completion import (
    IncidentCompletion,
    IncidentCompletionEvidence,
    IncidentStanding,
    complete_incident,
    completion_obligations,
    incident_acceptance_scope,
    incident_effect_refusal,
    read_incident_standing,
)
from livespec_orchestrator_beads_fabro.incident_normal_repayment import MasterCiRun
from livespec_orchestrator_beads_fabro.store import (
    append_work_item,
    materialize_work_items,
    read_work_items,
)
from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem

REPOSITORY = "owner/repository"
ITEM = "bd-ib-incident"
PRINCIPAL = "operator:alice"
REPAIR_REF = "refs/heads/incident/bd-ib-incident-1"
REPAYMENT_REF = "refs/heads/feat/bd-ib-incident"
REPAIR_PR = 7
REPAYMENT_PR = 12
REPAIR_HEAD = "d" * 40
REPAY_HEAD = "9" * 40
ORIGINAL_PATHS = ("app.py", "tests/test_app.py")
DEFERRED = ("normal-factory-proof", "spec-debt:scenario-12")
REPAIR_DIFF = "diff --git a/app.py b/app.py\n+repaired\n"
MARKER_DIFF = "diff --git a/app.py b/app.py\n-# EXPEDITED_INCIDENT_RESPONSE flag: x\n"
GREEN = MasterCiRun(run_id="run-9", head=REPAY_HEAD, conclusion="success", complete=True)
FULL = IncidentCompletionEvidence(
    merged_pr_number=REPAYMENT_PR,
    master_ci=GREEN,
    marker_paths=(),
    validated_paths=ORIGINAL_PATHS,
    repaid_debt=DEFERRED,
    manual_outcome=True,
)


@pytest.fixture(autouse=True)
def _fresh_tenant(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> object:
    """An empty in-memory tenant, from a root that commits no claim-token key."""
    monkeypatch.setenv("LIVESPEC_BEADS_FAKE", "1")
    _ = (tmp_path / ".livespec.jsonc").write_text(
        '{"livespec-orchestrator-beads-fabro": {"connection": {"prefix": "bd-ib"}}}',
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    reset_fake_singleton()
    yield
    reset_fake_singleton()


@dataclass(frozen=True, kw_only=True)
class _AcceptancePass:
    verdict: str
    proof: None = None
    absent_evidence: tuple[str, ...] = ()

    def journal_record(self, *, work_item_id: str, policy: str) -> dict[str, object]:
        return {"stage": "acceptance-ai-pass", "work_item_id": work_item_id, "policy": policy}


@dataclass(frozen=True, kw_only=True)
class _MemoryJournal:
    records: list[dict[str, object]]
    path: Path = Path("unused-journal.jsonl")

    def append(self, *, record: dict[str, object]) -> None:
        self.records.append(record)


@dataclass(frozen=True, kw_only=True)
class _DiffRunner:
    """Answers `gh pr diff <n>` from a table; anything else exits non-zero."""

    diffs: dict[str, str]
    calls: list[list[str]]

    def run(
        self,
        *,
        argv: list[str],
        cwd: Path,
        timeout_seconds: float,
        env: dict[str, str] | None = None,
    ) -> CommandResult:
        _ = (cwd, timeout_seconds, env)
        self.calls.append(list(argv))
        text = self.diffs.get(argv[3], "")
        return CommandResult(exit_code=0 if text else 1, stdout=text, stderr="")


def _config() -> StoreConfig:
    return StoreConfig(
        tenant="livespec-impl-beads",
        prefix="livespec-impl-beads",
        server_user="livespec-impl-beads",
        database="livespec-impl-beads",
        bd_path="bd",
        fake=True,
    )


def _work_item(*, item_id: str = ITEM, status: str = "acceptance") -> WorkItem:
    return WorkItem(
        id=item_id,
        type="bug",  # type: ignore[arg-type]
        status=status,
        title="incident",
        description="Restore checkout.",
        origin="freeform",  # type: ignore[arg-type]
        gap_id=None,
        rank="a1",
        assignee=None,
        depends_on=(),
        captured_at="2026-11-05T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
        acceptance_policy="ai-only",
    )


def _seed(*, item_id: str = ITEM) -> tuple[FakeBeadsClient, str]:
    append_work_item(path=_config(), item=_work_item(item_id=item_id, status="ready"))
    client = fake_singleton()
    token = create_claim_token(client=client)
    client.update_issue(
        issue_id=item_id, metadata={CLAIM_TOKEN_METADATA_KEY: token}, names_claim_token=True
    )
    return client, token


def _json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


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


def _expedited_merge(client: FakeBeadsClient, token: str) -> IncidentReading:
    """Genesis, the repair PR bound, then its merge observed: only an expedited merge exists."""
    request = decode_genesis_request(
        text=_json(
            {"schema": 1, "principal": PRINCIPAL, "expected_claim": token, "attempt": _attempt()}
        ),
        repository=REPOSITORY,
        item_id=ITEM,
        operation_id="operation-1",
    )
    assert request is not None
    assert not isinstance(
        publish_incident_genesis(client=client, request=request, claim_tokens=True),
        AuthorityRefusal,
    )
    first = read_incident_authority(
        client=client,
        repository=REPOSITORY,
        item_id=ITEM,
        query={
            key: _attempt()[key]
            for key in ("attempt_id", "phase", "operation_id", "generation", "owner")
        },
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


def _repayment_merged(client: FakeBeadsClient, token: str) -> IncidentReading:
    """The same item's normal factory repayment PR bound and merged: repayment-acceptance."""
    reading = _expedited_merge(client, token)
    repaid = {
        "attempt_id": "repayment-1",
        "owner": "fabro",
        "base": REPAIR_HEAD,
        "head": REPAIR_HEAD,
    }
    for phase in ("repayment-admission", "repayment-ready", "repayment-active"):
        reading = _advance(
            client,
            reading,
            operation_id=f"repayment-1#{phase}",
            phase=phase,
            carrier=_carrier(ref=REPAYMENT_REF, state="branch-reserved"),
            **repaid,
        )
    return _advance(
        client,
        reading,
        operation_id="repayment-1#repayment-acceptance",
        phase="repayment-acceptance",
        pr_number=REPAYMENT_PR,
        landed_commits=[REPAY_HEAD],
        landed_trees=["f" * 40],
        carrier=_carrier(ref=REPAYMENT_REF, head=REPAY_HEAD),
        **(repaid | {"head": REPAY_HEAD}),
    )


def _outcome(*, pr_number: int) -> DispatchOutcome:
    return DispatchOutcome(
        work_item_id=ITEM,
        status="green",
        stage="done",
        pr_number=pr_number,
        merge_sha=REPAY_HEAD,
        detail="merged",
    )


def _complete(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, *, verdict: str, pr_number: int
) -> tuple[bool, Mock, Mock, Mock, list[dict[str, object]]]:
    """Run the completion valve every reconcile-merged and proof-only resume reaches."""
    close, park, acceptance = Mock(), Mock(), Mock(return_value=_AcceptancePass(verdict=verdict))
    monkeypatch.setattr(_dispatcher_completion, "store_config", Mock(return_value=_config()))
    monkeypatch.setattr(_dispatcher_completion, "write_work_item_status_and_reconcile", Mock())
    monkeypatch.setattr(_dispatcher_completion, "read_dispatch_labels", Mock(return_value=()))
    monkeypatch.setattr(_dispatcher_completion, "run_acceptance_pass", acceptance)
    monkeypatch.setattr(_dispatcher_completion, "close_dispatch_item", close)
    monkeypatch.setattr(_dispatcher_completion, "park_in_acceptance", park)
    journal = _MemoryJournal(records=[])
    disposition = _dispatcher_completion.complete_and_accept(
        repo=tmp_path, item=_work_item(), outcome=_outcome(pr_number=pr_number), journal=journal
    )
    return disposition.closed, close, park, acceptance, journal.records


def _stages(records: list[dict[str, object]]) -> list[object]:
    return [record["stage"] for record in records]


def _status(item_id: str = ITEM) -> str:
    return materialize_work_items(records=read_work_items(path=_config()))[item_id].status


def test_acceptance_grades_cumulative_original_incident_behavior_and_evidence_together_with_the_current_repayment_pull_request(
    tmp_path: Path,
) -> None:
    client, token = _seed()
    _ = _repayment_merged(client, token)
    # An ordinary progress comment beside the genesis locates nothing.
    client.seed_comment(issue_id=ITEM, text="repayment PR opened")
    standing = read_incident_standing(client=client, item_id=ITEM)
    scope = incident_acceptance_scope(standing=standing, merged_pr=REPAYMENT_PR)
    assert scope is not None
    runner = _DiffRunner(
        diffs={str(REPAIR_PR): REPAIR_DIFF, str(REPAYMENT_PR): MARKER_DIFF}, calls=[]
    )
    cumulative = read_merged_diff(
        repo=tmp_path, outcome=_outcome(pr_number=REPAYMENT_PR), runner=runner, incident=scope
    )
    unreadable = read_merged_diff(
        repo=tmp_path,
        outcome=_outcome(pr_number=REPAYMENT_PR),
        runner=_DiffRunner(diffs={str(REPAYMENT_PR): MARKER_DIFF}, calls=[]),
        incident=scope,
    )
    # The expedited repair PR resumed for proof is not the incident's current carrier.
    stale = incident_acceptance_scope(standing=standing, merged_pr=REPAIR_PR)
    assert stale is not None
    quiet = _DiffRunner(diffs={}, calls=[])
    marker_only = read_merged_diff(
        repo=tmp_path, outcome=_outcome(pr_number=REPAIR_PR), runner=quiet, incident=stale
    )
    graded = run_acceptance_pass(
        repo=tmp_path,
        item=_work_item(),
        outcome=_outcome(pr_number=REPAIR_PR),
        runner=quiet,
        incident=stale,
    )
    normal_client, _ = _seed(item_id="bd-ib-normal")
    normal = read_incident_standing(client=normal_client, item_id="bd-ib-normal")
    # A repayment with no recorded expedited carrier has no original corpus to grade.
    orphan = incident_acceptance_scope(
        standing=replace(standing, history=standing.history[-1:]), merged_pr=REPAYMENT_PR
    )
    facts = [
        (scope.original_prs, scope.current_pr, scope.refusal) == ((REPAIR_PR,), REPAYMENT_PR, None),
        cumulative.merged_diff == REPAIR_DIFF + MARKER_DIFF and cumulative.gradeable,
        "cumulative incident diff" in cumulative.reason,
        unreadable.merged_diff is None and not unreadable.gradeable,
        f"#{REPAIR_PR}" in unreadable.reason,
        stale.refusal is not None and f"#{REPAIR_PR}" in stale.refusal,
        marker_only.merged_diff is None and not marker_only.gradeable and quiet.calls == [],
        graded.verdict == "NEEDS_ATTENTION" and MERGED_DIFF_LEG in graded.absent_evidence,
        (normal.kind, normal.outstanding) == ("normal", ()),
        incident_acceptance_scope(standing=normal, merged_pr=REPAIR_PR) is None,
        _dispatcher_incident_closure.closure_obligations_for(
            config=_config(), item_id="bd-ib-normal"
        )
        == (),
        orphan is not None and orphan.refusal is not None and "no original" in orphan.refusal,
    ]
    assert all(facts), facts


def test_accept_reconcile_merged_close_no_change_needed_and_proof_only_resume_preserve_the_incident_obligation_while_only_an_expedited_repair_merge_exists(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    client, token = _seed()
    observed = _expedited_merge(client, token)
    client.update_issue(issue_id=ITEM, status="acceptance")
    standing = read_incident_standing(client=client, item_id=ITEM)
    passed = _complete(monkeypatch, tmp_path, verdict="PASS", pr_number=REPAIR_PR)
    no_change = _complete(monkeypatch, tmp_path, verdict="NO_CHANGE_NEEDED", pr_number=REPAIR_PR)
    scope = passed[3].call_args.kwargs["incident"]
    accepted = accept_item(
        repo=tmp_path, config=_config(), item=_work_item(), action_id=f"accept:{ITEM}"
    )
    refusals = []
    for resolution in ("completed", "no-longer-applicable"):
        with pytest.raises(IncidentClosureRefusedError) as refused:
            _ = close_with_resolution(path=_config(), item_id=ITEM, resolution=resolution)
        refusals.append(refused.value.outstanding)
    exit_code = main(argv=[ITEM, "--resolution", "no-longer-applicable"])
    # No writer may record `closed` straight from the expedited merge either.
    closed = decode_attempt(
        value=_attempt(
            generation=4,
            operation_id="close-1",
            phase="closed",
            pr_number=REPAIR_PR,
            landed_commits=[REPAIR_HEAD],
            landed_trees=["e" * 40],
            carrier=_carrier(ref=REPAIR_REF),
        )
    )
    assert closed is not None
    forged = commit_incident_transition(client=client, observed=observed, successor=closed)
    evidence = replace(FULL, merged_pr_number=REPAIR_PR, master_ci=replace(GREEN, head=REPAIR_HEAD))
    completion = complete_incident(client=client, item_id=ITEM, evidence=evidence)
    facts = [
        "normal-repayment-unmerged:master-observation" in standing.outstanding,
        passed[0] is False and passed[1].call_count == 0 and passed[2].call_count == 1,
        no_change[0] is False and no_change[1].call_count == 0 and no_change[2].call_count == 1,
        "incident-obligation-outstanding" in _stages(passed[4]),
        "incident-proof-pointer-refused" in _stages(passed[4]),
        scope is not None and scope.refusal is not None,
        (accepted["status"], accepted["domain_error"])
        == ("failed", "incident-obligation-outstanding"),
        all(outstanding == standing.outstanding for outstanding in refusals),
        exit_code == 5 and ITEM in capsys.readouterr().err,
        _status() == "acceptance",
        isinstance(forged, AuthorityRefusal)
        and forged.code == "incident-transition-invalid-successor",
        isinstance(completion, IncidentCompletion) and not completion.recorded,
        isinstance(completion, IncidentCompletion)
        and f"repayment-master-ci-not-for-repayment:{REPAIR_HEAD}" in completion.outstanding,
    ]
    assert all(facts), facts


def test_incident_closure_requires_the_current_normal_repayment_merged_its_master_ci_marker_removal_manual_outcome_and_repaid_debt(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    client, token = _seed()
    _ = _repayment_merged(client, token)
    history = read_incident_standing(client=client, item_id=ITEM).history
    unrecorded = (*history[:-1], replace(history[-1], landed_commits=()))
    named = {
        "repayment-merge-unobserved:12": replace(FULL, merged_pr_number=None),
        "repayment-pr-not-current:7": replace(FULL, merged_pr_number=REPAIR_PR),
        "repayment-master-ci-failed:run-9:failure": replace(
            FULL, master_ci=replace(GREEN, conclusion="failure")
        ),
        "marker-present:app.py": replace(FULL, marker_paths=("app.py",)),
        "original-path-unvalidated:tests/test_app.py": replace(FULL, validated_paths=("app.py",)),
        "deferred-debt-outstanding:spec-debt:scenario-12": replace(
            FULL, repaid_debt=("normal-factory-proof",)
        ),
        "manual-outcome-missing": replace(FULL, manual_outcome=False),
        "related-failure-undisposed:consumer-x": replace(FULL, undisposed_failures=("consumer-x",)),
    }
    obligations = {
        name: completion_obligations(history=history, evidence=evidence)
        for name, evidence in named.items()
    }
    recorded = complete_incident(client=client, item_id=ITEM, evidence=FULL)
    again = complete_incident(client=client, item_id=ITEM, evidence=FULL)
    after = read_incident_standing(client=client, item_id=ITEM)
    client.update_issue(issue_id=ITEM, status="acceptance")
    passed = _complete(monkeypatch, tmp_path, verdict="PASS", pr_number=REPAYMENT_PR)
    closed = close_with_resolution(path=_config(), item_id=ITEM, resolution="completed")
    facts = [
        all(obligations[name] == (name,) for name in named),
        completion_obligations(history=unrecorded, evidence=FULL)
        == (
            "repayment-landed-commits-unrecorded:12",
            f"repayment-master-ci-not-for-repayment:{REPAY_HEAD}",
        ),
        isinstance(recorded, IncidentCompletion) and recorded.recorded and not recorded.recovered,
        isinstance(again, IncidentCompletion) and again.recorded and again.recovered,
        after.outstanding == () and after.history[-1].phase == "closed",
        passed[0] is True and passed[1].call_count == 1,
        closed.status == "done" and _status() == "done",
    ]
    assert all(facts), facts


def test_missing_cancelled_or_unreadable_proof_remains_an_explicit_outstanding_obligation_rather_than_satisfying_completion(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, token = _seed()
    _ = _repayment_merged(client, token)
    history = read_incident_standing(client=client, item_id=ITEM).history
    named = {
        "repayment-master-ci-missing": replace(FULL, master_ci=None),
        "repayment-master-ci-cancelled:run-9": replace(
            FULL, master_ci=replace(GREEN, conclusion="cancelled", complete=False)
        ),
        "repayment-master-ci-incomplete:run-9": replace(
            FULL, master_ci=replace(GREEN, complete=False)
        ),
        "marker-removal-unobserved": replace(FULL, marker_paths=None),
    }
    obligations = {
        name: completion_obligations(history=history, evidence=evidence)
        for name, evidence in named.items()
    }
    unobserved = complete_incident(
        client=client, item_id=ITEM, evidence=named["marker-removal-unobserved"]
    )
    still = read_incident_standing(client=client, item_id=ITEM)
    # Unreadable incident evidence is never a normal item.
    for item_id, texts in {
        "bd-ib-malformed": [GENESIS_MARKER + "{"],
        "bd-ib-ambiguous": [
            GENESIS_MARKER
            + _json(
                {
                    "schema": 1,
                    "repository": repo,
                    "item_id": "bd-ib-ambiguous",
                    "root_token_id": "token",
                }
            )
            for repo in ("a/one", "b/two")
        ],
        "bd-ib-rootless": [
            GENESIS_MARKER
            + _json(
                {
                    "schema": 1,
                    "repository": "a/one",
                    "item_id": "bd-ib-rootless",
                    "root_token_id": "missing",
                }
            )
        ],
    }.items():
        _ = _seed(item_id=item_id)
        for text in texts:
            client.seed_comment(issue_id=item_id, text=text)
    # A genesis whose root token was never closed has no generation to read.
    _ = _seed(item_id="bd-ib-unwalked")
    root = client.create_no_history_issue(title=TOKEN_TITLE, description="open root")
    client.seed_comment(
        issue_id="bd-ib-unwalked",
        text=GENESIS_MARKER
        + _json(
            {"schema": 1, "repository": "a/one", "item_id": "bd-ib-unwalked", "root_token_id": root}
        ),
    )
    unreadable = {
        item_id: read_incident_standing(client=client, item_id=item_id).outstanding
        for item_id in ("bd-ib-malformed", "bd-ib-ambiguous", "bd-ib-rootless", "bd-ib-unwalked")
    }
    _ = _seed(item_id="bd-ib-normal")
    normal = complete_incident(client=client, item_id="bd-ib-normal", evidence=FULL)
    empty = IncidentStanding(
        item_id=ITEM,
        kind="incident",
        repository=REPOSITORY,
        history=(),
        outstanding=("incident-history-empty",),
    )
    empty_scope = incident_acceptance_scope(standing=empty, merged_pr=REPAYMENT_PR)
    monkeypatch.setattr(
        client,
        "close_issue_without_verdict",
        Mock(side_effect=BeadsCommandError(command="bd close", exit_code=1, stderr="gone")),
    )
    lost = complete_incident(client=client, item_id=ITEM, evidence=FULL)
    monkeypatch.setattr(
        client,
        "list_comments",
        Mock(side_effect=BeadsCommandError(command="bd comments", exit_code=1, stderr="gone")),
    )
    outage = read_incident_standing(client=client, item_id=ITEM)
    outage_scope = incident_acceptance_scope(standing=outage, merged_pr=REPAYMENT_PR)
    outage_completion = complete_incident(client=client, item_id=ITEM, evidence=FULL)
    facts = [
        all(obligations[name] == (name,) for name in named),
        isinstance(unobserved, IncidentCompletion) and not unobserved.recorded,
        still.history[-1].phase == "repayment-acceptance",
        unreadable["bd-ib-malformed"] == ("incident-authority-invalid-genesis",),
        unreadable["bd-ib-ambiguous"] == ("incident-authority-ambiguous",),
        unreadable["bd-ib-rootless"][0].startswith("incident-authority-unreadable:"),
        unreadable["bd-ib-unwalked"]
        == ("incident-authority-unreadable:incident-authority-identity-mismatch",),
        isinstance(normal, AuthorityRefusal) and normal.code == "incident-authority-missing",
        completion_obligations(history=(), evidence=FULL) == ("incident-history-empty",),
        empty_scope is not None and empty_scope.refusal is not None,
        isinstance(lost, AuthorityRefusal) and lost.code == "incident-transition-unavailable",
        outage.kind == "unreadable",
        outage.outstanding[0].startswith("incident-standing-unavailable:"),
        outage_scope is not None and outage_scope.refusal is not None,
        isinstance(outage_completion, AuthorityRefusal)
        and outage_completion.code == "incident-completion-unreadable",
    ]
    assert all(facts), facts


def test_a_superseded_repayment_operation_is_refused_at_every_proof_and_closure_site(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """bd-ib-k5teti's `require_repayment_current`, taken right before each side effect."""
    client, token = _seed()
    merged = _repayment_merged(client, token)
    client.update_issue(issue_id=ITEM, status="acceptance")
    stale = read_incident_standing(client=client, item_id=ITEM)
    # An attributable regression reopens the same item into `reverting` meanwhile.
    _ = _advance(
        client,
        merged,
        attempt_id="recovery-1",
        operation_id="recovery-1#reverting",
        phase="reverting",
        owner=PRINCIPAL,
        pr_number=REPAYMENT_PR,
        landed_commits=[REPAY_HEAD],
        landed_trees=["f" * 40],
        carrier=_carrier(ref=REPAYMENT_REF, head=REPAY_HEAD),
    )
    monkeypatch.setattr(incident_completion, "read_incident_standing", Mock(return_value=stale))
    closure = complete_incident(client=client, item_id=ITEM, evidence=FULL)
    # The proof pointer for the graded repayment PR is withheld once it is superseded.
    monkeypatch.setattr(
        _dispatcher_incident_closure, "incident_standing_for", Mock(return_value=stale)
    )
    proof = _complete(monkeypatch, tmp_path, verdict="PASS", pr_number=REPAYMENT_PR)
    # A standing that owed nothing when read is still refused at the close itself.
    judged = replace(stale, outstanding=())
    monkeypatch.setattr(
        _dispatcher_incident_closure, "incident_standing_for", Mock(return_value=judged)
    )
    completed = _complete(monkeypatch, tmp_path, verdict="PASS", pr_number=REPAYMENT_PR)
    accepted = accept_item(
        repo=tmp_path, config=_config(), item=_work_item(), action_id=f"accept:{ITEM}"
    )
    with pytest.raises(IncidentClosureRefusedError) as refused:
        _ = close_with_resolution(path=_config(), item_id=ITEM, resolution="completed")
    normal_client, _ = _seed(item_id="bd-ib-normal")
    normal = read_incident_standing(client=normal_client, item_id="bd-ib-normal")
    pointer = [record for record in proof[4] if record["stage"] == "incident-proof-pointer-refused"]
    holds = [
        record for record in completed[4] if record["stage"] == "incident-obligation-outstanding"
    ]
    superseded = "incident-repayment-superseded"
    facts = [
        isinstance(closure, AuthorityRefusal) and closure.code == superseded,
        isinstance(closure, AuthorityRefusal) and "closure refused" in closure.detail,
        len(pointer) == 1 and str(pointer[0]["reason"]).startswith(superseded),
        "proof refused" in str(pointer[0]["reason"]),
        completed[0] is False and completed[1].call_count == 0,
        len(holds) == 1 and str(holds[0]["outstanding"]).count(superseded) == 1,
        accepted["status"] == "failed" and superseded in accepted["summary"],
        refused.value.outstanding[0].startswith(superseded),
        _status() == "acceptance",
        incident_effect_refusal(client=normal_client, standing=normal, effect="merge") is None,
    ]
    assert all(facts), facts
