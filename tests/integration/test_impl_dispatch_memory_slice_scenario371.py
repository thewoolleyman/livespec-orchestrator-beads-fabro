"""An impl dispatch launches its loop inside the host's dispatch memory slice.

Binds `SPECIFICATION/scenarios.md` Scenario 371 and the "Host dispatch memory
slice" clause of `SPECIFICATION/contracts.md` (work-item `bd-ib-szbxu7`).

THE SUBJECT IS THE ARGV AN `impl:` DISPATCH HANDS ITS RUNNER, plus the record it
leaves. Nothing here can create a real transient scope: that needs a systemd user
manager that loads `factory-dispatch.slice` and delegates the memory controller,
which no factory sandbox provides, so the dev-host replay owns the cgroup
assertion. What a hermetic tier CAN establish is everything the launch decides:
which command is run, and that the journal and the `drive` result say which launch
was used.

TWO SEAMS ARE STOOD IN, and each is named so a reader knows what is not proved.
The host (does the slice load, is the memory controller delegated, is
`systemd-run` present, what does the published bound file hold) is replaced
through `default_scope_host`, the one function the launch reads it through; and
the command runner is the injected `CommandRunner` every `drive` test uses. The
real `run_impl_dispatch`, the real argv builder and the real on-disk dispatch
journal are production code.
"""

from __future__ import annotations

import importlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest
from livespec_orchestrator_beads_fabro.commands._drive_impl_dispatch import (
    CommandRun,
    build_dispatcher_argv,
    run_impl_dispatch,
)

_ITEM = "bd-ib-szbxu7"
_SCOPE_MODULE = (
    Path(__file__).resolve().parents[2]
    / ".claude-plugin"
    / "scripts"
    / "livespec_orchestrator_beads_fabro"
    / "commands"
    / "_drive_impl_scope.py"
)
_SCOPE_MODULE_NAME = "livespec_orchestrator_beads_fabro.commands._drive_impl_scope"
_LAUNCHER = "/usr/bin/systemd-run"
_UNIT_FLAG = "--unit="


@dataclass(kw_only=True)
class _Host:
    """What the launching user's service manager and the host provision."""

    memory_max_value: str | None = "3500M"
    launcher_path: str | None = _LAUNCHER
    slice_is_loaded: bool = True
    memory_is_delegated: bool = True

    def memory_max(self) -> str | None:
        return self.memory_max_value

    def launcher(self) -> str | None:
        return self.launcher_path

    def slice_loaded(self) -> bool:
        return self.slice_is_loaded

    def memory_delegated(self) -> bool:
        return self.memory_is_delegated


@dataclass(kw_only=True)
class _Runner:
    """Records every launch and answers like `systemd-run --scope` does."""

    calls: list[tuple[str, ...]] = field(default_factory=list[tuple[str, ...]])

    def __call__(self, *, argv: tuple[str, ...], cwd: Path | None = None) -> CommandRun:
        del cwd
        self.calls.append(argv)
        units = [element for element in argv if element.startswith(_UNIT_FLAG)]
        stderr = "".join(
            f"Running scope as unit: {unit.removeprefix(_UNIT_FLAG)}\n" for unit in units
        )
        return CommandRun(argv=argv, returncode=0, stdout="[]", stderr=stderr)


def _journal_records(*, repo: Path) -> list[dict[str, Any]]:
    journal = repo / "tmp" / "fabro-dispatch-journal.jsonl"
    return [json.loads(line) for line in journal.read_text(encoding="utf-8").splitlines()]


def _dispatch(
    *, repo: Path, host: _Host, monkeypatch: pytest.MonkeyPatch
) -> tuple[dict[str, Any], _Runner, tuple[str, ...]]:
    assert _SCOPE_MODULE.is_file(), "the launch-scope module is not delivered yet"
    scope = importlib.import_module(_SCOPE_MODULE_NAME)
    monkeypatch.setattr(scope, "default_scope_host", lambda: host)
    runner = _Runner()
    dispatcher_bin = repo / "dispatcher.py"
    result = run_impl_dispatch(
        repo=repo,
        work_item_ref=_ITEM,
        runner=runner,
        dispatcher_bin=dispatcher_bin,
        acp_nodes=(),
        workflow_name=None,
        identity=None,
    )
    loop_argv = build_dispatcher_argv(repo=repo, dispatcher_bin=dispatcher_bin, work_item_ref=_ITEM)
    return result, runner, loop_argv


