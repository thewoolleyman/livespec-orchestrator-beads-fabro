"""Tests for collecting ended runs of closed work-items whichever repository dispatched them."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandResult
from livespec_orchestrator_beads_fabro.commands._dispatcher_fleet_run_collection import (
    DispatchingRepository,
    collect_fleet_closed_ended_runs,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_reconcile_runs_attribution import (
    FactoryRunInventory,
    journaled_runs,
)
from livespec_orchestrator_beads_fabro.commands._fabro_port import FabroPort, FabroTarget
from livespec_orchestrator_beads_fabro.commands._fabro_port_records import FabroRunSummary
from livespec_orchestrator_beads_fabro.commands._run_attribution import GOAL_TEXT_ONLY


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
    """The forge reference interface; it records the directory each call ran in."""

    cwds: list[Path] = field(default_factory=list)

    def run(
        self,
        *,
        argv: list[str],
        cwd: Path,
        timeout_seconds: float,
        env: Mapping[str, str | None] | None = None,
        stdin: int | None = None,
    ) -> CommandResult:
        _ = (argv, timeout_seconds, env, stdin)
        self.cwds.append(cwd)
        return CommandResult(exit_code=0, stdout="", stderr="")


@dataclass(kw_only=True)
class _Journal:
    records: list[dict[str, object]] = field(default_factory=list)

    def append(self, *, record: dict[str, object]) -> None:
        self.records.append(record)


def test_one_pass_collects_a_closed_item_of_another_repository_and_journals_each_decision(
    tmp_path: Path,
) -> None:
    runner = _Runner()
    forge = _Forge()
    journal = _Journal()
    other = tmp_path / "livespec-q"

    collect_fleet_closed_ended_runs(
        inventory=_inventory(
            runs=(
                _run(run_id="01E", status_kind="succeeded"),
                _run(run_id="01F", status_kind="succeeded"),
                _run(run_id="01G", status_kind="failed"),
                _run(run_id="01CLEARANCE", status_kind="succeeded"),
                _run(run_id="01LIVE", status_kind="succeeded"),
            ),
            own_stamps=(),
        ),
        port=_port(tmp_path=tmp_path, runner=runner),
        runner=forge,
        journal=journal,
        dry_run=False,
        repositories=(
            _repository(
                repo=other,
                statuses={"q-e": "closed", "q-f": "blocked"},
                stamps=(("01E", "q-e"), ("01F", "q-f"), ("01G", "q-g")),
            ),
        ),
    )

    assert runner.calls == [["fabro", "rm", "01E", "--server", "https://factory.test"]]
    assert set(forge.cwds) == {other}
    assert [
        (
            record["stage"],
            record["run_id"],
            record["dispatching_repository"],
            record["work_item_id"],
            record["work_item_status"],
        )
        for record in journal.records
    ] == [
        ("ended-run-collected", "01E", "livespec-q", "q-e", "closed"),
        ("ended-run-collection-refused", "01F", "livespec-q", "q-f", "blocked"),
        ("ended-run-collection-refused", "01G", "livespec-q", "q-g", None),
    ]


def test_a_run_the_passs_own_repository_attributes_is_left_to_its_own_collection(
    tmp_path: Path,
) -> None:
    runner = _Runner()
    journal = _Journal()

    collect_fleet_closed_ended_runs(
        inventory=_inventory(
            runs=(_run(run_id="01OWN", status_kind="succeeded"),),
            own_stamps=(("01OWN", "own-1"),),
        ),
        port=_port(tmp_path=tmp_path, runner=runner),
        runner=_Forge(),
        journal=journal,
        dry_run=False,
        repositories=(
            _repository(
                repo=tmp_path / "livespec-q",
                statuses={"q-1": "closed"},
                stamps=(("01OWN", "q-1"),),
            ),
        ),
    )

    assert (runner.calls, journal.records) == ([], [])


def test_a_dry_run_collects_and_journals_nothing_for_another_repository(tmp_path: Path) -> None:
    runner = _Runner()
    journal = _Journal()

    collect_fleet_closed_ended_runs(
        inventory=_inventory(
            runs=(_run(run_id="01E", status_kind="succeeded"),),
            own_stamps=(),
        ),
        port=_port(tmp_path=tmp_path, runner=runner),
        runner=_Forge(),
        journal=journal,
        dry_run=True,
        repositories=(
            _repository(
                repo=tmp_path / "livespec-q",
                statuses={"q-e": "closed"},
                stamps=(("01E", "q-e"),),
            ),
        ),
    )

    assert (runner.calls, journal.records) == ([], [])


def test_a_targeted_pass_leaves_every_other_repositorys_runs_alone(tmp_path: Path) -> None:
    runner = _Runner()
    journal = _Journal()

    collect_fleet_closed_ended_runs(
        inventory=_inventory(
            runs=(_run(run_id="01E", status_kind="succeeded"),),
            own_stamps=(),
            only_work_item_id="own-1",
        ),
        port=_port(tmp_path=tmp_path, runner=runner),
        runner=_Forge(),
        journal=journal,
        dry_run=False,
        repositories=(
            _repository(
                repo=tmp_path / "livespec-q",
                statuses={"q-e": "closed"},
                stamps=(("01E", "q-e"),),
            ),
        ),
    )

    assert (runner.calls, journal.records) == ([], [])


def _repository(
    *,
    repo: Path,
    statuses: dict[str, str],
    stamps: tuple[tuple[str, str], ...],
) -> DispatchingRepository:
    return DispatchingRepository(
        repo=repo,
        id_prefix="q",
        item_statuses=statuses,
        journaled=journaled_runs(text=_stamp_lines(stamps=stamps)),
        attribution=GOAL_TEXT_ONLY,
    )


def _inventory(
    *,
    runs: tuple[FabroRunSummary, ...],
    own_stamps: tuple[tuple[str, str], ...],
    only_work_item_id: str | None = None,
) -> FactoryRunInventory:
    return FactoryRunInventory(
        runs=runs,
        item_statuses={"own-1": "done"},
        journaled=journaled_runs(text=_stamp_lines(stamps=own_stamps)),
        id_prefix="own",
        factory_name="factory",
        factory_server_url="https://factory.test",
        only_work_item_id=only_work_item_id,
    )


def _stamp_lines(*, stamps: tuple[tuple[str, str], ...]) -> str:
    return "\n".join(
        f'{{"stage":"dispatch-run-stamp","run_id":"{run_id}","work_item_id":"{item_id}"}}'
        for run_id, item_id in stamps
    )


def _port(*, tmp_path: Path, runner: _Runner) -> FabroPort:
    return FabroPort(
        fabro_bin="fabro",
        target=FabroTarget(server_url="https://factory.test"),
        runner=runner,
        cwd=tmp_path,
    )


def _run(*, run_id: str, status_kind: str) -> FabroRunSummary:
    return FabroRunSummary(
        run_id=run_id,
        status_kind=status_kind,
        goal=None,
        total_usd_micros=None,
    )
