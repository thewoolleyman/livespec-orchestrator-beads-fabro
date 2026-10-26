"""A live reconcile pass performs cleanup without entering the drift lane."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

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


def _args(*, root: Path) -> argparse.Namespace:
    return argparse.Namespace(
        repo=str(root),
        factory=None,
        fabro_bin="fabro",
        dry_run=False,
        as_json=True,
        journal=str(root / "journal.jsonl"),
        calibration_spans=str(root / "spans.jsonl"),
        invoker="role:test",
    )


def _intercept_drift_lane(*, monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    """Capture a forbidden drift call without letting it touch the test project."""
    seen: list[dict[str, Any]] = []

    def _lane(**kwargs: Any) -> None:
        seen.append(kwargs)

    monkeypatch.setattr(command, "run_drift_lane", _lane, raising=False)
    return seen


def test_a_live_reconcile_pass_runs_no_drift_lane_or_model_judgement(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _project(root=tmp_path)
    seen = _intercept_drift_lane(monkeypatch=monkeypatch)

    exit_code = command.run_reconcile_runs_command(args=_args(root=tmp_path))
    _ = capsys.readouterr()

    assert exit_code == 1
    assert seen == []
    assert not hasattr(command, "drift_judge")
