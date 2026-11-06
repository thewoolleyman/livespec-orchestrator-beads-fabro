"""A stranded-claim recovery and a human valve on one active claim.

`SPECIFICATION/scenarios.md` Scenario 263, "Two hosts race to change one active
claim": "a recovery on host A and a resolve-blocked valve on host B both read
the item ... exactly one close reason is recorded on T ... only the writer whose
reason was recorded writes to the item, naming its successor token ... the other
writes nothing, discards its own successor and reports claim-changed".

Both writers here are the real ones. The recovery is `recover_claim`, with its
lock, its re-reads and its ordered effects. The valves are `resolve_blocked_item`
and `move_item`, each handed the item as it read it.

WHAT A `resolve-blocked` PRESS CAN AND CANNOT DO TO AN ACTIVE CLAIM. The valve
acts on an item it read as `blocked / needs-human`, and its write states that:
it is made only while the item still rests there. A claim the recovery acts on
is `active`. So a press whose read predates the claim never contests the token
at all, in any order: it reports `claim-changed`, closes nothing, and the
recovery is the only writer. The first three cases bind that, with the valve
pressed while the recovery is in flight, after it, and before it.

THE TWO-CLOSER RACE IS RUN WITH `move`, the valve that does act on an `active`
item. There both writers read the same open token and both close it; each case
starts one and, at the instant it closes the token, runs the other to
completion, so the second one's close is the one the ledger records. The loser
discards its own successor. The last case is the same pair without overlap: the
`move` decided on the active item, the recovery finished, and the `move` then
wrote nothing.

"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro._beads_client import (
    FakeBeadsClient,
    make_beads_client,
    reset_fake_singleton,
)
from livespec_orchestrator_beads_fabro._store_dispatch_claim import (
    CLAIM_TOKEN_METADATA_KEY,
    ClaimStamp,
    create_claim_token,
    record_claim_stamp,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_claim_guard import (
    TRANSITION_OBSERVATIONS,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import JournalFile
from livespec_orchestrator_beads_fabro.commands._dispatcher_stranded_claim_recovery import (
    ClaimRecoveryRequest,
    recover_claim,
)
from livespec_orchestrator_beads_fabro.commands._drive_policy_valves import (
    move_item,
    resolve_blocked_item,
)
from livespec_orchestrator_beads_fabro.store import append_work_item
from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem

_ITEM_ID = "bd-ib-claimrace"
_RUN_ID = "01STRANDEDRACERUN"
_DISPATCH_ID = "01DISPATCHRACE"
_FACTORY = "hp"
_SERVER = "https://hp.example:32276"


@pytest.fixture(autouse=True)
def _fresh_tenant(monkeypatch: pytest.MonkeyPatch) -> object:
    monkeypatch.setenv("LIVESPEC_BEADS_FAKE", "1")
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


def _repo(*, tmp_path: Path) -> Path:
    """A repository whose committed configuration has cut over to claim tokens."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _ = (repo / ".livespec.jsonc").write_text(
        '{"livespec-orchestrator-beads-fabro": {"connection": {"prefix": "bd-ib"}, '
        '"dispatcher": {"claim_tokens": true}}}',
        encoding="utf-8",
    )
    return repo


def _journal(*, repo: Path) -> JournalFile:
    """A journal carrying this item's one launch: a confirmed first dispatch."""
    path = repo / "tmp" / "journal.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    _ = path.write_text(
        "".join(
            f"{json.dumps(record)}\n"
            for record in (
                {"stage": "dispatch-id", "work_item_id": _ITEM_ID, "dispatch_id": _DISPATCH_ID},
                {"stage": "dispatch-run-stamp", "work_item_id": _ITEM_ID, "run_id": _RUN_ID},
            )
        ),
        encoding="utf-8",
    )
    return JournalFile(path=path)


def _seed() -> tuple[WorkItem, FakeBeadsClient, str]:
    """The active claim: assigned `fabro`, stamped with its run, naming an open token."""
    item = WorkItem(
        id=_ITEM_ID,
        type="bug",
        status="active",
        title="A dispatched slice whose run vanished",
        description="Implement the slice.",
        origin="freeform",
        gap_id=None,
        rank="a0",
        assignee="fabro",
        depends_on=(),
        captured_at="2026-11-06T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
        admission_policy="auto",
        acceptance_policy="ai-only",
        acceptance_criteria="The dispatched slice is verified green by the check suite.",
    )
    append_work_item(path=_config(), item=item)
    record_claim_stamp(
        path=_config(),
        work_item_id=_ITEM_ID,
        stamp=ClaimStamp(
            dispatch_id=_DISPATCH_ID,
            dispatching_host="owning-host",
            run_id=_RUN_ID,
            factory_name=_FACTORY,
            factory_server=_SERVER,
        ),
    )
    client = make_beads_client(config=_config())
    assert isinstance(client, FakeBeadsClient)
    token = create_claim_token(client=client)
    metadata = dict(client.show_issue(issue_id=_ITEM_ID)["metadata"])
    metadata[CLAIM_TOKEN_METADATA_KEY] = token
    client.update_issue(issue_id=_ITEM_ID, metadata=metadata, names_claim_token=True)
    return item, client, token


