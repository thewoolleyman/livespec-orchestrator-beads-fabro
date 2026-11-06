"""Every operation that closes a work item wins the item's claim token first.

`SPECIFICATION/contracts.md` ("Claim tokens") makes any write that changes an
item's status a claim-changing write, and a close changes it. `bd close` is its
own verb and cannot name a successor token, so a closer wins the item's current
token in a HOLD that names the successor and changes nothing else, and closes
only after that write landed. Four closes took no hold: `close-work-item`, the
groom front-end's regroom of an original, a plan child disposition and a plan
archive. Each case here drives one of them through the surface an operator or
a plan session uses, against the in-memory tenant, in a repository of its own
that commits `dispatcher.claim_tokens` as `true`.

The fourth bullet is about ORDER, in the closes that already held. A hold names
a successor; a status write that wins THAT successor between the hold and the
close is a later, legitimate write, and the close used to land over it. So the
hold answers `claim-changed` when the item no longer names the successor it
wrote, and the caller closes nothing. That case drives the Dispatcher's groom
apply seam, whose close already held, with a second writer that wins the
successor at the instant the hold's write lands.
"""

from __future__ import annotations

import copy
import json
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace

import pytest
from livespec_orchestrator_beads_fabro import intake_dor
from livespec_orchestrator_beads_fabro._beads_client import (
    EDGE_BLOCKS,
    EDGE_PARENT_CHILD,
    FakeBeadsClient,
    IssueDraft,
    make_beads_client,
    reset_fake_singleton,
)
from livespec_orchestrator_beads_fabro._store_dispatch_claim import (
    CLAIM_TOKEN_METADATA_KEY,
    change_claim,
)
from livespec_orchestrator_beads_fabro._store_groom_approval import GroomApproval
from livespec_orchestrator_beads_fabro.commands import plan
from livespec_orchestrator_beads_fabro.commands._config import resolve_store_config
from livespec_orchestrator_beads_fabro.commands._dispatcher_claim_guard import (
    TRANSITION_OBSERVATIONS,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_definition_of_done import (
    PROOF_MODE_HOST_CAPTURED,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandResult
from livespec_orchestrator_beads_fabro.commands._dispatcher_groom_apply import file_groom_plan
from livespec_orchestrator_beads_fabro.commands._dispatcher_host_build_identity import (
    BuildIdentity,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_host_record_render import (
    RecordAssertion,
    render_proof_record,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import JournalFile
from livespec_orchestrator_beads_fabro.commands._dispatcher_proof_record import (
    VERDICT_CAPTURED,
    VERDICT_VERIFIED,
)
from livespec_orchestrator_beads_fabro.commands._plan_definition_of_done import (
    PlanDefinitionOfDone,
)
from livespec_orchestrator_beads_fabro.commands._plan_disposition import close_plan_child
from livespec_orchestrator_beads_fabro.commands._plan_proof_record import (
    PLAN_PROOF_RECORD_TITLE,
)
from livespec_orchestrator_beads_fabro.commands._plan_release_forge import (
    governed_repository_argv,
)
from livespec_orchestrator_beads_fabro.commands._spec_change_tier import exempt_decision
from livespec_orchestrator_beads_fabro.commands._spec_change_tier_record import (
    STAGE_FILING,
    spec_change_tier_comment,
)
from livespec_orchestrator_beads_fabro.commands.close_work_item import main as close_work_item
from livespec_orchestrator_beads_fabro.commands.groom import CandidateSlice, file_approved_slices
from livespec_orchestrator_beads_fabro.errors import GroomExitRefusedError
from livespec_orchestrator_beads_fabro.store import append_work_item, read_work_items
from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem, WorkItemStatus

_ITEM_ID = "bd-ib-closehold"
_EPIC_ID = "bd-ib-closehold-epic"
_CHILD_ID = "bd-ib-closehold-child"
_HEADING = "## A governing clause"
# The repository's directory name is the identity a slice's `repo_target` is matched against.
_LOCAL_REPO = "repo"
_SLICE = "Keep the one slice"
_SLUG = "archive-thread"
_PLAN_ASSERTION = "The operator drives the delivered command and sees it work."
_NOW = "2026-11-06T09:00:00Z"
_ANOTHER_WRITER = "another writer won this token"
_RACER = "a-status-writer"
_HUMAN_VALVE = "human-valve"
_APPROVAL = GroomApproval(approver="thewoolleyman", route="resolve-blocked ready valve")
_GROOM_VARIANT = "groom-cut"
_GROOM_DIR = ".fabro/workflows/groom-cut"
_ARCHIVING_SESSION_ENV = {"CLAUDE_CODE_SESSION_ID": "archiving-session"}
_REVIEWING_SESSION_ENV = {"CLAUDE_CODE_SESSION_ID": "reviewing-session"}
_CONNECTION = {
    "tenant": "livespec-impl-beads",
    "prefix": "bd-ib",
    "server_user": "livespec-impl-beads",
    "database": "livespec-impl-beads",
    "bd_path": "bd",
    "fake": True,
}
_PLAN_TEXT = (
    "livespec-groom-plan | approver=thewoolleyman | route=resolve-blocked ready valve"
    f" ;; slice={_SLICE} | tier=factory | repo={_LOCAL_REPO}"
    " | acceptance=The Dispatcher files the cut. | blockers=none | spec=no"
    " | scope=Read the plan off the terminated run and file it."
)


@pytest.fixture(autouse=True)
def _fresh_tenant(monkeypatch: pytest.MonkeyPatch) -> object:
    monkeypatch.setenv("LIVESPEC_BEADS_FAKE", "1")
    reset_fake_singleton()
    TRANSITION_OBSERVATIONS.clear()
    # The Definition-of-Done judgement is a model call and not this module's
    # subject; stood down, intake routes a filed slice on its mechanical findings.
    monkeypatch.setattr(
        intake_dor, "judge_item_definition_of_done", lambda **_kwargs: SimpleNamespace(holds=False)
    )
    yield
    TRANSITION_OBSERVATIONS.clear()
    reset_fake_singleton()


def _repo(*, tmp_path: Path, claim_tokens: bool = True) -> Path:
    """A repository with a readable spec tree and a groom variant, committing the key."""
    repo = tmp_path / _LOCAL_REPO
    spec = repo / "SPECIFICATION"
    (spec / "history" / "v001").mkdir(parents=True)
    _ = (spec / "contracts.md").write_text(
        f"# Contracts\n\n{_HEADING}\n\nBody.\n", encoding="utf-8"
    )
    variant = repo / _GROOM_DIR
    variant.mkdir(parents=True)
    _ = (variant / "workflow.toml").write_text(
        '[workflow]\ngraph = "workflow.fabro"\n\n[run.inputs]\nworkflow_kind = "groom"\n',
        encoding="utf-8",
    )
    dispatcher: dict[str, object] = {
        "claim_tokens": claim_tokens,
        "workflows": {_GROOM_VARIANT: _GROOM_DIR},
    }
    block = {"connection": _CONNECTION, "dispatcher": dispatcher}
    _ = (repo / ".livespec.jsonc").write_text(
        json.dumps({"livespec-orchestrator-beads-fabro": block}), encoding="utf-8"
    )
    return repo


def _config(*, repo: Path) -> StoreConfig:
    """The descriptor an operator's invocation resolves in `repo`, naming it as the root."""
    return resolve_store_config(cwd=repo, work_items_arg=None)


def _item(
    *, status: WorkItemStatus, item_id: str = _ITEM_ID, assignee: str | None = None
) -> WorkItem:
    return WorkItem(
        id=item_id,
        type="task",
        status=status,
        title="An item some operation closes",
        description=f"## Definition of Done\n\n- It does the thing.\n\nReferences: {_HEADING}\n",
        origin="freeform",
        gap_id=None,
        rank="a0",
        assignee=assignee,
        depends_on=(),
        captured_at="2026-11-06T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
        admission_policy="auto",
        acceptance_policy="ai-only",
        acceptance_criteria="- The slice is verified green by the check suite.",
    )


def _file(*, config: StoreConfig, item: WorkItem) -> tuple[FakeBeadsClient, str]:
    """File `item` in the cut-over repository, where the store names its first token."""
    append_work_item(path=config, item=item)
    client = make_beads_client(config=config)
    assert isinstance(client, FakeBeadsClient)
    return client, _named(client=client, item_id=item.id)


def _named(*, client: FakeBeadsClient, item_id: str = _ITEM_ID) -> str:
    return str(client.show_issue(issue_id=item_id)["metadata"][CLAIM_TOKEN_METADATA_KEY])


def _status(*, client: FakeBeadsClient, item_id: str = _ITEM_ID) -> object:
    return client.show_issue(issue_id=item_id)["status"]


def _snapshot(*, client: FakeBeadsClient, item_id: str = _ITEM_ID) -> dict[str, object]:
    return copy.deepcopy(client.show_issue(issue_id=item_id))


def _is_closed(*, client: FakeBeadsClient, token: str) -> bool:
    return client.show_issue(issue_id=token)["status"] == "closed"


def _won_with(*, client: FakeBeadsClient, token: str) -> tuple[tuple[str, str], str]:
    """The writer and intent `token` was won with, and the successor that win named."""
    reason = json.loads(str(client.show_issue(issue_id=token)["close_reason"]))
    return (reason["writer"], reason["intent"]), reason["successor"]


def _lose_the_token(
    *, client: FakeBeadsClient, token: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Have an unnamed writer close `token` at the instant the closer closes it."""
    close = client.close_issue_without_verdict

    def _raced(*, issue_id: str, reason: str) -> None:
        if issue_id == token:
            close(issue_id=issue_id, reason=_ANOTHER_WRITER)
        close(issue_id=issue_id, reason=reason)

    monkeypatch.setattr(client, "close_issue_without_verdict", _raced)


def _recorded(
    *, client: FakeBeadsClient, monkeypatch: pytest.MonkeyPatch, item_id: str = _ITEM_ID
) -> list[str]:
    """Every token close, item write and item close of an operation, in order."""
    events: list[str] = []
    close_token = client.close_issue_without_verdict
    close_item = client.close_issue
    update = client.update_issue

    def _closing_a_token(*, issue_id: str, reason: str) -> None:
        events.append("token-closed")
        close_token(issue_id=issue_id, reason=reason)

    def _closing_the_item(*, issue_id: str, reason: str | None) -> None:
        if issue_id == item_id:
            events.append("item-closed")
        close_item(issue_id=issue_id, reason=reason)

    def _writing(**fields: object) -> None:
        if fields["issue_id"] == item_id:
            events.append(f"item-written:status={fields.get('status')}")
        update(**fields)

    monkeypatch.setattr(client, "close_issue_without_verdict", _closing_a_token)
    monkeypatch.setattr(client, "close_issue", _closing_the_item)
    monkeypatch.setattr(client, "update_issue", _writing)
    return events


def _win_the_successor_at_the_hold(
    *, client: FakeBeadsClient, monkeypatch: pytest.MonkeyPatch, status: str
) -> None:
    """Have a status writer win the successor a hold names, the instant the hold's write lands.

    A hold is the one protocol write on the item that changes no status. The
    writer runs the real protocol, so it wins the successor the hold named and
    writes `status` with a successor of its own: the next legitimate write.
    """
    update = client.update_issue
    fired: list[str] = []

    def _racing(**fields: object) -> None:
        update(**fields)
        is_hold = (
            fields.get("issue_id") == _ITEM_ID
            and bool(fields.get("names_claim_token"))
            and fields.get("status") is None
        )
        if is_hold and not fired:
            fired.append(_ITEM_ID)
            won = change_claim(
                client=client,
                work_item_id=_ITEM_ID,
                writer=_RACER,
                intent="move",
                claim_tokens=True,
                status=status,
            )
            assert won.outcome == "applied"

    monkeypatch.setattr(client, "update_issue", _racing)


# --- Bullet 1: close-work-item -----------------------------------------------------------------


def _close(*, repo: Path, capsys: pytest.CaptureFixture[str]) -> tuple[int, str, str]:
    """One operator invocation of `close-work-item`, and what it printed."""
    code = close_work_item(
        argv=[_ITEM_ID, "--reason", "shipped by hand", "--project-root", str(repo)]
    )
    printed = capsys.readouterr()
    return code, printed.out, printed.err


def test_a_close_work_item_that_wins_the_token_names_the_successor_and_then_closes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """DoD 1: the hold wins the current token and names the successor; the close follows it."""
    repo = _repo(tmp_path=tmp_path)
    client, token = _file(config=_config(repo=repo), item=_item(status="ready"))
    events = _recorded(client=client, monkeypatch=monkeypatch)

    code, out, _err = _close(repo=repo, capsys=capsys)

    assert events[:3] == ["token-closed", "item-written:status=None", "item-closed"]
    hold, successor = _won_with(client=client, token=token)
    assert hold == (_HUMAN_VALVE, "close-work-item")
    assert successor == _named(client=client)
    assert not _is_closed(client=client, token=successor)
    assert (code, _status(client=client)) == (0, "closed")
    assert "resolution:completed" in client.show_issue(issue_id=_ITEM_ID)["labels"]
    assert f"closed {_ITEM_ID} resolution:completed" in out


def test_a_close_work_item_that_loses_the_token_reports_claim_changed_and_closes_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """DoD 1: a lost hold closes nothing, and the operation says `claim-changed`."""
    repo = _repo(tmp_path=tmp_path)
    client, token = _file(config=_config(repo=repo), item=_item(status="ready"))
    before = _snapshot(client=client)
    _lose_the_token(client=client, token=token, monkeypatch=monkeypatch)

    code, out, err = _close(repo=repo, capsys=capsys)

    assert (code, out) == (4, "")
    assert err == (
        f"ERROR: {_HUMAN_VALVE} (close-work-item) refused: the claim-token protocol reported "
        f"claim-changed; the status and claim of {_ITEM_ID} were not written.\n"
    )
    assert _snapshot(client=client) == before
    assert client.show_issue(issue_id=token)["close_reason"] == _ANOTHER_WRITER


def test_a_close_work_item_with_the_key_false_touches_no_token(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Before the cutover the close is the one write it always was."""
    repo = _repo(tmp_path=tmp_path, claim_tokens=False)
    append_work_item(path=_config(repo=repo), item=_item(status="ready"))
    client = make_beads_client(config=_config(repo=repo))
    assert isinstance(client, FakeBeadsClient)

    code, _out, _err = _close(repo=repo, capsys=capsys)

    assert (code, _status(client=client)) == (0, "closed")
    assert CLAIM_TOKEN_METADATA_KEY not in client.show_issue(issue_id=_ITEM_ID)["metadata"]
    assert all("claim-token" not in (record.get("labels") or []) for record in client.list_issues())


# --- Bullet 2: a regroom through the groom front-end --------------------------------------------


def _regroom(*, repo: Path) -> object:
    """The front-end's filing of an approved cut of one local slice over `_ITEM_ID`."""
    return file_approved_slices(
        path=_config(repo=repo),
        regroom_item_id=_ITEM_ID,
        local_repo=_LOCAL_REPO,
        approval=_APPROVAL,
        slices=[
            CandidateSlice(
                title=_SLICE,
                description="Do the one thing the slice names.",
                acceptance="The check suite verifies it.",
                autonomy_tier="factory",
                repo_target=_LOCAL_REPO,
            )
        ],
    )


def _filed_slice_ids(*, config: StoreConfig) -> list[str]:
    return [item.id for item in read_work_items(path=config) if item.title == _SLICE]


def test_a_regroom_closes_the_original_only_after_winning_its_token(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """DoD 2: the hold on the original is taken after the slices are filed, before its close."""
    repo = _repo(tmp_path=tmp_path)
    client, token = _file(config=_config(repo=repo), item=_item(status="backlog"))
    events = _recorded(client=client, monkeypatch=monkeypatch)

    result = _regroom(repo=repo)

    assert getattr(result, "regroomed_out", None) is True
    closed = events.index("item-closed")
    assert events[closed - 2 : closed] == ["token-closed", "item-written:status=None"]
    hold, successor = _won_with(client=client, token=token)
    assert hold == (_HUMAN_VALVE, "groom-close")
    assert successor == _named(client=client)
    assert not _is_closed(client=client, token=successor)
    assert _status(client=client) == "closed"


def test_a_regroom_that_loses_the_original_token_leaves_the_original_open_naming_its_slices(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """DoD 2: a lost hold refuses the close, with the slices already filed and named."""
    repo = _repo(tmp_path=tmp_path)
    config = _config(repo=repo)
    client, token = _file(config=config, item=_item(status="backlog"))
    _lose_the_token(client=client, token=token, monkeypatch=monkeypatch)

    with pytest.raises(GroomExitRefusedError) as refused:
        _ = _regroom(repo=repo)

    filed = _filed_slice_ids(config=config)
    assert len(filed) == 1
    assert refused.value.detail == (
        "the original was not closed because the claim-token protocol reported claim-changed; "
        f"nothing was written to it, and its replacement slices are already filed: {filed[0]}"
    )
    assert (_status(client=client), _named(client=client)) == ("backlog", token)
    assert client.show_issue(issue_id=token)["close_reason"] == _ANOTHER_WRITER


# --- Bullet 3a: a plan child disposition --------------------------------------------------------


def _seed_plan_child(*, config: StoreConfig) -> tuple[FakeBeadsClient, str]:
    """An epic with one classified `backlog` child the session may dispose of."""
    client, token = _file(config=config, item=_item(status="backlog", item_id=_CHILD_ID))
    _ = client.create_issue(
        draft=IssueDraft(
            issue_id=_EPIC_ID,
            issue_type="epic",
            title="A plan epic",
            description="The plan.",
            assignee=None,
            created_at=_NOW,
            metadata={"rank": "a1"},
            labels=["origin:freeform"],
        )
    )
    client.add_dependency(from_id=_CHILD_ID, to_id=_EPIC_ID, edge_type=EDGE_PARENT_CHILD)
    client.add_comment(
        issue_id=_CHILD_ID,
        body=spec_change_tier_comment(
            item_id=_CHILD_ID,
            stage=STAGE_FILING,
            decision=exempt_decision(classification="bug"),
            spec_version="1",
            digest="a-digest",
        ),
    )
    return client, token


def _dispose(*, config: StoreConfig) -> None:
    close_plan_child(
        config=config,
        epic_id=_EPIC_ID,
        child_id=_CHILD_ID,
        rationale="Superseded by the scope event.",
        author="the-plan-session",
        now=_NOW,
    )


def test_a_plan_child_disposition_closes_the_child_only_after_winning_its_token(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """DoD 3: the disposition is recorded, then the hold, then the close."""
    config = _config(repo=_repo(tmp_path=tmp_path))
    client, token = _seed_plan_child(config=config)
    events = _recorded(client=client, monkeypatch=monkeypatch, item_id=_CHILD_ID)

    _dispose(config=config)

    assert events[:3] == ["token-closed", "item-written:status=None", "item-closed"]
    hold, successor = _won_with(client=client, token=token)
    assert hold == (_HUMAN_VALVE, "plan-child-close")
    assert successor == _named(client=client, item_id=_CHILD_ID)
    assert not _is_closed(client=client, token=successor)
    assert _status(client=client, item_id=_CHILD_ID) == "closed"


def test_a_plan_child_disposition_that_loses_the_token_closes_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """DoD 3: a lost hold leaves the child open, with the recorded rationale explaining the intent."""
    config = _config(repo=_repo(tmp_path=tmp_path))
    client, token = _seed_plan_child(config=config)
    _lose_the_token(client=client, token=token, monkeypatch=monkeypatch)

    with pytest.raises(Exception, match="claim-changed") as refused:
        _dispose(config=config)

    assert type(refused.value).__name__ == "ClaimWriteRefusedError"
    assert getattr(refused.value, "outcome", None) == "claim-changed"
    assert (
        _status(client=client, item_id=_CHILD_ID),
        _named(client=client, item_id=_CHILD_ID),
    ) == (
        "backlog",
        token,
    )
    assert any(
        "plan-child-disposition" in str(comment["text"])
        for comment in client.list_comments(issue_id=_CHILD_ID)
    )


# --- Bullet 3b: a plan archive ------------------------------------------------------------------


@dataclass(kw_only=True)
class _UnreleasedForge:
    """A forge that names the governed repository and reports it carries no release tag."""

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
        if argv == governed_repository_argv():
            return CommandResult(exit_code=0, stdout="thewoolleyman/livespec", stderr="")
        return CommandResult(exit_code=0, stdout="", stderr="")


def _seed_plan_proof(*, client: FakeBeadsClient, epic_id: str) -> None:
    """The captured/verified plan record pair the archive's proof leg reads."""
    for verdict, identity, reproduced in (
        (VERDICT_CAPTURED, "session capturing-session", None),
        (VERDICT_VERIFIED, "session replaying-session", True),
    ):
        client.add_comment(
            issue_id=epic_id,
            body=render_proof_record(
                title=PLAN_PROOF_RECORD_TITLE,
                verdict=verdict,
                identity=identity,
                timestamp="2026-10-05T01:00:00Z",
                build=BuildIdentity(release_tag=None, installed_build=None, commit="c0ffee1"),
                assertions=(
                    RecordAssertion(
                        text=_PLAN_ASSERTION,
                        proof_mode=PROOF_MODE_HOST_CAPTURED,
                        governing_scenario=None,
                        steps=("Run the delivered command on the operator host.",),
                        proof="$ delivered --version\n0.1.0",
                        reproduced=reproduced,
                    ),
                ),
            ),
        )


def _seed_archivable_plan(*, repo: Path) -> tuple[FakeBeadsClient, str, str]:
    """A plan whose every archive gate passes, and the token its epic names."""
    config = _config(repo=repo)
    created = plan.create_thread(
        project_root=repo,
        config=config,
        slug=_SLUG,
        title="Archive thread",
        research_filename="initial.md",
        research_text="research\n",
        now=_NOW,
        definition_of_done=PlanDefinitionOfDone(
            statement="Done when the operator has driven it and seen it work.",
            assertions=(_PLAN_ASSERTION,),
        ),
    )
    epic_id = created["epic_id"]
    client = make_beads_client(config=config)
    assert isinstance(client, FakeBeadsClient)
    _ = client.create_issue(
        draft=IssueDraft(
            issue_id=_CHILD_ID,
            issue_type="task",
            title="child",
            description="child work",
            assignee=None,
            created_at=_NOW,
            metadata={"rank": "a1"},
            labels=["origin:freeform"],
        )
    )
    client.add_dependency(from_id=_CHILD_ID, to_id=epic_id, edge_type=EDGE_BLOCKS)
    client.close_issue(issue_id=_CHILD_ID, reason="completed")
    plan.record_completeness_review_evidence(
        config=config,
        epic_id=epic_id,
        evidence_id="review-evidence-1",
        env=_REVIEWING_SESSION_ENV,
        reviewed_child_ids=(),
        separate_reviewer=True,
        attests_complete_requirement_coverage=True,
        body="All research requirements and deferrals have ledger carriers.",
        now="2026-11-06T10:00:00Z",
    )
    _seed_plan_proof(client=client, epic_id=epic_id)
    return client, epic_id, _named(client=client, item_id=epic_id)


def _archive(*, repo: Path, epic_id: str) -> dict[str, str]:
    return plan.archive_thread(
        env=_ARCHIVING_SESSION_ENV,
        runner=_UnreleasedForge(),
        project_root=repo,
        config=_config(repo=repo),
        slug=_SLUG,
        epic_id=epic_id,
        completeness_review_comment_id="review-evidence-1",
    )


def test_a_plan_archive_closes_the_epic_only_after_winning_its_token(tmp_path: Path) -> None:
    """DoD 3: the archive wins the epic's token before it moves the plan and closes the epic."""
    repo = _repo(tmp_path=tmp_path)
    client, epic_id, token = _seed_archivable_plan(repo=repo)

    result = _archive(repo=repo, epic_id=epic_id)

    assert result["archive_path"] == f"plan/archive/{_SLUG}"
    assert _is_closed(client=client, token=token)
    hold, successor = _won_with(client=client, token=token)
    assert hold == (_HUMAN_VALVE, "plan-archive")
    assert successor == _named(client=client, item_id=epic_id)
    assert not _is_closed(client=client, token=successor)
    assert _status(client=client, item_id=epic_id) == "closed"


def test_a_plan_archive_that_loses_the_epic_token_moves_nothing_and_closes_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """DoD 3: a lost hold refuses before the plan directory moves, so the archive can be retried."""
    repo = _repo(tmp_path=tmp_path)
    client, epic_id, token = _seed_archivable_plan(repo=repo)
    _lose_the_token(client=client, token=token, monkeypatch=monkeypatch)

    with pytest.raises(Exception, match="claim-changed") as refused:
        _ = _archive(repo=repo, epic_id=epic_id)

    assert type(refused.value).__name__ == "ClaimWriteRefusedError"
    assert getattr(refused.value, "outcome", None) == "claim-changed"
    assert (repo / "plan" / _SLUG).is_dir()
    assert not (repo / "plan" / "archive").exists()
    assert _status(client=client, item_id=epic_id) != "closed"
    assert _named(client=client, item_id=epic_id) == token


# --- Bullet 4: a status write that wins the successor between the hold and the close -----------


def _journal(*, repo: Path) -> JournalFile:
    path = repo / "tmp" / "journal.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    _ = path.write_text("", encoding="utf-8")
    return JournalFile(path=path)


def _stages(*, journal: JournalFile) -> list[tuple[object, object, object]]:
    """Each journal row's stage, reason and detail, in order."""
    rows = [json.loads(line) for line in journal.path.read_text(encoding="utf-8").splitlines()]
    return [(row.get("stage"), row.get("reason"), row.get("detail")) for row in rows]


def _apply(*, repo: Path, item: WorkItem, journal: JournalFile) -> bool:
    """The Dispatcher's groom apply seam, whose close of the original already held its token."""
    return file_groom_plan(
        repo=repo,
        item=item,
        text=_PLAN_TEXT,
        variant=_GROOM_VARIANT,
        run_id="01RUN",
        journal=journal,
    )


def test_a_status_write_that_wins_the_successor_between_the_hold_and_the_close_is_not_overwritten(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """DoD 4: the later winner's status stands; the hold answers claim-changed and nothing closes."""
    repo = _repo(tmp_path=tmp_path)
    item = _item(status="active", assignee="dispatcher")
    client, token = _file(config=_config(repo=repo), item=item)
    _win_the_successor_at_the_hold(client=client, monkeypatch=monkeypatch, status="blocked")
    journal = _journal(repo=repo)

    filed = _apply(repo=repo, item=item, journal=journal)

    release, released = _won_with(client=client, token=token)
    hold, held = _won_with(client=client, token=released)
    racer, current = _won_with(client=client, token=held)
    assert (release[1], hold, racer) == (
        "groom-apply-release",
        ("dispatcher-terminal", "groom-apply-close"),
        (_RACER, "move"),
    )
    assert (filed, _status(client=client), _named(client=client)) == (False, "blocked", current)
    assert not _is_closed(client=client, token=current)
    stages = _stages(journal=journal)
    assert [stage for stage, _reason, _detail in stages] == [
        "claim-write-refused",
        "groom-cut-refused",
    ]
    assert stages[0][1] == "claim-changed"
    assert "claim-changed" in str(stages[1][2])
