"""Edges of selecting an incident item's pull request through the chain."""

# EXPEDITED_INCIDENT_RESPONSE flag: bd-ib-dzbwaq
from __future__ import annotations

import json
import runpy
from pathlib import Path
from typing import Any

import pytest
from livespec_orchestrator_beads_fabro._beads_client import (
    FakeBeadsClient,
    IssueDraft,
    fake_singleton,
    reset_fake_singleton,
)
from livespec_orchestrator_beads_fabro._incident_authority_payload import (
    GENESIS_MARKER,
    TOKEN_TITLE,
)
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
from livespec_orchestrator_beads_fabro.commands._dispatcher_host_record_target import (
    host_record_target,
)
from livespec_orchestrator_beads_fabro.commands.dispatcher import main
from livespec_orchestrator_beads_fabro.errors import BeadsCommandError
from livespec_orchestrator_beads_fabro.incident_authority import (
    AuthorityRefusal,
    IncidentReading,
    publish_incident_genesis,
    read_incident_head,
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
OTHER_ROOT = "other"
REF = f"refs/heads/incident/{ITEM_ID}-attempt-1"
_RUNNER_SEAM = (
    "livespec_orchestrator_beads_fabro.commands._dispatcher_reconcile_merged.ShellCommandRunner"
)


@pytest.fixture(autouse=True)
def _hermetic_fake_backend(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> object:
    monkeypatch.setenv("LIVESPEC_BEADS_FAKE", "1")
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    reset_fake_singleton()
    yield
    reset_fake_singleton()


class _Runner:
    """A forge that cannot name its repository, or one that answers everything else."""

    def __init__(self, *, slug: str | None = REPOSITORY) -> None:
        self.slug = slug
        self.argvs: list[list[str]] = []

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
            return CommandResult(exit_code=0, stdout="origin/master\n", stderr="")
        if argv[:3] == ["gh", "repo", "view"]:
            if self.slug is None:
                return CommandResult(exit_code=1, stdout="", stderr="no remote")
            return CommandResult(exit_code=0, stdout=self.slug + "\n", stderr="")
        return CommandResult(exit_code=1, stdout="", stderr="unstubbed")


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
        status="active",
        title="Repair the outage",
        description="Repair.\n\n## Definition of Done\n\n- The outage is repaired.\n",
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
        '{"livespec-orchestrator-beads-fabro": {"connection": {"prefix": "bd-ib"}, '
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


def _seed_reserved() -> FakeBeadsClient:
    """An incident item whose chain is still branch-reserved: no pull request yet."""
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
    return client


def _stored() -> WorkItem:
    return materialize_work_items(records=read_work_items(path=_config()))[ITEM_ID]


def _reconcile(
    *, repo: Path, monkeypatch: pytest.MonkeyPatch, runner: _Runner, extra: list[str]
) -> int:
    monkeypatch.setattr(_RUNNER_SEAM, lambda: runner)
    monkeypatch.setattr(_dispatcher_completion, "run_acceptance_pass", lambda **_: None)
    return main(argv=["reconcile-merged", "--repo", str(repo), "--item", ITEM_ID, *extra])


def test_a_chain_without_a_pull_request_refuses_both_valves_by_name(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = _repo(tmp_path)
    _ = _seed_reserved()
    runner = _Runner()
    assert _reconcile(repo=repo, monkeypatch=monkeypatch, runner=runner, extra=[]) == 3
    error = capsys.readouterr().err
    assert "incident-carrier-unbound" in error and "branch-reserved" in error
    assert ["gh", "pr", "list"] not in [argv[:3] for argv in runner.argvs]
    assert _stored().status == "active"
    target = host_record_target(repo=repo, item=_stored(), runner=_Runner())
    assert isinstance(target, str) and "post-host-record refused" in target
    assert "incident-carrier-unbound" in target


def test_an_unresolvable_repository_and_an_unreadable_ledger_refuse_rather_than_rank(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = _repo(tmp_path)
    client = _seed_reserved()
    assert _reconcile(repo=repo, monkeypatch=monkeypatch, runner=_Runner(slug=None), extra=[]) == 3
    assert "incident-repository-unresolved" in capsys.readouterr().err

    def outage(*, issue_id: str) -> list[dict[str, Any]]:
        raise BeadsCommandError(command=f"bd comments {issue_id}", exit_code=1, stderr="gone")

    monkeypatch.setattr(client, "list_comments", outage)
    assert _reconcile(repo=repo, monkeypatch=monkeypatch, runner=_Runner(), extra=[]) == 3
    assert "incident-authority-unavailable" in capsys.readouterr().err


def test_an_operator_selector_naming_another_pull_request_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = _repo(tmp_path)
    _ = _seed_reserved()
    target = incident_pr.IncidentCarrierTarget(
        pr_number=90, branch="incident/x", remote_head="b" * 40
    )
    monkeypatch.setattr(incident_pr, "incident_carrier_target", lambda **_kwargs: target)
    status = _reconcile(repo=repo, monkeypatch=monkeypatch, runner=_Runner(), extra=["--pr", "88"])
    assert status == 3
    error = capsys.readouterr().err
    assert "--pr 88" in error and "#90" in error


def test_a_chain_with_an_ambiguous_root_or_an_empty_history_refuses_the_head_read(
    tmp_path: Path,
) -> None:
    repo = _repo(tmp_path)
    client = _seed_reserved()
    client.add_comment(
        issue_id=ITEM_ID,
        body=GENESIS_MARKER
        + _json(dict(schema=1, repository=REPOSITORY, item_id=ITEM_ID, root_token_id=OTHER_ROOT)),
    )
    head = read_incident_head(client=client, repository=REPOSITORY, item_id=ITEM_ID)
    assert isinstance(head, AuthorityRefusal) and head.code == "incident-authority-ambiguous"
    refused = host_record_target(repo=repo, item=_stored(), runner=_Runner())
    assert isinstance(refused, str) and "incident-authority-ambiguous" in refused
    empty = FakeBeadsClient()
    empty.create_issue(
        draft=IssueDraft(
            issue_id=ITEM_ID,
            issue_type="bug",
            title="incident",
            description="behavior",
            assignee=None,
            created_at="2026-11-06T00:00:00Z",
        )
    )
    root = empty.create_no_history_issue(title=TOKEN_TITLE, description="authority")
    empty.add_comment(
        issue_id=ITEM_ID,
        body=GENESIS_MARKER
        + _json(dict(schema=1, repository=REPOSITORY, item_id=ITEM_ID, root_token_id=root)),
    )
    unstarted = read_incident_head(client=empty, repository=REPOSITORY, item_id=ITEM_ID)
    assert isinstance(unstarted, AuthorityRefusal)
    assert unstarted.code == "incident-authority-identity-mismatch"

    def gone(*, issue_id: str) -> dict[str, Any]:
        raise BeadsCommandError(command=f"bd show {issue_id}", exit_code=1, stderr="gone")

    empty.show_issue = gone  # type: ignore[method-assign]
    outage = read_incident_head(client=empty, repository=REPOSITORY, item_id=ITEM_ID)
    assert isinstance(outage, AuthorityRefusal) and outage.code == "incident-authority-unavailable"


def test_the_head_read_is_the_current_generation_and_a_broken_chain_refuses() -> None:
    client = _seed_reserved()
    head = read_incident_head(client=client, repository=REPOSITORY, item_id=ITEM_ID)
    assert isinstance(head, IncidentReading)
    assert (head.is_current, head.attempt.generation, head.attempt.carrier is not None) == (
        True,
        1,
        True,
    )
    # The root re-created open is neither a closed transition nor the open successor.
    client.delete_issue(issue_id=head.committed_token_id)
    _ = client.create_issue(
        draft=IssueDraft(
            issue_id=head.committed_token_id,
            issue_type="task",
            title=TOKEN_TITLE,
            description="reopened",
            assignee=None,
            created_at="2026-11-06T00:00:00Z",
        )
    )
    broken = read_incident_head(client=client, repository=REPOSITORY, item_id=ITEM_ID)
    assert isinstance(broken, AuthorityRefusal)
    assert broken.code == "incident-authority-invalid-token-state"


def test_the_runner_doubles_answer_a_comments_read_and_an_unstubbed_call(tmp_path: Path) -> None:
    """The wiring module's forge double answers a comments read; this one refuses the rest."""
    wiring = runpy.run_path(str(Path(__file__).with_name("test_incident_pr_selection_wiring.py")))
    comments = wiring["_Runner"]().run(
        argv=["gh", "pr", "view", "90", "--json", "comments"], cwd=tmp_path, timeout_seconds=1.0
    )
    assert json.loads(comments.stdout) == {"comments": []}
    other = _Runner().run(argv=["git", "status"], cwd=tmp_path, timeout_seconds=1.0)
    assert (other.exit_code, other.stderr) == (1, "unstubbed")
