"""Which of two ways a Dispatcher claim write is made, and what a refusal is.

`_dispatcher_claim_writes` is the one place the Dispatcher's claim writers
(admission, a terminal write, a recovery effect) decide whether a write is
token-guarded. The committed key `dispatcher.claim_tokens` selects:

- `false` or unset: the caller's own store writer, called with exactly the
  arguments that caller passed before this module existed. These cases record
  the call and assert its keyword arguments, because "no behaviour change
  before the cutover" is a statement about that call.
- `true`: one token-guarded write against the tenant, asserted on what the
  tenant then holds.
- unreadable: no write at all, reported as `claim-tokens-unreadable`.

A refusal is a return value. It is journaled once as `claim-write-refused`,
and a caller that passed no journal still gets the outcome back.
"""

from __future__ import annotations

import copy
import json
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
from livespec_orchestrator_beads_fabro.commands._dispatcher_claim_guard import (
    TRANSITION_OBSERVATIONS,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_claim_writes import (
    CLAIM_TOKENS_UNREADABLE,
    CLAIM_WRITE_REFUSED_STAGE,
    LEDGER_WRITE_ERRORS,
    WRITER_ADMISSION,
    WRITER_RECOVERY,
    WRITER_RUN_STAMP,
    WRITER_TERMINAL,
    claim_blocked_write,
    claim_hold,
    claim_stamp_write,
    claim_status_write,
    claim_tokens_setting,
    settle_claim_write,
)
from livespec_orchestrator_beads_fabro.errors import (
    BeadsCommandError,
    BeadsConnectionError,
    BeadsMappingError,
    BeadsTenantMissingError,
    WorkItemNotFoundError,
)
from livespec_orchestrator_beads_fabro.types import StoreConfig

_ITEM_ID = "bd-ib-claimwrite"
_PLUGIN_BLOCK = "livespec-orchestrator-beads-fabro"
_ANOTHER_WRITER = "another writer won this token"


@pytest.fixture(autouse=True)
def _fresh_tenant() -> object:
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


def _repo(*, tmp_path: Path, config_text: str | None) -> Path:
    """A repository whose committed `.livespec.jsonc` is `config_text`, or absent."""
    if config_text is not None:
        _ = (tmp_path / ".livespec.jsonc").write_text(config_text, encoding="utf-8")
    return tmp_path


def _enabled(*, tmp_path: Path) -> Path:
    return _repo(
        tmp_path=tmp_path,
        config_text=json.dumps({_PLUGIN_BLOCK: {"dispatcher": {"claim_tokens": True}}}),
    )


def _disabled(*, tmp_path: Path) -> Path:
    return _repo(tmp_path=tmp_path, config_text=None)


def _unreadable(*, tmp_path: Path) -> Path:
    return _repo(tmp_path=tmp_path, config_text="{ this is not jsonc")


def _claim() -> tuple[FakeBeadsClient, str]:
    """An `active` item assigned `fabro` that names an open current token."""
    client = make_beads_client(config=_config())
    assert isinstance(client, FakeBeadsClient)
    _ = client.create_issue(
        draft=IssueDraft(
            issue_id=_ITEM_ID,
            issue_type="task",
            title="A dispatched slice",
            description="Implement the slice.",
            assignee="fabro",
            created_at="2026-11-06T00:00:00Z",
        )
    )
    token = create_claim_token(client=client)
    client.update_issue(
        issue_id=_ITEM_ID, status="active", metadata={CLAIM_TOKEN_METADATA_KEY: token}
    )
    return client, token


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


class _Journal:
    """A journal that keeps what it was handed."""

    def __init__(self) -> None:
        self.records: list[dict[str, object]] = []

    def append(self, *, record: dict[str, object]) -> None:
        self.records.append(record)


class _Recorder:
    """A store writer or hook that records the keyword arguments of each call."""

    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def __call__(self, **kwargs: object) -> None:
        self.calls.append(kwargs)


def test_the_shared_ledger_fault_tuple_names_the_five_store_write_faults() -> None:
    assert set(LEDGER_WRITE_ERRORS) == {
        WorkItemNotFoundError,
        BeadsCommandError,
        BeadsConnectionError,
        BeadsMappingError,
        BeadsTenantMissingError,
    }


def test_the_four_writer_names_are_distinct() -> None:
    writers = {WRITER_ADMISSION, WRITER_TERMINAL, WRITER_RECOVERY, WRITER_RUN_STAMP}

    # One name per writer the module knows.
    assert len(writers) == 4


def test_the_setting_is_false_when_the_file_or_the_key_is_absent(tmp_path: Path) -> None:
    assert claim_tokens_setting(repo=_disabled(tmp_path=tmp_path)) is False
    keyless = tmp_path / "keyless"
    keyless.mkdir()
    _ = (keyless / ".livespec.jsonc").write_text(
        json.dumps({_PLUGIN_BLOCK: {"dispatcher": {"wip_cap": 2}}}), encoding="utf-8"
    )
    assert claim_tokens_setting(repo=keyless) is False


def test_the_setting_is_true_only_when_committed_true(tmp_path: Path) -> None:
    assert claim_tokens_setting(repo=_enabled(tmp_path=tmp_path)) is True


def test_the_setting_is_none_when_the_file_cannot_be_read(tmp_path: Path) -> None:
    assert claim_tokens_setting(repo=_unreadable(tmp_path=tmp_path)) is None


def test_a_disabled_key_runs_the_unguarded_writer_and_never_the_guarded_one(
    tmp_path: Path,
) -> None:
    ran: list[str] = []
    journal = _Journal()

    refusal = settle_claim_write(
        repo=_disabled(tmp_path=tmp_path),
        item_id=_ITEM_ID,
        writer=WRITER_TERMINAL,
        intent="any",
        unguarded=lambda: ran.append("unguarded"),
        guarded=lambda: pytest.fail("the guarded writer ran before the cutover"),
        journal=journal,
    )

    assert refusal is None
    assert ran == ["unguarded"]
    assert journal.records == []


def test_an_enabled_key_runs_the_guarded_writer_and_never_the_unguarded_one(
    tmp_path: Path,
) -> None:
    journal = _Journal()

    refusal = settle_claim_write(
        repo=_enabled(tmp_path=tmp_path),
        item_id=_ITEM_ID,
        writer=WRITER_TERMINAL,
        intent="any",
        unguarded=lambda: pytest.fail("the unguarded writer ran after the cutover"),
        guarded=lambda: None,
        journal=journal,
    )

    assert refusal is None
    assert journal.records == []


def test_a_refused_guarded_write_is_returned_and_journaled_once(tmp_path: Path) -> None:
    journal = _Journal()

    refusal = settle_claim_write(
        repo=_enabled(tmp_path=tmp_path),
        item_id=_ITEM_ID,
        writer=WRITER_RECOVERY,
        intent="absent-run-release",
        unguarded=lambda: pytest.fail("the unguarded writer ran after the cutover"),
        guarded=lambda: "claim-changed",
        journal=journal,
    )

    assert refusal == "claim-changed"
    assert journal.records == [
        {
            "stage": CLAIM_WRITE_REFUSED_STAGE,
            "work_item_id": _ITEM_ID,
            "writer": WRITER_RECOVERY,
            "intent": "absent-run-release",
            "reason": "claim-changed",
        }
    ]


def test_a_refusal_with_no_journal_is_still_returned(tmp_path: Path) -> None:
    refusal = settle_claim_write(
        repo=_enabled(tmp_path=tmp_path),
        item_id=_ITEM_ID,
        writer=WRITER_RECOVERY,
        intent="absent-run-release",
        unguarded=lambda: pytest.fail("the unguarded writer ran after the cutover"),
        guarded=lambda: "claim-unobservable",
    )

    assert refusal == "claim-unobservable"


def test_an_unreadable_key_runs_neither_writer_and_refuses(tmp_path: Path) -> None:
    journal = _Journal()

    refusal = settle_claim_write(
        repo=_unreadable(tmp_path=tmp_path),
        item_id=_ITEM_ID,
        writer=WRITER_ADMISSION,
        intent="admit",
        unguarded=lambda: pytest.fail("a write was made on a key that could not be read"),
        guarded=lambda: pytest.fail("a write was made on a key that could not be read"),
        journal=journal,
    )

    assert refusal == CLAIM_TOKENS_UNREADABLE
    assert [record["reason"] for record in journal.records] == [CLAIM_TOKENS_UNREADABLE]


@pytest.mark.parametrize(
    ("optional", "expected"),
    [
        ({}, {}),
        ({"assignee": "fabro"}, {"assignee": "fabro"}),
        ({"clear_assignee": True}, {"clear_assignee": True}),
    ],
)
def test_a_disabled_status_write_calls_the_callers_writer_with_only_what_it_set(
    tmp_path: Path, optional: dict[str, object], expected: dict[str, object]
) -> None:
    write = _Recorder()
    reconcile = _Recorder()

    refusal = claim_status_write(
        repo=_disabled(tmp_path=tmp_path),
        path=_config(),
        intent="any",
        write=write,
        item_id=_ITEM_ID,
        status="ready",
        reconcile=reconcile,
        **optional,
    )

    assert refusal is None
    assert write.calls == [{"path": _config(), "item_id": _ITEM_ID, "status": "ready", **expected}]
    # The caller's own writer reconciles for itself; the hook is the guarded path's.
    assert reconcile.calls == []


def test_an_enabled_status_write_wins_the_token_then_runs_the_reconcile_hook(
    tmp_path: Path,
) -> None:
    client, token = _claim()
    reconcile = _Recorder()

    refusal = claim_status_write(
        repo=_enabled(tmp_path=tmp_path),
        path=_config(),
        intent="complete",
        write=lambda **_: pytest.fail("the unguarded writer ran after the cutover"),
        item_id=_ITEM_ID,
        status="acceptance",
        reconcile=reconcile,
    )

    assert refusal is None
    assert client.show_issue(issue_id=_ITEM_ID)["status"] == "acceptance"
    assert _won(client=client, token=token) == (WRITER_TERMINAL, "complete", True)
    assert reconcile.calls == [{"path": _config(), "item_id": _ITEM_ID, "status": "acceptance"}]


def test_an_enabled_status_write_with_no_hook_just_lands(tmp_path: Path) -> None:
    client, token = _claim()

    refusal = claim_status_write(
        repo=_enabled(tmp_path=tmp_path),
        path=_config(),
        intent="pre-run-release",
        write=lambda **_: pytest.fail("the unguarded writer ran after the cutover"),
        item_id=_ITEM_ID,
        status="ready",
        clear_assignee=True,
        writer=WRITER_RECOVERY,
    )

    record = client.show_issue(issue_id=_ITEM_ID)
    assert refusal is None
    assert (record["status"], record["assignee"]) == ("ready", None)
    assert _won(client=client, token=token) == (WRITER_RECOVERY, "pre-run-release", True)


def test_a_refused_status_write_runs_no_reconcile_hook_and_writes_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client, token = _claim()
    before = _snapshot(client=client)
    _lose_the_token(client=client, token=token, monkeypatch=monkeypatch)
    reconcile = _Recorder()
    journal = _Journal()

    refusal = claim_status_write(
        repo=_enabled(tmp_path=tmp_path),
        path=_config(),
        intent="complete",
        write=lambda **_: pytest.fail("the unguarded writer ran after the cutover"),
        item_id=_ITEM_ID,
        status="acceptance",
        reconcile=reconcile,
        journal=journal,
    )

    assert refusal == "claim-changed"
    assert _snapshot(client=client) == before
    assert reconcile.calls == []
    assert [(record["stage"], record["intent"]) for record in journal.records] == [
        (CLAIM_WRITE_REFUSED_STAGE, "complete")
    ]


@pytest.mark.parametrize(
    ("optional", "expected"),
    [({}, {}), ({"admission_policy": "manual"}, {"admission_policy": "manual"})],
)
def test_a_disabled_blocked_write_calls_the_callers_writer_with_only_what_it_set(
    tmp_path: Path, optional: dict[str, object], expected: dict[str, object]
) -> None:
    write = _Recorder()

    refusal = claim_blocked_write(
        repo=_disabled(tmp_path=tmp_path),
        path=_config(),
        intent="any",
        write=write,
        item_id=_ITEM_ID,
        blocked_reason="needs-human",
        **optional,
    )

    assert refusal is None
    assert write.calls == [
        {
            "path": _config(),
            "item_id": _ITEM_ID,
            "status": "blocked",
            "blocked_reason": "needs-human",
            **expected,
        }
    ]


def test_an_enabled_blocked_write_rests_the_item_under_the_won_token(tmp_path: Path) -> None:
    client, token = _claim()

    refusal = claim_blocked_write(
        repo=_enabled(tmp_path=tmp_path),
        path=_config(),
        intent="needs-human-block",
        write=lambda **_: pytest.fail("the unguarded writer ran after the cutover"),
        item_id=_ITEM_ID,
        blocked_reason="needs-human",
        admission_policy="manual",
    )

    record = client.show_issue(issue_id=_ITEM_ID)
    assert refusal is None
    assert record["status"] == "blocked"
    assert sorted(record["labels"]) == ["admission:manual", "blocked-reason:needs-human"]
    assert _won(client=client, token=token) == (WRITER_TERMINAL, "needs-human-block", True)


def test_a_refused_blocked_write_writes_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client, token = _claim()
    before = _snapshot(client=client)
    _lose_the_token(client=client, token=token, monkeypatch=monkeypatch)

    refusal = claim_blocked_write(
        repo=_enabled(tmp_path=tmp_path),
        path=_config(),
        intent="needs-human-block",
        write=lambda **_: pytest.fail("the unguarded writer ran after the cutover"),
        item_id=_ITEM_ID,
        blocked_reason="needs-human",
    )

    assert refusal == "claim-changed"
    assert _snapshot(client=client) == before


def test_a_disabled_hold_writes_nothing_at_all(tmp_path: Path) -> None:
    client, token = _claim()
    before = _snapshot(client=client)

    refusal = claim_hold(
        repo=_disabled(tmp_path=tmp_path), path=_config(), intent="close", item_id=_ITEM_ID
    )

    assert refusal is None
    assert _snapshot(client=client) == before
    assert client.show_issue(issue_id=token)["status"] != "closed"


def test_an_enabled_hold_wins_the_token_and_names_the_successor(tmp_path: Path) -> None:
    client, token = _claim()

    refusal = claim_hold(
        repo=_enabled(tmp_path=tmp_path), path=_config(), intent="close", item_id=_ITEM_ID
    )

    assert refusal is None
    assert client.show_issue(issue_id=_ITEM_ID)["status"] == "active"
    assert _won(client=client, token=token) == (WRITER_TERMINAL, "close", True)


def test_a_refused_hold_names_no_successor(tmp_path: Path) -> None:
    """An item with no current token is refused, so its close never starts."""
    client, _ = _claim()
    client.update_issue(issue_id=_ITEM_ID, metadata={})
    journal = _Journal()

    refusal = claim_hold(
        repo=_enabled(tmp_path=tmp_path),
        path=_config(),
        intent="close",
        item_id=_ITEM_ID,
        journal=journal,
    )

    assert refusal == "claim-token-missing"
    assert client.show_issue(issue_id=_ITEM_ID)["metadata"] == {}
    assert [record["reason"] for record in journal.records] == ["claim-token-missing"]


def test_a_disabled_stamp_write_is_the_callers_own_write_and_touches_no_token(
    tmp_path: Path,
) -> None:
    client, token = _claim()
    before = _snapshot(client=client)
    ran: list[str] = []

    refusal = claim_stamp_write(
        repo=_disabled(tmp_path=tmp_path),
        path=_config(),
        intent="run-stamp",
        write=lambda: ran.append("the caller's stamp write"),
        item_id=_ITEM_ID,
        metadata={"dispatch_fabro_run_id": "01RUN"},
    )

    assert refusal is None
    assert ran == ["the caller's stamp write"]
    assert _snapshot(client=client) == before
    assert client.show_issue(issue_id=token)["status"] != "closed"


def test_an_enabled_stamp_write_lands_the_overlay_under_the_won_token(tmp_path: Path) -> None:
    client, token = _claim()

    refusal = claim_stamp_write(
        repo=_enabled(tmp_path=tmp_path),
        path=_config(),
        intent="run-stamp",
        write=lambda: pytest.fail("the unguarded writer ran after the cutover"),
        item_id=_ITEM_ID,
        metadata={"dispatch_fabro_run_id": "01RUN"},
    )

    record = client.show_issue(issue_id=_ITEM_ID)
    assert refusal is None
    assert record["metadata"]["dispatch_fabro_run_id"] == "01RUN"
    assert (record["status"], record["assignee"]) == ("active", "fabro")
    assert _won(client=client, token=token) == (WRITER_RUN_STAMP, "run-stamp", True)


def test_a_refused_stamp_write_writes_nothing_and_journals_the_refusal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client, token = _claim()
    before = _snapshot(client=client)
    _lose_the_token(client=client, token=token, monkeypatch=monkeypatch)
    journal = _Journal()

    refusal = claim_stamp_write(
        repo=_enabled(tmp_path=tmp_path),
        path=_config(),
        intent="run-stamp",
        write=lambda: pytest.fail("the unguarded writer ran after the cutover"),
        item_id=_ITEM_ID,
        metadata={"dispatch_fabro_run_id": "01RUN"},
        journal=journal,
    )

    assert refusal == "claim-changed"
    assert _snapshot(client=client) == before
    assert [(record["writer"], record["intent"]) for record in journal.records] == [
        (WRITER_RUN_STAMP, "run-stamp")
    ]


def _never(_record: dict[str, object]) -> bool:
    return False


_DECIDED_WRITES: dict[str, object] = {
    "status": lambda repo: claim_status_write(
        repo=repo,
        path=_config(),
        intent="complete",
        write=lambda **_: pytest.fail("the unguarded writer ran after the cutover"),
        item_id=_ITEM_ID,
        status="acceptance",
        reconcile=lambda **_: pytest.fail("reconciled a write that never landed"),
        still_as_decided=_never,
    ),
    "blocked": lambda repo: claim_blocked_write(
        repo=repo,
        path=_config(),
        intent="needs-human-block",
        write=lambda **_: pytest.fail("the unguarded writer ran after the cutover"),
        item_id=_ITEM_ID,
        blocked_reason="needs-human",
        still_as_decided=_never,
    ),
    "hold": lambda repo: claim_hold(
        repo=repo, path=_config(), intent="close", item_id=_ITEM_ID, still_as_decided=_never
    ),
    "stamp": lambda repo: claim_stamp_write(
        repo=repo,
        path=_config(),
        intent="run-stamp",
        write=lambda: pytest.fail("the unguarded writer ran after the cutover"),
        item_id=_ITEM_ID,
        metadata={"dispatch_fabro_run_id": "01RUN"},
        still_as_decided=_never,
    ),
}


@pytest.mark.parametrize("write", sorted(_DECIDED_WRITES))
def test_every_claim_write_refuses_uncontested_when_its_decision_no_longer_holds(
    write: str, tmp_path: Path
) -> None:
    client, token = _claim()
    before = _snapshot(client=client)

    refusal = _DECIDED_WRITES[write](_enabled(tmp_path=tmp_path))

    assert refusal == "claim-changed"
    assert _snapshot(client=client) == before
    assert client.no_history_issue_ids() == (token,)
    assert client.show_issue(issue_id=token)["status"] != "closed"


def test_a_disabled_claim_write_never_asks_what_was_decided(tmp_path: Path) -> None:
    """The predicate is the guarded path's: before the cutover the caller's write is made."""
    write = _Recorder()

    refusal = claim_status_write(
        repo=_disabled(tmp_path=tmp_path),
        path=_config(),
        intent="any",
        write=write,
        item_id=_ITEM_ID,
        status="ready",
        still_as_decided=lambda _record: pytest.fail("asked before the cutover"),
    )

    assert refusal is None
    assert write.calls == [{"path": _config(), "item_id": _ITEM_ID, "status": "ready"}]
