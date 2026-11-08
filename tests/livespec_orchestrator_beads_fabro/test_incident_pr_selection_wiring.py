"""reconcile-merged and post-host-record select an incident item's pull request through the chain.

Three cases, one per Definition-of-Done bullet, through the public surfaces: the
`reconcile-merged` command and the posting primitive, over the fake tenant with
a chain published by the canonical incident writer and a forge answered by a
recording runner.
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
from livespec_orchestrator_beads_fabro.commands import _dispatcher_incident_pr as incident_pr
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandResult
from livespec_orchestrator_beads_fabro.commands._dispatcher_host_record_post import (
    HostRecordPost,
    host_record_argv,
    run_post_host_record_command,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_host_record_target import (
    host_record_target,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_proof_record import (
    VERDICT_HOST_RECORDED,
)
from livespec_orchestrator_beads_fabro.commands.dispatcher import main
from livespec_orchestrator_beads_fabro.incident_authority import (
    IncidentReading,
    commit_incident_transition,
    publish_incident_genesis,
    read_incident_authority,
)
from livespec_orchestrator_beads_fabro.store import (
    append_work_item,
    materialize_work_items,
    read_work_items,
)
from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem

ITEM_ID = "bd-ib-incident"
REPOSITORY = "owner/repository"
PRINCIPAL = "operator:alice"
BRANCH = f"incident/{ITEM_ID}-attempt-1"
REF = "refs/heads/" + BRANCH
INCIDENT_PR = 90
EARLIER_PR = 88
JOURNAL_PR = 42
SESSION = "01M44THISSESSION"
HOST_ASSERTION = "The released build resolves the host mode on an operator host."
DESCRIPTION = f"""Repair the outage.

## Definition of Done

- The dispatch result reports the parked verdict.

### Host-captured

Reason: the proof needs the released build installed on an operator host.

- {HOST_ASSERTION}

References: ## Scenario 136 — A host-captured assertion holds the item in acceptance
"""
_RUNNER_SEAM = (
    "livespec_orchestrator_beads_fabro.commands._dispatcher_reconcile_merged.ShellCommandRunner"
)
_GREEN_JANITOR_STEPS = 8


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


def _unstubbed() -> CommandResult:
    return CommandResult(exit_code=1, stdout="", stderr="unstubbed")


def _merged(*, number: int, title: str, head: str, sha: str) -> dict[str, object]:
    return {
        "number": number,
        "title": title,
        "body": "",
        "headRefName": head,
        "baseRefName": "master",
        "state": "MERGED",
        "mergeCommit": {"oid": sha},
    }


@dataclass(kw_only=True)
class _Runner:
    """Answers by argv shape; the forge has an earlier repair merge AND the chain's."""

    comments: str = field(default_factory=lambda: json.dumps({"comments": []}))
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
        if "--json" in argv and "comments" in joined:
            return _ok(self.comments)
        return self._forge(argv=argv)

    def _forge(self, *, argv: list[str]) -> CommandResult:
        verb = tuple(argv[:3])
        if verb == ("gh", "pr", "view"):
            return (
                _ok(json.dumps(self._incident())) if argv[3] == str(INCIDENT_PR) else _unstubbed()
            )
        answers: dict[tuple[str, ...], str] = {
            ("gh", "repo", "view"): REPOSITORY + "\n",
            ("gh", "pr", "list"): json.dumps([self._earlier(), self._incident()]),
            ("gh", "pr", "comment"): "posted\n",
        }
        return _ok(answers.get(verb, ""))

    def _incident(self) -> dict[str, object]:
        return _merged(number=INCIDENT_PR, title="incident repair", head=BRANCH, sha="inc90")

    def _earlier(self) -> dict[str, object]:
        return _merged(number=EARLIER_PR, title=f"fix: {ITEM_ID}", head="fix/early", sha="early88")


def _config() -> StoreConfig:
    return StoreConfig(
        tenant="livespec-impl-beads",
        prefix="bd-ib",
        server_user="livespec-impl-beads",
        database="livespec-impl-beads",
        bd_path="bd",
        fake=True,
    )


