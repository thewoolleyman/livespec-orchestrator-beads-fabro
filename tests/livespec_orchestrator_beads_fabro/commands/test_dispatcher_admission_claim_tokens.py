"""Admission and stranded-claim recovery change a claim only through its token.

`SPECIFICATION/contracts.md` ("Dispatcher policy settings" -> "Stranded claim
release" -> "Claim tokens") makes admission and a recovery effect two of the
writers of a dispatch claim. While the committed key `dispatcher.claim_tokens`
is `true`, each may change an item's status or its `fabro` assignee only after
winning the item's current claim token, and the winner names the successor
token in that one write. `SPECIFICATION/scenarios.md` Scenario 263 states the
same thing as outcomes: exactly one writer changes the claim, and every other
writer stands down having written nothing to the item.

Every case here drives a PUBLIC entry point (`admit_and_select`,
`recover_claim`) against the in-memory tenant and asserts on what the tenant
then holds: the item, the token it named before, and the token it names now.
Nothing is asserted about how the writer got there, so the cases read the same
against any implementation of the protocol.

THE DISABLED CASE IS HERE ON PURPOSE. The cutover key defaults to `false`, and
before it is committed `true` an admission must write exactly what it wrote
before the protocol existed: no token is closed and none is named.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro._beads_client import (
    FakeBeadsClient,
    make_beads_client,
    reset_fake_singleton,
)
from livespec_orchestrator_beads_fabro._store_dispatch_claim import (
    CLAIM_STAMP_METADATA_KEY,
    CLAIM_TOKEN_METADATA_KEY,
    ClaimStamp,
    create_claim_token,
    record_claim_stamp,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_admission import admit_and_select
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import JournalFile
from livespec_orchestrator_beads_fabro.commands._dispatcher_stranded_claim_recovery import (
    ClaimRecoveryRequest,
    recover_claim,
)
from livespec_orchestrator_beads_fabro.store import append_work_item
from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem, WorkItemStatus

_ITEM_ID = "bd-ib-claim"
_RUN_ID = "01STRANDEDRUN"
_NOW = "2026-11-06T09:00:00Z"
_TOKENS_ON = ', "dispatcher": {"claim_tokens": true}'
_ANOTHER_WRITER = "another writer won this token"


@pytest.fixture(autouse=True)
def _fresh_tenant(monkeypatch: pytest.MonkeyPatch) -> object:
    monkeypatch.setenv("LIVESPEC_BEADS_FAKE", "1")
    reset_fake_singleton()
    yield
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


def _tenant() -> FakeBeadsClient:
    client = make_beads_client(config=_config())
    assert isinstance(client, FakeBeadsClient)
    return client


def _repo(*, tmp_path: Path, dispatcher: str = "", name: str = "repo") -> Path:
    repo = tmp_path / name
    repo.mkdir()
    _ = (repo / ".livespec.jsonc").write_text(
        '{"livespec-orchestrator-beads-fabro": {"connection": {"prefix": "bd-ib"}'
        + dispatcher
        + "}}",
        encoding="utf-8",
    )
    return repo


def _journal(*, repo: Path) -> JournalFile:
    path = repo / "tmp" / "journal.jsonl"
    path.parent.mkdir(parents=True)
    _ = path.write_text("", encoding="utf-8")
    return JournalFile(path=path)


def _stages(*, journal: JournalFile) -> list[object]:
    return [
        json.loads(line).get("stage")
        for line in journal.path.read_text(encoding="utf-8").splitlines()
    ]


def _item(*, status: WorkItemStatus, assignee: str | None) -> WorkItem:
    return WorkItem(
        id=_ITEM_ID,
        type="task",
        status=status,
        title="A slice whose claim is contested",
        description="Implement the slice.",
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
    )


def _name_current_token(*, client: FakeBeadsClient) -> str:
    """Give the seeded item an open current token, as the migration pass does."""
    token = create_claim_token(client=client)
    metadata = dict(client.show_issue(issue_id=_ITEM_ID)["metadata"])
    metadata[CLAIM_TOKEN_METADATA_KEY] = token
    client.update_issue(issue_id=_ITEM_ID, metadata=metadata, names_claim_token=True)
    return token


def _snapshot(*, client: FakeBeadsClient) -> dict[str, object]:
    """The item as the tenant holds it now, detached from the tenant's own record."""
    return copy.deepcopy(client.show_issue(issue_id=_ITEM_ID))


