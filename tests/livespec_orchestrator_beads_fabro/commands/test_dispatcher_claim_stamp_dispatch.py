"""The two dispatch-time claim-stamp writes, at the surfaces that write them.

`test_store_dispatch_claim.py` covers the stamp VALUE and its one writer. This
covers the PRODUCTION callers — admission, and the stamp written when the run
is learned — because the writer existing is worth nothing if nothing calls it:
a reconciler reading an unstamped row grades it `claim-unattributable`, which
names the wrong remedy, and a reconciler reading a row still carrying the
PREVIOUS dispatch's run id releases a live dispatch's claim.

THE PENDING STAMP'S WHOLE JOB IS TO BE DISTINGUISHABLE FROM THE CLAIM IT
REPLACES, so the fixture seeds a previous RUN stamp rather than a clean row.
That is the state the defect actually occurs in — an item released by a human
valve and admitted again — and a test seeding no stamp would pass against an
implementation that wrote the pending stamp only onto rows that had none.

THE ORDERING TEST IS NOT CEREMONY. `record_claim_stamp`'s docstring promises
the pending stamp lands in a write that PRECEDES the `ready -> active`
transition, which is what leaves no instant in which the row is `active` under
this dispatch while still stamped with the previous dispatch's run. A claim in
a docstring that nothing binds is a claim that drifts.
"""

from __future__ import annotations

import importlib
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

