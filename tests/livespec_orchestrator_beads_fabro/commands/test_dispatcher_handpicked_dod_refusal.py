"""Tests for concise hand-picked Definition-of-Done refusals."""

from __future__ import annotations

from argparse import Namespace
from contextlib import nullcontext
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro.commands import _dispatcher_pre_dispatch_wall as wall


def test_handpicked_dod_refusal_writes_one_line(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A hand-picked Definition-of-Done decision has exactly one stderr line."""
    monkeypatch.setattr(wall, "prelaunch_phase", lambda **_kwargs: nullcontext())
    monkeypatch.setattr(
        wall,
        "_refusing_sequence",
        lambda **_kwargs: (
            (lambda: "REFUSED: work-item bd-ib-dod is held.\nDetail.", 5, False, "dod-judgement"),
        ),
    )
    monkeypatch.setattr(wall, "selection_credential_requirement", lambda **_kwargs: None)

    assert (
        wall.pre_dispatch_wall_exit(
            args=Namespace(items=["bd-ib-dod"]),
            repo=tmp_path,
            items=(),
            journal=Path(tmp_path / "journal"),
            prelaunch_checkpoint=None,
        )
        == 5
    )
    assert capsys.readouterr().err.splitlines() == ["REFUSED: work-item bd-ib-dod is held."]
