"""reconcile-merged resolves a merge-held incident repayment's explicit merged pull request.

bd-ib-iwksr3. A repayment attempt walks `repayment-admission` to
`repayment-active` on its own `branch-reserved` carrier with no PR, and under
merge-hold the factory run ends before its pull request merges, so the run's
merge poll never moves the item to acceptance. `reconcile-merged` is the valve
that does, and `bind-repayment-acceptance` will not bind until it has. These
cases drive the public `reconcile-merged` surface over the fake tenant, with a
chain the canonical incident writers recorded and a forge answered by argv
shape: an operator `--pr` naming a MERGED pull request whose head branch is the
carrier's reserved ref resolves the merge; without `--pr`, outside a repayment
phase, or naming another branch or an unmerged pull request, it still refuses.
The last case then binds that same pull request through
`bind-repayment-acceptance`, which the reconcile has unblocked.
"""

# EXPEDITED_INCIDENT_RESPONSE flag: bd-ib-dzbwaq
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest
from livespec_orchestrator_beads_fabro._beads_client import (
    FakeBeadsClient,
    fake_singleton,
    reset_fake_singleton,
)
from livespec_orchestrator_beads_fabro._incident_authority_payload import decode_attempt
from livespec_orchestrator_beads_fabro._incident_genesis import (
    GenesisReceipt,
    decode_genesis_request,
)
from livespec_orchestrator_beads_fabro._store_dispatch_claim import (
    CLAIM_TOKEN_METADATA_KEY,
    create_claim_token,
)
from livespec_orchestrator_beads_fabro.commands import _dispatcher_completion
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandResult
from livespec_orchestrator_beads_fabro.commands._incident_authority_binding import (
    bind_repayment_acceptance,
)
from livespec_orchestrator_beads_fabro.commands.dispatcher import main
from livespec_orchestrator_beads_fabro.incident_authority import (
    IncidentReading,
    commit_incident_transition,
    publish_incident_genesis,
    read_incident_authority,
    read_incident_head,
)
from livespec_orchestrator_beads_fabro.incident_normal_repayment import RepaymentEntry
from livespec_orchestrator_beads_fabro.store import (
    append_work_item,
    materialize_work_items,
    read_work_items,
)
from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem

ITEM_ID = "bd-ib-incident"
REPOSITORY = "owner/repository"
PRINCIPAL = "operator:alice"
REPAIR_REF = f"refs/heads/incident/{ITEM_ID}-attempt-1"
REPAYMENT_BRANCH = f"fabro/{ITEM_ID}"
REPAYMENT_REF = "refs/heads/" + REPAYMENT_BRANCH
REPAIR_PR = 7
REPAYMENT_PR = 12
REPAIR_HEAD = "d" * 40
PR_HEAD = "8" * 40
MERGE_SHA = "9" * 40
HEADLINE = "fix: repay the incident"
UNBOUND = "incident-carrier-unbound"
_IDENTITY = ("attempt_id", "phase", "operation_id", "generation", "owner")
_REPAYMENT_PHASES = ("repayment-admission", "repayment-ready", "repayment-active")
_RUNNER_SEAM = (
    "livespec_orchestrator_beads_fabro.commands._dispatcher_reconcile_merged.ShellCommandRunner"
)
_FORGE_READ = [
    "gh",
    "pr",
    "view",
    str(REPAYMENT_PR),
    "--repo",
    REPOSITORY,
    "--json",
    "number,state,headRefName,headRefOid",
]
DESCRIPTION = """Repay the incident through the factory.

## Definition of Done

- The repayment reaches acceptance once its merge-held pull request merged.

References: ## Expedited incident lifecycle
"""


