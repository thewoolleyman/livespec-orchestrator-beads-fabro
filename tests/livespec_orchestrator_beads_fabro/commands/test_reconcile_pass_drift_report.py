"""The cleanup reconcile pass does not report a drift lane."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from livespec_orchestrator_beads_fabro._beads_client import reset_fake_singleton
from livespec_orchestrator_beads_fabro.commands import _dispatcher_reconcile_runs_command as command

from tests.livespec_orchestrator_beads_fabro.commands.test_reconcile_pass_drift_lane_wiring import (
    _intercept_drift_lane,
)

if TYPE_CHECKING:
    from collections.abc import Iterator


@pytest.fixture(autouse=True)
def _hermetic_fake_backend() -> Iterator[None]:
    reset_fake_singleton()
    yield
    reset_fake_singleton()


def _project(*, root: Path) -> None:
    _ = (root / ".livespec.jsonc").write_text(
        json.dumps(
            {
                "livespec-orchestrator-beads-fabro": {
                    "connection": {
                        "tenant": "t",
                        "prefix": "bd-ib",
                        "server_user": "u",
                        "database": "d",
                        "bd_path": "bd",
                        "fake": True,
                    },
                    "dispatcher": {},
                }
            },
            indent=2,
        ),
        encoding="utf-8",
    )


def _args(*, root: Path, as_json: bool) -> argparse.Namespace:
    return argparse.Namespace(
        repo=str(root),
        factory=None,
        fabro_bin="fabro",
        dry_run=False,
        as_json=as_json,
        journal=str(root / "journal.jsonl"),
        calibration_spans=str(root / "spans.jsonl"),
        invoker="role:test",
    )


def test_the_json_projection_carries_no_drift_entry(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _project(root=tmp_path)

    _ = command.run_reconcile_runs_command(args=_args(root=tmp_path, as_json=True))

    payload = json.loads(capsys.readouterr().out)
    assert "drift" not in payload


def test_the_human_output_carries_no_drift_line(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _project(root=tmp_path)

    exit_code = command.run_reconcile_runs_command(args=_args(root=tmp_path, as_json=False))

    output = capsys.readouterr().out
    assert exit_code == 1
    assert "DRIFT" not in output


def test_the_forbidden_drift_spy_records_a_hypothetical_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Keep the no-call sentinel itself covered without exercising cleanup."""
    seen = _intercept_drift_lane(monkeypatch=monkeypatch)

    command.run_drift_lane(source="coverage")

    assert seen == [{"source": "coverage"}]
