"""A pre-claim refusal lands before recovery routing reads an item's seed ruling.

`SPECIFICATION/contracts.md` section "Factory-configurable ACP fallback priority"
→ "Recovery from the failed run's preserved work" → "A ruled seed names the tree a
released item's next dispatch starts from": a pre-claim refusal is still graded
first, as for every released item, so an item it refuses MUST NOT be routed and
MUST NOT be offered to the admission valve in that pass.

WHAT THIS PROVES. Every pre-claim refusal occupies ONE position —
`pre_dispatch_wall_exit`, run by both dispatch commands after selection and before
recovery routing. These cases drive that EXISTING wall, with a refusing wall
standing in for whichever row refuses, and prove the POSITION: with the wall
refusing, the item is neither routed nor offered, the ruling on its ledger comments
is never read, and the refusal is journaled before any of that could happen. The
control is the same item with the wall silent, which does reach routing and does
read the ledger. No refusal mechanism is added or implied by these cases.
"""

from __future__ import annotations

import argparse
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from livespec_orchestrator_beads_fabro.commands import _dispatcher_loop_command as loop_command
from livespec_orchestrator_beads_fabro.commands import _dispatcher_loop_wave as loop_wave
from livespec_orchestrator_beads_fabro.commands import _dispatcher_run_commands as run_commands
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import JournalFile
from livespec_orchestrator_beads_fabro.commands._dispatcher_recovery_routes import (
    ROUTE_FRESH,
    RecoveryRoute,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_recovery_routing import (
    RecoveryRouting,
)
from livespec_orchestrator_beads_fabro.types import WorkItem

_ITEM = "bd-ib-ruled"
_REFUSED_EXIT = 3
_STAND_IN_STAGE = "stand-in-pre-claim-refusal"


def _work_item() -> WorkItem:
    return WorkItem(
        id=_ITEM,
        type="bug",
        status="ready",
        title="An item an operator ruled a seed for",
        description="",
        origin="freeform",
        gap_id=None,
        rank="a0",
        assignee=None,
        depends_on=(),
        captured_at="2026-11-10T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
        admission_policy="auto",
        acceptance_policy="ai-only",
    )


class _Probe:
    """What the pass reached: routing, the admission valve, and the ledger read."""

    def __init__(self, *, wall_refuses: bool) -> None:
        self.wall_refuses = wall_refuses
        self.routed: list[str] = []
        self.offered: list[str] = []

    def wall(self, **kwargs: Any) -> int | None:
        if not self.wall_refuses:
            return None
        kwargs["journal"].append(record={"stage": _STAND_IN_STAGE, "work_item_id": _ITEM})
        return _REFUSED_EXIT

    def route(self, **kwargs: Any) -> RecoveryRouting:
        self.routed.extend(one.id for one in kwargs["candidates"])
        return RecoveryRouting(
            routes=tuple(
                RecoveryRoute(work_item_id=one.id, route=ROUTE_FRESH)
                for one in kwargs["candidates"]
            )
        )

    def admit(self, **kwargs: Any) -> None:
        self.offered.extend(one.id for one in kwargs["candidates"])
        raise _Stop

    def admit_target(self, **kwargs: Any) -> None:
        self.offered.append(kwargs["target"].id)
        raise _Stop


class _Stop(Exception):  # noqa: N818 — a test stop signal, not an error condition.
    """Ends a pass the moment it reaches admission."""


def _args(*, tmp_path: Path) -> argparse.Namespace:
    return argparse.Namespace(
        repo=str(tmp_path),
        journal=str(tmp_path / "journal.jsonl"),
        item=_ITEM,
        items=None,
        budget=1,
        parallel=1,
        as_json=False,
        dry_run=False,
        skip_ledger_check=True,
        workflow_name=None,
        fabro_bin="/usr/local/bin/fabro",
    )


def _journal(*, tmp_path: Path) -> JournalFile:
    return JournalFile(path=tmp_path / "journal.jsonl")


def _stand_in_rows(*, journal: JournalFile) -> int:
    return journal.path.read_text(encoding="utf-8").count(_STAND_IN_STAGE)


def _arm_dispatch(*, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, probe: _Probe) -> JournalFile:
    journal = _journal(tmp_path=tmp_path)
    started = SimpleNamespace(janitor=None, items=[_work_item()], journal=journal)
    monkeypatch.setattr(run_commands, "_start_dispatch", lambda **_: started)
    monkeypatch.setattr(run_commands, "_target_item", lambda **_: (_work_item(), False))
    monkeypatch.setattr(run_commands, "pre_dispatch_wall_exit", probe.wall)
    monkeypatch.setattr(run_commands, "route_recovery", probe.route)
    monkeypatch.setattr(run_commands, "admit_and_dispatch_target", probe.admit_target)
    return journal


def _arm_loop(*, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, probe: _Probe) -> JournalFile:
    journal = _journal(tmp_path=tmp_path)
    started = SimpleNamespace(janitor=None, items=[_work_item()], journal=journal)
    monkeypatch.setattr(loop_command, "_start_loop", lambda **_: started)
    monkeypatch.setattr(loop_command, "factory_size_loop_exit", lambda **_: None)
    monkeypatch.setattr(loop_command, "candidates", lambda **_: [_work_item()])
    monkeypatch.setattr(loop_command, "pre_dispatch_wall_exit", probe.wall)
    monkeypatch.setattr(loop_wave, "await_usable_credential", lambda **_: None)
    monkeypatch.setattr(loop_wave, "resolve_acp_preflight", lambda **_: None)
    monkeypatch.setattr(loop_wave, "route_recovery", probe.route)
    monkeypatch.setattr(loop_wave, "admit_and_select", probe.admit)
    return journal


def test_a_refusing_wall_stops_the_single_dispatch_before_routing_and_admission(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    probe = _Probe(wall_refuses=True)
    journal = _arm_dispatch(monkeypatch=monkeypatch, tmp_path=tmp_path, probe=probe)

    assert run_commands.run_dispatch_command(args=_args(tmp_path=tmp_path)) == _REFUSED_EXIT

    assert _stand_in_rows(journal=journal) == 1
    assert probe.routed == []
    assert probe.offered == []


def test_a_refusing_wall_stops_the_drain_before_routing_and_admission(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    probe = _Probe(wall_refuses=True)
    journal = _arm_loop(monkeypatch=monkeypatch, tmp_path=tmp_path, probe=probe)

    assert loop_command.run_loop_command(args=_args(tmp_path=tmp_path)) == _REFUSED_EXIT

    assert _stand_in_rows(journal=journal) == 1
    assert probe.routed == []
    assert probe.offered == []


def test_a_silent_wall_reaches_routing_and_admission_in_both_commands(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The control: without it the two refusal cases pass against a pass that never routes."""
    dispatch = _Probe(wall_refuses=False)
    _ = _arm_dispatch(monkeypatch=monkeypatch, tmp_path=tmp_path / "dispatch", probe=dispatch)
    with pytest.raises(_Stop):
        _ = run_commands.run_dispatch_command(args=_args(tmp_path=tmp_path / "dispatch"))

    loop = _Probe(wall_refuses=False)
    _ = _arm_loop(monkeypatch=monkeypatch, tmp_path=tmp_path / "loop", probe=loop)
    with pytest.raises(_Stop):
        _ = loop_command.run_loop_command(args=_args(tmp_path=tmp_path / "loop"))

    assert dispatch.routed == [_ITEM]
    assert dispatch.offered == [_ITEM]
    assert loop.routed == [_ITEM]
    assert loop.offered == [_ITEM]
