"""What an admission of an already-`active` row plans on, and the rework claim.

`_dispatcher_admission_claims` has two halves. `planned_claim_rows` is the
read an admission pass takes before its first ledger write, of each row it may
admit that is already `active`. `claim_rework_row` is the one ledger write the
rework leg makes once `dispatcher.claim_tokens` is true: it replaces the
previous dispatch's claim stamp with a pending one, under the row's won token.

The valve-level behaviour, two admissions that planned on one row included, is
asserted in `test_dispatcher_claim_token_followups.py`. These cases pin each
half on its own, against the in-memory tenant.
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
    ClaimRow,
    ClaimStamp,
    claim_row_for,
    create_claim_token,
    record_claim_stamp,
)
from livespec_orchestrator_beads_fabro._store_rework_mutations import (
    update_work_item_rework_pending,
)
from livespec_orchestrator_beads_fabro.commands import _dispatcher_claim_stamp
from livespec_orchestrator_beads_fabro.commands._dispatcher_admission_claims import (
    REWORK_ADMIT_INTENT,
    claim_rework_row,
    planned_claim_rows,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_claim_guard import (
    TRANSITION_OBSERVATIONS,
)
from livespec_orchestrator_beads_fabro.errors import BeadsConnectionError
from livespec_orchestrator_beads_fabro.store import append_work_item
from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem, WorkItemStatus

_ROW = "bd-ib-marked"
_DISPATCH = "01REWORKDISPATCH"
_PREVIOUS_RUN = "01PREVIOUSRUN"
_PENDING_STAGE = "dispatch-claim-stamp-pending"
_REFUSED_STAGE = "claim-write-refused"


@pytest.fixture(autouse=True)
def _fresh_tenant(monkeypatch: pytest.MonkeyPatch) -> object:
    monkeypatch.setenv("LIVESPEC_BEADS_FAKE", "1")
    reset_fake_singleton()
    TRANSITION_OBSERVATIONS.clear()
    yield
    TRANSITION_OBSERVATIONS.clear()
    reset_fake_singleton()


class _Journal:
    def __init__(self) -> None:
        self.records: list[dict[str, object]] = []

    def append(self, *, record: dict[str, object]) -> None:
        self.records.append(record)

    def stages(self) -> list[object]:
        return [record["stage"] for record in self.records]


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


def _repo(*, tmp_path: Path, claim_tokens: bool = True) -> Path:
    dispatcher = {"claim_tokens": True} if claim_tokens else {}
    _ = (tmp_path / ".livespec.jsonc").write_text(
        json.dumps(
            {
                "livespec-orchestrator-beads-fabro": {
                    "connection": {"prefix": "bd-ib"},
                    "dispatcher": dispatcher,
                }
            }
        ),
        encoding="utf-8",
    )
    return tmp_path


def _item(*, item_id: str, status: WorkItemStatus) -> WorkItem:
    return WorkItem(
        id=item_id,
        type="task",
        status=status,
        title=f"Item {item_id}",
        description="Implement the slice.",
        origin="freeform",
        gap_id=None,
        rank="a0",
        assignee="fabro" if status == "active" else None,
        depends_on=(),
        captured_at="2026-11-06T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
    )


def _previous_stamp() -> ClaimStamp:
    return ClaimStamp(
        dispatch_id="01PREVIOUSDISPATCH",
        dispatching_host="owning-host",
        run_id=_PREVIOUS_RUN,
        factory_name="hp",
        factory_server=None,
    )


def _marked_row(*, marked: bool = True) -> tuple[FakeBeadsClient, str]:
    """An `active` row stamped by its previous dispatch, naming an open token."""
    append_work_item(path=_config(), item=_item(item_id=_ROW, status="active"))
    update_work_item_rework_pending(path=_config(), item_id=_ROW, value=marked)
    record_claim_stamp(path=_config(), work_item_id=_ROW, stamp=_previous_stamp())
    client = _tenant()
    token = create_claim_token(client=client)
    metadata = dict(client.show_issue(issue_id=_ROW)["metadata"])
    metadata[CLAIM_TOKEN_METADATA_KEY] = token
    client.update_issue(issue_id=_ROW, metadata=metadata, names_claim_token=True)
    return client, token


def _snapshot(*, client: FakeBeadsClient) -> dict[str, object]:
    return copy.deepcopy(client.show_issue(issue_id=_ROW))


def _planned() -> ClaimRow:
    return claim_row_for(path=_config(), work_item_id=_ROW)


def _claim(*, repo: Path, journal: _Journal, planned: ClaimRow | None) -> str | None:
    return claim_rework_row(
        repo=repo, journal=journal, item_id=_ROW, dispatch_id=_DISPATCH, planned=planned
    )


def test_a_disabled_pass_plans_on_no_read(tmp_path: Path) -> None:
    """Before the cutover an admission states no decision, so nothing is read for one."""
    repo = _repo(tmp_path=tmp_path, claim_tokens=False)
    _ = _marked_row()

    rows = planned_claim_rows(repo=repo, candidates=[_item(item_id=_ROW, status="active")])

    assert rows == {}


def test_an_enabled_pass_reads_each_active_row_it_may_admit_and_no_other(tmp_path: Path) -> None:
    """A groom-door claim among the candidates, and each listed row the accounting marked."""
    repo = _repo(tmp_path=tmp_path)
    _ = _marked_row()
    ready = _item(item_id="bd-ib-ready", status="ready")
    door_claimed = _item(item_id="bd-ib-door", status="active")
    unmarked = _item(item_id="bd-ib-other", status="active")
    for filed in (ready, door_claimed, unmarked):
        append_work_item(path=_config(), item=filed)

    rows = planned_claim_rows(
        repo=repo,
        candidates=[ready, door_claimed],
        items=[ready, door_claimed, unmarked, _item(item_id=_ROW, status="active")],
        rework_ids=(_ROW,),
    )

    assert rows == {
        "bd-ib-door": ClaimRow(status="active", assignee="fabro", stamp=None),
        _ROW: ClaimRow(status="active", assignee="fabro", stamp=_previous_stamp()),
    }


def test_a_disabled_rework_claim_writes_nothing_and_lets_the_row_launch(tmp_path: Path) -> None:
    repo = _repo(tmp_path=tmp_path, claim_tokens=False)
    client, token = _marked_row()
    before = _snapshot(client=client)
    journal = _Journal()

    refusal = _claim(repo=repo, journal=journal, planned=None)

    assert refusal is None
    assert _snapshot(client=client) == before
    assert client.show_issue(issue_id=token)["status"] != "closed"
    assert journal.records == []


def test_an_enabled_rework_claim_replaces_the_stamp_under_the_won_token(tmp_path: Path) -> None:
    repo = _repo(tmp_path=tmp_path)
    client, token = _marked_row()
    journal = _Journal()

    refusal = _claim(repo=repo, journal=journal, planned=_planned())

    metadata = client.show_issue(issue_id=_ROW)["metadata"]
    won = json.loads(client.show_issue(issue_id=token)["close_reason"])
    assert refusal is None
    assert (won["writer"], won["intent"]) == ("dispatcher-admission", REWORK_ADMIT_INTENT)
    assert metadata[CLAIM_TOKEN_METADATA_KEY] == won["successor"]
    assert metadata[CLAIM_STAMP_METADATA_KEY]["dispatch_id"] == _DISPATCH
    assert metadata[CLAIM_STAMP_METADATA_KEY]["run_id"] is None
    assert journal.records == [
        {
            "work_item_id": _ROW,
            "stage": _PENDING_STAGE,
            "dispatch_id": _DISPATCH,
            "claim_stamped": True,
            "claim_stamp_failure_detail": None,
        }
    ]


def test_a_caller_that_planned_on_no_read_has_the_row_read_at_the_claim(tmp_path: Path) -> None:
    repo = _repo(tmp_path=tmp_path)
    client, token = _marked_row()

    refusal = _claim(repo=repo, journal=_Journal(), planned=None)

    assert refusal is None
    assert client.show_issue(issue_id=token)["status"] == "closed"
    assert client.show_issue(issue_id=_ROW)["metadata"][CLAIM_STAMP_METADATA_KEY]["run_id"] is None


def test_a_row_another_dispatch_stamped_since_the_plan_is_refused_uncontested(
    tmp_path: Path,
) -> None:
    """The claim row is no longer the one planned on, so the token is not even closed."""
    repo = _repo(tmp_path=tmp_path)
    client, token = _marked_row()
    planned = _planned()
    record_claim_stamp(
        path=_config(),
        work_item_id=_ROW,
        stamp=ClaimStamp(
            dispatch_id="01ANOTHERDISPATCH",
            dispatching_host="another-host",
            run_id=None,
            factory_name="hp",
            factory_server=None,
        ),
    )
    before = _snapshot(client=client)
    journal = _Journal()

    refusal = _claim(repo=repo, journal=journal, planned=planned)

    assert refusal == "claim-changed"
    assert _snapshot(client=client) == before
    assert client.show_issue(issue_id=token)["status"] != "closed"
    assert journal.stages() == [_REFUSED_STAGE]


def test_a_row_whose_marker_was_cleared_since_the_plan_is_refused(tmp_path: Path) -> None:
    """Still `active` and still stamped as planned, but no longer parked for rework."""
    repo = _repo(tmp_path=tmp_path)
    client, token = _marked_row(marked=False)
    before = _snapshot(client=client)

    refusal = _claim(repo=repo, journal=_Journal(), planned=_planned())

    assert refusal == "claim-changed"
    assert _snapshot(client=client) == before
    assert client.show_issue(issue_id=token)["status"] != "closed"


def test_a_pending_stamp_that_cannot_be_built_clears_the_previous_one_and_says_why(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The row must not stay stamped with a run its new dispatch is not running."""
    repo = _repo(tmp_path=tmp_path)
    client, token = _marked_row()
    journal = _Journal()

    def _no_route(**_: object) -> object:
        raise BeadsConnectionError(detail="the tenant did not answer")

    monkeypatch.setattr(_dispatcher_claim_stamp, "unrecorded_dispatch_factory_target", _no_route)

    refusal = _claim(repo=repo, journal=journal, planned=_planned())

    metadata = client.show_issue(issue_id=_ROW)["metadata"]
    assert refusal is None
    assert client.show_issue(issue_id=token)["status"] == "closed"
    assert metadata[CLAIM_STAMP_METADATA_KEY] is None
    assert claim_row_for(path=_config(), work_item_id=_ROW).stamp is None
    assert [record["claim_stamped"] for record in journal.records] == [False]
    assert "claim stamp could not be built: BeadsConnectionError" in str(
        journal.records[0]["claim_stamp_failure_detail"]
    )
