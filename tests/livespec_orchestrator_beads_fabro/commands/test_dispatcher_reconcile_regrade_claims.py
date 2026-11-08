"""What the re-grade arm's two writes are bound to, under the claim-token cutover.

`reconcile-merged --regrade` reads a `rework:pending` item, grades it for as
long as an acceptance pass takes, and then parks or closes it. With
`dispatcher.claim_tokens` true each of those is a token-guarded write, and the
token alone does not stop an arm that decided on an earlier read. What stops it
is the predicate the write carries.

THE CASE THIS MODULE EXISTS FOR. A rework re-dispatch re-occupies an `active`
row: it writes no status and no assignee and leaves `rework:pending` in place.
A rework run admitted while the arm graded therefore leaves the status and the
marker exactly as the arm read them. An arm bound to those two alone would
close or park the item under a live run. What the run does change is the
claim stamp, when it learns its run id, so the arm binds the claim row it read
BEFORE it graded: status, assignee and the whole stamp.

Every case reads the row with `regrade_claim`, changes the item the way one
other writer would while the arm grades, and then makes the arm's write.
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
    IssueDraft,
    make_beads_client,
    reset_fake_singleton,
)
from livespec_orchestrator_beads_fabro._store_dispatch_claim import (
    CLAIM_TOKEN_METADATA_KEY,
    ClaimStamp,
    claim_row_from_record,
    create_claim_token,
    record_claim_stamp,
)
from livespec_orchestrator_beads_fabro.commands import _dispatcher_lifecycle_writes as lifecycle
from livespec_orchestrator_beads_fabro.commands import _intake_valve_claim_writes as writes
from livespec_orchestrator_beads_fabro.commands._dispatcher_claim_guard import (
    TRANSITION_OBSERVATIONS,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import DispatchOutcome
from livespec_orchestrator_beads_fabro.commands._dispatcher_reconcile_regrade_claims import (
    RegradeClaim,
    refused_regrade_outcome,
    regrade_claim,
)
from livespec_orchestrator_beads_fabro.store import materialize_work_items, read_work_items
from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem

_ITEM_ID = "bd-ib-regradeclaim"
_PLUGIN_BLOCK = "livespec-orchestrator-beads-fabro"
_MARKER = "rework:pending"
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
    """A repository committing `dispatcher.claim_tokens` as the given value."""
    block = {"connection": _CONNECTION, "dispatcher": {"claim_tokens": claim_tokens}}
    _ = (tmp_path / ".livespec.jsonc").write_text(
        json.dumps({_PLUGIN_BLOCK: block}), encoding="utf-8"
    )
    return tmp_path


def _stamp(*, dispatch_id: str, run_id: str | None) -> ClaimStamp:
    return ClaimStamp(
        dispatch_id=dispatch_id,
        dispatching_host="host-a",
        run_id=run_id,
        factory_name="hp",
        factory_server="https://hp.example:32276",
    )


def _seed() -> tuple[FakeBeadsClient, str, WorkItem]:
    """An `active`, marked item whose claim names the run that merged, as the arm reads it."""
    client = make_beads_client(config=_config())
    assert isinstance(client, FakeBeadsClient)
    _ = client.create_issue(
        draft=IssueDraft(
            issue_id=_ITEM_ID,
            issue_type="task",
            title="A merged slice whose acceptance failed",
            description="Implement the slice.",
            assignee="fabro",
            created_at="2026-11-06T00:00:00Z",
            labels=[_MARKER],
        )
    )
    token = create_claim_token(client=client)
    client.update_issue(
        issue_id=_ITEM_ID,
        status="active",
        metadata={CLAIM_TOKEN_METADATA_KEY: token},
        names_claim_token=True,
    )
    record_claim_stamp(
        path=_config(),
        work_item_id=_ITEM_ID,
        stamp=_stamp(dispatch_id="01DISPATCHMERGED", run_id="01RUNMERGED"),
    )
    item = materialize_work_items(records=read_work_items(path=_config()))[_ITEM_ID]
    assert (item.status, item.assignee, item.rework_pending) == ("active", "fabro", True)
    return client, token, item


@dataclass(kw_only=True)
class _Journal:
    records: list[dict[str, object]] = field(default_factory=list)

    def append(self, *, record: dict[str, object]) -> None:
        self.records.append(record)


def _reconciled(*, monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, str]]:
    """Every post-write run reconciliation either rendering of the park asks for."""
    seen: list[tuple[str, str]] = []

    def _reconcile(**fields: object) -> None:
        seen.append((str(fields["item_id"]), str(fields["status"])))

    monkeypatch.setattr(writes, "reconcile_after_lifecycle_write", _reconcile)
    monkeypatch.setattr(lifecycle, "reconcile_after_lifecycle_write", _reconcile)
    return seen


def _snapshot(*, client: FakeBeadsClient) -> dict[str, object]:
    return copy.deepcopy(client.show_issue(issue_id=_ITEM_ID))


def _is_open(*, client: FakeBeadsClient, token: str) -> bool:
    return client.show_issue(issue_id=token)["status"] != "closed"


def _won(*, client: FakeBeadsClient, token: str) -> tuple[object, object, bool]:
    """The writer and intent `token` was won with, and whether the item names its successor."""
    reason = json.loads(client.show_issue(issue_id=token)["close_reason"])
    named = client.show_issue(issue_id=_ITEM_ID)["metadata"][CLAIM_TOKEN_METADATA_KEY]
    return reason["writer"], reason["intent"], reason["successor"] == named


def _park(claim: RegradeClaim) -> str | None:
    return claim.park()


def _hold(claim: RegradeClaim) -> str | None:
    return claim.hold()


_WRITES = [
    pytest.param(_park, "regrade:park", id="park"),
    pytest.param(_hold, "regrade:close", id="hold"),
]


def test_the_claim_row_is_read_before_grading_as_the_ledger_holds_it(tmp_path: Path) -> None:
    repo = _repo(tmp_path=tmp_path)
    client, _, item = _seed()
    journal = _Journal()

    claim = regrade_claim(repo=repo, item=item, journal=journal)

    assert claim.row == claim_row_from_record(record=client.show_issue(issue_id=_ITEM_ID))
    assert claim.row is not None
    assert (claim.row.status, claim.row.assignee) == ("active", "fabro")
    assert claim.row.stamp == _stamp(dispatch_id="01DISPATCHMERGED", run_id="01RUNMERGED")
    assert (claim.repo, claim.item, claim.journal) == (repo, item, journal)


@pytest.mark.parametrize("claim_tokens", [False, None, "yes"])
def test_no_row_is_read_while_the_key_is_not_readable_as_true(
    claim_tokens: object, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Before the cutover the arm makes no ledger read it did not make before."""
    repo = _repo(tmp_path=tmp_path, claim_tokens=claim_tokens)
    client, _, item = _seed()
    reads: list[object] = []
    monkeypatch.setattr(client, "show_issue", lambda **fields: reads.append(fields))

    claim = regrade_claim(repo=repo, item=item, journal=_Journal())

    assert claim.row is None
    assert reads == []


