"""A takeover follows the token chain to an open token, and a stand-down leaves the item writable.

`SPECIFICATION/contracts.md` ("Stranded claim release" -> "Claim tokens", step
5) exists so that "a winner that crashed between its close and its item write
never leaves the item unwritable". Two shapes measured on 2026-11-06 (the
08:25:40Z comment on bd-ib-7uue5s) did leave one:

- a takeover writer that is itself stranded after its close leaves the item
  naming a closed token whose successor is closed too, with an open token one
  hop further on. A writer that follows ONE hop can never close the middle
  token, so it reports `claim-changed` for ever;
- a takeover that stands down because the original winner's write landed late
  has already closed the stranded successor, and discarding its own left the
  chain ending in a closed token that names no live successor. A stand-down
  now names its own successor on the item in a write that changes nothing
  else, so the next writer wins that successor at once.

A chain that still ends in a closed token naming no successor can only come
from a write made outside the protocol; needs-attention surfaces it.

Each case drives the public entry point against the in-memory tenant: the
`move` valve through `drive.run_action` for every claim writer, and
`needs_attention.build_attention` for the attention surface. The tenant is
left the way production leaves it, by real writers: a press wins the item's
token and its item write then fails. No case sleeps: the takeover wait is
replaced by one on a clock the case owns, whose sleep ages this process's
recorded sightings by the time slept, which is all a real sleep does to what
the protocol measures.
"""

from __future__ import annotations

