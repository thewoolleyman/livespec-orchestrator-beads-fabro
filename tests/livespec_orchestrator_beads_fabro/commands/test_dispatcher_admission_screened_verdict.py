"""The valve reuses the pre-dispatch screen's headroom reading only while it is fresh.

`bd-ib-tsrkqf`. The session-headroom screen now runs ahead of the expensive
pre-dispatch rows, so a dispatch it PASSES reaches the admission valve after
those rows have run. The valve must not spend a second provider request to
re-ask what the screen just answered -- Scenario 231 counts the requests of one
dispatch -- and it must not trust a reading the intervening rows have made stale,
because the clause requires the assessment before claim.

Both halves are bound here, each beside the control that makes it evidence: the
reuse case would also pass a valve that ignored the hand-over and read again
only if the read were uncounted, so the read IS counted; and the stale case
advances the clock rather than sleeping, since a real wait would test the test.
"""

from __future__ import annotations

import argparse
import importlib
import time
from dataclasses import dataclass
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro.commands import _acp_candidate_preflight as preflight
from livespec_orchestrator_beads_fabro.commands import _dispatcher_admission as admission_module
from livespec_orchestrator_beads_fabro.commands import (
    _dispatcher_screened_verdict as screened_module,
)
from livespec_orchestrator_beads_fabro.commands._acp_hold_ledger import read_acp_hold_ledger
from livespec_orchestrator_beads_fabro.commands._acp_preflight_verdict import (
    AcpPreflightVerdict,
    build_acp_preflight_verdict,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import JournalFile
from livespec_orchestrator_beads_fabro.types import WorkItem

_NOW = "2026-10-28T15:31:00Z"
_GRAPH = """
    start [shape=Mdiamond]
    exit  [shape=Msquare]
    start -> exit
"""


@dataclass(frozen=True, kw_only=True)
class _Accounting:
    active_count: int = 0
    live_lock_active_ids: tuple[str, ...] = ()
    journal_unreadable_active_ids: tuple[str, ...] = ()
    green_terminal_active_ids: tuple[str, ...] = ()
    rework_pending_active_ids: tuple[str, ...] = ()


def _verdict() -> AcpPreflightVerdict:
    return build_acp_preflight_verdict(
        chains={},
        graph_text=_GRAPH,
        ledger=read_acp_hold_ledger(journal_path=None, now_iso=_NOW),
        inputs=preflight.PreflightInputs(builtin_pairs=frozenset(), headroom=None),
    )


def _admit(
    *,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    screened: screened_module.ScreenedVerdict | None,
) -> tuple[AcpPreflightVerdict, list[str]]:
    """Run an empty admission pass, returning its verdict and each resolution it made."""
    resolutions: list[str] = []
    resolved = _verdict()

    def counting_resolve(**_kwargs: object) -> AcpPreflightVerdict:
        resolutions.append("resolved")
        return resolved

    monkeypatch.setattr(admission_module, "resolve_acp_preflight", counting_resolve)
    monkeypatch.setattr(admission_module, "claimed_active_accounting", lambda **_: _Accounting())
    monkeypatch.setattr(admission_module, "store_config", lambda **_: tmp_path)
    monkeypatch.setattr(admission_module, "update_work_item_status", lambda **_: None)
    admission = admission_module.admit_and_select(
        repo=tmp_path,
        items=[],
        candidates=[],
        journal=JournalFile(path=tmp_path / "journal.jsonl"),
        enforce_cap=False,
        screened=screened,
    )
    assert admission.verdict is not None
    return admission.verdict, resolutions


def test_a_fresh_screened_verdict_is_reused_without_a_second_assessment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The valve answers from the screen's reading, and resolves nothing of its own."""
    screened = screened_module.ScreenedVerdict(verdict=_verdict(), taken_at=time.monotonic())

    verdict, resolutions = _admit(tmp_path=tmp_path, monkeypatch=monkeypatch, screened=screened)

    assert verdict is screened.verdict
    assert resolutions == []


def test_a_stale_screened_verdict_is_ignored_and_the_assessment_repeated(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The control: the rows between screen and claim can age a reading out."""
    screened = screened_module.ScreenedVerdict(verdict=_verdict(), taken_at=100.0)
    later = 100.0 + screened_module.SCREENED_VERDICT_REUSE_SECONDS
    monkeypatch.setattr(screened_module.time, "monotonic", lambda: later)

    verdict, resolutions = _admit(tmp_path=tmp_path, monkeypatch=monkeypatch, screened=screened)

    assert verdict is not screened.verdict
    assert resolutions == ["resolved"]


def test_a_valve_handed_no_screened_verdict_assesses_for_itself(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An invocation that never reached the screen is graded as it always was."""
    _, resolutions = _admit(tmp_path=tmp_path, monkeypatch=monkeypatch, screened=None)

    assert resolutions == ["resolved"]


def test_the_screened_verdict_is_read_off_the_arguments_only_when_it_is_one() -> None:
    """An absent attribute and a foreign value both mean there is no screen to reuse."""
    screened = screened_module.ScreenedVerdict(verdict=_verdict(), taken_at=1.0)
    carrying = argparse.Namespace(**{screened_module.SCREENED_VERDICT_ARG: screened})
    foreign = argparse.Namespace(**{screened_module.SCREENED_VERDICT_ARG: "not a verdict"})

    assert screened_module.screened_verdict_of(args=carrying) is screened
    assert screened_module.screened_verdict_of(args=foreign) is None
    assert screened_module.screened_verdict_of(args=argparse.Namespace()) is None


def test_a_screen_that_passes_leaves_its_verdict_on_the_arguments(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The hand-over the valve reads: set on a pass, and only on a pass of a real selection."""
    screen_module = importlib.import_module(
        "livespec_orchestrator_beads_fabro.commands._dispatcher_session_headroom_screen"
    )
    verdict = _verdict()
    monkeypatch.setattr(screen_module, "admission_acp_verdict", lambda **_: verdict)
    journal = JournalFile(path=tmp_path / "journal.jsonl")
    idle = argparse.Namespace()
    selected = argparse.Namespace()

    idle_refusal = screen_module.session_headroom_screen_refusal(
        args=idle, repo=tmp_path, items=[], journal=journal
    )
    refusal = screen_module.session_headroom_screen_refusal(
        args=selected, repo=tmp_path, items=[_item()], journal=journal
    )

    assert idle_refusal is None
    assert screened_module.screened_verdict_of(args=idle) is None
    assert refusal is None
    carried = screened_module.screened_verdict_of(args=selected)
    assert carried is not None
    assert carried.verdict is verdict


def _item() -> WorkItem:
    return WorkItem(
        id="bd-ib-tsrkqf",
        type="bug",
        status="ready",
        title="Run the session-headroom admission check first",
        description="Screen first.",
        origin="freeform",
        gap_id=None,
        rank="a0",
        assignee=None,
        depends_on=(),
        captured_at="2026-10-28T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
        admission_policy="auto",
        acceptance_policy="ai-only",
    )