def _recover(*, repo: Path, item: WorkItem) -> object:
    """Host A: release the claim of a run the factory reports absent."""
    return recover_claim(
        repo=repo,
        journal=_journal(repo=repo),
        request=ClaimRecoveryRequest(
            item=item,
            run_id=_RUN_ID,
            factory_name=_FACTORY,
            factory_server_url=_SERVER,
            action="absent-run-release",
            predecessor_run_id="01PREVIOUSRUN",
        ),
        now_iso="2026-11-06T09:00:00Z",
    )


def _resolve(*, repo: Path, item: WorkItem) -> dict[str, object]:
    """Host B: the valve, pressed on the item as it read it before the claim."""
    return resolve_blocked_item(
        config=_config(repo_root=repo),
        item=replace(item, status="blocked", blocked_reason="needs-human"),
        aid=f"resolve-blocked:{_ITEM_ID}:ready",
        target_status="ready",
    )


def _move(*, repo: Path, item: WorkItem) -> dict[str, object]:
    """Host B: a `move` to `ready`, pressed on the active item as it read it."""
    return move_item(
        config=_config(repo_root=repo),
        item=item,
        aid=f"move:{_ITEM_ID}:ready",
        target_status="ready",
    )


def _race(
    *,
    client: FakeBeadsClient,
    token: str,
    rival: Callable[[], object],
    monkeypatch: pytest.MonkeyPatch,
) -> list[object]:
    """Run `rival` to completion at the instant the first writer closes `token`."""
    close = client.close_issue_without_verdict
    finished: list[object] = []
    started: list[str] = []

    def _closing(*, issue_id: str, reason: str) -> None:
        if issue_id == token and not started:
            started.append(issue_id)
            finished.append(rival())
        close(issue_id=issue_id, reason=reason)

    monkeypatch.setattr(client, "close_issue_without_verdict", _closing)
    return finished


def _observe(
    *, client: FakeBeadsClient, monkeypatch: pytest.MonkeyPatch
) -> tuple[list[str], list[str]]:
    """The successors minted and the status writes sent to the item, as they happen."""
    mint = client.create_no_history_issue
    update = client.update_issue
    minted: list[str] = []
    writes: list[str] = []

    def _minting(*, title: str, description: str) -> str:
        minted.append(mint(title=title, description=description))
        return minted[-1]

    def _updating(**fields: object) -> None:
        if fields["issue_id"] == _ITEM_ID and fields.get("status") is not None:
            writes.append(str(fields["status"]))
        update(**fields)

    monkeypatch.setattr(client, "create_no_history_issue", _minting)
    monkeypatch.setattr(client, "update_issue", _updating)
    return minted, writes


def _reason(*, client: FakeBeadsClient, token: str) -> dict[str, str]:
    """The recorded close reason of a token that a claim writer closed."""
    record = client.show_issue(issue_id=token)
    assert record["status"] == "closed", "no writer closed this token"
    return json.loads(record["close_reason"])


def _held(*, outcome: object) -> object:
    return getattr(outcome, "hold_reason", None)


def _named(*, client: FakeBeadsClient) -> str:
    return client.show_issue(issue_id=_ITEM_ID)["metadata"][CLAIM_TOKEN_METADATA_KEY]


def _is_open(*, client: FakeBeadsClient, token: str) -> bool:
    return client.show_issue(issue_id=token)["status"] != "closed"


def test_a_resolve_blocked_pressed_while_the_recovery_is_in_flight_writes_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """DoD 4: the recovery's reason is the one recorded, so the recovery alone writes."""
    repo = _repo(tmp_path=tmp_path)
    item, client, token = _seed()
    minted, writes = _observe(client=client, monkeypatch=monkeypatch)
    resolved = _race(
        client=client,
        token=token,
        rival=lambda: _resolve(repo=repo, item=item),
        monkeypatch=monkeypatch,
    )

    outcome = _recover(repo=repo, item=item)

    won = _reason(client=client, token=token)
    record = client.show_issue(issue_id=_ITEM_ID)
    assert _held(outcome=outcome) is None
    assert [(press["status"], press["domain_error"]) for press in resolved] == [
        ("failed", "claim-changed")
    ]
    assert (won["writer"], won["intent"]) == ("stranded-claim-recovery", "absent-run-release")
    assert won["successor"] == _named(client=client)
    assert (record["status"], record["assignee"]) == ("ready", None)
    assert writes == ["ready"]
    # The valve never contested the token: the only successor minted is the recovery's.
    assert minted == [_named(client=client)]