def _winning_close(*, client: FakeBeadsClient, token: str) -> dict[str, object]:
    """The close reason the item's former token was won with."""
    reason = client.show_issue(issue_id=token).get("close_reason")
    assert reason is not None, "the item was written without winning its current claim token"
    return json.loads(reason)


def _lose_the_token(
    *, client: FakeBeadsClient, token: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Let another writer's close of `token` land first, as a lost race does."""
    close = client.close_issue_without_verdict

    def _raced(*, issue_id: str, reason: str) -> None:
        if issue_id == token:
            close(issue_id=issue_id, reason=_ANOTHER_WRITER)
        close(issue_id=issue_id, reason=reason)

    monkeypatch.setattr(client, "close_issue_without_verdict", _raced)


def _admit(*, repo: Path, item: WorkItem, journal: JournalFile) -> list[str]:
    admission = admit_and_select(
        repo=repo, items=[item], candidates=[item], journal=journal, enforce_cap=False
    )
    return [admitted.id for admitted in admission.admitted]


def _ready_item_naming_a_token() -> tuple[WorkItem, FakeBeadsClient, str]:
    item = _item(status="ready", assignee=None)
    append_work_item(path=_config(), item=item)
    client = _tenant()
    return item, client, _name_current_token(client=client)


def _stranded_claim_naming_a_token() -> tuple[WorkItem, FakeBeadsClient, str]:
    item = _item(status="active", assignee="fabro")
    append_work_item(path=_config(), item=item)
    record_claim_stamp(
        path=_config(),
        work_item_id=_ITEM_ID,
        stamp=ClaimStamp(
            dispatch_id="01DISPATCH",
            dispatching_host="owning-host",
            run_id=_RUN_ID,
            factory_name="hp",
            factory_server="https://hp.example:32276",
        ),
    )
    client = _tenant()
    return item, client, _name_current_token(client=client)


def _release_request(*, item: WorkItem) -> ClaimRecoveryRequest:
    return ClaimRecoveryRequest(
        item=item,
        run_id=_RUN_ID,
        factory_name="hp",
        factory_server_url="https://hp.example:32276",
        action="absent-run-release",
        predecessor_run_id="01PREVIOUSRUN",
    )


def test_enabled_admission_wins_the_token_and_names_its_successor_in_the_claiming_write(
    tmp_path: Path,
) -> None:
    """DoD 1: `active` with `fabro` lands only with the won token's successor."""
    repo = _repo(tmp_path=tmp_path, dispatcher=_TOKENS_ON)
    item, client, token = _ready_item_naming_a_token()

    admitted = _admit(repo=repo, item=item, journal=_journal(repo=repo))

    record = client.show_issue(issue_id=_ITEM_ID)
    successor = record["metadata"][CLAIM_TOKEN_METADATA_KEY]
    assert admitted == [_ITEM_ID]
    assert (record["status"], record["assignee"]) == ("active", "fabro")
    won = _winning_close(client=client, token=token)
    assert successor != token
    assert (won["writer"], won["intent"], won["successor"]) == (
        "dispatcher-admission",
        "admit",
        successor,
    )
    assert client.show_issue(issue_id=successor)["status"] != "closed"
    # The pending claim stamp rode the same write: it names this dispatch and no run.
    assert record["metadata"][CLAIM_STAMP_METADATA_KEY]["run_id"] is None


def test_enabled_admission_that_loses_the_token_writes_nothing_to_the_item(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """DoD 1: an admission that does not win leaves the item exactly as it read it."""
    repo = _repo(tmp_path=tmp_path, dispatcher=_TOKENS_ON)
    item, client, token = _ready_item_naming_a_token()
    before = _snapshot(client=client)
    _lose_the_token(client=client, token=token, monkeypatch=monkeypatch)
    journal = _journal(repo=repo)

    admitted = _admit(repo=repo, item=item, journal=journal)

    assert admitted == []
    assert _snapshot(client=client) == before
    assert client.show_issue(issue_id=token)["close_reason"] == _ANOTHER_WRITER
    assert "ledger-admit" not in _stages(journal=journal)


def test_disabled_admission_claims_the_item_without_touching_any_token(tmp_path: Path) -> None:
    """Before the cutover the admission write is the one it always was."""
    repo = _repo(tmp_path=tmp_path)
    item, client, token = _ready_item_naming_a_token()

    admitted = _admit(repo=repo, item=item, journal=_journal(repo=repo))

    record = client.show_issue(issue_id=_ITEM_ID)
    assert admitted == [_ITEM_ID]
    assert (record["status"], record["assignee"]) == ("active", "fabro")
    assert record["metadata"][CLAIM_TOKEN_METADATA_KEY] == token
    assert client.show_issue(issue_id=token)["status"] != "closed"


def test_enabled_recovery_that_loses_the_token_reports_claim_changed_and_leaves_the_item(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """DoD 3: a lost token is `claim-changed`, with the item's claim untouched.

    The journal record and the ledger comment are written before the token is
    contested, because the contract orders them ahead of the transition. What a
    losing recovery must not change is the item itself: its status, assignee,
    labels and metadata.
    """
    repo = _repo(tmp_path=tmp_path, dispatcher=_TOKENS_ON)
    item, client, token = _stranded_claim_naming_a_token()
    before = _snapshot(client=client)
    _lose_the_token(client=client, token=token, monkeypatch=monkeypatch)

    outcome = recover_claim(
        repo=repo, journal=_journal(repo=repo), request=_release_request(item=item), now_iso=_NOW
    )

    assert getattr(outcome, "hold_reason", None) == "claim-changed"
    assert _snapshot(client=client) == before
    assert client.show_issue(issue_id=token)["close_reason"] == _ANOTHER_WRITER


def test_enabled_recovery_that_wins_the_token_releases_the_claim_and_names_its_successor(
    tmp_path: Path,
) -> None:
    """DoD 3's other half: the recovery that wins is the one writer that acts."""
    repo = _repo(tmp_path=tmp_path, dispatcher=_TOKENS_ON)
    item, client, token = _stranded_claim_naming_a_token()

    outcome = recover_claim(
        repo=repo, journal=_journal(repo=repo), request=_release_request(item=item), now_iso=_NOW
    )

    record = client.show_issue(issue_id=_ITEM_ID)
    successor = record["metadata"][CLAIM_TOKEN_METADATA_KEY]
    assert getattr(outcome, "hold_reason", None) is None
    assert (record["status"], record["assignee"]) == ("ready", None)
    won = _winning_close(client=client, token=token)
    assert successor != token
    assert (won["writer"], won["successor"]) == ("stranded-claim-recovery", successor)


def test_two_admissions_deciding_on_one_read_admit_the_item_exactly_once(tmp_path: Path) -> None:
    """Sequential, not racing: the second admission must not win the first's successor.

    Two Dispatchers, each in its own checkout of the one tenant, were handed
    the same read of the item, `ready`. The second runs only after the first
    has finished, so it finds the first's successor open and could win it. It
    must stand down as `claim-changed` instead, leaving the item exactly as the
    first admission left it.
    """
    first_host = _repo(tmp_path=tmp_path, dispatcher=_TOKENS_ON, name="first-host")
    second_host = _repo(tmp_path=tmp_path, dispatcher=_TOKENS_ON, name="second-host")
    item, client, token = _ready_item_naming_a_token()
    second_journal = _journal(repo=second_host)

    first = _admit(repo=first_host, item=item, journal=_journal(repo=first_host))
    as_first_left_it = _snapshot(client=client)
    second = _admit(repo=second_host, item=item, journal=second_journal)

    assert (first, second) == ([_ITEM_ID], [])
    assert _snapshot(client=client) == as_first_left_it
    successor = _winning_close(client=client, token=token)["successor"]
    assert as_first_left_it["metadata"][CLAIM_TOKEN_METADATA_KEY] == successor
    assert client.show_issue(issue_id=successor)["status"] != "closed"
    second_stages = _stages(journal=second_journal)
    assert "ledger-admit" not in second_stages
    assert "claim-write-refused" in second_stages


def test_two_recoveries_deciding_on_one_read_release_the_claim_exactly_once(
    tmp_path: Path,
) -> None:
    """Sequential, not racing: the second recovery reports `claim-changed` and writes nothing."""
    repo = _repo(tmp_path=tmp_path, dispatcher=_TOKENS_ON)
    item, client, token = _stranded_claim_naming_a_token()
    journal = _journal(repo=repo)
    request = _release_request(item=item)

    first = recover_claim(repo=repo, journal=journal, request=request, now_iso=_NOW)
    as_first_left_it = _snapshot(client=client)
    second = recover_claim(repo=repo, journal=journal, request=request, now_iso=_NOW)

    successor = _winning_close(client=client, token=token)["successor"]
    assert getattr(first, "hold_reason", None) is None
    assert getattr(second, "hold_reason", None) == "claim-changed"
    assert _snapshot(client=client) == as_first_left_it
    assert as_first_left_it["metadata"][CLAIM_TOKEN_METADATA_KEY] == successor
    assert client.show_issue(issue_id=successor)["status"] != "closed"
