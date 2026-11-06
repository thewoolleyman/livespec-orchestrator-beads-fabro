"""`reject:<id>:regroom` contests the item's claim token before it reverts the merge.

`reject` is the one human valve that also rewrites the repository: its
`regroom` arm runs `git revert` on the merged change and then moves the item to
`backlog`. Under the claim-token cutover (`SPECIFICATION/contracts.md`, "Claim
tokens") the move is made only after winning the item's current token. A revert
made before that contest stands even when the contest is lost, so a press that
loses would leave a revert commit beside an item still in `acceptance`.

So the press contests the token FIRST, with a hold: it wins the item's current
token and names the successor, changing nothing else. Only a press that won
reverts, and the move that follows is a second guarded write, which wins the
successor the hold named.

Every case presses the valve through `drive.run_action`, the surface an
operator uses, against the in-memory tenant, in a scratch repository that
commits `dispatcher.claim_tokens` as `true` (one case commits a value that
cannot be read). No command is run: the valve is handed a runner that records
the `git revert` it was asked for and answers for it.
"""

from __future__ import annotations

import copy
import json
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro._beads_client import (
    FakeBeadsClient,
    make_beads_client,
    reset_fake_singleton,
)
from livespec_orchestrator_beads_fabro._store_dispatch_claim import (
    CLAIM_TOKEN_METADATA_KEY,
    create_claim_token,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_claim_guard import (
    TRANSITION_OBSERVATIONS,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_invoker import InvokerIdentity
from livespec_orchestrator_beads_fabro.commands.drive import CommandRun, run_action
from livespec_orchestrator_beads_fabro.store import (
    append_work_item,
    materialize_work_items,
    read_work_items,
)
from livespec_orchestrator_beads_fabro.types import AuditRecord, StoreConfig, WorkItem

_ITEM_ID = "bd-ib-regroomorder"
_HEADING = "## Effective acceptance criteria"
_MERGE_SHA = "feed01"
_REVERT = ("git", "revert", "--no-edit", _MERGE_SHA)
_ANOTHER_WRITER = "another writer won this token"
_HOLD = ("human-valve", "reject:regroom-hold")
_MOVE = ("human-valve", "reject:regroom")
_NOTHING_WRITTEN = f"nothing was written to {_ITEM_ID}."
_CONNECTION = {
    "tenant": "livespec-impl-beads",
    "prefix": "bd-ib",
    "server_user": "livespec-impl-beads",
    "database": "livespec-impl-beads",
    "bd_path": "bd",
    "fake": True,
}


@pytest.fixture(autouse=True)
def _fresh_tenant(monkeypatch: pytest.MonkeyPatch) -> object:
    monkeypatch.setenv("LIVESPEC_BEADS_FAKE", "1")
    reset_fake_singleton()
    TRANSITION_OBSERVATIONS.clear()
    yield
    TRANSITION_OBSERVATIONS.clear()
    reset_fake_singleton()


def _config() -> StoreConfig:
    return StoreConfig(
        tenant="livespec-impl-beads",
        prefix="bd-ib",
        server_user="livespec-impl-beads",
        database="livespec-impl-beads",
        bd_path="bd",
        fake=True,
    )


def _repo(*, tmp_path: Path, claim_tokens: object = True) -> Path:
    """A repository with a readable spec tree, committing the given key."""
    repo = tmp_path / "repo"
    spec = repo / "SPECIFICATION"
    spec.mkdir(parents=True)
    _ = (spec / "contracts.md").write_text(
        f"# Contracts\n\n{_HEADING}\n\nSome prose.\n", encoding="utf-8"
    )
    block = {"connection": _CONNECTION, "dispatcher": {"claim_tokens": claim_tokens}}
    _ = (repo / ".livespec.jsonc").write_text(
        json.dumps({"livespec-orchestrator-beads-fabro": block}), encoding="utf-8"
    )
    return repo


def _merged_item() -> WorkItem:
    """An item in `acceptance` whose audit records the merge a regroom reverts."""
    return WorkItem(
        id=_ITEM_ID,
        type="task",
        status="acceptance",
        title="A merged slice a human rejects for regrooming",
        description=(
            "Do the thing.\n\n## Definition of Done\n\n"
            f"- The dispatched slice lands its change.\n\nReferences: {_HEADING}\n"
        ),
        origin="freeform",
        gap_id=None,
        rank="a2",
        assignee=None,
        depends_on=(),
        captured_at="2026-11-06T00:00:00Z",
        resolution=None,
        reason=None,
        audit=AuditRecord(
            verification_timestamp="2026-11-06T01:00:00Z",
            commits=(),
            files_changed=(),
            merge_sha=_MERGE_SHA,
            pr_number=7,
        ),
        superseded_by=None,
        admission_policy="auto",
        acceptance_criteria="The dispatched slice is verified green by the check suite.",
    )


def _seed(*, name_a_token: bool = True) -> tuple[FakeBeadsClient, str]:
    """File the item through a descriptor naming no repository, naming a fresh open token."""
    append_work_item(path=_config(), item=_merged_item())
    client = make_beads_client(config=_config())
    assert isinstance(client, FakeBeadsClient)
    token = create_claim_token(client=client)
    metadata = dict(client.show_issue(issue_id=_ITEM_ID)["metadata"])
    if name_a_token:
        metadata[CLAIM_TOKEN_METADATA_KEY] = token
    client.update_issue(issue_id=_ITEM_ID, metadata=metadata, names_claim_token=True)
    return client, token


def _snapshot(*, client: FakeBeadsClient) -> dict[str, object]:
    return copy.deepcopy(client.show_issue(issue_id=_ITEM_ID))


def _named(*, client: FakeBeadsClient) -> str:
    return client.show_issue(issue_id=_ITEM_ID)["metadata"][CLAIM_TOKEN_METADATA_KEY]


def _is_closed(*, client: FakeBeadsClient, token: str) -> bool:
    return client.show_issue(issue_id=token)["status"] == "closed"


def _won_with(*, client: FakeBeadsClient, token: str) -> tuple[tuple[str, str], str]:
    """The writer and intent `token` was won with, and the successor that win named."""
    reason = json.loads(client.show_issue(issue_id=token)["close_reason"])
    return (reason["writer"], reason["intent"]), reason["successor"]


def _stored_status() -> str:
    return materialize_work_items(records=read_work_items(path=_config()))[_ITEM_ID].status


def _lose_the_token(
    *, client: FakeBeadsClient, token: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Have an unnamed writer close `token` at the instant the valve closes it."""
    close = client.close_issue_without_verdict

    def _raced(*, issue_id: str, reason: str) -> None:
        if issue_id == token:
            close(issue_id=issue_id, reason=_ANOTHER_WRITER)
        close(issue_id=issue_id, reason=reason)

    monkeypatch.setattr(client, "close_issue_without_verdict", _raced)


def _nothing() -> None:
    """What happens in the tenant while a revert runs, when a case names nothing."""


@dataclass(kw_only=True)
class _Git:
    """The command runner a `reject` press is handed, and what it was asked to run.

    `events` is the order of the press's effects, shared with `_recorded`.
    `during` runs while the revert does, for what another writer does then.
    """

    events: list[str] = field(default_factory=list)
    calls: list[tuple[str, ...]] = field(default_factory=list)
    returncode: int = 0
    during: Callable[[], None] = _nothing

    def __call__(self, *, argv: tuple[str, ...], cwd: Path | None = None) -> CommandRun:
        _ = cwd
        self.calls.append(argv)
        self.events.append("git-revert")
        self.during()
        return CommandRun(argv=argv, returncode=self.returncode, stdout="", stderr="boom")


def _recorded(*, client: FakeBeadsClient, git: _Git, monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Every token close and every item write of a press, in order, among `git`'s reverts."""
    close = client.close_issue_without_verdict
    update = client.update_issue

    def _closing(*, issue_id: str, reason: str) -> None:
        git.events.append("token-closed")
        close(issue_id=issue_id, reason=reason)

    def _writing(**fields: object) -> None:
        if fields["issue_id"] == _ITEM_ID:
            git.events.append(f"item-written:status={fields.get('status')}")
        update(**fields)

    monkeypatch.setattr(client, "close_issue_without_verdict", _closing)
    monkeypatch.setattr(client, "update_issue", _writing)
    return git.events


def _reject_regroom(*, repo: Path, git: _Git) -> dict[str, object]:
    """One operator press of `reject:<id>:regroom`, through the surface an operator uses."""
    return run_action(
        repo=repo,
        action_id=f"reject:{_ITEM_ID}:regroom",
        identity=InvokerIdentity(invoker="human:cw", invoker_source="flag"),
        runner=git,
    )


def test_a_reject_regroom_that_loses_the_token_makes_no_revert_and_reports_claim_changed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """DoD 1: the token is contested before the revert, so a loser has reverted nothing."""
    repo = _repo(tmp_path=tmp_path)
    client, token = _seed()
    before = _snapshot(client=client)
    _lose_the_token(client=client, token=token, monkeypatch=monkeypatch)
    git = _Git()

    result = _reject_regroom(repo=repo, git=git)

    assert git.calls == []
    assert (result["status"], result["domain_error"]) == ("failed", "claim-changed")
    assert result["summary"] == (
        f"reject refused: the claim-token protocol reported claim-changed; {_NOTHING_WRITTEN}"
    )
    assert _snapshot(client=client) == before
    assert client.show_issue(issue_id=token)["close_reason"] == _ANOTHER_WRITER


def test_a_reject_regroom_that_wins_the_token_reverts_and_then_moves_the_item_under_the_protocol(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """DoD 2: hold, revert, move. Each of the two item writes won the token current then."""
    repo = _repo(tmp_path=tmp_path)
    client, token = _seed()
    git = _Git()
    events = _recorded(client=client, git=git, monkeypatch=monkeypatch)

    result = _reject_regroom(repo=repo, git=git)

    assert events == [
        "token-closed",
        "item-written:status=None",
        "git-revert",
        "token-closed",
        "item-written:status=backlog",
    ]
    hold, held = _won_with(client=client, token=token)
    move, successor = _won_with(client=client, token=held)
    assert (hold, move) == (_HOLD, _MOVE)
    assert successor == _named(client=client)
    assert not _is_closed(client=client, token=successor)
    assert git.calls == [_REVERT]
    assert (result["status"], result["target_status"]) == ("green", "backlog")
    assert _stored_status() == "backlog"


def test_a_move_refused_after_the_revert_says_the_revert_stands(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The press won its hold and reverted; another writer then won the token the hold named.

    The token is not a lock across the revert, so this is what is left of the
    old order: the refusal still has to say that the revert was made.
    """
    repo = _repo(tmp_path=tmp_path)
    client, token = _seed()
    git = _Git(
        during=lambda: _lose_the_token(
            client=client, token=_named(client=client), monkeypatch=monkeypatch
        )
    )

    result = _reject_regroom(repo=repo, git=git)

    assert _named(client=client) != token
    hold, held = _won_with(client=client, token=token)
    assert (hold, held) == (_HOLD, _named(client=client))
    assert client.show_issue(issue_id=held)["close_reason"] == _ANOTHER_WRITER
    assert git.calls == [_REVERT]
    assert (result["status"], result["domain_error"]) == ("failed", "claim-changed")
    assert result["summary"] == (
        "reject refused: the claim-token protocol reported claim-changed; "
        "the merged change was already reverted in the repository checkout (git revert) "
        "and that revert stands, so a second press would run the revert again; "
        f"the status and claim of {_ITEM_ID} were not written."
    )
    assert _stored_status() == "acceptance"


def test_a_revert_that_fails_after_the_hold_leaves_the_item_in_acceptance_naming_an_open_token(
    tmp_path: Path,
) -> None:
    """A failed revert is reported as before; the hold it followed left the item writable."""
    repo = _repo(tmp_path=tmp_path)
    client, token = _seed()
    git = _Git(returncode=1)

    result = _reject_regroom(repo=repo, git=git)

    assert _is_closed(client=client, token=token)
    hold, held = _won_with(client=client, token=token)
    assert (hold, held) == (_HOLD, _named(client=client))
    assert not _is_closed(client=client, token=held)
    assert git.calls == [_REVERT]
    assert (result["status"], result["domain_error"]) == ("failed", "revert-failed")
    assert result["summary"] == f"reject:regroom refused: git revert {_MERGE_SHA} failed: boom"
    assert _stored_status() == "acceptance"


@pytest.mark.parametrize(
    ("claim_tokens", "name_a_token", "outcome"),
    [(True, False, "claim-token-missing"), ("yes", True, "claim-tokens-unreadable")],
)
def test_a_reject_regroom_that_cannot_contest_a_token_refuses_before_it_reverts(
    *, claim_tokens: object, name_a_token: bool, outcome: str, tmp_path: Path
) -> None:
    """An item naming no token, and a key this host cannot read, each refuse with no revert."""
    repo = _repo(tmp_path=tmp_path, claim_tokens=claim_tokens)
    client, _ = _seed(name_a_token=name_a_token)
    before = _snapshot(client=client)
    git = _Git()

    result = _reject_regroom(repo=repo, git=git)

    assert git.calls == []
    assert (result["status"], result["domain_error"]) == ("failed", outcome)
    assert result["summary"] == (
        f"reject refused: the claim-token protocol reported {outcome}; {_NOTHING_WRITTEN}"
    )
    assert _snapshot(client=client) == before
