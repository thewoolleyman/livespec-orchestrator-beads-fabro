"""The groom door and the groom apply seam, after the claim-token cutover.

Both seams change a dispatch claim, so with `dispatcher.claim_tokens` true each
writes the item only after winning its current claim token
(`SPECIFICATION/contracts.md`, "Claim tokens"):

- THE DOOR takes a `backlog` item to `active` under an assignee and a
  groom-variant pin. Before the cutover the pin is a write of its own, ahead of
  the status. After it the pin rides the ONE write that claims the item, because
  a door that does not win must write nothing, the pin included.
- THE APPLY SEAM releases the claim back to `backlog` before it files the
  approved cut. A release that loses the token files nothing: the filing would
  close an original some other writer now holds.

The disabled behaviour of both seams is asserted in their own modules,
`test_dispatcher_groom_door.py` and `test_dispatcher_groom_apply.py`.
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
    CLAIM_TOKEN_METADATA_KEY,
    create_claim_token,
)
from livespec_orchestrator_beads_fabro._store_dispatch_workflow import (
    dispatch_workflow_for,
    record_dispatch_workflow,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_claim_guard import (
    TRANSITION_OBSERVATIONS,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_dispatch_lock import (
    live_dispatch_lock,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_groom_apply import (
    GROOM_CUT_FILED_STAGE,
    GROOM_CUT_REFUSED_STAGE,
    file_groom_plan,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_groom_door import (
    GROOM_DISPATCH_STAGE,
    GROOM_DOOR_CLAIM_REFUSED,
    GROOM_DOOR_REFUSED_STAGE,
    GroomDispatch,
    GroomDoorRefusal,
    groom_dispatch,
)
from livespec_orchestrator_beads_fabro.store import append_work_item, read_work_items
from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem, WorkItemStatus

_ITEM_ID = "bd-ib-groom-token"
_RUN_ID = "01GROOMTOKENRUN"
_GROOM_VARIANT = "groom-cut"
_GROOM_DIR = ".fabro/workflows/groom-cut"
# The repository's directory name is the identity a slice's `repo=` is matched against.
_LOCAL_REPO = "repo"
_SLICE = "Move the filing host-side"
_PLAN = (
    "livespec-groom-plan | approver=thewoolleyman | route=resolve-blocked ready valve"
    f" ;; slice={_SLICE} | tier=factory | repo={_LOCAL_REPO}"
    " | acceptance=The Dispatcher files the cut. | blockers=none | spec=no"
    " | scope=Read the plan off the terminated run and file it."
)
_ANOTHER_WRITER = "another writer won this token"
_REFUSED_STAGE = "claim-write-refused"


@pytest.fixture(autouse=True)
def _fresh_tenant() -> object:
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
        prefix="livespec-impl-beads",
        server_user="livespec-impl-beads",
        database="livespec-impl-beads",
        bd_path="bd",
        fake=True,
    )


def _repo(*, tmp_path: Path) -> Path:
    """A target registering one groom variant, cut over to claim tokens."""
    repo = tmp_path / _LOCAL_REPO
    target = repo / _GROOM_DIR
    target.mkdir(parents=True)
    _ = (target / "workflow.toml").write_text(
        '[workflow]\ngraph = "workflow.fabro"\n\n[run.inputs]\nworkflow_kind = "groom"\n',
        encoding="utf-8",
    )
    _ = (repo / ".livespec.jsonc").write_text(
        json.dumps(
            {
                "livespec-orchestrator-beads-fabro": {
                    "connection": {
                        "tenant": "livespec-impl-beads",
                        "prefix": "livespec-impl-beads",
                        "server_user": "livespec-impl-beads",
                        "database": "livespec-impl-beads",
                        "bd_path": "bd",
                        "fake": True,
                    },
                    "dispatcher": {
                        "workflows": {_GROOM_VARIANT: _GROOM_DIR},
                        "claim_tokens": True,
                    },
                }
            }
        ),
        encoding="utf-8",
    )
    return repo


def _filed(
    *, status: WorkItemStatus, assignee: str | None
) -> tuple[WorkItem, FakeBeadsClient, str]:
    """The regroom target, naming an open current token."""
    item = WorkItem(
        id=_ITEM_ID,
        type="task",
        status=status,
        title="An epic with more than one coherent done",
        description="It carries more than one coherent done.",
        origin="freeform",
        gap_id=None,
        rank="m",
        assignee=assignee,
        depends_on=(),
        captured_at="2026-11-06T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
        acceptance_criteria="- The epic is decomposed.",
    )
    append_work_item(path=_config(), item=item)
    client = make_beads_client(config=_config())
    assert isinstance(client, FakeBeadsClient)
    token = create_claim_token(client=client)
    metadata = dict(client.show_issue(issue_id=_ITEM_ID)["metadata"])
    metadata[CLAIM_TOKEN_METADATA_KEY] = token
    client.update_issue(issue_id=_ITEM_ID, metadata=metadata, names_claim_token=True)
    return item, client, token


def _snapshot(*, client: FakeBeadsClient) -> dict[str, object]:
    return copy.deepcopy(client.show_issue(issue_id=_ITEM_ID))


def _won(*, client: FakeBeadsClient, token: str) -> tuple[object, object]:
    reason = json.loads(client.show_issue(issue_id=token)["close_reason"])
    return reason["writer"], reason["intent"]


def _lose_the_token(
    *, client: FakeBeadsClient, token: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    close = client.close_issue_without_verdict

    def _raced(*, issue_id: str, reason: str) -> None:
        if issue_id == token:
            close(issue_id=issue_id, reason=_ANOTHER_WRITER)
        close(issue_id=issue_id, reason=reason)

    monkeypatch.setattr(client, "close_issue_without_verdict", _raced)


def test_an_enabled_door_claims_the_item_and_pins_the_variant_in_one_won_write(
    tmp_path: Path,
) -> None:
    repo = _repo(tmp_path=tmp_path)
    item, client, token = _filed(status="backlog", assignee=None)
    journal = _Journal()

    opened = groom_dispatch(repo=repo, item=item, variant=_GROOM_VARIANT, journal=journal)

    record = client.show_issue(issue_id=_ITEM_ID)
    successor = json.loads(client.show_issue(issue_id=token)["close_reason"])["successor"]
    assert isinstance(opened, GroomDispatch)
    assert (record["status"], record["assignee"]) == ("active", opened.assignee)
    assert dispatch_workflow_for(path=_config(), work_item_id=_ITEM_ID) == _GROOM_VARIANT
    assert _won(client=client, token=token) == ("dispatcher-admission", "groom-door")
    assert record["metadata"][CLAIM_TOKEN_METADATA_KEY] == successor
    assert live_dispatch_lock(repo=repo, work_item_id=_ITEM_ID) is not None
    assert journal.stages()[-1:] == [GROOM_DISPATCH_STAGE]
    assert _REFUSED_STAGE not in journal.stages()


def test_an_enabled_door_that_loses_the_token_writes_nothing_not_even_the_pin(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _repo(tmp_path=tmp_path)
    item, client, token = _filed(status="backlog", assignee=None)
    before = _snapshot(client=client)
    _lose_the_token(client=client, token=token, monkeypatch=monkeypatch)
    journal = _Journal()

    refusal = groom_dispatch(repo=repo, item=item, variant=_GROOM_VARIANT, journal=journal)

    assert isinstance(refusal, GroomDoorRefusal)
    assert refusal.cause == GROOM_DOOR_CLAIM_REFUSED
    assert "claim-changed" in refusal.detail
    assert _snapshot(client=client) == before
    assert dispatch_workflow_for(path=_config(), work_item_id=_ITEM_ID) is None
    assert live_dispatch_lock(repo=repo, work_item_id=_ITEM_ID) is None
    assert journal.stages()[-2:] == [_REFUSED_STAGE, GROOM_DOOR_REFUSED_STAGE]
    assert GROOM_DISPATCH_STAGE not in journal.stages()


def _apply(*, repo: Path, item: WorkItem, journal: _Journal) -> bool:
    return file_groom_plan(
        repo=repo, item=item, text=_PLAN, variant=_GROOM_VARIANT, run_id=_RUN_ID, journal=journal
    )


def _titles() -> set[str]:
    return {item.title for item in read_work_items(path=_config())}


def test_an_enabled_apply_releases_the_claim_under_the_won_token_and_files_the_cut(
    tmp_path: Path,
) -> None:
    repo = _repo(tmp_path=tmp_path)
    item, client, token = _filed(status="active", assignee="dispatcher")
    record_dispatch_workflow(path=_config(), work_item_id=_ITEM_ID, workflow=_GROOM_VARIANT)
    journal = _Journal()

    filed = _apply(repo=repo, item=item, journal=journal)

    assert filed is True
    assert _won(client=client, token=token) == ("dispatcher-terminal", "groom-apply-release")
    assert _SLICE in _titles()
    assert client.show_issue(issue_id=_ITEM_ID)["status"] == "closed"
    assert journal.stages() == [GROOM_CUT_FILED_STAGE]


def test_an_enabled_apply_that_loses_the_token_releases_nothing_and_files_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _repo(tmp_path=tmp_path)
    item, client, token = _filed(status="active", assignee="dispatcher")
    before = _snapshot(client=client)
    _lose_the_token(client=client, token=token, monkeypatch=monkeypatch)
    journal = _Journal()

    filed = _apply(repo=repo, item=item, journal=journal)

    assert filed is False
    assert _snapshot(client=client) == before
    assert _SLICE not in _titles()
    assert journal.stages() == [_REFUSED_STAGE, GROOM_CUT_REFUSED_STAGE]
    assert journal.records[1]["reason"] == "GroomExitRefusedError"
    assert "claim-changed" in str(journal.records[1]["detail"])


def test_an_enabled_door_handed_a_stale_backlog_read_does_not_claim_an_item_already_opened(
    tmp_path: Path,
) -> None:
    """Sequential, not racing: the second door finds the item `active` and stands down."""
    repo = _repo(tmp_path=tmp_path)
    item, client, token = _filed(status="backlog", assignee=None)
    second_journal = _Journal()

    first = groom_dispatch(repo=repo, item=item, variant=_GROOM_VARIANT, journal=_Journal())
    as_first_left_it = _snapshot(client=client)
    second = groom_dispatch(repo=repo, item=item, variant=_GROOM_VARIANT, journal=second_journal)

    successor = json.loads(client.show_issue(issue_id=token)["close_reason"])["successor"]
    assert isinstance(first, GroomDispatch)
    assert isinstance(second, GroomDoorRefusal)
    assert second.cause == GROOM_DOOR_CLAIM_REFUSED
    assert _snapshot(client=client) == as_first_left_it
    assert client.show_issue(issue_id=successor)["status"] != "closed"
    assert GROOM_DISPATCH_STAGE not in second_journal.stages()


def test_an_enabled_apply_of_a_claim_another_writer_already_moved_releases_nothing(
    tmp_path: Path,
) -> None:
    repo = _repo(tmp_path=tmp_path)
    item, client, token = _filed(status="active", assignee="dispatcher")
    client.update_issue(issue_id=_ITEM_ID, status="blocked")
    before = _snapshot(client=client)
    journal = _Journal()

    filed = _apply(repo=repo, item=item, journal=journal)

    assert filed is False
    assert _snapshot(client=client) == before
    assert client.show_issue(issue_id=token)["status"] != "closed"
    assert _SLICE not in _titles()
    assert journal.stages() == [_REFUSED_STAGE, GROOM_CUT_REFUSED_STAGE]