def _item(*, status: str) -> WorkItem:
    return WorkItem(
        id=ITEM_ID,
        type="bug",
        status=status,
        title="Repair the outage",
        description=DESCRIPTION,
        origin="freeform",
        gap_id=None,
        rank="a0",
        assignee=None,
        depends_on=(),
        captured_at="2026-11-06T00:00:00Z",
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


def _attempt(**changes: Any) -> dict[str, Any]:
    return (
        dict(
            repository=REPOSITORY,
            item_id=ITEM_ID,
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
                state="branch-reserved", target_ref=REF, input_parent="a" * 40, staged_tree="c" * 40
            ),
        )
        | changes
    )


def _reading(client: FakeBeadsClient, **changes: Any) -> IncidentReading:
    attempt = _attempt(**changes)
    reading = read_incident_authority(
        client=client,
        repository=REPOSITORY,
        item_id=ITEM_ID,
        query={
            k: attempt[k] for k in ("attempt_id", "phase", "operation_id", "generation", "owner")
        },
    )
    assert isinstance(reading, IncidentReading)
    return reading


def _advance(client: FakeBeadsClient, observed: IncidentReading, **changes: Any) -> IncidentReading:
    successor = decode_attempt(value=_attempt(**changes))
    assert successor is not None
    advanced = commit_incident_transition(client=client, observed=observed, successor=successor)
    assert isinstance(advanced, IncidentReading)
    return advanced


def _seed(*, status: str, chain: bool) -> FakeBeadsClient:
    """File the item; with `chain`, publish its incident authority up to a pr-bound carrier."""
    append_work_item(path=_config(), item=_item(status=status))
    client = fake_singleton()
    assert isinstance(client, FakeBeadsClient)
    if not chain:
        return client
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
    published = _advance(
        client,
        _reading(client),
        generation=2,
        operation_id="publish-1",
        carrier=_attempt()["carrier"] | {"state": "head-published", "remote_head": "b" * 40},
    )
    _ = _advance(
        client,
        published,
        generation=3,
        operation_id="bind-1",
        pr_number=INCIDENT_PR,
        carrier=_attempt()["carrier"] | {"state": "pr-bound", "remote_head": "b" * 40},
    )
    # Restore the status the case is about: entry moved the item to active under the owner.
    client.update_issue(issue_id=ITEM_ID, status=status)
    return client


def _stored() -> WorkItem:
    return materialize_work_items(records=read_work_items(path=_config()))[ITEM_ID]


def _journal(repo: Path) -> list[dict[str, Any]]:
    path = repo / "tmp" / "fabro-dispatch-journal.jsonl"
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def _outcome(repo: Path) -> tuple[object, object, str]:
    """The merge the valve reconciled, from its journaled outcome, with the item's rest."""
    [outcome] = [row["outcome"] for row in _journal(repo) if row.get("stage") == "outcome"]
    return outcome.get("pr_number"), outcome.get("merge_sha"), _stored().status


