"""Scenario 26, through the real list-work-items command and the real store seam.

Binds `SPECIFICATION/scenarios.md` "## Scenario 26 — list-work-items emits lane
and lane_reason", whose heading-coverage entry owed an integration-tier test
"exercising user-observable Dispatcher/store behavior against the in-memory
`FakeBeadsClient`, never a unit-tier test".

SO THE THREE ITEMS LIVE IN ONE TENANT AND ARE READ BACK OFF ONE WIRE. The
scenario's three `Then`s are one claim about one `--json` payload, because a
lane is DERIVED rather than stored: the ready item's lane depends on the state
of the OTHER item it depends on. A reading that seeded each item into its own
tenant and asserted its lane in isolation would therefore pass against a build
that never consulted a dependency at all — the ready item would have no open
dependency to consult. The open dependency, the item that depends on it, and
the active item are all stored here, so the derivation has the whole population
it is defined over.

NOTHING IS STOOD IN. The items are written through the production
`append_work_item`, `main` resolves its own tenant connection out of a
committed `.livespec.jsonc` exactly as an operator's invocation does, and the
`lane` / `lane_reason` asserted below are the bytes the console consumes — not
a call of the lane function in isolation, which is what
`tests/livespec_orchestrator_beads_fabro/commands/test_list_work_items.py`
grades at the unit tier.

THE BLOCKED ITEM'S `lane_reason` IS ITS STORED `blocked_reason`, which is what
makes the two blocked rows discriminating: both emit lane `blocked`, and only
the reason says whether the item is waiting on a dependency the store can see
or on a human it cannot. A projection that emitted one constant reason for
every blocked row would satisfy neither assertion.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro._beads_client import reset_fake_singleton
from livespec_orchestrator_beads_fabro.commands.list_work_items import main
from livespec_orchestrator_beads_fabro.store import append_work_item
from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem

_DEPENDENCY = "bd-ib-lane-dep"
_READY_WITH_OPEN_DEPENDENCY = "bd-ib-lane-ready"
_STORED_BLOCKED = "bd-ib-lane-blocked"
_ACTIVE = "bd-ib-lane-active"


def _config() -> StoreConfig:
    return StoreConfig(
        tenant="livespec-impl-beads",
        prefix="bd-ib",
        server_user="livespec-impl-beads",
        database="livespec-impl-beads",
        bd_path="bd",
        fake=True,
    )


@pytest.fixture(autouse=True)
def _hermetic_tenant(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[None]:
    """A fresh in-memory tenant, reached from a committed connection block.

    `main` reads its connection out of the governed repository's own
    `.livespec.jsonc` through the production `resolve_store_config`, so the
    file is written rather than the config injected: that read is part of what
    this tier is asserting about.
    """
    monkeypatch.setenv("LIVESPEC_BEADS_FAKE", "1")
    monkeypatch.chdir(tmp_path)
    _ = (tmp_path / ".livespec.jsonc").write_text(
        '{"livespec-orchestrator-beads-fabro": {"connection": {"prefix": "bd-ib"}}}',
        encoding="utf-8",
    )
    reset_fake_singleton()
    yield
    reset_fake_singleton()


def _seed(
    *,
    id_: str,
    status: str,
    depends_on: tuple[str, ...] = (),
    blocked_reason: str | None = None,
) -> None:
    append_work_item(
        path=_config(),
        item=WorkItem(
            id=id_,
            type="task",
            status=status,  # pyright: ignore[reportArgumentType]
            title=f"{id_} title",
            description="d",
            origin="freeform",
            gap_id=None,
            rank="a2",
            assignee=None,
            depends_on=depends_on,
            captured_at="2026-10-22T00:00:00Z",
            resolution=None,
            reason=None,
            audit=None,
            superseded_by=None,
            blocked_reason=blocked_reason,
        ),
    )


def _lanes(*, payload: str) -> dict[str, tuple[object, object]]:
    """Every emitted item's `(lane, lane_reason)` pair, keyed by work-item id."""
    return {
        str(entry["id"]): (entry.get("lane"), entry.get("lane_reason"))
        for entry in json.loads(payload)
    }


def test_scenario26_lane_and_lane_reason_are_computed_from_lane_of(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """One `--json` read answers all three of the scenario's `Then`s at once."""
    _seed(id_=_DEPENDENCY, status="ready")
    _seed(
        id_=_READY_WITH_OPEN_DEPENDENCY,
        status="ready",
        depends_on=(_DEPENDENCY,),
    )
    _seed(id_=_STORED_BLOCKED, status="blocked", blocked_reason="needs-human")
    _seed(id_=_ACTIVE, status="active")

    exit_code = main(argv=["--json"])

    assert exit_code == 0
    lanes = _lanes(payload=capsys.readouterr().out)
    # The stored status is `ready` and the emitted lane is NOT: the open
    # dependency is what moves it, and `dependency` is what says so.
    assert lanes[_READY_WITH_OPEN_DEPENDENCY] == ("blocked", "dependency")
    # Same lane, a different reason, carried from the row's own stored field —
    # so the consumer can tell a store-visible wait from a human one.
    assert lanes[_STORED_BLOCKED] == ("blocked", "needs-human")
    # An active item has nothing to be blocked ON, so the reason is null rather
    # than an empty string: the console renders absence, not a blank cause.
    assert lanes[_ACTIVE] == ("active", None)
    # The dependency itself is genuinely open, which is the premise the first
    # assertion rests on — if it had emitted a terminal lane the ready item
    # would have had nothing to wait for.
    assert lanes[_DEPENDENCY] == ("ready", None)
