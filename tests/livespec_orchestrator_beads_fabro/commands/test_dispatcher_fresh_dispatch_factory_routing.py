"""A FRESH dispatch does not read the item's recorded factory as a pin.

`SPECIFICATION/contracts.md` section "Factory addresses resolved from a host
registry" fixes the selection order — an explicit `--factory`, then
`LIVESPEC_FABRO_FACTORY`, then, "for a resume only, the item's recorded
factory", then overflow selection or `dispatcher.default_factory` — and says
outright that "a fresh dispatch MUST NOT read the item's recorded factory as a
pin" and that the admission claim stamp "MUST apply the same order, using the
route recovery routing assigned before the admission valve".

WHY EVERY CASE SEEDS A RECORDED PIN THAT IS NOT THE DEFAULT. That is the state
the defect occurs in: an item that once ran on one factory routes back to it on
its next dispatch, however the repository's default has moved since. A case
whose pin names the default factory passes against a resolution that reads the
pin unconditionally, because there is then nothing for the pin to win — the two
answers coincide. The pin here is a STILL-DECLARED factory, for the same reason:
a name `dispatcher.factories` no longer declares is already ignored, so a case
built on a stale name cannot distinguish the rule from its one pre-existing
escape.

WHY THE STAMP AND THE SUBMISSION ARE ASSERTED TOGETHER. They are two resolutions
of one order, taken at different moments by different code — the pending claim
stamp at admission, through `unrecorded_dispatch_factory_target`, and the launch
through `args_with_dispatch_factory_target` — and the measured failure mode of
letting them drift is a claim held against a factory the run never reached. A
test that read only one of them would pass for a build that moved the other.

WHY THE ROUTE IS CONSTRUCTED RATHER THAN MEASURED. Recovery routing's own
decision is the subject of its own tests; what is under test here is what each
launch path DOES with the route it was handed. Handing the path a route also
makes the resume case expressible at all: a resume route is reached only through
a released item with a live anchor, which a unit tier cannot stage without
standing in for the forge.
"""

from __future__ import annotations

import argparse
import importlib
from pathlib import Path
from typing import Any

import pytest
from livespec_orchestrator_beads_fabro._beads_client import reset_fake_singleton
from livespec_orchestrator_beads_fabro._store_dispatch_claim import ClaimStamp, claim_row_for
from livespec_orchestrator_beads_fabro.commands._dispatcher_dispatching_host import (
    DISPATCHING_HOST_ENV_VAR,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import DispatchOutcome
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import JournalFile
from livespec_orchestrator_beads_fabro.commands._dispatcher_paths import store_config
from livespec_orchestrator_beads_fabro.commands._dispatcher_recovery_routes import (
    ROUTE_FRESH,
    RecoveryRoute,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_recovery_routing import RecoveryRouting
from livespec_orchestrator_beads_fabro.store import (
    append_work_item,
    dispatch_factory_for,
    record_dispatch_factory,
)
from livespec_orchestrator_beads_fabro.types import WorkItem

_PACKAGE = "livespec_orchestrator_beads_fabro.commands"

_ITEM_ID = "bd-ib-freshfactory"
_HOST = "admitting-host"
_ENV_FACTORY_VAR = "LIVESPEC_FABRO_FACTORY"

# The repository's default, and the factory the item has been running on. They
# are deliberately DIFFERENT declared entries: see the module docstring.
_DEFAULT = "petri"
_DEFAULT_SERVER = "https://gmktec-xubuntu.perch-rudd.ts.net:32276"
_RECORDED = "hp"

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
    monkeypatch.delenv(_ENV_FACTORY_VAR, raising=False)
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
              "default_factory": "petri",
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
        captured_at="2026-10-23T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
    )


def _seed_pinned(*, repo: Path) -> None:
    """Seed the row AND the recorded factory pin every case has to overcome."""
    append_work_item(path=store_config(repo=repo), item=_item())
    record_dispatch_factory(path=store_config(repo=repo), work_item_id=_ITEM_ID, factory=_RECORDED)


def _stamp_now(*, repo: Path) -> ClaimStamp | None:
    return claim_row_for(path=store_config(repo=repo), work_item_id=_ITEM_ID).stamp


def _launch_through(
    *,
    repo: Path,
    monkeypatch: pytest.MonkeyPatch,
    routing: RecoveryRouting,
    factory: str | None = None,
) -> argparse.Namespace:
    """Drive `dispatch --item`'s admit-and-launch step and return the launch args.

    Only what LEAVES the process is stood in for: the ledger status write, the
    dispatch-label read, the publish-branch reclaim and the Fabro launch itself.
    The admission valve, its claim stamp and the per-item argument pins all run
    for real, because they are between them the whole subject — a stubbed pin
    would make this a test of the stub's own answer.
    """
    launch_module = importlib.import_module(f"{_PACKAGE}._dispatcher_run_launch")
    eligibility_module = importlib.import_module(f"{_PACKAGE}._dispatcher_admission_eligibility")
    admission_module = importlib.import_module(f"{_PACKAGE}._dispatcher_admission")
    monkeypatch.setattr(eligibility_module, "read_dispatch_labels", lambda **_: ())
    monkeypatch.setattr(admission_module, "update_work_item_status", lambda **_: None)
    monkeypatch.setattr(launch_module, "post_admission_publish_branch_reclaim", lambda **_: None)
    launched: list[argparse.Namespace] = []

    def _dispatch(**kwargs: Any) -> DispatchOutcome:
        launched.append(kwargs["args"])
        return _LAUNCHED

    monkeypatch.setattr(launch_module, "dispatch_one", _dispatch)

    outcome = launch_module.admit_and_dispatch_target(
        args=argparse.Namespace(
            factory=factory,
            journal=None,
            fabro_bin=None,
            workflow_name=None,
        ),
        repo=repo,
        items=[],
        target=_item(),
        journal=JournalFile(path=repo / "journal.jsonl"),
        janitor=None,
        marked=False,
        routing=routing,
    )

    # The valve ADMITTED the target rather than holding or refusing it, which is
    # what makes the stamp and the launch args below this dispatch's own.
    assert outcome is _LAUNCHED
    return launched[0]


def test_a_fresh_dispatch_of_a_pinned_item_is_stamped_with_and_sent_to_the_default(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A `fresh` route ignores the recorded pin, at the stamp and at the launch.

    The item records a still-declared factory that is NOT the configured
    default, nothing routes this dispatch, and recovery routing assigned it the
    `fresh` route — so the pin has no layer to win on and both resolutions must
    answer `dispatcher.default_factory`.

    The recorded pin is asserted to have MOVED as well, because the dispatch
    writes it: an item left recording the old factory would route back to it the
    next time any surface read that record as a pin.
    """
    repo = _repo(tmp_path=tmp_path)
    _seed_pinned(repo=repo)

    launched = _launch_through(
        repo=repo,
        monkeypatch=monkeypatch,
        routing=RecoveryRouting(routes=(RecoveryRoute(work_item_id=_ITEM_ID, route=ROUTE_FRESH),)),
    )

    stamp = _stamp_now(repo=repo)
    assert stamp is not None
    assert stamp.factory_name == _DEFAULT
    assert stamp.factory_server == _DEFAULT_SERVER
    assert launched.fabro_factory_target.name == _DEFAULT
    assert launched.fabro_factory_target.server == _DEFAULT_SERVER
    assert dispatch_factory_for(path=store_config(repo=repo), work_item_id=_ITEM_ID) == _DEFAULT