def _reconcile(*, repo: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[int, _Runner]:
    runner = _Runner()
    monkeypatch.setattr(_RUNNER_SEAM, lambda: runner)
    monkeypatch.setattr(
        _dispatcher_completion, "run_acceptance_pass", lambda **_: _AcceptancePass()
    )
    return main(argv=["reconcile-merged", "--repo", str(repo), "--item", ITEM_ID]), runner


def test_reconcile_merged_resolves_an_incident_item_s_pull_request_through_the_chain(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _repo(tmp_path)
    _ = _seed(status="active", chain=True)
    exit_code, runner = _reconcile(repo=repo, monkeypatch=monkeypatch)
    assert exit_code == 0
    assert _outcome(repo) == (INCIDENT_PR, "inc90", "acceptance")
    assert ["gh", "pr", "list"] not in [argv[:3] for argv in runner.argvs]
    slug_reads = [argv[:5] for argv in runner.argvs if argv[:3] == ["gh", "repo", "view"]]
    assert slug_reads == [["gh", "repo", "view", "--json", "nameWithOwner"]]
    selected = [row for row in _journal(repo) if row.get("stage") == "reconcile-pr-selected"]
    assert [(row["pr_number"], row["merge_sha"]) for row in selected] == [(INCIDENT_PR, "inc90")]


def _post(*, repo: Path, runner: _Runner) -> tuple[int, str, list[str]]:
    emitted: list[str] = []
    driven: list[str] = []
    record = repo / "record.json"
    _ = record.write_text(
        json.dumps(
            {
                "build": {"release_tag": "v0.296.0", "installed_build": "orchestrator 0.296.0"},
                "assertions": [
                    {
                        "text": HOST_ASSERTION,
                        "steps": ["Install the released build.", "Drive the valve."],
                        "proof": "$ drive --action accept:x\nrefused\n",
                        "reproduced": None,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    status = run_post_host_record_command(
        post=HostRecordPost(
            repo=repo, work_item_id=ITEM_ID, verdict=VERDICT_HOST_RECORDED, record_path=record
        ),
        runner=runner,
        env={"CLAUDE_CODE_SESSION_ID": SESSION},
        emit=emitted.append,
        reconcile=lambda *, work_item_id: driven.append(work_item_id) or 0,
    )
    return status, "".join(emitted), driven


def test_post_host_record_posts_on_the_pull_request_the_chain_names(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    _ = _seed(status="acceptance", chain=True)
    runner = _Runner()
    status, emitted, _ = _post(repo=repo, runner=runner)
    assert status == 0, emitted
    posted = [argv for argv in runner.argvs if argv[:3] == ["gh", "pr", "comment"]]
    assert len(posted) == 1
    assert posted[0] == host_record_argv(pr_number=INCIDENT_PR, body_file=Path(posted[0][-1]))
    assert ["gh", "pr", "list"] not in [argv[:3] for argv in runner.argvs]


def test_post_host_record_refuses_a_superseded_reading_as_incident_carrier_stale(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _repo(tmp_path)
    client = _seed(status="acceptance", chain=True)
    bound = _reading(
        client,
        generation=3,
        operation_id="bind-1",
        pr_number=INCIDENT_PR,
        carrier=_attempt()["carrier"] | {"state": "pr-bound", "remote_head": "b" * 40},
    )
    _ = _advance(
        client,
        bound,
        generation=4,
        operation_id="observe-1",
        phase="master-observation",
        pr_number=INCIDENT_PR,
        landed_commits=["d" * 40],
        landed_trees=["e" * 40],
        carrier=_attempt()["carrier"] | {"state": "pr-bound", "remote_head": "b" * 40},
    )
    # The reading the selector is handed is the superseded generation 3.
    monkeypatch.setattr(incident_pr, "read_incident_head", lambda **_kwargs: bound)
    runner = _Runner()
    status, emitted, driven = _post(repo=repo, runner=runner)
    assert (status, driven) == (3, [])
    assert "incident-carrier-stale" in emitted and ITEM_ID in emitted
    assert [argv for argv in runner.argvs if argv[:3] == ["gh", "pr", "comment"]] == []


def test_an_item_without_an_incident_chain_resolves_exactly_as_today(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _repo(tmp_path)
    _ = _seed(status="active", chain=False)
    exit_code, runner = _reconcile(repo=repo, monkeypatch=monkeypatch)
    assert exit_code == 0
    # Ranking as before: only the title-identified merge is a candidate, so it resolves.
    assert _outcome(repo) == (EARLIER_PR, "early88", "acceptance")
    assert ["gh", "repo", "view"] not in [argv[:3] for argv in runner.argvs]
    journal = repo / "tmp" / "fabro-dispatch-journal.jsonl"
    _ = journal.write_text(
        json.dumps(
            {
                "stage": "reconcile-pr-selected",
                "work_item_id": ITEM_ID,
                "pr_number": JOURNAL_PR,
                "merge_sha": "journal42",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    assert host_record_target(repo=repo, item=_stored(), runner=_Runner()) == JOURNAL_PR
