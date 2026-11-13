"""The recovery reader's factory boundary and liveness answers."""

from __future__ import annotations

import argparse
import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from types import SimpleNamespace

import pytest
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandResult
from livespec_orchestrator_beads_fabro.commands._dispatcher_resume_factory_reading import (
    FactoryReading,
    factory_reading,
)
from livespec_orchestrator_beads_fabro.types import WorkItem

_ITEM_ID = "hxi-wv762e"
_EARLIER_RUN = "01M778HJT951KC7G0BSC0V3MVW"
_SERVER = "http://petri:32276"
_WRAPPER = "/host/default-family-wrapper"


@dataclass(kw_only=True)
class _Runner:
    """Return the answer keyed by the innermost Fabro command."""

    answers: dict[str, CommandResult]
    calls: list[tuple[list[str], Mapping[str, str | None] | None]] = field(default_factory=list)

    def run(
        self,
        *,
        argv: list[str],
        cwd: Path,
        timeout_seconds: float,
        env: Mapping[str, str | None] | None = None,
        stdin: int | None = None,
    ) -> CommandResult:
        _ = (cwd, timeout_seconds, stdin)
        self.calls.append((argv, env))
        fabro_index = next(index for index, value in enumerate(argv) if Path(value).name == "fabro")
        return self.answers[argv[fabro_index + 1]]


def _ok(*, payload: object) -> CommandResult:
    return CommandResult(exit_code=0, stdout=json.dumps(payload), stderr="")


def _failed() -> CommandResult:
    return CommandResult(exit_code=1, stdout="", stderr="unreachable")


def _item() -> WorkItem:
    return WorkItem(
        id=_ITEM_ID,
        type="task",
        status="ready",
        title="Recovery liveness stays outside the tenant wrapper",
        description="## Definition of Done\n\n- Factory liveness is observable.\n",
        origin="freeform",
        gap_id=None,
        rank="a0",
        assignee=None,
        depends_on=(),
        captured_at="2026-11-13T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
    )


def _journal(*, path: Path) -> Path:
    rows = [
        {"stage": "run-stamp", "work_item_id": _ITEM_ID, "run_id": _EARLIER_RUN},
        {"stage": "run-stamp", "work_item_id": _ITEM_ID, "run_id": "later-run"},
    ]
    _ = path.write_text("".join(f"{json.dumps(row)}\n" for row in rows), encoding="utf-8")
    return path


def _args(*, target: object | None = None) -> argparse.Namespace:
    return argparse.Namespace(fabro_bin="fabro", fabro_factory_target=target)


def _reading(
    *,
    tmp_path: Path,
    args: argparse.Namespace,
    runner: _Runner,
    earlier_run_id: str | None = _EARLIER_RUN,
) -> FactoryReading:
    return factory_reading(
        args=args,
        repo=tmp_path,
        item=_item(),
        journal_path=_journal(path=tmp_path / "journal.jsonl"),
        earlier_run_id=earlier_run_id,
        runner=runner,
    )


def test_the_host_wrapper_reads_an_ended_run_without_tenant_factory_settings(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A sealed tenant's earlier terminal run is observable rather than held."""
    monkeypatch.setenv("LIVESPEC_FACTORY_READ_WRAPPER", _WRAPPER)
    target = SimpleNamespace(name="petri", server=_SERVER, dev_token=None)
    runner = _Runner(
        answers={
            "ps": _ok(
                payload=[
                    {
                        "run_id": _EARLIER_RUN,
                        "status": "failed",
                        "goal": f"Work-item: {_ITEM_ID}",
                    }
                ]
            ),
            "inspect": _ok(payload=[{"status": "failed"}]),
        }
    )

    reading = _reading(tmp_path=tmp_path, args=_args(target=target), runner=runner)

    assert reading.observed is True
    assert reading.live_runs == ()
    argv, environment = runner.calls[0]
    assert argv[:4] == [
        _WRAPPER,
        "--",
        "sh",
        "-ec",
    ]
    assert argv[5:8] == [
        "factory-read",
        "petri",
        _SERVER,
    ]
    assert "FABRO_DEV_TOKEN__$factory" in argv[4]
    assert environment is None


def test_factory_liveness_failure_remains_unobservable(tmp_path: Path) -> None:
    """A factory error differs from a terminal earlier run the factory reports."""
    runner = _Runner(answers={"ps": _failed()})

    reading = _reading(tmp_path=tmp_path, args=_args(), runner=runner)

    assert reading.observed is False
    assert reading.live_runs == ()
    assert reading.executing_node is None


def test_a_live_earlier_run_is_inspected_and_a_journal_fallback_can_succeed(tmp_path: Path) -> None:
    """Both the held-run inspection and the journal's latest-id fallback are preserved."""
    live_runner = _Runner(
        answers={
            "ps": _ok(
                payload=[
                    {
                        "run_id": _EARLIER_RUN,
                        "status": "running",
                        "goal": f"Work-item: {_ITEM_ID}",
                    }
                ]
            ),
            "inspect": _ok(payload=[{"checkpoints": [{"checkpoint": {"next_node_id": "review"}}]}]),
        }
    )
    live = _reading(tmp_path=tmp_path, args=_args(), runner=live_runner)
    succeeded_runner = _Runner(
        answers={
            "ps": _ok(payload=[{"run_id": "later-run", "status": "succeeded", "goal": "other"}]),
            "inspect": _ok(payload=[]),
        }
    )
    succeeded = _reading(
        tmp_path=tmp_path,
        args=_args(),
        runner=succeeded_runner,
        earlier_run_id=None,
    )

    assert live.executing_node == "review"
    assert live.live_runs[0].run_id == _EARLIER_RUN
    assert succeeded.observed is True
    assert succeeded.earlier_run_succeeded is True