def test_a_resolve_blocked_pressed_after_the_recovery_finished_writes_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """DoD 4, sequential: the item still names the recovery's successor, still open."""
    repo = _repo(tmp_path=tmp_path)
    item, client, token = _seed()
    minted, writes = _observe(client=client, monkeypatch=monkeypatch)
    outcome = _recover(repo=repo, item=item)

    resolved = _resolve(repo=repo, item=item)

    won = _reason(client=client, token=token)
    assert _held(outcome=outcome) is None
    assert (resolved["status"], resolved["domain_error"]) == ("failed", "claim-changed")
    assert won["writer"] == "stranded-claim-recovery"
    assert minted == [won["successor"]] == [_named(client=client)]
    assert _is_open(client=client, token=won["successor"])
    assert writes == ["ready"]


def test_a_resolve_blocked_pressed_before_the_recovery_leaves_the_claim_to_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """DoD 4, the other order: the refused press closed nothing, so the recovery still wins."""
    repo = _repo(tmp_path=tmp_path)
    item, client, token = _seed()
    minted, writes = _observe(client=client, monkeypatch=monkeypatch)

    resolved = _resolve(repo=repo, item=item)

    assert (resolved["status"], resolved["domain_error"]) == ("failed", "claim-changed")
    assert _is_open(client=client, token=token)
    assert (minted, writes) == ([], [])

    outcome = _recover(repo=repo, item=item)

    won = _reason(client=client, token=token)
    assert _held(outcome=outcome) is None
    assert (won["writer"], won["successor"]) == ("stranded-claim-recovery", _named(client=client))
    assert writes == ["ready"]


def test_the_recovery_and_a_move_both_close_the_token_and_the_recovery_wins(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Two closers of one open token: the recovery's reason is recorded, the move stands down."""
    repo = _repo(tmp_path=tmp_path)
    item, client, token = _seed()
    minted, writes = _observe(client=client, monkeypatch=monkeypatch)
    recovered = _race(
        client=client,
        token=token,
        rival=lambda: _recover(repo=repo, item=item),
        monkeypatch=monkeypatch,
    )

    moved = _move(repo=repo, item=item)

    won = _reason(client=client, token=token)
    [discarded] = [successor for successor in minted if successor != _named(client=client)]
    assert [_held(outcome=outcome) for outcome in recovered] == [None]
    assert (moved["status"], moved["domain_error"]) == ("failed", "claim-changed")
    assert (won["writer"], won["intent"]) == ("stranded-claim-recovery", "absent-run-release")
    assert won["successor"] == _named(client=client)
    assert writes == ["ready"]
    assert _reason(client=client, token=discarded)["kind"] == "claim-token-discard"


def test_the_recovery_and_a_move_both_close_the_token_and_the_move_wins(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The other way round: the move's reason is recorded, the recovery is held."""
    repo = _repo(tmp_path=tmp_path)
    item, client, token = _seed()
    minted, writes = _observe(client=client, monkeypatch=monkeypatch)
    moved = _race(
        client=client,
        token=token,
        rival=lambda: _move(repo=repo, item=item),
        monkeypatch=monkeypatch,
    )

    outcome = _recover(repo=repo, item=item)

    won = _reason(client=client, token=token)
    [discarded] = [successor for successor in minted if successor != _named(client=client)]
    assert [press["status"] for press in moved] == ["green"]
    assert _held(outcome=outcome) == "claim-changed"
    assert (won["writer"], won["intent"]) == ("human-valve", "move:ready")
    assert won["successor"] == _named(client=client)
    assert writes == ["ready"]
    assert _reason(client=client, token=discarded)["kind"] == "claim-token-discard"


def test_a_move_decided_before_the_recovery_finished_writes_nothing_after_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """No overlap: the move read the active item, the recovery released it, then the move wrote."""
    repo = _repo(tmp_path=tmp_path)
    item, client, token = _seed()
    minted, writes = _observe(client=client, monkeypatch=monkeypatch)
    outcome = _recover(repo=repo, item=item)

    moved = _move(repo=repo, item=item)

    won = _reason(client=client, token=token)
    assert _held(outcome=outcome) is None
    assert (moved["status"], moved["domain_error"]) == ("failed", "claim-changed")
    assert won["writer"] == "stranded-claim-recovery"
    assert minted == [won["successor"]] == [_named(client=client)]
    assert _is_open(client=client, token=won["successor"])
    assert writes == ["ready"]
