"""Which of two ways intake and a human valve write a claim, and what a refusal is.

`_intake_valve_claim_writes` is where the two non-Dispatcher claim writers that
`SPECIFICATION/contracts.md` ("Claim tokens") names decide whether a write is
token-guarded. The committed key `dispatcher.claim_tokens` selects:

- `false` or unset: the caller's own unguarded writer, called once, and nothing
  else. No token is read, minted or closed.
- `true`: one token-guarded write against the tenant, asserted on what the
  tenant then holds, followed by whatever the unguarded writer would have done
  after its own write.
- unreadable: no write at all, reported as `claim-tokens-unreadable`.

The repository whose key is read is the one the caller names, else the store
descriptor's own. A descriptor that names none has no key to read, so its write
is made unguarded.

Every guarded write also states what its decision rested on. A write whose
predicate no longer holds on the item, as it is read with its token, closes
nothing and writes nothing: the token is still OPEN afterwards, which is what
tells that refusal from a lost race.

A write that meets an UNAPPLIED TRANSITION waits it out and writes again, once.
The stranded state is made the way production makes it: a first writer wins the
item's token and its item write then fails. No case sleeps. `_Time` is the
clock and the sleep the write is handed, and its sleep ages this process's
recorded observations by the time slept, which is all a real sleep does to
what `change_claim` measures.
"""

from __future__ import annotations

import copy
import json
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro._beads_client import (
    FakeBeadsClient,
    IssueDraft,
    make_beads_client,
    reset_fake_singleton,
)
from livespec_orchestrator_beads_fabro._store_dispatch_claim import (
    CLAIM_TOKEN_METADATA_KEY,
    create_claim_token,
)
from livespec_orchestrator_beads_fabro.commands import _intake_valve_claim_writes as writes
from livespec_orchestrator_beads_fabro.commands._dispatcher_claim_guard import (
    TRANSITION_OBSERVATIONS,
)
from livespec_orchestrator_beads_fabro.commands._intake_valve_claim_writes import (
    WRITER_HUMAN_VALVE,
    WRITER_INTAKE,
    ClaimWrite,
    ClaimWriteRefused,
    TakeoverWait,
    resting_at,
    valve_claim_refusal,
)
from livespec_orchestrator_beads_fabro.errors import BeadsCommandError
from livespec_orchestrator_beads_fabro.types import StoreConfig

_ITEM_ID = "bd-ib-humanwrite"
_PLUGIN_BLOCK = "livespec-orchestrator-beads-fabro"
_ANOTHER_WRITER = "another writer won this token"
_REASON = "the item exceeds the adopted assertion ceiling"


@pytest.fixture(autouse=True)
def _fresh_tenant() -> object:
    reset_fake_singleton()
    TRANSITION_OBSERVATIONS.clear()
    yield
    TRANSITION_OBSERVATIONS.clear()
    reset_fake_singleton()


def _config(*, repo_root: Path | None = None) -> StoreConfig:
    return StoreConfig(
        tenant="livespec-impl-beads",
        prefix="bd-ib",
        server_user="livespec-impl-beads",
        database="livespec-impl-beads",
        bd_path="bd",
        fake=True,
        repo_root=repo_root,
    )


def _repo(*, tmp_path: Path, claim_tokens: object) -> Path:
    """A repository committing `dispatcher.claim_tokens` as the given value."""
    _ = (tmp_path / ".livespec.jsonc").write_text(
        json.dumps({_PLUGIN_BLOCK: {"dispatcher": {"claim_tokens": claim_tokens}}}),
        encoding="utf-8",
    )
    return tmp_path


def _item(*, name_a_token: bool = True) -> tuple[FakeBeadsClient, str]:
    """A `blocked` item awaiting a human that names an open current token."""
    client = make_beads_client(config=_config())
    assert isinstance(client, FakeBeadsClient)
    _ = client.create_issue(
        draft=IssueDraft(
            issue_id=_ITEM_ID,
            issue_type="task",
            title="A slice a human is asked about",
            description="Implement the slice.",
            assignee="fabro",
            created_at="2026-11-06T00:00:00Z",
            labels=["blocked-reason:needs-human", "rework:pending"],
        )
    )
    token = create_claim_token(client=client)
    client.update_issue(
        issue_id=_ITEM_ID,
        status="blocked",
        metadata={CLAIM_TOKEN_METADATA_KEY: token} if name_a_token else {},
        names_claim_token=True,
    )
    return client, token