@pytest.mark.parametrize(("write", "intent"), _WRITES)
def test_a_write_on_the_item_exactly_as_the_arm_read_it_wins_the_token(
    write: Callable[[RegradeClaim], str | None],
    intent: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = _repo(tmp_path=tmp_path)
    client, token, item = _seed()
    reconciled = _reconciled(monkeypatch=monkeypatch)
    journal = _Journal()

    refusal = write(regrade_claim(repo=repo, item=item, journal=journal))

    assert refusal is None
    assert _won(client=client, token=token) == ("human-valve", intent, True)
    assert journal.records == []
    parked = intent == "regrade:park"
    assert client.show_issue(issue_id=_ITEM_ID)["status"] == ("acceptance" if parked else "active")
    assert reconciled == ([(_ITEM_ID, "acceptance")] if parked else [])


def _a_rework_run_learns_its_run_id(client: FakeBeadsClient) -> None:
    """The re-dispatch wrote no status or assignee and left the marker: only the stamp moved."""
    _ = client
    record_claim_stamp(
        path=_config(),
        work_item_id=_ITEM_ID,
        stamp=_stamp(dispatch_id="01DISPATCHREWORK", run_id="01RUNREWORK"),
    )


def _another_dispatch_stamps_pending(client: FakeBeadsClient) -> None:
    _ = client
    record_claim_stamp(
        path=_config(),
        work_item_id=_ITEM_ID,
        stamp=_stamp(dispatch_id="01DISPATCHREWORK", run_id=None),
    )


def _the_same_dispatch_names_another_run(client: FakeBeadsClient) -> None:
    _ = client
    record_claim_stamp(
        path=_config(),
        work_item_id=_ITEM_ID,
        stamp=_stamp(dispatch_id="01DISPATCHMERGED", run_id="01RUNREWORK"),
    )


def _the_assignee_is_cleared(client: FakeBeadsClient) -> None:
    client.update_issue(issue_id=_ITEM_ID, clear_assignee=True)


def _the_marker_is_removed(client: FakeBeadsClient) -> None:
    client.update_issue(issue_id=_ITEM_ID, remove_labels=[_MARKER])


def _the_item_is_moved(client: FakeBeadsClient) -> None:
    client.update_issue(issue_id=_ITEM_ID, status="blocked")


_CHANGES = [
    pytest.param(_a_rework_run_learns_its_run_id, id="rework-run-stamped"),
    pytest.param(_another_dispatch_stamps_pending, id="another-dispatch-pending"),
    pytest.param(_the_same_dispatch_names_another_run, id="same-dispatch-other-run"),
    pytest.param(_the_assignee_is_cleared, id="assignee-cleared"),
    pytest.param(_the_marker_is_removed, id="marker-removed"),
    pytest.param(_the_item_is_moved, id="status-moved"),
]


@pytest.mark.parametrize("changed_while_grading", _CHANGES)
@pytest.mark.parametrize(("write", "intent"), _WRITES)
def test_an_item_another_writer_changed_while_the_arm_graded_is_not_written(
    write: Callable[[RegradeClaim], str | None],
    intent: str,
    changed_while_grading: Callable[[FakeBeadsClient], None],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The arm stands down as `claim-changed` and contests no token."""
    repo = _repo(tmp_path=tmp_path)
    client, token, item = _seed()
    reconciled = _reconciled(monkeypatch=monkeypatch)
    journal = _Journal()
    claim = regrade_claim(repo=repo, item=item, journal=journal)
    changed_while_grading(client)
    before = _snapshot(client=client)

    refusal = write(claim)

    assert refusal == "claim-changed"
    assert _snapshot(client=client) == before
    assert _is_open(client=client, token=token)
    assert reconciled == []
    assert journal.records == [
        {
            "stage": "claim-write-refused",
            "work_item_id": _ITEM_ID,
            "writer": "human-valve",
            "intent": intent,
            "reason": "claim-changed",
        }
    ]


def test_an_item_reassigned_between_the_arms_read_and_its_row_read_is_not_written(
    tmp_path: Path,
) -> None:
    """The assignee is bound to the item the arm was handed, as well as to the row."""
    repo = _repo(tmp_path=tmp_path)
    client, token, item = _seed()
    client.update_issue(issue_id=_ITEM_ID, assignee="someone-else")
    claim = regrade_claim(repo=repo, item=item, journal=_Journal())
    assert claim.row is not None
    assert claim.row.assignee == "someone-else"

    assert claim.hold() == "claim-changed"
    assert _is_open(client=client, token=token)


def test_an_arm_that_read_no_row_cannot_state_its_decision_and_is_refused(tmp_path: Path) -> None:
    """The key was not `true` before the arm graded, and is `true` when it writes."""
    client, token, item = _seed()
    claim = regrade_claim(
        repo=_repo(tmp_path=tmp_path, claim_tokens=False), item=item, journal=_Journal()
    )
    _ = _repo(tmp_path=tmp_path, claim_tokens=True)
    before = _snapshot(client=client)

    assert claim.row is None
    assert claim.hold() == "claim-changed"
    assert _snapshot(client=client) == before
    assert _is_open(client=client, token=token)


def test_before_the_cutover_the_park_is_the_unguarded_write_and_the_hold_writes_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _repo(tmp_path=tmp_path, claim_tokens=False)
    client, token, item = _seed()
    reconciled = _reconciled(monkeypatch=monkeypatch)
    journal = _Journal()
    claim = regrade_claim(repo=repo, item=item, journal=journal)
    before = _snapshot(client=client)

    held = claim.hold()

    assert held is None
    assert _snapshot(client=client) == before

    parked = claim.park()

    record = client.show_issue(issue_id=_ITEM_ID)
    assert parked is None
    assert record["status"] == "acceptance"
    assert record["metadata"][CLAIM_TOKEN_METADATA_KEY] == token
    assert _is_open(client=client, token=token)
    assert reconciled == [(_ITEM_ID, "acceptance")]
    assert journal.records == []


def test_a_refused_disposition_is_reported_failed_on_the_arms_own_outcome(
    capsys: pytest.CaptureFixture[str],
) -> None:
    _, _, item = _seed()
    outcome = DispatchOutcome(
        work_item_id=_ITEM_ID,
        status="green",
        stage="regrade",
        pr_number=2459,
        merge_sha="51d99744",
        detail="re-grading against merged PR #2459",
    )

    refused = refused_regrade_outcome(item=item, outcome=outcome, refusal="claim-changed")

    detail = (
        "re-graded PASS, but the claim-token protocol refused the ledger write "
        "(claim-changed); nothing was written"
    )
    assert (refused.status, refused.stage, refused.detail) == ("failed", "regrade", detail)
    assert (refused.pr_number, refused.merge_sha) == (2459, "51d99744")
    assert capsys.readouterr().err == (
        f"SURFACE: work-item {_ITEM_ID} {detail} against merged PR #2459. Re-run --regrade.\n"
    )
