"""Every reconcile pass runs the drift lane — and a DRY pass runs nothing.

The binding half of assertion 1 of `bd-ib-yvjxo4`: "EACH reconcile pass
enumerates every default-branch merge after the recorded frontier". The lane
being correct is a separate claim from the lane being REACHED, and only the
second makes the contract's "each reconcile pass" true — a lane nothing calls
is a primitive, not a binding.

THE DRY PASS IS THE CONTROL, and it is not symmetry for its own sake. The
command's own contract says a dry run "performs no export, no termination, and
no journal write", and the drift lane's whole output is a record on the
detection-coverage anchor plus a proposal document under `proposed_changes/`.
A dry pass that filed a proposal would be an act taken by a projection — so a
build that called the lane unconditionally fails here while satisfying the
live case exactly as well as a correct one.

AND THE LANE IS REACHED WITH NO FACTORY SURVEYED, which is the third case. The
two lanes answer unrelated questions, and this command returns non-zero when it
surveyed no factory; a build that ran the drift lane only on an otherwise
healthy pass would stop judging merges on every host whose factory table went
unresolvable, with nothing naming the drift lane as the casualty.
"""

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


def _calls(*, monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    """Record every drift-lane call the command makes, without running one."""
    seen: list[dict[str, Any]] = []

    def _lane(**kwargs: Any) -> None:
        seen.append(kwargs)

    monkeypatch.setattr(command, "run_drift_lane", _lane)
    monkeypatch.setattr(command, "drift_judge", lambda **kwargs: kwargs)
    return seen


def test_a_live_reconcile_pass_runs_the_drift_lane_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _project(root=tmp_path)
    seen = _calls(monkeypatch=monkeypatch)

    _ = command.run_reconcile_runs_command(args=_args(root=tmp_path, dry_run=False))
    _ = capsys.readouterr()

    assert len(seen) == 1
    assert seen[0]["repo"] == tmp_path


def test_a_dry_reconcile_pass_runs_the_drift_lane_not_at_all(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _project(root=tmp_path)
    seen = _calls(monkeypatch=monkeypatch)

    _ = command.run_reconcile_runs_command(args=_args(root=tmp_path, dry_run=True))
    _ = capsys.readouterr()

    assert seen == []


def test_the_drift_lane_runs_even_when_no_factory_was_surveyed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _project(root=tmp_path)
    seen = _calls(monkeypatch=monkeypatch)

    exit_code = command.run_reconcile_runs_command(args=_args(root=tmp_path, dry_run=False))
    _ = capsys.readouterr()

    # This fixture declares no factories table, so the runs lane surveyed
    # nothing and the command reports that. The drift lane ran regardless, and
    # its own state is recorded on the anchor rather than in this exit code.
    assert exit_code == 1
    assert len(seen) == 1