@dataclass(kw_only=True)
class _Journal:
    records: list[dict[str, object]] = field(default_factory=list)

    def append(self, *, record: dict[str, object]) -> None:
        self.records.append(record)


def _snapshot(*, client: FakeBeadsClient) -> dict[str, object]:
    return copy.deepcopy(client.show_issue(issue_id=_ITEM_ID))


def _won(*, client: FakeBeadsClient, token: str) -> tuple[object, object, bool]:
    """The writer and intent `token` was won with, and whether the item names its successor."""
    reason = json.loads(client.show_issue(issue_id=token)["close_reason"])
    named = client.show_issue(issue_id=_ITEM_ID)["metadata"][CLAIM_TOKEN_METADATA_KEY]
    return reason["writer"], reason["intent"], reason["successor"] == named


def _lose_the_token(
    *, client: FakeBeadsClient, token: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    close = client.close_issue_without_verdict

    def _raced(*, issue_id: str, reason: str) -> None:
        if issue_id == token:
            close(issue_id=issue_id, reason=_ANOTHER_WRITER)
        close(issue_id=issue_id, reason=reason)

    monkeypatch.setattr(client, "close_issue_without_verdict", _raced)


def _reconciled(*, monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, str]]:
    """Every post-write run reconciliation this module asks for."""
    seen: list[tuple[str, str]] = []

    def _reconcile(**fields: object) -> None:
        seen.append((str(fields["item_id"]), str(fields["status"])))

    monkeypatch.setattr(writes, "reconcile_after_lifecycle_write", _reconcile)
    return seen


def _is_open(*, client: FakeBeadsClient, token: str) -> bool:
    return client.show_issue(issue_id=token)["status"] != "closed"


def _claim(
    *,
    repo: Path | None,
    path: StoreConfig | None = None,
    writer: str = WRITER_HUMAN_VALVE,
    intent: str = "move:ready",
    status: str = "blocked",
    journal: object = None,
    takeover_wait: TakeoverWait | None = None,
) -> ClaimWrite:
    """A write decided on the seeded item: `blocked`, awaiting a human."""
    return ClaimWrite(
        path=_config() if path is None else path,
        repo=repo,
        item_id=_ITEM_ID,
        writer=writer,
        intent=intent,
        still_as_decided=resting_at(status=status, labels=("blocked-reason:needs-human",)),
        journal=journal,
        takeover_wait=takeover_wait,
    )


def _move(*, claim: ClaimWrite, calls: list[str], reconcile: bool) -> object:
    """A `move` to `ready`, whose unguarded writer only records that it ran."""
    return claim.write_status(
        status="ready",
        clear_assignee=True,
        reconcile=reconcile,
        unguarded=lambda: calls.append("unguarded"),
    )


