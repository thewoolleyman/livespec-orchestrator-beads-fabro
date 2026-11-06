"""The admission valve's ledger writes: the approval leg, the claim, the withheld.

`_dispatcher_admission_writes` owns what an admission plan does to the ledger.
Two properties are pinned here, one per value of `dispatcher.claim_tokens`:

- false or unset: the valve's two store writers are called exactly as the valve
  called them before this module existed. The pending claim stamp goes first,
  then `ready -> active` with the assignee. These cases record the calls and
  assert their order and keyword arguments.
- true: an admission is ONE write against the tenant. It lands only after the
  admission has won the item's current claim token, names the successor token
  and carries the pending claim stamp. An admission that does not win writes
  nothing, the stamp included.

A refused claim is a FAILED outcome at the `admission-claim-refused` stage, so
the dispatch result reports it and the next pass tries again.
"""

from __future__ import annotations

import copy
import json
from dataclasses import replace
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
    create_claim_token,
)
from livespec_orchestrator_beads_fabro.commands import _dispatcher_claim_stamp
from livespec_orchestrator_beads_fabro.commands._dispatcher_admission import admit_and_select
from livespec_orchestrator_beads_fabro.commands._dispatcher_admission_writes import (
    ADMISSION_CLAIM_REFUSED_STAGE,
    admission_held_outcome,
    admit_item,
    approve_ready_items,
    withheld_outcomes,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_claim_guard import (
    TRANSITION_OBSERVATIONS,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_claim_stamp import (
    PENDING_CLAIM_STAMP_STAGE,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import JournalFile
from livespec_orchestrator_beads_fabro.commands._dispatcher_valves import AdmissionPlan
from livespec_orchestrator_beads_fabro.errors import BeadsConnectionError
from livespec_orchestrator_beads_fabro.store import append_work_item
from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem

_ITEM_ID = "bd-ib-admitwrite"
_DISPATCH_ID = "01DISPATCHADMIT"
_ANOTHER_WRITER = "another writer won this token"


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


def _repo(*, tmp_path: Path, claim_tokens: bool) -> Path:
    dispatcher = ', "dispatcher": {"claim_tokens": true}' if claim_tokens else ""
    _ = (tmp_path / ".livespec.jsonc").write_text(
        '{"livespec-orchestrator-beads-fabro": {"connection": {"prefix": "bd-ib"}'
        + dispatcher
        + "}}",
        encoding="utf-8",
    )
    return tmp_path


def _journal(*, tmp_path: Path) -> JournalFile:
    path = tmp_path / "journal.jsonl"
    _ = path.write_text("", encoding="utf-8")
    return JournalFile(path=path)


def _records(*, journal: JournalFile) -> list[dict[str, object]]:
    return [json.loads(line) for line in journal.path.read_text(encoding="utf-8").splitlines()]


def _stages(*, journal: JournalFile) -> list[object]:
    return [record.get("stage") for record in _records(journal=journal)]


def _item(**overrides: object) -> WorkItem:
    base = WorkItem(
        id=_ITEM_ID,
        type="task",
        status="ready",
        title="A slice the valve is about to claim",
        description="Implement the slice.",
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
    )
    return replace(base, **overrides)


def _seed(*, item: WorkItem) -> tuple[FakeBeadsClient, str]:
    """File the item and give it an open current token."""
    append_work_item(path=_config(), item=item)
    client = make_beads_client(config=_config())
    assert isinstance(client, FakeBeadsClient)
    token = create_claim_token(client=client)
    metadata = dict(client.show_issue(issue_id=item.id)["metadata"])
    metadata[CLAIM_TOKEN_METADATA_KEY] = token
    client.update_issue(issue_id=item.id, metadata=metadata)
    return client, token


def _snapshot(*, client: FakeBeadsClient) -> dict[str, object]:
    return copy.deepcopy(client.show_issue(issue_id=_ITEM_ID))


def _lose_the_token(
    *, client: FakeBeadsClient, token: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    close = client.close_issue_without_verdict

    def _raced(*, issue_id: str, reason: str) -> None:
        if issue_id == token:
            close(issue_id=issue_id, reason=_ANOTHER_WRITER)
        close(issue_id=issue_id, reason=reason)

    monkeypatch.setattr(client, "close_issue_without_verdict", _raced)


class _Recorder:
    """The valve's two store writers, recording each call in the order made."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, object]]] = []

    def stamp(self, **kwargs: object) -> None:
        self.calls.append(("stamp", kwargs))

    def write(self, **kwargs: object) -> None:
        self.calls.append(("write", kwargs))


def _admit(
    *, repo: Path, journal: JournalFile, recorder: _Recorder, resume: bool = False
) -> str | None:
    return admit_item(
        repo=repo,
        config=_config(),
        journal=journal,
        item_id=_ITEM_ID,
        assignee="fabro",
        dispatch_id=_DISPATCH_ID,
        resume=resume,
        explicit_factory="hp",
        stamp=recorder.stamp,
        write=recorder.write,
    )


def test_a_disabled_admission_stamps_then_claims_through_the_valves_own_writers(
    tmp_path: Path,
) -> None:
    repo = _repo(tmp_path=tmp_path, claim_tokens=False)
    journal = _journal(tmp_path=tmp_path)
    recorder = _Recorder()

    refusal = _admit(repo=repo, journal=journal, recorder=recorder, resume=True)

    assert refusal is None
    assert recorder.calls == [
        (
            "stamp",
            {
                "repo": repo,
                "work_item_id": _ITEM_ID,
                "dispatch_id": _DISPATCH_ID,
                "journal": journal,
                "resume": True,
                "explicit_factory": "hp",
            },
        ),
        (
            "write",
            {"path": _config(), "item_id": _ITEM_ID, "status": "active", "assignee": "fabro"},
        ),
    ]
    assert _records(journal=journal) == []


def test_an_enabled_admission_is_one_write_carrying_claim_successor_and_pending_stamp(
    tmp_path: Path,
) -> None:
    repo = _repo(tmp_path=tmp_path, claim_tokens=True)
    client, token = _seed(item=_item())
    journal = _journal(tmp_path=tmp_path)
    recorder = _Recorder()

    refusal = _admit(repo=repo, journal=journal, recorder=recorder)

    record = client.show_issue(issue_id=_ITEM_ID)
    won = json.loads(client.show_issue(issue_id=token)["close_reason"])
    stamp = record["metadata"][CLAIM_STAMP_METADATA_KEY]
    assert refusal is None
    assert recorder.calls == []
    assert (record["status"], record["assignee"]) == ("active", "fabro")
    assert (won["writer"], won["intent"]) == ("dispatcher-admission", "admit")
    assert won["successor"] == record["metadata"][CLAIM_TOKEN_METADATA_KEY]
    assert (stamp["dispatch_id"], stamp["run_id"], stamp["factory"]["name"]) == (
        _DISPATCH_ID,
        None,
        "hp",
    )
    assert [
        (row["stage"], row["claim_stamped"], row["claim_stamp_failure_detail"])
        for row in _records(journal=journal)
    ] == [(PENDING_CLAIM_STAMP_STAGE, True, None)]


def test_an_enabled_admission_that_loses_the_token_writes_nothing_not_even_the_stamp(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _repo(tmp_path=tmp_path, claim_tokens=True)
    client, token = _seed(item=_item())
    before = _snapshot(client=client)
    _lose_the_token(client=client, token=token, monkeypatch=monkeypatch)
    journal = _journal(tmp_path=tmp_path)
    recorder = _Recorder()

    refusal = _admit(repo=repo, journal=journal, recorder=recorder)

    assert refusal == "claim-changed"
    assert recorder.calls == []
    assert _snapshot(client=client) == before
    # The refusal is journaled; no pending-stamp record claims a stamp that never landed.
    assert _stages(journal=journal) == ["claim-write-refused"]


def test_an_enabled_admission_whose_stamp_cannot_be_built_still_claims_and_says_why(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The stamp stays fail-open: the claim lands without it and the cause is journaled."""
    repo = _repo(tmp_path=tmp_path, claim_tokens=True)
    client, _ = _seed(item=_item())
    journal = _journal(tmp_path=tmp_path)

    def _no_route(**_: object) -> object:
        raise BeadsConnectionError(detail="no route")

    monkeypatch.setattr(_dispatcher_claim_stamp, "unrecorded_dispatch_factory_target", _no_route)

    refusal = _admit(repo=repo, journal=journal, recorder=_Recorder())

    record = client.show_issue(issue_id=_ITEM_ID)
    [row] = _records(journal=journal)
    assert refusal is None
    assert (record["status"], record["assignee"]) == ("active", "fabro")
    assert CLAIM_STAMP_METADATA_KEY not in record["metadata"]
    assert row["claim_stamped"] is False
    assert row["claim_stamp_failure_detail"].startswith(
        "claim stamp could not be built: BeadsConnectionError:"
    )


def _plan(*, approved: tuple[WorkItem, ...]) -> AdmissionPlan:
    return AdmissionPlan(approved=approved, admitted=(), held=())


def test_a_disabled_approval_leg_writes_ready_through_the_valves_writer_and_journals_it(
    tmp_path: Path,
) -> None:
    repo = _repo(tmp_path=tmp_path, claim_tokens=False)
    journal = _journal(tmp_path=tmp_path)
    recorder = _Recorder()
    labelled = _item(status="pending-approval", admission_policy="auto")
    configured = _item(id="bd-ib-configured", status="pending-approval")

    approved_ids, refused = approve_ready_items(
        repo=repo,
        plan=_plan(approved=(labelled, configured)),
        config=_config(),
        journal=journal,
        write=recorder.write,
    )

    assert (approved_ids, refused) == ({_ITEM_ID, "bd-ib-configured"}, [])
    assert recorder.calls == [
        ("write", {"path": _config(), "item_id": _ITEM_ID, "status": "ready"}),
        ("write", {"path": _config(), "item_id": "bd-ib-configured", "status": "ready"}),
    ]
    assert [(row["stage"], row.get("governing_settings")) for row in _records(journal=journal)] == [
        ("ledger-approve", None),
        ("auto-disposition", ["admission:auto"]),
        ("ledger-approve", None),
        ("auto-disposition", ["auto_approve_ready"]),
    ]


def test_an_enabled_approval_leg_moves_the_item_to_ready_under_the_won_token(
    tmp_path: Path,
) -> None:
    repo = _repo(tmp_path=tmp_path, claim_tokens=True)
    item = _item(status="pending-approval", admission_policy="auto")
    client, token = _seed(item=item)
    recorder = _Recorder()

    approved_ids, refused = approve_ready_items(
        repo=repo,
        plan=_plan(approved=(item,)),
        config=_config(),
        journal=_journal(tmp_path=tmp_path),
        write=recorder.write,
    )

    won = json.loads(client.show_issue(issue_id=token)["close_reason"])
    assert (approved_ids, refused) == ({_ITEM_ID}, [])
    assert recorder.calls == []
    assert client.show_issue(issue_id=_ITEM_ID)["status"] == "ready"
    assert (won["writer"], won["intent"]) == ("dispatcher-admission", "auto-approve")


def test_an_enabled_approval_that_loses_the_token_is_reported_refused_and_not_approved(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _repo(tmp_path=tmp_path, claim_tokens=True)
    item = _item(status="pending-approval", admission_policy="auto")
    client, token = _seed(item=item)
    before = _snapshot(client=client)
    _lose_the_token(client=client, token=token, monkeypatch=monkeypatch)
    journal = _journal(tmp_path=tmp_path)

    approved_ids, refused = approve_ready_items(
        repo=repo,
        plan=_plan(approved=(item,)),
        config=_config(),
        journal=journal,
        write=_Recorder().write,
    )

    assert approved_ids == set()
    assert refused == [(item, "claim-changed")]
    assert _snapshot(client=client) == before
    assert _stages(journal=journal) == ["claim-write-refused"]


def test_the_admission_held_outcome_is_a_failed_terminal_that_launches_nothing() -> None:
    outcome = admission_held_outcome(item=_item(), reason="manual-admission")

    assert (outcome.work_item_id, outcome.status, outcome.stage) == (
        _ITEM_ID,
        "failed",
        "admission-held",
    )
    assert (outcome.pr_number, outcome.merge_sha) == (None, None)
    assert _ITEM_ID in outcome.detail


def test_withheld_outcomes_journal_and_surface_every_held_and_refused_item(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    journal = _journal(tmp_path=tmp_path)
    refused_item = _item(id="bd-ib-refused")

    outcomes = withheld_outcomes(
        held=[(_item(), "manual-admission")],
        claim_refused=[(refused_item, "claim-changed")],
        journal=journal,
    )

    assert [(outcome.work_item_id, outcome.status, outcome.stage) for outcome in outcomes] == [
        (_ITEM_ID, "failed", "admission-held"),
        ("bd-ib-refused", "failed", ADMISSION_CLAIM_REFUSED_STAGE),
    ]
    assert "claim-changed" in outcomes[1].detail
    assert [
        (row["stage"], row["outcome"]["work_item_id"]) for row in _records(journal=journal)
    ] == [("outcome", _ITEM_ID), ("outcome", "bd-ib-refused")]
    surfaced = capsys.readouterr().err.splitlines()
    assert [line.startswith("SURFACE: ") for line in surfaced] == [True, True]
    assert "bd-ib-refused" in surfaced[1]


def _admitted_through_the_valve(*, repo: Path, item: WorkItem, journal: JournalFile) -> object:
    return admit_and_select(
        repo=repo, items=[item], candidates=[item], journal=journal, enforce_cap=False
    )


def test_the_valve_approves_then_admits_an_auto_item_through_two_won_tokens(
    tmp_path: Path,
) -> None:
    """Each leg is its own claim-changing write, so each wins its own token."""
    repo = _repo(tmp_path=tmp_path, claim_tokens=True)
    item = _item(status="pending-approval", admission_policy="auto")
    client, token = _seed(item=item)

    admission = _admitted_through_the_valve(
        repo=repo, item=item, journal=_journal(tmp_path=tmp_path)
    )

    approval = json.loads(client.show_issue(issue_id=token)["close_reason"])
    claim = json.loads(client.show_issue(issue_id=approval["successor"])["close_reason"])
    record = client.show_issue(issue_id=_ITEM_ID)
    assert [admitted.id for admitted in admission.admitted] == [_ITEM_ID]
    assert (record["status"], record["assignee"]) == ("active", "fabro")
    assert (approval["intent"], claim["intent"]) == ("auto-approve", "admit")
    assert record["metadata"][CLAIM_TOKEN_METADATA_KEY] == claim["successor"]


def test_the_valve_does_not_admit_an_item_whose_approval_the_protocol_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A refused approval left the item `pending-approval`, which is not admissible."""
    repo = _repo(tmp_path=tmp_path, claim_tokens=True)
    item = _item(status="pending-approval", admission_policy="auto")
    client, token = _seed(item=item)
    before = _snapshot(client=client)
    _lose_the_token(client=client, token=token, monkeypatch=monkeypatch)
    journal = _journal(tmp_path=tmp_path)

    admission = _admitted_through_the_valve(repo=repo, item=item, journal=journal)

    assert admission.admitted == []
    assert [(outcome.work_item_id, outcome.stage) for outcome in admission.refused] == [
        (_ITEM_ID, ADMISSION_CLAIM_REFUSED_STAGE)
    ]
    assert admission.deferred == []
    assert _snapshot(client=client) == before
    assert _stages(journal=journal).count("claim-write-refused") == 1


def test_an_enabled_admission_of_an_item_already_admitted_is_refused_uncontested(
    tmp_path: Path,
) -> None:
    """Admission is `ready -> active`: an item that already left `ready` is not claimed."""
    repo = _repo(tmp_path=tmp_path, claim_tokens=True)
    client, token = _seed(item=_item())
    client.update_issue(issue_id=_ITEM_ID, status="active", assignee="another-dispatcher")
    before = _snapshot(client=client)
    journal = _journal(tmp_path=tmp_path)

    refusal = _admit(repo=repo, journal=journal, recorder=_Recorder())

    assert refusal == "claim-changed"
    assert _snapshot(client=client) == before
    assert client.show_issue(issue_id=token)["status"] != "closed"
    assert _stages(journal=journal) == ["claim-write-refused"]


def test_an_enabled_approval_of_an_item_that_left_pending_approval_is_refused_uncontested(
    tmp_path: Path,
) -> None:
    repo = _repo(tmp_path=tmp_path, claim_tokens=True)
    item = _item(status="pending-approval", admission_policy="auto")
    client, token = _seed(item=item)
    client.update_issue(issue_id=_ITEM_ID, status="backlog")
    before = _snapshot(client=client)

    approved_ids, refused = approve_ready_items(
        repo=repo,
        plan=_plan(approved=(item,)),
        config=_config(),
        journal=_journal(tmp_path=tmp_path),
        write=_Recorder().write,
    )

    assert (approved_ids, refused) == (set(), [(item, "claim-changed")])
    assert _snapshot(client=client) == before
    assert client.show_issue(issue_id=token)["status"] != "closed"