import pytest
from livespec_orchestrator_beads_fabro._beads_client import reset_fake_singleton
from livespec_orchestrator_beads_fabro._store_dispatch_claim import (
    ClaimStamp,
    claim_row_for,
    record_claim_stamp,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_dispatching_host import (
    DISPATCHING_HOST_ENV_VAR,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import JournalFile
from livespec_orchestrator_beads_fabro.commands._dispatcher_paths import store_config
from livespec_orchestrator_beads_fabro.commands._dispatcher_plan import build_plan
from livespec_orchestrator_beads_fabro.store import append_work_item
from livespec_orchestrator_beads_fabro.types import WorkItem

_PACKAGE = "livespec_orchestrator_beads_fabro.commands"

_ITEM_ID = "bd-ib-claimstamp"
_PREVIOUS_DISPATCH = "01PREVIOUSDISPATCH"
_PREVIOUS_RUN = "01PREVIOUSRUN"
_NEW_RUN = "01NEWRUN"
_HOST = "admitting-host"
_FACTORY = "hp"
_SERVER = "https://hp-xubuntu.perch-rudd.ts.net:32276"


@pytest.fixture(autouse=True)
def _fresh_tenant(monkeypatch: pytest.MonkeyPatch) -> Any:
    monkeypatch.setenv("LIVESPEC_BEADS_FAKE", "1")
    monkeypatch.setenv(DISPATCHING_HOST_ENV_VAR, _HOST)
    reset_fake_singleton()
    yield
    reset_fake_singleton()


@dataclass(kw_only=True)
class _Journal:
    records: list[dict[str, object]] = field(default_factory=list)

    def append(self, *, record: dict[str, object]) -> None:
        self.records.append(record)


def _repo(*, tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    _ = (repo / ".livespec.jsonc").write_text(
        """
        {
          "livespec-orchestrator-beads-fabro": {
            "connection": {"prefix": "bd-ib", "tenant": "test-tenant", "fake": true},
            "dispatcher": {
              "default_factory": "hp",
              "factories": {
                "hp": {"server": "https://hp-xubuntu.perch-rudd.ts.net:32276"}
              }
            }
          }
        }
        """,
        encoding="utf-8",
    )
    return repo


def _item(**overrides: object) -> WorkItem:
    base = WorkItem(
        id=_ITEM_ID,
        type="bug",
        status="ready",
        title="A dispatchable slice",
        description="Implement the slice.",
        origin="freeform",
        gap_id=None,
        rank="a0",
        assignee=None,
        depends_on=(),
        captured_at="2026-10-18T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
    )
    return replace(base, **overrides)


def _previous_run_stamp() -> ClaimStamp:
    """The claim the PREVIOUS dispatch left behind, run id and all."""
    return ClaimStamp(
        dispatch_id=_PREVIOUS_DISPATCH,
        dispatching_host=_HOST,
        run_id=_PREVIOUS_RUN,
        factory_name=_FACTORY,
        factory_server=_SERVER,
    )


def _seed(*, repo: Path, item: WorkItem, stamp: ClaimStamp) -> None:
    """Seed the row AND a prior claim stamp. The stamp is required, not optional.

    Every case here starts from a row that already carries a claim, because an
    unstamped row is the state an implementation writing the pending stamp only
    onto fresh rows would also satisfy.
    """
    append_work_item(path=store_config(repo=repo), item=item)
    record_claim_stamp(path=store_config(repo=repo), work_item_id=item.id, stamp=stamp)


def _stamp_now(*, repo: Path) -> ClaimStamp | None:
    return claim_row_for(path=store_config(repo=repo), work_item_id=_ITEM_ID).stamp


def _admit(*, repo: Path, monkeypatch: pytest.MonkeyPatch, journal: Any) -> Any:
    """Drive the real admission valve, with only its status write stubbed out.

    The status write is stubbed rather than exercised because this is a test
    about the STAMP: the `ready -> active` transition is the subject of the
    valve's own tests, and leaving it real would make the fake tenant's row
    disagree with the `candidates` list admission was handed.
    """
    admission_module = importlib.import_module(f"{_PACKAGE}._dispatcher_admission")
    eligibility_module = importlib.import_module(f"{_PACKAGE}._dispatcher_admission_eligibility")
    monkeypatch.setattr(eligibility_module, "read_dispatch_labels", lambda **_: ())
    monkeypatch.setattr(admission_module, "update_work_item_status", lambda **_: None)
    return admission_module.admit_and_select(
        repo=repo,
        items=[],
        candidates=[_item()],
        journal=journal,
        enforce_cap=False,
    )


def test_admission_replaces_the_run_stamp_with_a_pending_stamp(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A fresh admission's stamp names its own dispatch, its host, and no run."""
    repo = _repo(tmp_path=tmp_path)
    _seed(repo=repo, item=_item(), stamp=_previous_run_stamp())
    journal = JournalFile(path=repo / "journal.jsonl")

    admitted = _admit(repo=repo, monkeypatch=monkeypatch, journal=journal)

    assert [item.id for item in admitted.admitted] == [_ITEM_ID]
    stamp = _stamp_now(repo=repo)
    assert stamp is not None
    # The run id is the load-bearing field: a stamp still naming the PREVIOUS
    # run is exactly what releases a live dispatch's claim.
    assert stamp.run_id is None
    assert stamp.pending is True
    assert stamp.dispatching_host == _HOST
    assert stamp.factory_name == _FACTORY
    assert stamp.factory_server == _SERVER
    # A NEW dispatch id, not the one the replaced claim carried.
    assert stamp.dispatch_id is not None
    assert stamp.dispatch_id != _PREVIOUS_DISPATCH


def test_the_pending_stamp_is_written_before_the_ready_to_active_transition(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """No instant has the row `active` under this dispatch and stamped with the old run."""
    repo = _repo(tmp_path=tmp_path)
    _seed(repo=repo, item=_item(), stamp=_previous_run_stamp())
    journal = JournalFile(path=repo / "journal.jsonl")
    admission_module = importlib.import_module(f"{_PACKAGE}._dispatcher_admission")
    eligibility_module = importlib.import_module(f"{_PACKAGE}._dispatcher_admission_eligibility")
    monkeypatch.setattr(eligibility_module, "read_dispatch_labels", lambda **_: ())
    observed: list[str | None] = []

    def _record_stamp_at_transition(**_kwargs: object) -> None:
        stamp = _stamp_now(repo=repo)
        observed.append(None if stamp is None else stamp.run_id)

    monkeypatch.setattr(admission_module, "update_work_item_status", _record_stamp_at_transition)

    _ = admission_module.admit_and_select(
        repo=repo,
        items=[],
        candidates=[_item()],
        journal=journal,
        enforce_cap=False,
    )

    # Read AT the transition, the stamp is already pending — so the window in
    # which an `active` row still names the previous run never exists.
    assert observed == [None]


def test_the_run_stamp_written_when_the_run_is_learned_names_the_dispatching_host(
    tmp_path: Path,
) -> None:
    """Learning the run fills the claim in; the host is what scopes its recovery."""
    repo = _repo(tmp_path=tmp_path)
    _seed(
        repo=repo,
        item=_item(status="active", assignee="fabro"),
        stamp=replace(_previous_run_stamp(), run_id=None, dispatch_id="01THISDISPATCH"),
    )
    module = importlib.import_module(f"{_PACKAGE}._dispatcher_run_stamp")
    journal = _Journal()

    _ = module.stamp_dispatch_run(
        plan=build_plan(
            repo=repo,
            work_item_id=_ITEM_ID,
            workflow_toml=repo / "workflow.toml",
            goal_file=repo / "goal.md",
            fabro_bin="fabro",
            janitor=None,
            janitor_checkout=repo / "janitor",
            fabro_factory_name=_FACTORY,
            fabro_factory_server=_SERVER,
        ),
        journal=journal,
        run_id=_NEW_RUN,
    )

    stamp = _stamp_now(repo=repo)
    assert stamp is not None
    assert stamp.run_id == _NEW_RUN
    assert stamp.dispatching_host == _HOST
    assert stamp.factory_name == _FACTORY
    assert stamp.factory_server == _SERVER
    assert stamp.pending is False
    # The dispatch the admission stamp named is PRESERVED rather than dropped:
    # the four facts are only meaningful as a set.
    assert stamp.dispatch_id == "01THISDISPATCH"