def test_a_guarded_status_write_is_the_stores_transition_under_the_won_token(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Status, assignee and both lane-label removals land in the one write."""
    repo = _repo(tmp_path=tmp_path, claim_tokens=True)
    client, token = _item()
    reconciled = _reconciled(monkeypatch=monkeypatch)
    calls: list[str] = []

    refusal = _move(claim=_claim(repo=repo), calls=calls, reconcile=True)

    record = client.show_issue(issue_id=_ITEM_ID)
    assert refusal is None
    assert calls == []
    assert _won(client=client, token=token) == (WRITER_HUMAN_VALVE, "move:ready", True)
    assert (record["status"], record["assignee"], record["labels"]) == ("ready", None, [])
    assert "ready_since" in record["metadata"]
    assert reconciled == [(_ITEM_ID, "ready")]


def test_a_writer_whose_unguarded_write_reconciles_nothing_is_not_reconciled_guarded(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _repo(tmp_path=tmp_path, claim_tokens=True)
    client, _ = _item()
    reconciled = _reconciled(monkeypatch=monkeypatch)

    refusal = _move(claim=_claim(repo=repo), calls=[], reconcile=False)

    assert refusal is None
    assert client.show_issue(issue_id=_ITEM_ID)["status"] == "ready"
    assert reconciled == []


def test_a_status_write_that_loses_its_token_writes_and_reconciles_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _repo(tmp_path=tmp_path, claim_tokens=True)
    client, token = _item()
    before = _snapshot(client=client)
    reconciled = _reconciled(monkeypatch=monkeypatch)
    _lose_the_token(client=client, token=token, monkeypatch=monkeypatch)
    calls: list[str] = []

    refusal = _move(claim=_claim(repo=repo), calls=calls, reconcile=True)

    assert refusal == "claim-changed"
    assert calls == []
    assert _snapshot(client=client) == before
    assert reconciled == []


@pytest.mark.parametrize("decided_on", ["ready", "blocked"])
def test_a_write_whose_decision_no_longer_holds_closes_nothing_and_writes_nothing(
    decided_on: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A status that moved on, or a label that went: either way the token stays open."""
    repo = _repo(tmp_path=tmp_path, claim_tokens=True)
    client, token = _item()
    # The item is `blocked`; with the reason label gone, neither decision holds.
    client.update_issue(issue_id=_ITEM_ID, remove_labels=["blocked-reason:needs-human"])
    before = _snapshot(client=client)
    reconciled = _reconciled(monkeypatch=monkeypatch)
    calls: list[str] = []

    refusal = _move(claim=_claim(repo=repo, status=decided_on), calls=calls, reconcile=True)

    assert refusal == "claim-changed"
    assert calls == []
    assert _snapshot(client=client) == before
    assert _is_open(client=client, token=token)
    assert reconciled == []


@pytest.mark.parametrize(
    ("record", "still"),
    [
        ({"status": "closed", "labels": ["rework:pending", "x"]}, True),
        ({"status": "closed", "labels": ["x"]}, False),
        ({"status": "closed"}, False),
        ({"status": "acceptance", "labels": ["rework:pending"]}, False),
    ],
)
def test_resting_at_reads_the_stored_status_and_every_named_label(
    *, record: dict[str, object], still: bool
) -> None:
    """The livespec `done` is the ledger's `closed`, and an omitted label list carries none."""
    assert resting_at(status="done", labels=("rework:pending",))(record) is still
    assert resting_at(status="done")({"status": "closed"}) is True


@pytest.mark.parametrize("claim_tokens", [False, None])
def test_the_unguarded_writer_runs_alone_while_the_key_is_false_or_unset(
    claim_tokens: object, tmp_path: Path
) -> None:
    repo = _repo(tmp_path=tmp_path, claim_tokens=claim_tokens)
    client, token = _item()
    before = _snapshot(client=client)
    calls: list[str] = []

    refusal = _move(claim=_claim(repo=repo), calls=calls, reconcile=True)

    assert refusal is None
    assert calls == ["unguarded"]
    assert _snapshot(client=client) == before
    assert _is_open(client=client, token=token)


def test_an_unreadable_key_withholds_the_write_and_a_journal_records_the_refusal(
    tmp_path: Path,
) -> None:
    repo = _repo(tmp_path=tmp_path, claim_tokens="yes")
    client, token = _item()
    before = _snapshot(client=client)
    calls: list[str] = []
    journal = _Journal()

    refusal = _move(claim=_claim(repo=repo, journal=journal), calls=calls, reconcile=True)

    assert refusal == "claim-tokens-unreadable"
    assert calls == []
    assert _snapshot(client=client) == before
    assert _is_open(client=client, token=token)
    assert journal.records == [
        {
            "stage": "claim-write-refused",
            "work_item_id": _ITEM_ID,
            "writer": WRITER_HUMAN_VALVE,
            "intent": "move:ready",
            "reason": "claim-tokens-unreadable",
        }
    ]


def test_the_descriptors_own_repository_is_read_when_the_caller_names_none(
    tmp_path: Path,
) -> None:
    repo = _repo(tmp_path=tmp_path, claim_tokens=True)
    client, token = _item()

    refusal = _move(
        claim=_claim(repo=None, path=_config(repo_root=repo)), calls=[], reconcile=False
    )

    assert refusal is None
    assert _won(client=client, token=token) == (WRITER_HUMAN_VALVE, "move:ready", True)


def test_a_descriptor_naming_no_repository_has_no_key_and_writes_unguarded() -> None:
    client, token = _item()
    calls: list[str] = []

    refusal = _move(claim=_claim(repo=None), calls=calls, reconcile=True)

    assert refusal is None
    assert calls == ["unguarded"]
    assert _is_open(client=client, token=token)


def _route(*, repo: Path, calls: list[str], reconcile_status: str | None) -> object:
    """A raw write by intake: `backlog`, one label off and one label on."""
    return _claim(repo=repo, writer=WRITER_INTAKE, intent="route:backlog").write_raw(
        unguarded=lambda: calls.append("unguarded"),
        reconcile_status=reconcile_status,
        status="backlog",
        add_labels=["intake:triaged"],
        remove_labels=["blocked-reason:needs-human"],
    )


@pytest.mark.parametrize(
    ("reconcile_status", "reconciliations"), [("backlog", [(_ITEM_ID, "backlog")]), (None, [])]
)
def test_a_guarded_raw_write_sends_the_named_fields_and_nothing_else(
    reconcile_status: str | None,
    reconciliations: list[tuple[str, str]],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Unlike a status write it adds no removal of its own: `rework:pending` stays."""
    repo = _repo(tmp_path=tmp_path, claim_tokens=True)
    client, token = _item()
    reconciled = _reconciled(monkeypatch=monkeypatch)
    calls: list[str] = []

    refusal = _route(repo=repo, calls=calls, reconcile_status=reconcile_status)

    record = client.show_issue(issue_id=_ITEM_ID)
    assert refusal is None
    assert calls == []
    assert _won(client=client, token=token) == (WRITER_INTAKE, "route:backlog", True)
    assert (record["status"], record["assignee"]) == ("backlog", "fabro")
    assert record["labels"] == ["rework:pending", "intake:triaged"]
    assert "ready_since" not in record["metadata"]
    assert reconciled == reconciliations


def test_a_raw_write_that_loses_its_token_writes_and_reconciles_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _repo(tmp_path=tmp_path, claim_tokens=True)
    client, token = _item()
    before = _snapshot(client=client)
    reconciled = _reconciled(monkeypatch=monkeypatch)
    _lose_the_token(client=client, token=token, monkeypatch=monkeypatch)

    refusal = _route(repo=repo, calls=[], reconcile_status="backlog")

    assert refusal == "claim-changed"
    assert _snapshot(client=client) == before
    assert reconciled == []


def test_a_guarded_move_out_of_blocked_clears_the_reason_and_stamps_no_ready_instant(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """What the store's blocked-state writer sends for a cleared reason, and no more."""
    repo = _repo(tmp_path=tmp_path, claim_tokens=True)
    client, token = _item()
    reconciled = _reconciled(monkeypatch=monkeypatch)
    calls: list[str] = []

    refusal = _claim(repo=repo, intent="resolve-blocked:ready").write_cleared_block(
        status="ready", unguarded=lambda: calls.append("unguarded")
    )

    record = client.show_issue(issue_id=_ITEM_ID)
    assert refusal is None
    assert calls == []
    assert _won(client=client, token=token) == (WRITER_HUMAN_VALVE, "resolve-blocked:ready", True)
    assert (record["status"], record["assignee"], record["labels"]) == ("ready", "fabro", [])
    assert "ready_since" not in record["metadata"]
    assert reconciled == [(_ITEM_ID, "ready")]


def _decompose(*, repo: Path) -> object:
    return _claim(
        repo=repo, writer=WRITER_INTAKE, intent="size-decomposition"
    ).write_size_decomposition(reason=_REASON)


def _comments(*, client: FakeBeadsClient) -> list[str]:
    return [comment["text"] for comment in client.list_comments(issue_id=_ITEM_ID)]


@pytest.mark.parametrize("claim_tokens", [True, False])
def test_a_size_decomposition_moves_the_item_to_backlog_and_then_records_its_reason(
    *, claim_tokens: bool, tmp_path: Path
) -> None:
    """The same two effects either way; guarded, the token is won first."""
    repo = _repo(tmp_path=tmp_path, claim_tokens=claim_tokens)
    client, token = _item()

    refusal = _decompose(repo=repo)

    assert refusal is None
    assert client.show_issue(issue_id=_ITEM_ID)["status"] == "backlog"
    assert _comments(client=client) == [_REASON]
    assert _is_open(client=client, token=token) is not claim_tokens


def test_a_size_decomposition_that_loses_its_token_records_no_reason(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _repo(tmp_path=tmp_path, claim_tokens=True)
    client, token = _item()
    before = _snapshot(client=client)
    _lose_the_token(client=client, token=token, monkeypatch=monkeypatch)

    refusal = _decompose(repo=repo)

    assert refusal == "claim-changed"
    assert _snapshot(client=client) == before
    assert _comments(client=client) == []


def test_a_hold_wins_the_token_and_names_the_successor_changing_nothing_else(
    tmp_path: Path,
) -> None:
    """The write a close is preceded by: the caller closes only after it landed."""
    repo = _repo(tmp_path=tmp_path, claim_tokens=True)
    client, token = _item()
    before = _snapshot(client=client)

    refusal = _claim(repo=repo, intent="regrade:close").hold()

    after = _snapshot(client=client)
    named = after["metadata"].pop(CLAIM_TOKEN_METADATA_KEY)
    before["metadata"].pop(CLAIM_TOKEN_METADATA_KEY)
    assert refusal is None
    assert _won(client=client, token=token) == (WRITER_HUMAN_VALVE, "regrade:close", True)
    assert named != token
    assert after == before


@pytest.mark.parametrize(("claim_tokens", "refusal"), [(True, "claim-changed"), (False, None)])
def test_a_hold_writes_nothing_when_it_loses_and_nothing_before_the_cutover(
    *, claim_tokens: bool, refusal: str | None, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _repo(tmp_path=tmp_path, claim_tokens=claim_tokens)
    client, token = _item()
    before = _snapshot(client=client)
    _lose_the_token(client=client, token=token, monkeypatch=monkeypatch)

    assert _claim(repo=repo, intent="regrade:close").hold() == refusal
    assert _snapshot(client=client) == before


def test_a_guarded_write_to_an_item_naming_no_token_is_refused_and_not_written_blind(
    tmp_path: Path,
) -> None:
    repo = _repo(tmp_path=tmp_path, claim_tokens=True)
    client, _ = _item(name_a_token=False)
    before = _snapshot(client=client)

    refusal = _move(claim=_claim(repo=repo), calls=[], reconcile=True)

    assert refusal == "claim-token-missing"
    assert _snapshot(client=client) == before


@dataclass(kw_only=True)
class _Time:
    """A clock a case owns, on which only its own `sleep` makes time pass.

    `longest_sleep` is how long one sleep really lasts, whatever it was asked
    for. `during` runs inside each sleep, for what another writer does
    while this one waits.
    """

    now: float = 1000.0
    longest_sleep: float = 180.0
    during: Callable[[], None] | None = None
    slept: list[float] = field(default_factory=list)

    def clock(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.slept.append(seconds)
        passed = min(seconds, self.longest_sleep)
        self.now += passed
        for observation in TRANSITION_OBSERVATIONS:
            TRANSITION_OBSERVATIONS[observation] -= passed
        if self.during is not None:
            self.during()

    def wait(self) -> TakeoverWait:
        return TakeoverWait(clock=self.clock, sleep=self.sleep)


def _strand_a_transition(
    *, client: FakeBeadsClient, repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A first writer wins the item's current token, and its item write then fails.

    The item is left naming a closed token whose close reason names a
    successor the item does not name: the transition is unapplied.
    """
    real = client.update_issue

    def _failing_on_the_item(**fields: object) -> None:
        if fields["issue_id"] == _ITEM_ID:
            raise BeadsCommandError(command="bd update", exit_code=1, stderr="server gone")
        real(**fields)

    with monkeypatch.context() as patched:
        patched.setattr(client, "update_issue", _failing_on_the_item)
        with pytest.raises(BeadsCommandError):
            _ = _move(claim=_claim(repo=repo, intent="move:backlog"), calls=[], reconcile=False)


def _named(*, client: FakeBeadsClient) -> str:
    return client.show_issue(issue_id=_ITEM_ID)["metadata"][CLAIM_TOKEN_METADATA_KEY]


def _stranded_successor(*, client: FakeBeadsClient) -> str:
    """The successor the item's closed current token was won with."""
    reason = client.show_issue(issue_id=_named(client=client))["close_reason"]
    return json.loads(reason)["successor"]


def test_a_write_that_meets_an_unapplied_transition_waits_it_out_and_takes_it_over(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """One process observes the transition, waits the takeover wait, and writes.

    Without the wait a one-shot writer could never write this item again: each
    process starts with no observation and reports the transition pending.
    """
    repo = _repo(tmp_path=tmp_path, claim_tokens=True)
    client, token = _item()
    _strand_a_transition(client=client, repo=repo, monkeypatch=monkeypatch)
    stranded = _stranded_successor(client=client)
    reconciled = _reconciled(monkeypatch=monkeypatch)
    clock = _Time()
    journal = _Journal()

    refusal = _move(
        claim=_claim(repo=repo, journal=journal, takeover_wait=clock.wait()),
        calls=[],
        reconcile=True,
    )

    record = client.show_issue(issue_id=_ITEM_ID)
    took_over = json.loads(client.show_issue(issue_id=stranded)["close_reason"])
    assert refusal is None
    assert clock.slept == [180.0]
    assert _named(client=client) not in (token, stranded)
    assert (took_over["writer"], took_over["intent"]) == (WRITER_HUMAN_VALVE, "move:ready")
    assert took_over["successor"] == _named(client=client)
    assert (record["status"], record["assignee"]) == ("ready", None)
    assert reconciled == [(_ITEM_ID, "ready")]
    assert journal.records == []
    notice = capsys.readouterr().err
    assert notice.startswith(f"NOTICE: work-item {_ITEM_ID} names a claim token")
    assert "human-valve (move:ready) found claim-transition-pending" in notice
    assert "Waiting 180 seconds" in notice


def test_a_wait_that_ends_on_another_unapplied_transition_is_final_and_is_not_waited_again(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The write is made twice at most: the second answer is the one reported.

    While this writer waits, the first winner's item write lands after all,
    and a third writer wins the successor it named and fails in its turn.
    """
    repo = _repo(tmp_path=tmp_path, claim_tokens=True)
    client, _ = _item()
    _strand_a_transition(client=client, repo=repo, monkeypatch=monkeypatch)
    stranded = _stranded_successor(client=client)

    def _lands_and_strands_again() -> None:
        client.update_issue(
            issue_id=_ITEM_ID,
            metadata={CLAIM_TOKEN_METADATA_KEY: stranded},
            names_claim_token=True,
        )
        _strand_a_transition(client=client, repo=repo, monkeypatch=monkeypatch)

    clock = _Time(during=_lands_and_strands_again)
    journal = _Journal()
    reconciled = _reconciled(monkeypatch=monkeypatch)

    refusal = _move(
        claim=_claim(repo=repo, journal=journal, takeover_wait=clock.wait()),
        calls=[],
        reconcile=True,
    )

    record = client.show_issue(issue_id=_ITEM_ID)
    assert refusal == "claim-transition-pending"
    assert clock.slept == [180.0]
    assert (record["status"], _named(client=client)) == ("blocked", stranded)
    assert reconciled == []
    assert [entry["reason"] for entry in journal.records] == ["claim-transition-pending"]


def test_nothing_waits_while_the_key_is_false(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Before the cutover the unguarded writer runs at once, whatever the item names."""
    client, _ = _item()
    _strand_a_transition(
        client=client, repo=_repo(tmp_path=tmp_path, claim_tokens=True), monkeypatch=monkeypatch
    )
    repo = _repo(tmp_path=tmp_path, claim_tokens=False)
    clock = _Time()
    calls: list[str] = []

    refusal = _move(
        claim=_claim(repo=repo, takeover_wait=clock.wait()), calls=calls, reconcile=True
    )

    assert refusal is None
    assert calls == ["unguarded"]
    assert clock.slept == []
    assert capsys.readouterr().err == ""


def test_the_default_takeover_wait_is_the_protocols_180_seconds_on_the_real_clock() -> None:
    """`contracts.md`, "Claim tokens", step 5: "at least 180 seconds of elapsed time"."""
    wait = TakeoverWait()

    assert (wait.seconds, wait.clock, wait.sleep) == (180.0, time.monotonic, time.sleep)
    assert _claim(repo=None).takeover_wait is None


def test_a_sleep_that_returns_early_is_slept_again_until_the_whole_wait_has_passed() -> None:
    clock = _Time(longest_sleep=100.0)

    clock.wait().wait_out()

    assert clock.slept == [180.0, 80.0]
    assert clock.now == 1180.0


def test_a_refusal_after_a_side_effect_says_what_stands_and_what_was_not_written() -> None:
    """A valve that reverted, answered or rewrote before its write did not write nothing."""
    refusal = valve_claim_refusal(
        aid=f"reject:{_ITEM_ID}:regroom",
        wid=_ITEM_ID,
        verb="reject",
        outcome="claim-changed",
        already_done="the merged change was already reverted",
    )

    assert refusal["domain_error"] == "claim-changed"
    assert refusal["summary"] == (
        "reject refused: the claim-token protocol reported claim-changed; "
        "the merged change was already reverted; "
        f"the status and claim of {_ITEM_ID} were not written."
    )
    assert "nothing was written" not in refusal["summary"]


def test_a_refusal_that_is_still_pending_says_the_press_already_waited() -> None:
    refusal = valve_claim_refusal(
        aid=f"move:{_ITEM_ID}:ready", wid=_ITEM_ID, verb="move", outcome="claim-transition-pending"
    )

    assert refusal["summary"] == (
        "move refused: the claim-token protocol reported claim-transition-pending, "
        "after this press waited out the takeover wait and tried once more; "
        f"nothing was written to {_ITEM_ID}. "
        f"Remedy: wait for or trigger a Dispatcher pass on {_ITEM_ID}. A Dispatcher loop keeps "
        "its first sighting of an unapplied transition from one pass to the next, and takes the "
        "transition over on a pass made after the takeover wait."
    )


def test_a_refused_valve_reports_the_protocols_outcome_as_its_domain_error() -> None:
    assert valve_claim_refusal(
        aid=f"move:{_ITEM_ID}:ready", wid=_ITEM_ID, verb="move", outcome="claim-changed"
    ) == {
        "action_id": f"move:{_ITEM_ID}:ready",
        "kind": "human-valve",
        "status": "failed",
        "domain_error": "claim-changed",
        "summary": (
            "move refused: the claim-token protocol reported claim-changed; "
            f"nothing was written to {_ITEM_ID}."
        ),
        "work_item_ref": _ITEM_ID,
    }


def test_an_intake_refusal_names_the_item_the_writer_its_intent_and_the_outcome() -> None:
    refused = _claim(repo=None, writer=WRITER_INTAKE, intent="route:ready").refused(
        outcome="claim-changed"
    )

    assert refused == ClaimWriteRefused(
        work_item_id=_ITEM_ID, writer="intake", intent="route:ready", outcome="claim-changed"
    )
    assert (WRITER_INTAKE, WRITER_HUMAN_VALVE) == ("intake", "human-valve")


def test_an_intake_refusal_prints_as_a_sentence_and_names_the_remedy_only_when_pending() -> None:
    """`str` of the refusal is what a caller prints, in the valve refusal's own wording."""
    lost = _claim(repo=None, writer=WRITER_INTAKE, intent="route:ready").refused(
        outcome="claim-changed"
    )
    pending = _claim(repo=None, writer=WRITER_INTAKE, intent="route:backlog").refused(
        outcome="claim-transition-pending"
    )

    assert str(lost) == (
        "intake (route:ready) refused: the claim-token protocol reported claim-changed; "
        f"the status and claim of {_ITEM_ID} were not written."
    )
    assert str(pending) == (
        "intake (route:backlog) refused: the claim-token protocol reported "
        "claim-transition-pending, after this call waited out the takeover wait and tried "
        f"once more; the status and claim of {_ITEM_ID} were not written. "
        f"Remedy: wait for or trigger a Dispatcher pass on {_ITEM_ID}. A Dispatcher loop keeps "
        "its first sighting of an unapplied transition from one pass to the next, and takes the "
        "transition over on a pass made after the takeover wait."
    )
