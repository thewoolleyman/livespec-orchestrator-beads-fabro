"""Pacing keeps stale-item reaps from deleting a busy factory's run record."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import cast

import pytest
from livespec_orchestrator_beads_fabro.commands import _dispatcher_stale_item_reap
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import (
    CommandResult,
    CommandRunner,
    JournalWriter,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_plan import DispatchPlan, build_plan
from livespec_orchestrator_beads_fabro.commands._fabro_port import FabroPort
from livespec_orchestrator_beads_fabro.commands._fabro_port_factory import FabroRunner
from livespec_orchestrator_beads_fabro.commands._fabro_port_types import FabroCommandResult


@dataclass(kw_only=True)
class _Api:
    cancelled: list[str] = field(default_factory=list)

    def cancel(self, *, run_id: str, timeout_seconds: float) -> object:
        _ = timeout_seconds
        self.cancelled.append(run_id)
        return object()


@dataclass(kw_only=True)
class _Port:
    api: _Api
    removals: list[str] = field(default_factory=list)

    def server_api(self) -> _Api:
        return self.api

    def rm(self, *, run_id: str, timeout_seconds: float) -> FabroCommandResult:
        _ = timeout_seconds
        self.removals.append(run_id)
        return FabroCommandResult(command=CommandResult(exit_code=0, stdout="", stderr=""))


@dataclass(kw_only=True)
class _Journal:
    records: list[dict[str, object]] = field(default_factory=list)

    def append(self, *, record: dict[str, object]) -> None:
        self.records.append(record)


def _plan(*, tmp_path: Path) -> DispatchPlan:
    return build_plan(
        repo=tmp_path,
        work_item_id="bd-ib-vh23ja",
        workflow_toml=tmp_path / "workflow.toml",
        goal_file=tmp_path / "goal.md",
        fabro_bin="fabro",
        fabro_factory_name="petri",
        janitor=None,
        janitor_checkout=tmp_path / "janitor",
    )


def test_a_deferred_reap_cancels_now_and_leaves_the_record_for_later(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    class _Pacer:
        def __init__(self, *, repo: Path) -> None:
            _ = repo

        def permit(self, **_: object) -> bool:
            return False

    api = _Api()
    port = _Port(api=api)
    journal = _Journal()

    def _status(*, repo: Path, work_item_id: str) -> str:
        _ = (repo, work_item_id)
        return "done"

    def _port_for_plan(*, plan: object, runner: FabroRunner) -> FabroPort:
        _ = (plan, runner)
        return cast("FabroPort", port)

    monkeypatch.setattr(_dispatcher_stale_item_reap, "DeletionPacer", _Pacer)
    monkeypatch.setattr(_dispatcher_stale_item_reap, "_work_item_status", _status)
    monkeypatch.setattr(_dispatcher_stale_item_reap, "fabro_port_for_plan", _port_for_plan)

    status = _dispatcher_stale_item_reap.stale_item_reap(
        plan=_plan(tmp_path=tmp_path),
        runner=cast("CommandRunner", object()),
        journal=cast("JournalWriter", journal),
        run_id="01RUN",
    )

    assert status == "done"
    assert api.cancelled == ["01RUN"]
    assert port.removals == []
    assert journal.records[-1]["rm_exit_code"] is None


def test_an_unpaced_reap_removes_the_record(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class _Pacer:
        def __init__(self, *, repo: Path) -> None:
            _ = repo

        def permit(self, **_: object) -> bool:
            return True

    api = _Api()
    port = _Port(api=api)
    journal = _Journal()

    def _status(*, repo: Path, work_item_id: str) -> str:
        _ = (repo, work_item_id)
        return "done"

    def _port_for_plan(*, plan: object, runner: FabroRunner) -> FabroPort:
        _ = (plan, runner)
        return cast("FabroPort", port)

    monkeypatch.setattr(_dispatcher_stale_item_reap, "DeletionPacer", _Pacer)
    monkeypatch.setattr(_dispatcher_stale_item_reap, "_work_item_status", _status)
    monkeypatch.setattr(_dispatcher_stale_item_reap, "fabro_port_for_plan", _port_for_plan)

    assert (
        _dispatcher_stale_item_reap.stale_item_reap(
            plan=_plan(tmp_path=tmp_path),
            runner=cast("CommandRunner", object()),
            journal=cast("JournalWriter", journal),
            run_id="01RUN",
        )
        == "done"
    )
    assert api.cancelled == []
    assert port.removals == ["01RUN"]
    assert journal.records[-1]["rm_exit_code"] == 0
