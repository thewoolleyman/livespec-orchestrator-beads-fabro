"""A pre-launch phase that raises still journals its CPU row."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from livespec_orchestrator_beads_fabro.commands import _dispatcher_loop as loop_module
from livespec_orchestrator_beads_fabro.commands import _dispatcher_loop_run as run_module
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import JournalFile
from livespec_orchestrator_beads_fabro.commands._dispatcher_prelaunch_cpu import (
    prelaunch_phase,
)


def _plan() -> Any:
    return SimpleNamespace(work_item_id="bd-ib-5d5aue", fabro_factory_name="hp", branch="b")


def _rows(*, journal: JournalFile) -> list[str]:
    lines = journal.path.read_text(encoding="utf-8").splitlines()
    return [
        str(record["phase"])
        for record in map(json.loads, lines)
        if record.get("stage") == "pre-launch-cpu"
    ]


def _dispatch(*, tmp_path: Path, journal: JournalFile) -> None:
    anything: Any = object()
    lifetime: Any = SimpleNamespace(identity=SimpleNamespace(dispatch_id="dispatch-7"))
    _ = loop_module._dispatch_one_locked(  # noqa: SLF001 - the exact boundary under test.
        args=argparse.Namespace(),
        repo=tmp_path,
        item=SimpleNamespace(id="bd-ib-5d5aue"),
        journal=journal,
        janitor=None,
        verdict=anything,
        lifetime=lifetime,
    )


def test_a_helper_phase_that_raises_closes_its_row_and_propagates() -> None:
    names: list[str] = []

    def checkpoint(*, name: str) -> None:
        names.append(name)

    def boom() -> None:
        raise RuntimeError("boom")

    with (
        pytest.raises(RuntimeError, match="boom"),
        prelaunch_phase(checkpoint=checkpoint, name="spin"),
    ):
        boom()

    assert names == ["spin"]


def test_a_failing_record_dispatch_still_journals_its_row(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    journal = JournalFile(path=tmp_path / "journal.jsonl")

    def boom(**_: object) -> object:
        raise RuntimeError("record")

    monkeypatch.setattr(loop_module, "record_dispatch", boom)

    with pytest.raises(RuntimeError, match="record"):
        _dispatch(tmp_path=tmp_path, journal=journal)

    assert _rows(journal=journal) == ["record-dispatch"]


def test_a_failing_github_app_auth_still_journals_its_row(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    journal = JournalFile(path=tmp_path / "journal.jsonl")

    def boom() -> object:
        raise RuntimeError("auth")

    monkeypatch.setattr(loop_module, "record_dispatch", lambda **_: SimpleNamespace(plan=_plan()))
    monkeypatch.setattr(loop_module.selfup, "github_token_supplier", boom)

    with pytest.raises(RuntimeError, match="auth"):
        _dispatch(tmp_path=tmp_path, journal=journal)

    assert _rows(journal=journal) == ["record-dispatch", "github-app-auth"]


def test_a_failing_dispatch_span_still_journals_its_row(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    names: list[str] = []

    def checkpoint(*, name: str) -> None:
        names.append(name)

    def boom(**_: object) -> None:
        raise RuntimeError("span")

    monkeypatch.setattr(run_module, "emit_dispatch_span", boom)
    monkeypatch.setattr(run_module, "dispatch_spans_path", lambda **_: tmp_path / "spans.jsonl")
    anything: Any = object()

    with pytest.raises(RuntimeError, match="span"):
        _ = run_module.run_dispatch_with_watchdog(
            context=run_module.DispatchRunContext(
                args=argparse.Namespace(poll_attempts=1, poll_interval_seconds=0.0),
                repo=tmp_path,
                plan=_plan(),
                journal=JournalFile(path=tmp_path / "journal.jsonl"),
                overlay_file=tmp_path / "overlay.toml",
                token_supplier=lambda: "token",
                dispatch_id="dispatch-7",
                prelaunch_checkpoint=checkpoint,
            ),
            run_dispatch_func=anything,
            fabro_launcher_type=anything,
        )

    assert names == ["dispatch-span"]
