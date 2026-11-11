"""Tests that the reconciliation pass collects the other repositories' runs it is given."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro._beads_client_fake import FakeBeadsClient
from livespec_orchestrator_beads_fabro.commands import _dispatcher_reconcile_runs as reconcile
from livespec_orchestrator_beads_fabro.commands._config import FactoryTarget
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandResult
from livespec_orchestrator_beads_fabro.commands._dispatcher_fleet_run_collection import (
    DispatchingRepository,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_reconcile_runs_attribution import (
    FactoryRunInventory,
    journaled_runs,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_reconcile_runs_inputs import (
    ReconcileInputs,
)
from livespec_orchestrator_beads_fabro.commands._run_attribution import GOAL_TEXT_ONLY

_FACTORY = FactoryTarget(name="petri", server="https://petri.example:32276", dev_token=None)


@dataclass(kw_only=True)
class _Runner:
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
        return CommandResult(exit_code=0, stdout="[]", stderr="")


@dataclass(kw_only=True)
class _Journal:
    records: list[dict[str, object]] = field(default_factory=list)

    def append(self, *, record: dict[str, object]) -> None:
        self.records.append(record)


@dataclass(kw_only=True)
class _Spy:
    read: list[Path] = field(default_factory=list)
    collected: list[tuple[DispatchingRepository, ...]] = field(default_factory=list)
    refused_before: list[frozenset[tuple[str, str | None]]] = field(default_factory=list)


def test_the_named_repositories_are_read_once_and_handed_to_every_factorys_collection(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    spy = _spied(monkeypatch=monkeypatch, dispatching=("console",))
    journal_path = tmp_path / "journal.jsonl"
    _ = journal_path.write_text(
        '{"stage":"ended-run-collection-refused","run_id":"01OLD","work_item_status":"blocked"}\n',
        encoding="utf-8",
    )

    _ = reconcile.reconcile_runs(
        inputs=_inputs(
            tmp_path=tmp_path,
            dispatching=(tmp_path / "console", tmp_path / "no-config"),
            journal_path=journal_path,
        ),
        factories=(_FACTORY, FactoryTarget(name="hp", server="https://hp.example", dev_token=None)),
    )

    assert spy.read == [tmp_path / "console", tmp_path / "no-config"]
    assert [[repository.repo for repository in group] for group in spy.collected] == [
        [tmp_path / "console"],
        [tmp_path / "console"],
    ]
    assert spy.refused_before == [frozenset({("01OLD", "blocked")})] * 2


def test_a_dry_run_reads_no_other_repository(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    spy = _spied(monkeypatch=monkeypatch, dispatching=("console",))

    _ = reconcile.reconcile_runs(
        inputs=_inputs(tmp_path=tmp_path, dispatching=(tmp_path / "console",)),
        factories=(_FACTORY,),
        dry_run=True,
    )

    assert (spy.read, spy.collected) == ([], [()])


def test_a_targeted_pass_reads_no_other_repository(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    spy = _spied(monkeypatch=monkeypatch, dispatching=("console",))

    _ = reconcile.reconcile_runs(
        inputs=_inputs(
            tmp_path=tmp_path, dispatching=(tmp_path / "console",), only_work_item_id="bd-ib-1"
        ),
        factories=(_FACTORY,),
    )

    assert (spy.read, spy.collected) == ([], [()])


def _spied(*, monkeypatch: pytest.MonkeyPatch, dispatching: tuple[str, ...]) -> _Spy:
    spy = _Spy()

    def _read(*, repo: Path) -> DispatchingRepository | None:
        spy.read.append(repo)
        if repo.name not in dispatching:
            return None
        return DispatchingRepository(
            repo=repo,
            id_prefix="q",
            item_statuses={},
            journaled=journaled_runs(text=""),
            attribution=GOAL_TEXT_ONLY,
        )

    def _collect(
        *,
        inventory: FactoryRunInventory,
        repositories: tuple[DispatchingRepository, ...],
        **_: object,
    ) -> None:
        spy.collected.append(repositories)
        spy.refused_before.append(inventory.refused_before)

    monkeypatch.setattr(reconcile, "read_dispatching_repository", _read)
    monkeypatch.setattr(reconcile, "collect_fleet_closed_ended_runs", _collect)
    return spy


def _inputs(
    *,
    tmp_path: Path,
    dispatching: tuple[Path, ...],
    journal_path: Path | None = None,
    only_work_item_id: str | None = None,
) -> ReconcileInputs:
    return ReconcileInputs(
        repo=tmp_path,
        fabro_bin="fabro",
        id_prefix="bd-ib",
        items=[],
        journaled=journaled_runs(text="", source_path=journal_path),
        runner=_Runner(),
        journal=_Journal(),
        ledger=FakeBeadsClient(),
        only_work_item_id=only_work_item_id,
        dispatching_repositories=dispatching,
    )
