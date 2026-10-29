"""Where a dispatch pass opens and ends its journal snapshot.

`test_dispatcher_pass_snapshot.py` and `..._freshness.py` bind what the snapshot
does once a pass is open; this binds that the production entry points OPEN one
and that the launch ENDS it. A snapshot nobody opens is a reader falling back to
its own copy of the journal without anything failing, which is the defect the
snapshot exists to remove, so each entry point has its own case.

The cases replace the body each entry point wraps and read whether a pass is live
from INSIDE it. They never assert on the snapshot's own bookkeeping.
"""

from __future__ import annotations

import argparse
import importlib
from pathlib import Path
from typing import Any

import pytest
from livespec_orchestrator_beads_fabro.commands import _dispatcher_io_fabro_launcher as launcher
from livespec_orchestrator_beads_fabro.commands._dispatcher_pass_snapshot import snapshot_records

_PACKAGE = "livespec_orchestrator_beads_fabro.commands"


def _journal(*, tmp_path: Path) -> Path:
    path = tmp_path / "journal.jsonl"
    path.write_text('{"stage": "marker"}\n', encoding="utf-8")
    return path


def _is_live(*, journal: Path) -> bool:
    return snapshot_records(journal_path=journal) is not None


@pytest.mark.parametrize(
    ("module", "entry", "body"),
    [
        ("_dispatcher_run_commands", "run_dispatch_command", "_dispatch_in_pass"),
        ("_dispatcher_loop_command", "run_loop_command", "_loop_in_pass"),
        ("_dispatcher_resume_command", "run_resume_command", "_resume_in_pass"),
    ],
)
def test_each_dispatch_command_runs_inside_a_pass(
    module: str, entry: str, body: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    journal = _journal(tmp_path=tmp_path)
    loaded = importlib.import_module(f"{_PACKAGE}.{module}")
    seen: list[bool] = []

    def inside(**_kwargs: Any) -> int:
        seen.append(_is_live(journal=journal))
        return 0

    monkeypatch.setattr(loaded, body, inside)

    exit_code: int = getattr(loaded, entry)(args=argparse.Namespace())
    assert exit_code == 0
    assert seen == [True]
    assert not _is_live(journal=journal)


def test_a_reconciliation_pass_runs_inside_a_pass(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    journal = _journal(tmp_path=tmp_path)
    module = importlib.import_module(f"{_PACKAGE}._dispatcher_reconcile_runs_pass")
    seen: list[bool] = []

    def survey(**_kwargs: Any) -> object:
        seen.append(_is_live(journal=journal))
        raise OSError("survey stopped")

    monkeypatch.setattr(module, "_survey", survey)
    args = argparse.Namespace(journal=str(journal), fabro_bin="fabro", invoker="agent:test")

    _ = module.reconcile_runs_pass(args=args, repo=tmp_path)

    assert seen == [True]
    assert not _is_live(journal=journal)


def test_launching_a_run_ends_the_pass_snapshot(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    journal = _journal(tmp_path=tmp_path)
    seen: list[bool] = []

    class _LaunchedError(Exception):
        pass

    def port_for_plan(**_kwargs: Any) -> object:
        seen.append(_is_live(journal=journal))
        return object()

    def release() -> None:
        raise _LaunchedError

    def auth_login(**_kwargs: Any) -> None:
        return None

    monkeypatch.setattr(launcher, "run_fabro_factory_auth_login", auth_login)
    monkeypatch.setattr(launcher, "fabro_port_for_plan", port_for_plan)
    monkeypatch.setattr(launcher, "release_pass_snapshot", release)
    pass_snapshot = importlib.import_module(f"{_PACKAGE}._dispatcher_pass_snapshot")

    anything: Any = object()
    with pass_snapshot.pass_snapshot(), pytest.raises(_LaunchedError):
        _ = launcher.WatchedFabroLauncher().launch(plan=anything, runner=anything, journal=anything)

    assert seen == [True]