def test_a_host_with_the_slice_gets_a_scoped_launch_that_records_its_unit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    result, runner, loop_argv = _dispatch(repo=tmp_path, host=_Host(), monkeypatch=monkeypatch)

    assert len(runner.calls) == 1
    argv = runner.calls[0]
    assert argv[0] == _LAUNCHER
    assert argv[1:3] == ("--user", "--scope")
    assert "--slice=factory-dispatch.slice" in argv
    properties = [argv[index + 1] for index, element in enumerate(argv) if element == "-p"]
    assert sorted(properties) == ["MemoryMax=3500M", "OOMPolicy=continue"]
    separator = argv.index("--")
    assert argv[separator + 1 :] == loop_argv
    units = [element.removeprefix(_UNIT_FLAG) for element in argv if element.startswith(_UNIT_FLAG)]
    assert len(units) == 1
    unit = units[0]
    assert unit.startswith(f"livespec-dispatch-{_ITEM}-")
    assert unit.endswith(".scope")
    assert result["launch"] == "scoped"
    assert result["scope_unit"] == unit
    assert result["dispatcher"]["argv"] == list(loop_argv)
    (record,) = _journal_records(repo=tmp_path)
    assert record["stage"] == "dispatch-launch-scope"
    assert record["work_item_id"] == _ITEM
    assert record["launch"] == "scoped"
    assert record["scope_unit"] == unit


@dataclass(kw_only=True)
class _ScopeLauncherRunner(_Runner):
    """A scoped launch answers as scripted; the unscoped launch after it succeeds."""

    scoped_returncode: int = 1
    scope_created: bool = False

    def __call__(self, *, argv: tuple[str, ...], cwd: Path | None = None) -> CommandRun:
        if argv[0] != _LAUNCHER:
            return super().__call__(argv=argv, cwd=cwd)
        self.calls.append(argv)
        stderr = (
            "".join(
                f"Running scope as unit: {element.removeprefix(_UNIT_FLAG)}\n"
                for element in argv
                if element.startswith(_UNIT_FLAG)
            )
            if self.scope_created
            else "Failed to start transient scope unit: Access denied\n"
        )
        return CommandRun(argv=argv, returncode=self.scoped_returncode, stdout="", stderr=stderr)


def _dispatch_with(
    *, repo: Path, runner: _Runner, monkeypatch: pytest.MonkeyPatch
) -> dict[str, Any]:
    assert _SCOPE_MODULE.is_file(), "the launch-scope module is not delivered yet"
    scope = importlib.import_module(_SCOPE_MODULE_NAME)
    monkeypatch.setattr(scope, "default_scope_host", lambda: _Host())
    return run_impl_dispatch(
        repo=repo,
        work_item_ref=_ITEM,
        runner=runner,
        dispatcher_bin=repo / "dispatcher.py",
        acp_nodes=(),
        workflow_name=None,
        identity=None,
    )


def test_a_scoped_launch_that_fails_before_the_loop_falls_back_to_one_unscoped_launch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runner = _ScopeLauncherRunner()

    result = _dispatch_with(repo=tmp_path, runner=runner, monkeypatch=monkeypatch)

    loop_argv = build_dispatcher_argv(
        repo=tmp_path, dispatcher_bin=tmp_path / "dispatcher.py", work_item_ref=_ITEM
    )
    assert len(runner.calls) == 2
    assert runner.calls[0][0] == _LAUNCHER
    assert runner.calls[1] == loop_argv
    assert result["launch"] == "unscoped"
    assert "scope_unit" not in result
    assert result["dispatcher"]["argv"] == list(loop_argv)
    (record,) = _journal_records(repo=tmp_path)
    assert record["stage"] == "dispatch-launch-scope"
    assert record["launch"] == "unscoped"
    assert "scope_unit" not in record
    assert "Failed to start transient scope unit" in record["detail"]


def test_a_loop_that_ran_in_its_scope_and_exited_non_zero_is_not_relaunched(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runner = _ScopeLauncherRunner(scope_created=True, scoped_returncode=3)

    result = _dispatch_with(repo=tmp_path, runner=runner, monkeypatch=monkeypatch)

    assert len(runner.calls) == 1
    assert result["launch"] == "scoped"
    assert result["dispatcher"]["exit_code"] == 3
    (record,) = _journal_records(repo=tmp_path)
    assert record["launch"] == "scoped"
    assert "detail" not in record
