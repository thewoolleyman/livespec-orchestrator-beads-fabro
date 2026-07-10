"""Unit coverage for full autonomous mode two-factor arming (the S1 arm slice).

Covers `livespec_orchestrator_beads_fabro.commands._dispatcher_autonomous`,
the pure arming decision plus its surfacing/journaling binding at the
Dispatcher `loop` entry. Pins SPECIFICATION/scenarios.md "Scenario 37 — Full
autonomous mode is default-off and explicitly armed": both factors are
required (the persistent `dispatcher.autonomous_mode` permission AND the
per-run `--mode autonomous` opt-in), the mode is never inferred from the key
alone, an armed run surfaces an explicit dangerous-mode acknowledgement, and
the arming is never persisted beyond the invocation.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro.commands._dispatcher_autonomous import (
    ArmingDecision,
    arm_autonomous_for_loop,
    dangerous_autonomous_surface,
    decide_arming,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import JournalFile

_PERMISSION_ENABLED = (
    '{"livespec-orchestrator-beads-fabro": {"dispatcher": {"autonomous_mode": true}}}'
)


def _armed_repo(*, tmp_path: Path) -> Path:
    _ = (tmp_path / ".livespec.jsonc").write_text(_PERMISSION_ENABLED, encoding="utf-8")
    return tmp_path


def _read_journal(*, path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.exists() else ""


# ---------------------------------------------------------------------------
# decide_arming — the two-factor decision (Scenario 37)
# ---------------------------------------------------------------------------


def test_decide_arming_armed_requires_both_factors() -> None:
    decision = decide_arming(mode="autonomous", permission=True)
    assert decision.armed is True
    assert decision.reason == "armed"


def test_decide_arming_flag_without_permission_does_not_arm() -> None:
    # `--mode autonomous` with the permission off is the ordinary full-queue
    # factory drain: it MUST NOT arm full autonomous mode.
    decision = decide_arming(mode="autonomous", permission=False)
    assert decision.armed is False
    assert decision.reason == "flag-without-permission"


def test_decide_arming_permission_without_flag_does_not_arm() -> None:
    # The mode is never inferred from the persistent key alone.
    decision = decide_arming(mode="shadow", permission=True)
    assert decision.armed is False
    assert decision.reason == "permission-without-flag"


def test_decide_arming_neither_factor_does_not_arm() -> None:
    decision = decide_arming(mode="shadow", permission=False)
    assert decision.armed is False
    assert decision.reason == "neither"


# ---------------------------------------------------------------------------
# dangerous_autonomous_surface — the explicit acknowledgement
# ---------------------------------------------------------------------------


def test_dangerous_surface_declares_danger_and_no_persist() -> None:
    line = dangerous_autonomous_surface(
        decision=ArmingDecision(armed=True, mode="autonomous", permission=True, reason="armed")
    )
    assert "DANGEROUS" in line
    assert "ARMED" in line
    assert "NOT persisted" in line
    assert line.endswith("\n")


# ---------------------------------------------------------------------------
# arm_autonomous_for_loop — resolve + surface + journal binding
# ---------------------------------------------------------------------------


def test_arm_for_loop_armed_surfaces_and_journals(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = _armed_repo(tmp_path=tmp_path)
    journal_path = tmp_path / "journal.jsonl"
    journal = JournalFile(path=journal_path)

    decision = arm_autonomous_for_loop(mode="autonomous", repo=repo, journal=journal)

    assert decision.armed is True
    assert "DANGEROUS" in capsys.readouterr().err
    assert "autonomous-armed" in _read_journal(path=journal_path)


def test_arm_for_loop_flag_without_permission_is_silent(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # No `.livespec.jsonc` -> permission off. `--mode autonomous` alone is the
    # ordinary drain: not armed, no surface, no journal record.
    journal_path = tmp_path / "journal.jsonl"
    journal = JournalFile(path=journal_path)

    decision = arm_autonomous_for_loop(mode="autonomous", repo=tmp_path, journal=journal)

    assert decision.armed is False
    assert capsys.readouterr().err == ""
    assert _read_journal(path=journal_path) == ""
