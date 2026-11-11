"""Tests for where the fleet collection finds the repositories whose runs it collects."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro.commands import _dispatcher_fleet_run_collection as fleet
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandResult
from livespec_orchestrator_beads_fabro.commands._dispatcher_reconcile_runs_attribution import (
    FactoryRunInventory,
    journaled_runs,
)
from livespec_orchestrator_beads_fabro.commands._fabro_port import FabroPort, FabroTarget
from livespec_orchestrator_beads_fabro.commands._fabro_port_records import FabroRunSummary
from livespec_orchestrator_beads_fabro.commands._run_attribution import (
    GOAL_TEXT_ONLY,
    RunAttribution,
)
from livespec_orchestrator_beads_fabro.errors import (
    BeadsConnectionError,
    LivespecConfigUnreadableError,
)
from livespec_orchestrator_beads_fabro.types import WorkItem, WorkItemStatus

_PLUGIN = "livespec-orchestrator-beads-fabro@livespec"


def test_the_registry_names_each_other_repository_once_and_never_the_passs_own(
    tmp_path: Path,
) -> None:
    own, console, overseer, gone = (
        tmp_path / "own",
        tmp_path / "console",
        tmp_path / "overseer",
        tmp_path / "gone",
    )
    for directory in (own, console, overseer):
        directory.mkdir()
    registry = tmp_path / "installed_plugins.json"
    _ = registry.write_text(
        json.dumps(
            {
                "plugins": {
                    _PLUGIN: [
                        {"projectPath": str(console), "installPath": "/cache/a"},
                        {"projectPath": str(own), "installPath": "/cache/a"},
                        {"projectPath": str(console), "installPath": "/cache/b"},
                        {"projectPath": str(gone), "installPath": "/cache/a"},
                        {"projectPath": str(overseer), "installPath": "/cache/a"},
                    ]
                }
            }
        ),
        encoding="utf-8",
    )

    assert fleet.registered_dispatching_repositories(own_repo=own, install_record=registry) == (
        console.resolve(),
        overseer.resolve(),
    )


def test_a_repository_without_a_livespec_config_dispatches_nothing(tmp_path: Path) -> None:
    assert fleet.read_dispatching_repository(repo=tmp_path) is None


def test_a_repository_is_read_through_its_own_ledger_journal_and_run_stamps(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _ = (tmp_path / ".livespec.jsonc").write_text("{}", encoding="utf-8")
    (tmp_path / "tmp").mkdir()
    _ = (tmp_path / "tmp" / "fabro-dispatch-journal.jsonl").write_text(
        '{"stage":"dispatch-run-stamp","run_id":"01Q","work_item_id":"q-1"}\n', encoding="utf-8"
    )
    stamps = RunAttribution(metadata_run_ids={"01M": "q-2"})

    def _items(*, repo: Path) -> list[WorkItem]:
        _ = repo
        return [_item(id="q-1", status="done")]

    def _attribution(*, repo: Path) -> RunAttribution:
        _ = repo
        return stamps

    monkeypatch.setattr(fleet, "store_config", _config)
    monkeypatch.setattr(fleet, "load_items", _items)
    monkeypatch.setattr(fleet, "repo_run_attribution", _attribution)

    repository = fleet.read_dispatching_repository(repo=tmp_path)

    assert repository is not None
    assert repository.repo == tmp_path
    assert repository.id_prefix == "q"
    assert dict(repository.item_statuses) == {"q-1": "done"}
    assert dict(repository.journaled.item_id_by_run) == {"01Q": "q-1"}
    assert repository.attribution is stamps


def test_an_unreadable_ledger_reads_as_no_statuses_never_as_closed(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _ = (tmp_path / ".livespec.jsonc").write_text("{}", encoding="utf-8")

    def _unreachable(*, repo: Path) -> list[WorkItem]:
        _ = repo
        raise BeadsConnectionError(detail="tenant unreachable")

    monkeypatch.setattr(fleet, "store_config", _config)
    monkeypatch.setattr(fleet, "load_items", _unreachable)
    monkeypatch.setattr(fleet, "repo_run_attribution", _bare_attribution)

    repository = fleet.read_dispatching_repository(repo=tmp_path)

    assert repository is not None
    assert (repository.id_prefix, dict(repository.item_statuses)) == ("q", {})


def test_an_unreadable_config_still_leaves_the_journal_leg_and_no_statuses(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _ = (tmp_path / ".livespec.jsonc").write_text("{", encoding="utf-8")

    def _unparseable(*, repo: Path) -> object:
        _ = repo
        raise LivespecConfigUnreadableError(detail="stray comma")

    monkeypatch.setattr(fleet, "store_config", _unparseable)
    monkeypatch.setattr(fleet, "repo_run_attribution", _bare_attribution)

    repository = fleet.read_dispatching_repository(repo=tmp_path)

    assert repository is not None
    assert (repository.id_prefix, dict(repository.item_statuses)) == ("", {})


def test_a_run_the_first_repository_attributes_is_not_collected_through_the_second(
    tmp_path: Path,
) -> None:
    runner = _Runner()
    journal = _Journal()

    fleet.collect_fleet_closed_ended_runs(
        inventory=_inventory(runs=("01X", "01Y", "01Z")),
        port=_port(tmp_path=tmp_path, runner=runner),
        runner=_Forge(),
        journal=journal,
        dry_run=False,
        repositories=(
            _repository(repo=tmp_path / "first", stamps=("01X", "01Y"), status="closed"),
            _repository(repo=tmp_path / "second", stamps=("01Y", "01Z"), status="closed"),
        ),
    )

    assert [call[2] for call in runner.calls] == ["01X", "01Y", "01Z"]
    assert [(r["run_id"], r["dispatching_repository"]) for r in journal.records] == [
        ("01X", "first"),
        ("01Y", "first"),
        ("01Z", "second"),
    ]


def test_no_further_repository_is_consulted_once_every_run_is_claimed(tmp_path: Path) -> None:
    runner = _Runner()

    fleet.collect_fleet_closed_ended_runs(
        inventory=_inventory(runs=("01X",)),
        port=_port(tmp_path=tmp_path, runner=runner),
        runner=_Forge(),
        journal=_Journal(),
        dry_run=False,
        repositories=(
            _repository(repo=tmp_path / "first", stamps=("01X",), status="closed"),
            _repository(repo=tmp_path / "second", stamps=("01X",), status="closed"),
        ),
    )

    assert [call[2] for call in runner.calls] == ["01X"]


def test_a_standing_refusal_is_not_journaled_again_for_another_repository(
    tmp_path: Path,
) -> None:
    journal = _Journal()

    fleet.collect_fleet_closed_ended_runs(
        inventory=_inventory(runs=("01X",), refused_before=frozenset({("01X", "blocked")})),
        port=_port(tmp_path=tmp_path, runner=_Runner()),
        runner=_Forge(),
        journal=journal,
        dry_run=False,
        repositories=(_repository(repo=tmp_path / "q", stamps=("01X",), status="blocked"),),
    )

    assert journal.records == []


@dataclass(kw_only=True)
class _Config:
    prefix: str = "q"


def _config(*, repo: Path) -> _Config:
    _ = repo
    return _Config()


def _bare_attribution(*, repo: Path) -> RunAttribution:
    _ = repo
    return GOAL_TEXT_ONLY


@dataclass(kw_only=True)
class _Runner:
    calls: list[list[str]] = field(default_factory=list)

    def run(
        self,
        *,
        argv: list[str],
        cwd: Path,
        timeout_seconds: float,
        env: Mapping[str, str | None] | None = None,
        stdin: int | None = None,
    ) -> CommandResult:
        _ = (cwd, timeout_seconds, env, stdin)
        self.calls.append(argv)
        return CommandResult(exit_code=0, stdout="", stderr="")


@dataclass(kw_only=True)
class _Forge:
    def run(
        self,
        *,
        argv: list[str],
        cwd: Path,
        timeout_seconds: float,
        env: Mapping[str, str | None] | None = None,
        stdin: int | None = None,
    ) -> CommandResult:
        _ = (argv, cwd, timeout_seconds, env, stdin)
        return CommandResult(exit_code=0, stdout="", stderr="")


@dataclass(kw_only=True)
class _Journal:
    records: list[dict[str, object]] = field(default_factory=list)

    def append(self, *, record: dict[str, object]) -> None:
        self.records.append(record)


def _repository(*, repo: Path, stamps: tuple[str, ...], status: str) -> fleet.DispatchingRepository:
    return fleet.DispatchingRepository(
        repo=repo,
        id_prefix="q",
        item_statuses={f"item-{run_id}": status for run_id in stamps},
        journaled=journaled_runs(
            text="\n".join(
                f'{{"stage":"dispatch-run-stamp","run_id":"{run_id}","work_item_id":"item-{run_id}"}}'
                for run_id in stamps
            )
        ),
        attribution=GOAL_TEXT_ONLY,
    )


def _inventory(
    *,
    runs: tuple[str, ...],
    refused_before: frozenset[tuple[str, str | None]] = frozenset(),
) -> FactoryRunInventory:
    return FactoryRunInventory(
        runs=tuple(
            FabroRunSummary(
                run_id=run_id, status_kind="succeeded", goal=None, total_usd_micros=None
            )
            for run_id in runs
        ),
        item_statuses={},
        journaled=journaled_runs(text=""),
        id_prefix="own",
        factory_name="factory",
        factory_server_url="https://factory.test",
        refused_before=refused_before,
    )


def _port(*, tmp_path: Path, runner: _Runner) -> FabroPort:
    return FabroPort(
        fabro_bin="fabro",
        target=FabroTarget(server_url="https://factory.test"),
        runner=runner,
        cwd=tmp_path,
    )


def _item(*, id: str, status: WorkItemStatus) -> WorkItem:
    return WorkItem(
        id=id,
        type="task",
        status=status,
        blocked_reason=None,
        title=id,
        description=id,
        origin="freeform",
        gap_id=None,
        rank="a0",
        assignee=None,
        depends_on=(),
        captured_at="2026-08-30T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
    )
