"""The pending claim stamp names the factory the dispatch is ROUTED to.

`test_dispatcher_claim_stamp_dispatch.py` covers what the pending stamp says
about the DISPATCH — its own id, its host, and the absence of a run. This covers
what it says about the FACTORY, which is a different claim and fails for a
different reason: the stamp is written at admission, before any factory has been
recorded, so the name it carries comes from a resolution of its own, and that
resolution has to answer the same way the dispatch's does.

EVERY CASE SEEDS A RECORDED PIN, and the pin always names a DIFFERENT declared
factory from the one the case routes to. That is the state the defect occurs in:
an item dispatched fifteen times to one factory and then routed elsewhere. A
case with no recorded pin passes against a resolution that consults nothing but
the pin, because there is then nothing for the pin to win.
"""

from __future__ import annotations

import argparse
import importlib
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest
from livespec_orchestrator_beads_fabro._beads_client import reset_fake_singleton
from livespec_orchestrator_beads_fabro._store_dispatch_claim import (
    ClaimStamp,
    claim_row_for,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_dispatching_host import (
    DISPATCHING_HOST_ENV_VAR,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import DispatchOutcome
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import JournalFile
from livespec_orchestrator_beads_fabro.commands._dispatcher_paths import store_config
from livespec_orchestrator_beads_fabro.store import (
    append_work_item,
    record_dispatch_factory,
)
from livespec_orchestrator_beads_fabro.types import WorkItem

_PACKAGE = "livespec_orchestrator_beads_fabro.commands"

_ITEM_ID = "bd-ib-routedfactory"
_HOST = "admitting-host"
_ENV_FACTORY_VAR = "LIVESPEC_FABRO_FACTORY"

# The pin is the DEFAULT factory and the routed one is not, which is what makes
# a routed case able to fail for the right reason: a resolution that fell
# through to `dispatcher.default_factory` would answer the pin's name too.
_PINNED = "hp"
_ROUTED = "petri"
_ROUTED_SERVER = "https://gmktec-xubuntu.perch-rudd.ts.net:32276"

# The outcome the stubbed launch hands back, by IDENTITY: an admitted target is
# what reaches the launch at all, so the object coming out is what says the
# valve admitted rather than held or refused.
_LAUNCHED = DispatchOutcome(
    work_item_id=_ITEM_ID,
    status="succeeded",
    stage="done",
    pr_number=None,
    merge_sha=None,
    detail="stubbed launch",
)


@pytest.fixture(autouse=True)
def _fresh_tenant(monkeypatch: pytest.MonkeyPatch) -> Any:
    monkeypatch.setenv("LIVESPEC_BEADS_FAKE", "1")
    monkeypatch.setenv(DISPATCHING_HOST_ENV_VAR, _HOST)
    reset_fake_singleton()
    yield
    reset_fake_singleton()


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
                "hp": {"server": "https://hp-xubuntu.perch-rudd.ts.net:32276"},
                "petri": {"server": "https://gmktec-xubuntu.perch-rudd.ts.net:32276"}
              }
            }
          }
        }
        """,
        encoding="utf-8",
    )
    return repo


def _item() -> WorkItem:
    return WorkItem(
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
        captured_at="2026-10-19T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
    )


def _seed_pinned(*, repo: Path) -> None:
    """Seed the row AND the recorded factory pin every case has to overcome."""
    append_work_item(path=store_config(repo=repo), item=_item())
    record_dispatch_factory(path=store_config(repo=repo), work_item_id=_ITEM_ID, factory=_PINNED)


def _stamp_now(*, repo: Path) -> ClaimStamp | None:
    return claim_row_for(path=store_config(repo=repo), work_item_id=_ITEM_ID).stamp


def _admit(*, repo: Path, monkeypatch: pytest.MonkeyPatch) -> Any:
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
        candidates=[replace(_item())],
        journal=JournalFile(path=repo / "journal.jsonl"),
        enforce_cap=False,
    )


def test_an_environment_routed_dispatch_stamps_the_routed_factory_over_the_pin(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`LIVESPEC_FABRO_FACTORY` outranks the item's recorded pin, at the stamp too.

    This is the only routing mechanism `drive.py` has, and it is used precisely
    when the recorded factory identity is the point. The dispatch resolution
    already honours it above the pin; a stamp that does not names a factory the
    run never runs on, and the reconcile pass then holds the claim against that
    factory while reporting the stamp faithfully.

    The SERVER is asserted beside the name because the stamp carries both and
    the reconcile survey reaches the factory through the server: a name that
    moved while the server stayed behind is the same wrong answer one field
    later.
    """
    repo = _repo(tmp_path=tmp_path)
    _seed_pinned(repo=repo)
    monkeypatch.setenv(_ENV_FACTORY_VAR, _ROUTED)

    admitted = _admit(repo=repo, monkeypatch=monkeypatch)

    assert [item.id for item in admitted.admitted] == [_ITEM_ID]
    stamp = _stamp_now(repo=repo)
    assert stamp is not None
    assert stamp.factory_name == _ROUTED
    assert stamp.factory_server == _ROUTED_SERVER


def test_a_flag_routed_dispatch_stamps_the_flag_factory_over_the_pin(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`--factory` reaches the admission stamp, through the one path that carries it.

    Driven through `admit_and_dispatch_target` — `dispatch --item`'s own
    admit-and-launch step — rather than by handing the valve a name directly,
    because the name is not the claim: a valve that resolves a name it is GIVEN
    says nothing about whether the flag an operator typed ever arrives there,
    and that is the half the environment case cannot cover. Everything past the
    valve is stubbed, since the subject is the stamp the valve writes and not
    the run it then launches.

    The environment variable is deliberately UNSET, so the flag is the only
    thing that can carry the routed name: with it set, a build honouring the
    variable alone would pass while `--factory` still never reached the stamp.
    """
    repo = _repo(tmp_path=tmp_path)
    _seed_pinned(repo=repo)
    monkeypatch.delenv(_ENV_FACTORY_VAR, raising=False)
    launch_module = importlib.import_module(f"{_PACKAGE}._dispatcher_run_launch")
    routing_module = importlib.import_module(f"{_PACKAGE}._dispatcher_recovery_routing")
    eligibility_module = importlib.import_module(f"{_PACKAGE}._dispatcher_admission_eligibility")
    admission_module = importlib.import_module(f"{_PACKAGE}._dispatcher_admission")
    monkeypatch.setattr(eligibility_module, "read_dispatch_labels", lambda **_: ())
    monkeypatch.setattr(admission_module, "update_work_item_status", lambda **_: None)
    monkeypatch.setattr(launch_module, "post_admission_publish_branch_reclaim", lambda **_: None)
    monkeypatch.setattr(launch_module, "recovery_launch_args", lambda **_: argparse.Namespace())
    monkeypatch.setattr(launch_module, "dispatch_one", lambda **_: _LAUNCHED)

    outcome = launch_module.admit_and_dispatch_target(
        args=argparse.Namespace(factory=_ROUTED, journal=None),
        repo=repo,
        items=[],
        target=_item(),
        journal=JournalFile(path=repo / "journal.jsonl"),
        janitor=None,
        marked=False,
        routing=routing_module.RecoveryRouting(routes=()),
    )

    # The valve ADMITTED the target rather than holding or refusing it, which is
    # what makes the stamp below this dispatch's own and not a leftover.
    assert outcome is _LAUNCHED
    stamp = _stamp_now(repo=repo)
    assert stamp is not None
    assert stamp.factory_name == _ROUTED
    assert stamp.factory_server == _ROUTED_SERVER
