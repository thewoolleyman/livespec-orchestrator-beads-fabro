"""The standalone Dispatcher drift job keeps cleanup and model work separate."""

from __future__ import annotations

import argparse
import importlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from types import ModuleType
from typing import Protocol

import pytest
from livespec_orchestrator_beads_fabro.commands import dispatcher

_COMMANDS = (
    Path(__file__).resolve().parents[3]
    / ".claude-plugin"
    / "scripts"
    / "livespec_orchestrator_beads_fabro"
    / "commands"
)
_MODULE_NAME = "livespec_orchestrator_beads_fabro.commands._dispatcher_drift_run_command"
_MODULE_PATH = _COMMANDS / "_dispatcher_drift_run_command.py"
_SCHEDULE_ROOT = Path(__file__).resolve().parents[3] / "orchestrator-image" / "services"


class _DriftSeams(Protocol):
    runner: object
    judge: object


@dataclass(frozen=True, kw_only=True)
class _Outcome:
    scope: str = "deadbeef..HEAD"
    merges: tuple[str, ...] = ("aaaaaaa1",)
    frontier: str | None = "aaaaaaa1"
    filed: tuple[str, ...] = ("finding-1",)
    held: tuple[str, ...] = ()
    advanced: bool = True
    withheld_reason: str | None = None
    records: object | None = field(default_factory=object)


def _command() -> ModuleType:
    return importlib.import_module(_MODULE_NAME)


def test_drift_run_executes_the_lane_and_prints_its_reconcile_json_projection(
    *,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    assert _MODULE_PATH.is_file()
    command = _command()
    runner = object()
    judge = object()
    seen: dict[str, object] = {}

    def _judge(**kwargs: object) -> object:
        seen["judge"] = kwargs
        return judge

    def _lane(*, repo: Path, invoker: str, seams: _DriftSeams) -> _Outcome:
        seen["repo"] = repo
        seen["invoker"] = invoker
        seen["runner"] = seams.runner
        seen["lane_judge"] = seams.judge
        return _Outcome()

    monkeypatch.setattr(command, "ShellCommandRunner", lambda: runner)
    monkeypatch.setattr(command, "drift_judge", _judge)
    monkeypatch.setattr(command, "run_drift_lane", _lane)

    exit_code = command.run_drift_run_command(
        args=argparse.Namespace(
            repo=str(tmp_path), invoker="operator:drift", dry_run=False, as_json=True
        )
    )

    assert exit_code == 0
    assert seen["repo"] == tmp_path
    assert seen["invoker"] == "operator:drift"
    assert seen["runner"] is runner
    assert seen["lane_judge"] is judge
    assert seen["judge"] == {
        "project_root": tmp_path,
        "runner": runner,
        "caller": "operator:drift",
    }
    assert json.loads(capsys.readouterr().out) == {
        "advanced": True,
        "filed": ["finding-1"],
        "frontier": "aaaaaaa1",
        "held": [],
        "merges": ["aaaaaaa1"],
        "scope": "deadbeef..HEAD",
        "withheld_reason": None,
    }


def test_drift_run_dry_run_skips_the_lane_and_writes_no_outcome(
    *,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    assert _MODULE_PATH.is_file()
    command = _command()
    seen: list[object] = []
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(command, "run_drift_lane", lambda **kwargs: seen.append(kwargs))

    exit_code = command.run_drift_run_command(
        args=argparse.Namespace(repo=None, invoker="operator:drift", dry_run=True, as_json=True)
    )

    assert exit_code == 0
    assert seen == []
    assert capsys.readouterr().out == "null\n"


def test_drift_run_has_a_human_projection_for_a_withheld_frontier(
    *, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    assert _MODULE_PATH.is_file()
    command = _command()
    monkeypatch.setattr(
        command,
        "run_drift_lane",
        lambda **_kwargs: _Outcome(
            advanced=False,
            frontier=None,
            withheld_reason="no-recorded-drift-frontier",
        ),
    )
    monkeypatch.setattr(command, "ShellCommandRunner", object)
    monkeypatch.setattr(command, "drift_judge", lambda **_kwargs: object())

    exit_code = command.run_drift_run_command(
        args=argparse.Namespace(
            repo=str(tmp_path), invoker="operator:drift", dry_run=False, as_json=False
        )
    )

    assert exit_code == 0
    assert capsys.readouterr().out == (
        "DRIFT   advanced=false frontier=(none) reason=no-recorded-drift-frontier\n"
    )


def test_dispatcher_registers_drift_run_with_its_operator_arguments(
    *, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    assert hasattr(dispatcher, "run_drift_run_command")
    seen: list[argparse.Namespace] = []
    monkeypatch.setattr(
        dispatcher,
        "run_drift_run_command",
        lambda *, args: seen.append(args) or 0,
        raising=False,
    )

    exit_code = dispatcher.main(
        argv=[
            "drift-run",
            "--repo",
            str(tmp_path),
            "--invoker",
            "operator:drift",
            "--dry-run",
            "--json",
        ]
    )

    assert exit_code == 0
    assert seen[0].repo == str(tmp_path)
    assert seen[0].invoker == "operator:drift"
    assert seen[0].dry_run is True
    assert seen[0].as_json is True


def test_no_committed_service_or_installer_invokes_the_stopped_drift_job() -> None:
    schedule_files = [
        path
        for path in _SCHEDULE_ROOT.rglob("*")
        if path.is_file() and (path.name == "install.sh" or path.suffix in {".service", ".timer"})
    ]

    assert all(
        "dispatcher.py drift-run" not in path.read_text(encoding="utf-8") for path in schedule_files
    )
