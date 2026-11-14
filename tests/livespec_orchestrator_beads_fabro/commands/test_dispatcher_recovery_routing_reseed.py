"""Recovery routing applies the reseed to every route it would otherwise seed.

`SPECIFICATION/contracts.md` section "Factory-configurable ACP fallback priority"
→ "Recovery from the failed run's preserved work" → "A seed is moved onto the
current default branch before its run starts": the paragraph "governs every route
this clause would otherwise make `seeded`", and reads the tip "once per routing
pass, shared by every item the pass routes".

THE REAL REWRITE IS PROVED BY `test_dispatcher_recovery_reseed_route`; this module
proves the WIRING, which that one cannot: that `route_recovery` hands each released
item's finished route to the reseed step, that the route the step returns is the
route the pass records, that one reader serves the whole pass, and that an item
routed `fresh` without a release is never offered to it.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from livespec_orchestrator_beads_fabro.commands import _dispatcher_recovery_routing as routing
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import JournalFile
from livespec_orchestrator_beads_fabro.commands._dispatcher_recovery_records import (
    recovery_held_detail,
    recovery_held_report,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_recovery_reseed_route import (
    DefaultBranchTipReader,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_recovery_routes import (
    ROUTE_FRESH,
    ROUTE_HELD,
    ROUTE_SEEDED,
    RecoveryHold,
    RecoveryRoute,
    RecoverySeed,
    ReseedConflict,
)
from livespec_orchestrator_beads_fabro.types import WorkItem


def _item(*, item_id: str) -> WorkItem:
    return WorkItem(
        id=item_id,
        type="bug",
        status="ready",
        title="A released item",
        description="",
        origin="freeform",
        gap_id=None,
        rank="a0",
        assignee=None,
        depends_on=(),
        captured_at="2026-11-14T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
        admission_policy="auto",
        acceptance_policy="ai-only",
    )


def _seeded(*, item_id: str) -> RecoveryRoute:
    return RecoveryRoute(
        work_item_id=item_id,
        route=ROUTE_SEEDED,
        seed=RecoverySeed(
            source_run_id="run",
            remote="origin",
            commit_sha="a" * 40,
            preservation_ref="refs/heads/needs-human/run",
        ),
    )


def _args(*, tmp_path: Path) -> Any:
    import argparse

    return argparse.Namespace(repo=str(tmp_path))


def test_every_released_route_passes_through_the_reseed_step_with_one_shared_reader(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    items = [_item(item_id="bd-ib-one"), _item(item_id="bd-ib-two")]
    seen: list[tuple[str, DefaultBranchTipReader]] = []
    reseeded = {
        "bd-ib-one": RecoveryRoute(work_item_id="bd-ib-one", route=ROUTE_FRESH),
        "bd-ib-two": RecoveryRoute(work_item_id="bd-ib-two", route=ROUTE_HELD),
    }

    def _reseed(**kwargs: Any) -> RecoveryRoute:
        seen.append((kwargs["route"].work_item_id, kwargs["tip_reader"]))
        return reseeded[kwargs["route"].work_item_id]

    monkeypatch.setattr(routing, "current_seed_ruling", lambda **_kwargs: None)
    monkeypatch.setattr(routing, "released_for_recovery", lambda **_kwargs: True)
    monkeypatch.setattr(routing, "gather_resume", lambda **_kwargs: None)
    monkeypatch.setattr(
        routing, "_released_route", lambda **kwargs: _seeded(item_id=kwargs["item"].id)
    )
    monkeypatch.setattr(routing, "reseed_route", _reseed)

    routed = routing.route_recovery(
        args=_args(tmp_path=tmp_path),
        repo=tmp_path,
        candidates=items,
        journal=JournalFile(path=tmp_path / "journal.jsonl"),
    )

    assert [one.route for one in routed.routes] == [ROUTE_FRESH, ROUTE_HELD]
    assert [name for name, _reader in seen] == ["bd-ib-one", "bd-ib-two"]
    assert seen[0][1] is seen[1][1]
    assert isinstance(seen[0][1], DefaultBranchTipReader)


def test_an_unreleased_item_is_never_offered_to_the_reseed_step(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    offered: list[str] = []
    monkeypatch.setattr(routing, "current_seed_ruling", lambda **_kwargs: None)
    monkeypatch.setattr(routing, "released_for_recovery", lambda **_kwargs: False)
    monkeypatch.setattr(routing, "stale_assignee_with_run", lambda **_kwargs: False)
    monkeypatch.setattr(
        routing, "reseed_route", lambda **kwargs: offered.append(kwargs["route"].work_item_id)
    )

    routed = routing.route_recovery(
        args=_args(tmp_path=tmp_path),
        repo=tmp_path,
        candidates=[_item(item_id="bd-ib-one")],
        journal=JournalFile(path=tmp_path / "journal.jsonl"),
    )

    assert [one.route for one in routed.routes] == [ROUTE_FRESH]
    assert offered == []


def test_a_reseed_conflict_hold_names_the_seed_the_tip_and_every_path_to_the_operator() -> None:
    hold = RecoveryHold(
        refusals=("seed-reseed-conflict",),
        reseed_conflict=ReseedConflict(
            seed_ref="refs/heads/needs-human/run",
            seed_commit="a" * 40,
            default_branch_tip="b" * 40,
            paths=("a.txt", "b.txt"),
        ),
    )
    route = RecoveryRoute(work_item_id="bd-ib-one", route=ROUTE_HELD, hold=hold)

    report = recovery_held_report(work_item_id="bd-ib-one", hold=hold)
    detail = recovery_held_detail(route=route)

    for text in (report, detail):
        assert "seed-reseed-conflict" in text
        assert f"refs/heads/needs-human/run at {'a' * 40}" in text
        assert f"default branch at {'b' * 40}" in text
        assert "a.txt, b.txt" in text