import json
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
from livespec_orchestrator_beads_fabro.commands import _intake_valve_claim_writes as writes
from livespec_orchestrator_beads_fabro.commands import needs_attention
from livespec_orchestrator_beads_fabro.commands._dispatcher_claim_guard import (
    TRANSITION_OBSERVATIONS,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_invoker import InvokerIdentity
from livespec_orchestrator_beads_fabro.commands._intake_valve_claim_writes import TakeoverWait
from livespec_orchestrator_beads_fabro.commands.drive import run_action
from livespec_orchestrator_beads_fabro.commands.migrate_claim_tokens import CONFIRM_FLAG
from livespec_orchestrator_beads_fabro.commands.needs_attention import build_attention
from livespec_orchestrator_beads_fabro.errors import BeadsCommandError
from livespec_orchestrator_beads_fabro.store import (
    append_work_item,
    materialize_work_items,
    read_work_items,
)
from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem

_ITEM_ID = "bd-ib-chainend"
_WAITING_ITEM_ID = "bd-ib-chainwait"
_QUIET_ITEM_ID = "bd-ib-chainquiet"
_HEADING = "## Effective acceptance criteria"
_PENDING = "claim-transition-pending"
_LOST = "claim-changed"
_LANDED = "green"
_WAIT = 180.0
_DISCARD_REASON = '{"kind":"claim-token-discard","writer":"by-hand"}'
_CLAIM_TOKEN_ROW_PREFIX = "hygiene:claim-token-"
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


def _repo(*, tmp_path: Path) -> Path:
    """A repository with a readable spec tree, cut over to claim tokens."""
    repo = tmp_path / "repo"
    spec = repo / "SPECIFICATION"
    spec.mkdir(parents=True)
    _ = (spec / "contracts.md").write_text(
        f"# Contracts\n\n{_HEADING}\n\nSome prose.\n", encoding="utf-8"
    )
    block = {"connection": _CONNECTION, "dispatcher": {"claim_tokens": True}}
    _ = (repo / ".livespec.jsonc").write_text(
        json.dumps({"livespec-orchestrator-beads-fabro": block}), encoding="utf-8"
    )
    return repo


def _item(*, item_id: str) -> WorkItem:
    return WorkItem(
        id=item_id,
        type="task",
        status="backlog",
        title="A slice whose claim transitions were left unapplied",
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
        audit=None,
        superseded_by=None,
        admission_policy="auto",
        acceptance_criteria="The dispatched slice is verified green by the check suite.",
    )


def _seed(*, item_id: str = _ITEM_ID) -> FakeBeadsClient:
    """File a `backlog` item naming an open token."""
    append_work_item(path=_config(), item=_item(item_id=item_id))
    client = make_beads_client(config=_config())
    assert isinstance(client, FakeBeadsClient)
    _name(client=client, item_id=item_id, token=create_claim_token(client=client))
    return client


def _name(*, client: FakeBeadsClient, item_id: str, token: str) -> None:
    metadata = dict(client.show_issue(issue_id=item_id)["metadata"])
    metadata[CLAIM_TOKEN_METADATA_KEY] = token
    client.update_issue(issue_id=item_id, metadata=metadata, names_claim_token=True)


def _named(*, client: FakeBeadsClient, item_id: str = _ITEM_ID) -> str:
    return client.show_issue(issue_id=item_id)["metadata"][CLAIM_TOKEN_METADATA_KEY]


def _successor_of(*, client: FakeBeadsClient, token: str) -> str:
    """The successor a closed token was won with."""
    return json.loads(client.show_issue(issue_id=token)["close_reason"])["successor"]


def _is_open(*, client: FakeBeadsClient, token: str) -> bool:
    return client.show_issue(issue_id=token)["status"] != "closed"


def _stored_status(*, item_id: str = _ITEM_ID) -> str:
    return materialize_work_items(records=read_work_items(path=_config()))[item_id].status


def _move(*, repo: Path, target: str, item_id: str = _ITEM_ID) -> dict[str, object]:
    """One operator press of the `move` valve, through the surface an operator uses."""
    return run_action(
        repo=repo,
        action_id=f"move:{item_id}:{target}",
        identity=InvokerIdentity(invoker="human:cw", invoker_source="flag"),
    )


def _strand_a_transition(
    *, client: FakeBeadsClient, repo: Path, monkeypatch: pytest.MonkeyPatch, item_id: str = _ITEM_ID
) -> None:
    """A `move` press wins the item's current token, and its item write then fails.

    When the item already names a closed token the press waits out the takeover
    wait on the owned clock, wins the stranded successor, and is then stranded
    itself: the chain grows by one closed hop.
    """
    real = client.update_issue

    def _failing_on_the_item(**fields: object) -> None:
        if fields["issue_id"] == item_id:
            raise BeadsCommandError(command="bd update", exit_code=1, stderr="server gone")
        real(**fields)

    with monkeypatch.context() as patched:
        patched.setattr(client, "update_issue", _failing_on_the_item)
        with pytest.raises(BeadsCommandError):
            _ = _move(repo=repo, target="ready", item_id=item_id)


@dataclass(kw_only=True)
class _Clock:
    """A clock a case owns; its sleep ages this process's recorded sightings."""

    now: float = 0.0
    slept: list[float] = field(default_factory=list)

    def clock(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.slept.append(seconds)
        self.now += seconds
        for observation in TRANSITION_OBSERVATIONS:
            TRANSITION_OBSERVATIONS[observation] -= seconds


def _cut_over(*, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, _Clock]:
    """A cut-over repository whose one-shot writers wait on the owned clock."""
    repo = _repo(tmp_path=tmp_path)
    clock = _Clock()
    monkeypatch.setattr(
        writes, "TakeoverWait", lambda: TakeoverWait(clock=clock.clock, sleep=clock.sleep)
    )
    return repo, clock


def _stand_down(
    *, client: FakeBeadsClient, repo: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[dict[str, object], str, str, list[str]]:
    """A takeover that stands down: the original winner's write lands right after its close.

    Returns the takeover press's result, the stranded successor the takeover
    won, the successor the takeover created, and every token the press closed
    in order. A stand-down closes only the stranded successor: it names its
    own successor instead of discarding it.
    """
    stranded = _successor_of(client=client, token=_named(client=client))
    real_close = client.close_issue_without_verdict
    closed: list[str] = []

    def _land_the_original() -> None:
        client.update_issue(
            issue_id=_ITEM_ID,
            status="ready",
            clear_assignee=True,
            metadata={CLAIM_TOKEN_METADATA_KEY: stranded},
            names_claim_token=True,
        )

    def _landing_the_original(*, issue_id: str, reason: str) -> None:
        real_close(issue_id=issue_id, reason=reason)
        closed.append(issue_id)
        # The original write lands behind the close of the stranded successor
        # and behind no other close (a dispatch, so the helper has no branch).
        {stranded: _land_the_original}.get(issue_id, lambda: None)()

    monkeypatch.setattr(client, "close_issue_without_verdict", _landing_the_original)
    result = _move(repo=repo, target="ready")
    monkeypatch.setattr(client, "close_issue_without_verdict", real_close)
    assert closed[:1] == [stranded], "the takeover never closed the stranded successor"
    return result, stranded, _successor_of(client=client, token=stranded), closed


def test_a_takeover_follows_a_chain_of_two_closed_tokens_to_the_open_one_and_its_write_lands(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """DoD 1: each unapplied transition is observed for the takeover wait, then the write lands."""
    repo, clock = _cut_over(tmp_path=tmp_path, monkeypatch=monkeypatch)
    client = _seed()
    first = _named(client=client)
    _strand_a_transition(client=client, repo=repo, monkeypatch=monkeypatch)
    _strand_a_transition(client=client, repo=repo, monkeypatch=monkeypatch)
    second = _successor_of(client=client, token=first)
    third = _successor_of(client=client, token=second)
    assert _named(client=client) == first
    assert _is_open(client=client, token=third)
    TRANSITION_OBSERVATIONS.clear()
    clock.slept.clear()

    first_press = _move(repo=repo, target="ready")
    second_press = _move(repo=repo, target="ready")

    assert (first_press["status"], first_press["domain_error"]) == ("failed", _PENDING)
    assert second_press["status"] == _LANDED, second_press
    assert clock.slept == [_WAIT, _WAIT]
    assert _stored_status() == "ready"
    assert _named(client=client) == _successor_of(client=client, token=third)
    assert _is_open(client=client, token=_named(client=client))


def test_after_a_takeover_stands_down_the_next_claim_writers_write_lands(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """DoD 2: the original winner's write stands, and the item is still writable after it."""
    repo, clock = _cut_over(tmp_path=tmp_path, monkeypatch=monkeypatch)
    client = _seed()
    _strand_a_transition(client=client, repo=repo, monkeypatch=monkeypatch)
    clock.slept.clear()

    takeover, stranded, created, closed = _stand_down(
        client=client, repo=repo, monkeypatch=monkeypatch
    )
    assert (takeover["status"], takeover["domain_error"]) == ("failed", _LOST)
    assert clock.slept == [_WAIT]
    assert _stored_status() == "ready"
    assert not _is_open(client=client, token=stranded)
    assert _is_open(client=client, token=_named(client=client))

    next_press = _move(repo=repo, target="backlog")

    assert next_press["status"] == _LANDED, next_press
    assert clock.slept == [_WAIT]
    assert _stored_status() == "backlog"
    assert not _is_open(client=client, token=created)
    assert _is_open(client=client, token=_named(client=client))
    assert closed == [stranded]


def test_needs_attention_surfaces_an_item_whose_token_chain_ends_in_a_closed_token_naming_no_successor(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """DoD 3: the dead-ended chain is surfaced; a live transition and an open token are not.

    The dead end is made by hand, as only a write outside the protocol can make
    it now: the item is put back on the stranded token S, and the open successor
    the stand-down named is closed as a discard, so the chain reads S, closed
    naming a token that is closed and names nothing.
    """
    monkeypatch.setattr(needs_attention, "spec_next", lambda **_kwargs: None)
    monkeypatch.setattr(needs_attention, "currency_staleness_items", lambda **_kwargs: [])
    repo, _clock = _cut_over(tmp_path=tmp_path, monkeypatch=monkeypatch)
    client = _seed()
    _strand_a_transition(client=client, repo=repo, monkeypatch=monkeypatch)
    _result, stranded, created, _closed = _stand_down(
        client=client, repo=repo, monkeypatch=monkeypatch
    )
    _name(client=client, item_id=_ITEM_ID, token=stranded)
    client.close_issue(issue_id=created, reason=_DISCARD_REASON)
    assert not _is_open(client=client, token=stranded)
    assert _successor_of(client=client, token=stranded) == created
    _ = _seed(item_id=_WAITING_ITEM_ID)
    _strand_a_transition(
        client=client, repo=repo, monkeypatch=monkeypatch, item_id=_WAITING_ITEM_ID
    )
    _ = _seed(item_id=_QUIET_ITEM_ID)

    rows = [
        row
        for row in build_attention(project_root=repo, repo_name="repo", include_hygiene=False)
        if row.id.startswith(_CLAIM_TOKEN_ROW_PREFIX)
    ]

    assert [row.source_ref.work_item for row in rows] == [_ITEM_ID], [row.id for row in rows]
    row = rows[0]
    assert (row.kind, row.urgency, row.source_ref.repo) == ("hygiene", "high", "repo")
    assert _ITEM_ID in row.summary
    assert created in row.summary
    assert row.handoff.kind == "shell"
    assert "/bin/migrate_claim_tokens.py " in row.handoff.command
    assert row.handoff.command.endswith(f"--project-root {repo}")
    assert CONFIRM_FLAG not in row.handoff.command
