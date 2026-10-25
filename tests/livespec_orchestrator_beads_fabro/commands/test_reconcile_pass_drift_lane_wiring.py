"""The reconcile pass does cleanup only, without drift or model judgement.

The root timer exists to reconcile factory runs and work-item claims. Drift
assessment is a separately scheduled operation: invoking either the drift lane
or its model judge here spends tokens during a cleanup pass and advances the
recorded frontier from the wrong trigger.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from livespec_orchestrator_beads_fabro._beads_client import reset_fake_singleton
from livespec_orchestrator_beads_fabro.commands import _dispatcher_reconcile_runs_command as command

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


def _args(*, root: Path, dry_run: bool) -> argparse.Namespace:
    return argparse.Namespace(
        repo=str(root),
        factory=None,
        fabro_bin="fabro",
        dry_run=dry_run,
        as_json=True,
        journal=str(root / "journal.jsonl"),
        calibration_spans=str(root / "spans.jsonl"),
        invoker="role:test",
    )


def _calls(*, monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Record any drift-lane or model-judge call a cleanup pass makes."""
    seen: list[str] = []

    monkeypatch.setattr(
        command, "run_drift_lane", lambda **_kwargs: seen.append("lane"), raising=False
    )
    monkeypatch.setattr(
        command, "drift_judge", lambda **_kwargs: seen.append("judge"), raising=False
    )
    return seen


def test_a_live_reconcile_pass_runs_no_drift_lane_or_model_judge(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _project(root=tmp_path)
    seen = _calls(monkeypatch=monkeypatch)

    exit_code = command.run_reconcile_runs_command(args=_args(root=tmp_path, dry_run=False))
    _ = capsys.readouterr()

    assert (exit_code, seen) == (1, [])


def test_a_dry_reconcile_pass_runs_no_drift_lane_or_model_judge(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _project(root=tmp_path)
    seen = _calls(monkeypatch=monkeypatch)

    _ = command.run_reconcile_runs_command(args=_args(root=tmp_path, dry_run=True))
    _ = capsys.readouterr()

    assert seen == []
