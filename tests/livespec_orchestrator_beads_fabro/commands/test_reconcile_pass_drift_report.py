"""The reconcile pass emits runs-lane output without a drift projection."""

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


def test_the_json_projection_carries_no_drift_key(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _project(root=tmp_path)

    exit_code = command.run_reconcile_runs_command(args=_args(root=tmp_path, as_json=True))

    payload = json.loads(capsys.readouterr().out)
    assert (exit_code, "drift" not in payload) == (1, True)


def test_the_human_output_carries_no_drift_line_and_keeps_the_runs_exit_code(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _project(root=tmp_path)

    exit_code = command.run_reconcile_runs_command(args=_args(root=tmp_path, as_json=False))

    lines = capsys.readouterr().out.splitlines()
    assert (exit_code, all(not line.startswith("DRIFT") for line in lines), lines) == (
        1,
        True,
        [
            "ERROR   (none)  no-factory-surveyed: this pass surveyed no factory, so it "
            "reconciled nothing and observed nothing"
        ],
    )