@pytest.fixture(autouse=True)
def _hermetic_fake_backend(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> object:
    monkeypatch.setenv("LIVESPEC_BEADS_FAKE", "1")
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    reset_fake_singleton()
    yield
    reset_fake_singleton()


@dataclass(frozen=True, kw_only=True)
class _AcceptancePass:
    proof: None = None
    verdict: str = "PASS"
    absent_evidence: tuple[str, ...] = ()
    diff_reason: str = "merged diff read"
    telemetry_reason: str = "green merged dispatch with PR and merge sha"
    criteria: tuple[object, ...] = ()

    def journal_record(self, *, work_item_id: str, policy: str) -> dict[str, object]:
        return {
            "stage": "acceptance-ai-pass",
            "work_item_id": work_item_id,
            "verdict": self.verdict,
            "acceptance_policy": policy,
        }


def _ok(stdout: str = "") -> CommandResult:
    return CommandResult(exit_code=0, stdout=stdout, stderr="")


@dataclass(kw_only=True)
class _Runner:
    """Answers by argv shape; `pull` is the repayment PR as the forge reports it, or None."""

    pull: dict[str, object] | None
    argvs: list[list[str]] = field(default_factory=list)

    def run(
        self,
        *,
        argv: list[str],
        cwd: Path,
        timeout_seconds: float,
        env: dict[str, str] | None = None,
        stdin: int | None = None,
    ) -> CommandResult:
        del cwd, timeout_seconds, env, stdin
        self.argvs.append(list(argv))
        joined = " ".join(argv)
        if "defaultBranchRef" in joined or "refs/remotes/origin/HEAD" in joined:
            return _ok("origin/master\n")
        verb = tuple(argv[:3])
        if verb == ("gh", "pr", "view"):
            return self._view(number=argv[3])
        answers: dict[tuple[str, ...], str] = {
            ("gh", "repo", "view"): REPOSITORY + "\n",
            ("gh", "pr", "list"): "[]",
        }
        return _ok(answers.get(verb, ""))

    def _view(self, *, number: str) -> CommandResult:
        if self.pull is None or number != str(REPAYMENT_PR):
            return CommandResult(exit_code=1, stdout="", stderr="no pull requests found")
        return _ok(json.dumps(self.pull))


def _pull(**changes: object) -> dict[str, object]:
    return {
        "number": REPAYMENT_PR,
        "title": HEADLINE,
        "body": "",
        "headRefName": REPAYMENT_BRANCH,
        "headRefOid": PR_HEAD,
        "baseRefName": "master",
        "state": "MERGED",
        "mergeCommit": {"oid": MERGE_SHA},
    } | changes


@dataclass(kw_only=True)
class _BindForge:
    """The forge and landed history `bind-repayment-acceptance` reads: one rebased commit."""

    def run(self, *, argv: list[str], **_: object) -> CommandResult:
        if argv[:2] == ["git", "log"]:
            return _ok("\x00".join((MERGE_SHA, "6" * 40, "5" * 40, HEADLINE)) + "\n")
        if argv[:3] == ["gh", "pr", "view"]:
            return _ok(json.dumps(_pull(commits=[{"messageHeadline": HEADLINE}])))
        return _ok("")


def _config() -> StoreConfig:
    return StoreConfig(
        tenant="livespec-impl-beads",
        prefix="bd-ib",
        server_user="livespec-impl-beads",
        database="livespec-impl-beads",
        bd_path="bd",
        fake=True,
    )


def _item() -> WorkItem:
    return WorkItem(
        id=ITEM_ID,
        type="bug",
        status="ready",
        title="Repay the incident",
        description=DESCRIPTION,
        origin="freeform",
        gap_id=None,
        rank="a0",
        assignee=None,
        depends_on=(),
        captured_at="2026-11-09T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
        admission_policy="auto",
        acceptance_policy="ai-only",
    )


def _repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    _ = (repo / ".livespec.jsonc").write_text(
        '{"git_author": {"operator_name": "Chad Woolley", '
        '"operator_email": "thewoolleyman@gmail.com"}, '
        '"livespec-orchestrator-beads-fabro": {"connection": {"prefix": "bd-ib"}, '
        '"compat": {"pinned": "master"}, "dispatcher": {"acceptance_mode": "ai-only"}}}',
        encoding="utf-8",
    )
    return repo


def _json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _carrier(*, ref: str, state: str = "pr-bound") -> dict[str, str]:
    carrier = {"state": state, "target_ref": ref, "input_parent": "a" * 40, "staged_tree": "c" * 40}
    return carrier if state == "branch-reserved" else carrier | {"remote_head": "b" * 40}


def _attempt(**changes: Any) -> dict[str, Any]:
    return {
        "repository": REPOSITORY,
        "item_id": ITEM_ID,
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
        "original_paths": ["app.py"],
        "deferred_work": ["normal-factory-proof"],
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


def _seed(*, through: str | None) -> FakeBeadsClient:
    """File the item and publish genesis; with `through`, merge it and walk the repayment there.

    The repayment walks on its own `branch-reserved` carrier with no PR, exactly
    as `enter-repayment` and `advance-repayment` record it. The item then rests
    `active`, where a merge-held run leaves it after its pull request merges.
    """
    append_work_item(path=_config(), item=_item())
    client = fake_singleton()
    assert isinstance(client, FakeBeadsClient)
    token = create_claim_token(client=client)
    client.update_issue(
        issue_id=ITEM_ID, metadata={CLAIM_TOKEN_METADATA_KEY: token}, names_claim_token=True
    )
    request = decode_genesis_request(
        text=_json(dict(schema=1, principal=PRINCIPAL, expected_claim=token, attempt=_attempt())),
        repository=REPOSITORY,
        item_id=ITEM_ID,
        operation_id="operation-1",
    )
    assert request is not None
    assert isinstance(
        publish_incident_genesis(client=client, request=request, claim_tokens=True),
        GenesisReceipt,
    )
    if through is not None:
        _walk(client=client, through=through)
    client.update_issue(issue_id=ITEM_ID, status="active")
    return client


def _walk(*, client: FakeBeadsClient, through: str) -> None:
    reading = read_incident_authority(
        client=client,
        repository=REPOSITORY,
        item_id=ITEM_ID,
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
    repaid = {
        "attempt_id": "repayment-1",
        "owner": "fabro",
        "base": REPAIR_HEAD,
        "head": REPAIR_HEAD,
    }
    for phase in _REPAYMENT_PHASES[: _REPAYMENT_PHASES.index(through) + 1]:
        reading = _advance(
            client,
            reading,
            operation_id=f"repayment-1#{phase}",
            phase=phase,
            carrier=_carrier(ref=REPAYMENT_REF, state="branch-reserved"),
            **repaid,
        )


def _status() -> str:
    return materialize_work_items(records=read_work_items(path=_config()))[ITEM_ID].status


def _journal(repo: Path) -> list[dict[str, Any]]:
    path = repo / "tmp" / "fabro-dispatch-journal.jsonl"
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def _reconcile(
    *,
    repo: Path,
    monkeypatch: pytest.MonkeyPatch,
    pull: dict[str, object] | None,
    pr: int | None,
) -> tuple[int, _Runner]:
    runner = _Runner(pull=pull)
    monkeypatch.setattr(_RUNNER_SEAM, lambda: runner)
    monkeypatch.setattr(
        _dispatcher_completion, "run_acceptance_pass", lambda **_: _AcceptancePass()
    )
    selector = [] if pr is None else ["--pr", str(pr)]
    argv = ["reconcile-merged", "--repo", str(repo), "--item", ITEM_ID, *selector]
    return main(argv=argv), runner


def _refused(*, repo: Path, runner: _Runner, exit_code: int, err: str, code: str) -> None:
    """Refused before any merge was resolved: no PR selected and the item still active."""
    assert exit_code == 3, err
    assert code in err and ITEM_ID in err
    assert ["gh", "pr", "list"] not in [argv[:3] for argv in runner.argvs]
    stages = [row.get("stage") for row in _journal(repo)]
    assert "reconcile-pr-selected" not in stages
    assert _status() == "active"


def test_an_explicit_merged_pr_on_the_reserved_branch_resolves_a_repayment_merge(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _repo(tmp_path)
    _ = _seed(through="repayment-active")
    exit_code, runner = _reconcile(
        repo=repo, monkeypatch=monkeypatch, pull=_pull(), pr=REPAYMENT_PR
    )
    assert exit_code == 0
    # The forge, not the caller, names the pull request's state, head branch and head.
    assert _FORGE_READ in runner.argvs
    selected = [row for row in _journal(repo) if row.get("stage") == "reconcile-pr-selected"]
    assert [(row["pr_number"], row["merge_sha"]) for row in selected] == [(REPAYMENT_PR, MERGE_SHA)]
    [outcome] = [row["outcome"] for row in _journal(repo) if row.get("stage") == "outcome"]
    assert (outcome.get("pr_number"), outcome.get("merge_sha")) == (REPAYMENT_PR, MERGE_SHA)
    assert _status() == "acceptance"
    assert ["gh", "pr", "list"] not in [argv[:3] for argv in runner.argvs]


def test_without_an_explicit_pr_a_repayment_carrier_still_refuses_unbound(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = _repo(tmp_path)
    _ = _seed(through="repayment-active")
    exit_code, runner = _reconcile(repo=repo, monkeypatch=monkeypatch, pull=_pull(), pr=None)
    err = capsys.readouterr().err
    _refused(repo=repo, runner=runner, exit_code=exit_code, err=err, code=UNBOUND)
    assert _FORGE_READ not in runner.argvs


def test_an_explicit_pr_outside_a_repayment_phase_still_refuses_unbound(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = _repo(tmp_path)
    _ = _seed(through=None)
    exit_code, runner = _reconcile(
        repo=repo, monkeypatch=monkeypatch, pull=_pull(), pr=REPAYMENT_PR
    )
    err = capsys.readouterr().err
    _refused(repo=repo, runner=runner, exit_code=exit_code, err=err, code=UNBOUND)
    assert _FORGE_READ not in runner.argvs


@pytest.mark.parametrize(
    ("pull", "code"),
    [
        (_pull(headRefName="fabro/another-branch"), "incident-repayment-carrier-mismatch"),
        (_pull(state="OPEN", mergeCommit=None), "incident-repayment-pr-unmerged"),
        (None, "incident-repayment-pr-unobservable"),
    ],
    ids=["head-branch-differs", "not-merged", "forge-unreadable"],
)
def test_an_explicit_pr_the_forge_does_not_report_merged_on_the_reserved_branch_refuses(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    pull: dict[str, object] | None,
    code: str,
) -> None:
    repo = _repo(tmp_path)
    _ = _seed(through="repayment-active")
    exit_code, runner = _reconcile(repo=repo, monkeypatch=monkeypatch, pull=pull, pr=REPAYMENT_PR)
    err = capsys.readouterr().err
    _refused(repo=repo, runner=runner, exit_code=exit_code, err=err, code=code)
    assert _FORGE_READ in runner.argvs


def test_after_the_reconcile_bind_repayment_acceptance_binds_the_same_pull_request(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _repo(tmp_path)
    client = _seed(through="repayment-active")
    exit_code, _ = _reconcile(repo=repo, monkeypatch=monkeypatch, pull=_pull(), pr=REPAYMENT_PR)
    assert exit_code == 0
    head = read_incident_head(client=client, repository=REPOSITORY, item_id=ITEM_ID)
    assert isinstance(head, IncidentReading)
    bound = bind_repayment_acceptance(
        client=client,
        reading=head,
        runner=_BindForge(),
        repo=repo,
        repository=REPOSITORY,
        pr_number=REPAYMENT_PR,
    )
    assert isinstance(bound, RepaymentEntry), bound
    attempt = bound.reading.attempt
    assert (attempt.phase, attempt.pr_number, attempt.head) == (
        "repayment-acceptance",
        REPAYMENT_PR,
        PR_HEAD,
    )
    assert attempt.carrier is not None
    assert (attempt.carrier.state, attempt.carrier.target_ref) == ("pr-bound", REPAYMENT_REF)
