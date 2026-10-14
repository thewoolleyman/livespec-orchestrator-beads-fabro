"""The cap that triggered a non-convergence bounce, and what was observed.

Plan slice S4 (`bd-ib-tbgxm4`). The bounce path was unobservable in the one
place a calibration reading looks: `bounced_to_regroom` was keyed on the
watchdog's `stalled-no-progress` status ALONE, so the DOT fix-loop-cap
exhaustion — the signal the ratified design names as the reactive ceiling's
training signal — bounced the item to `backlog` while the calibration record
said `bounced_to_regroom: false`. Measured across 445 of this repository's own
records (plan research,
`plan/factory-test-first-enforcement/research/opening-research-2026-09-30.md`):
the flag was true on ZERO of them.

Two things are repaired here. The flag now reads the SAME predicate the bounce
itself reads, so a record cannot say "not bounced" about an item the Dispatcher
moved to `backlog`. And the bounce names WHICH cap tripped it, so a reading can
separate a watchdog stall from a fix-loop exhaustion instead of averaging two
unrelated failure modes.

WHY THE DOT CASE RECORDS NO OBSERVED VALUE. The fix-loop visit counter lives
inside the sandbox graph and the terminal carries no measurement of it, so the
observation is absent. Restating the CONFIGURED cap there would report a
constant as a measurement, which is the reading this repository's own trap
catalogue warns is indistinguishable from evidence. The watchdog case is
different: `decide_stall` confirms a stall only when the last-event timestamp
held across the FULL window, so the resolved window IS the measured quiet
duration at the moment it fired.
"""

from __future__ import annotations

import importlib
from dataclasses import dataclass, field
from pathlib import Path
from types import ModuleType

import pytest
from livespec_orchestrator_beads_fabro.commands import _dispatcher_completion
from livespec_orchestrator_beads_fabro.commands._dispatcher_calibration import bounced_to_regroom
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import DispatchOutcome
from livespec_orchestrator_beads_fabro.commands._dispatcher_plan import NON_CONVERGED_MARKER
from livespec_orchestrator_beads_fabro.commands._dispatcher_stall_window import (
    resolve_stall_window,
)
from livespec_orchestrator_beads_fabro.errors import WorkItemNotFoundError
from livespec_orchestrator_beads_fabro.types import WorkItem

_MODULE_NAME = "livespec_orchestrator_beads_fabro.commands._dispatcher_non_convergence_cap"
_MODULE_PATH = (
    Path(__file__).resolve().parents[3]
    / ".claude-plugin"
    / "scripts"
    / "livespec_orchestrator_beads_fabro"
    / "commands"
    / "_dispatcher_non_convergence_cap.py"
)
_CALIBRATION_MODULE_NAME = "livespec_orchestrator_beads_fabro.commands._dispatcher_calibration"
_ITEM_ID = "bd-ib-tbgxm4"
_BOUNCE_STAGE = "non-convergence-bounce"
_BOUNCE_ERROR_STAGE = "non-convergence-bounce-error"
_CAP_KEY = "bounce_cap"
_OBSERVED_KEY = "bounce_cap_observed"


def _module() -> ModuleType:
    """Import the module under test, asserting it exists first."""
    assert _MODULE_PATH.is_file(), f"{_MODULE_PATH} does not exist yet"
    return importlib.import_module(_MODULE_NAME)


def _calibration() -> ModuleType:
    """The calibration derivation module, reached by name rather than imported.

    The record field and the builder keyword land in this same change, so a
    top-level import of either would make the Red a type error instead of a
    failed assertion.
    """
    return importlib.import_module(_CALIBRATION_MODULE_NAME)


@dataclass(kw_only=True)
class _RecordingJournal:
    records: list[dict[str, object]] = field(default_factory=list)

    def append(self, *, record: dict[str, object]) -> None:
        self.records.append(record)


def _item() -> WorkItem:
    return WorkItem(
        id=_ITEM_ID,
        type="feature",
        status="active",
        title="Repair factory sizing telemetry",
        description="## Definition of Done\n\n- The bounce names its cap.\n",
        origin="freeform",
        gap_id=None,
        rank="a3",
        assignee="fabro",
        depends_on=(),
        captured_at="2026-10-06T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
    )


def _outcome(*, status: str, stage: str = "fabro-run", detail: str = "") -> DispatchOutcome:
    return DispatchOutcome(
        work_item_id=_ITEM_ID,
        status=status,
        stage=stage,
        pr_number=None,
        merge_sha=None,
        detail=detail,
    )


def _stalled() -> DispatchOutcome:
    return _outcome(
        status="stalled-no-progress",
        detail="run made no progress for the full stall window",
    )


def _cap_exhausted() -> DispatchOutcome:
    return _outcome(
        status="failed",
        detail=f"{NON_CONVERGED_MARKER}: janitor fix-loop cap hit without converging",
    )


def _write_stall_timeout(*, repo: Path, seconds: int) -> None:
    """Declare `dispatcher.stall_timeout_seconds` in `repo`'s committed config.

    The bounce resolves the window the watchdog graded against from the
    dispatch target's own configuration, so a test that wants a particular
    observed figure writes the key the resolver reads.
    """
    _ = (repo / ".livespec.jsonc").write_text(
        '{"livespec-orchestrator-beads-fabro": {"dispatcher": '
        f'{{"stall_timeout_seconds": {seconds}}}}}}}\n',
        encoding="utf-8",
    )


def _bounce(
    *, monkeypatch: pytest.MonkeyPatch, outcome: DispatchOutcome, tmp_path: Path
) -> tuple[_RecordingJournal, list[dict[str, object]]]:
    """Drive the bounce with the ledger seam captured rather than reached."""
    journal = _RecordingJournal()
    writes: list[dict[str, object]] = []

    def _record_write(**kwargs: object) -> None:
        writes.append(kwargs)

    monkeypatch.setattr(_dispatcher_completion, "store_config", lambda *, repo: repo)
    monkeypatch.setattr(_dispatcher_completion, "update_work_item_status", _record_write)
    _dispatcher_completion.bounce_non_convergence_to_backlog(
        repo=tmp_path,
        item=_item(),
        outcome=outcome,
        journal=journal,
    )
    return journal, writes


def _stage_record(*, journal: _RecordingJournal, stage: str) -> dict[str, object]:
    matching = [record for record in journal.records if record.get("stage") == stage]
    assert len(matching) == 1, f"expected one {stage!r} record, got {len(matching)}"
    return matching[0]


# --- the cap classification ------------------------------------------------


def test_a_watchdog_stall_names_no_cap_and_observes_nothing() -> None:
    """`bd-ib-nfbyot`: a stall is not a non-convergence, so it trips no cap.

    This asserted the opposite — the resolved window as the cap and the figure
    as its observation — until `contracts.md`'s "Dispatcher progress watchdog"
    ruled that "the calibration analysis pass MUST NOT count it as a
    non-convergence observation". The window still reaches an operator, on the
    `watchdog-stall-cancel` record the cancel journals.
    """
    module = _module()

    cap = module.non_convergence_cap(outcome=_stalled(), stall_seconds=1800.0)

    assert cap == module.UNTRIGGERED_NON_CONVERGENCE_CAP


def test_a_fix_loop_exhaustion_names_its_cap_and_observes_nothing() -> None:
    """A constant restated as an observation is not evidence, so it is absent."""
    module = _module()

    cap = module.non_convergence_cap(outcome=_cap_exhausted(), stall_seconds=1800.0)

    assert cap.cap == module.FIX_LOOP_VISIT_CAP
    assert cap.observed is None


def test_a_terminal_that_is_not_non_convergence_names_no_cap_at_all() -> None:
    """A green run, an ordinary failure and a human-gate park trip no cap."""
    module = _module()

    for outcome in (
        _outcome(status="green", stage="done"),
        _outcome(status="failed", stage="pr-view", detail="no PR found for branch"),
        _outcome(status="blocked", detail=NON_CONVERGED_MARKER),
    ):
        cap = module.non_convergence_cap(outcome=outcome, stall_seconds=1800.0)
        assert cap.cap is None
        assert cap.observed is None


def test_the_cap_flattens_to_two_sibling_journal_keys() -> None:
    """Flat scalars, so the egress leg promotes each without unwrapping a map."""
    module = _module()

    record = module.non_convergence_cap(outcome=_cap_exhausted(), stall_seconds=900.0).as_record()

    assert record == {_CAP_KEY: module.FIX_LOOP_VISIT_CAP, _OBSERVED_KEY: None}
    assert module.UNTRIGGERED_NON_CONVERGENCE_CAP.as_record() == {
        _CAP_KEY: None,
        _OBSERVED_KEY: None,
    }


def test_the_fix_loop_cap_names_the_graph_guard_an_operator_would_tune() -> None:
    """The one cap identity a bounce can name points at the guard that enforces it.

    `STALL_WINDOW_CAP` was asserted here beside the resolver that reads its
    committed key, until `bd-ib-nfbyot` removed the stall arm. The resolver is
    still asserted — in `test_the_stall_window_still_resolves_its_committed_key`
    below — because the key did not stop existing; it stopped being a cap.
    """
    module = _module()

    assert module.FIX_LOOP_VISIT_CAP == "workflow.janitor_fix_loop_visit_cap"


def test_the_stall_window_still_resolves_its_committed_key(tmp_path: Path) -> None:
    """The window the cancel record names is read from the key an operator writes.

    Retained from the removed cap assertion: a cancel record pointing at a knob
    that moves nothing is worse than no name at all, and that remains true now
    that the window rides the cancel record instead of a bounce cap.
    """
    _write_stall_timeout(repo=tmp_path, seconds=60)

    assert resolve_stall_window(cwd=tmp_path).seconds == 60.0


# --- the flag reads the same predicate the bounce reads ---------------------


def test_a_cap_triggered_bounce_is_reported_as_bounced_to_regroom() -> None:
    """The repair: the DOT exhaustion bounced the item while the flag said false."""
    assert bounced_to_regroom(outcome=_cap_exhausted()) is True


def test_a_watchdog_stall_is_not_reported_as_bounced_to_regroom() -> None:
    """`bd-ib-nfbyot`: a hang is not a slice that would not converge.

    This test asserted the opposite until the watchdog status was removed from
    `is_non_convergence_outcome`. `contracts.md`'s "Dispatcher progress
    watchdog" says a `stalled-no-progress` outcome "is NOT factory
    non-convergence", and the flag reads the same predicate the bounce reads,
    so the two surfaces move together by construction rather than by promise.
    """
    assert bounced_to_regroom(outcome=_stalled()) is False


def test_a_run_the_dispatcher_does_not_bounce_is_not_reported_as_bounced() -> None:
    """Narrow, deliberately: an ordinary failure must not read as a bounce."""
    assert bounced_to_regroom(outcome=_outcome(status="green", stage="done")) is False
    assert (
        bounced_to_regroom(outcome=_outcome(status="failed", stage="pr-view", detail="no PR"))
        is False
    )
    assert bounced_to_regroom(outcome=_outcome(status="blocked", detail=NON_CONVERGED_MARKER)) is (
        False
    )


# --- the transition and its record -----------------------------------------


def test_a_cap_triggered_bounce_writes_backlog_through_the_lifecycle_seam(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """One store-seam status write to `backlog`; nothing else moves the item."""
    module = _module()

    journal, writes = _bounce(monkeypatch=monkeypatch, outcome=_cap_exhausted(), tmp_path=tmp_path)

    assert len(writes) == 1
    assert writes[0]["item_id"] == _ITEM_ID
    assert writes[0]["status"] == "backlog"
    record = _stage_record(journal=journal, stage=_BOUNCE_STAGE)
    assert record[_CAP_KEY] == module.FIX_LOOP_VISIT_CAP
    assert record[_OBSERVED_KEY] is None


def test_a_stall_cancel_reaches_no_bounce_and_so_writes_no_record(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """`bd-ib-nfbyot`: the bounce declines a stall before touching the ledger.

    Both halves are asserted because they fail independently: a build that
    journals the row but skips the status write, and one that moves the item
    while journaling nothing, each satisfy exactly one of them. The stall
    window is still declared so a build that resolved it and then bounced
    anyway cannot pass for a build that declined.
    """
    _write_stall_timeout(repo=tmp_path, seconds=1200)

    journal, writes = _bounce(monkeypatch=monkeypatch, outcome=_stalled(), tmp_path=tmp_path)

    assert writes == []
    assert [record.get("stage") for record in journal.records] == []


def test_a_failed_ledger_write_still_records_which_cap_tripped(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The escalation that could not land is the one most worth naming."""
    module = _module()
    journal = _RecordingJournal()

    def _raise(**_kwargs: object) -> None:
        # One of the ledger-write errors the bounce swallows: the item vanished
        # between dispatch and bounce. An exception OUTSIDE that set is a bug and
        # must still propagate, so it would be the wrong fixture here.
        raise WorkItemNotFoundError(item_id=_ITEM_ID)

    monkeypatch.setattr(_dispatcher_completion, "store_config", lambda *, repo: repo)
    monkeypatch.setattr(_dispatcher_completion, "update_work_item_status", _raise)
    _dispatcher_completion.bounce_non_convergence_to_backlog(
        repo=tmp_path,
        item=_item(),
        outcome=_cap_exhausted(),
        journal=journal,
    )

    record = _stage_record(journal=journal, stage=_BOUNCE_ERROR_STAGE)
    assert record[_CAP_KEY] == module.FIX_LOOP_VISIT_CAP
    assert record[_OBSERVED_KEY] is None


def test_a_terminal_that_trips_no_cap_bounces_nothing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    journal, writes = _bounce(
        monkeypatch=monkeypatch,
        outcome=_outcome(status="failed", stage="pr-view", detail="no PR found for branch"),
        tmp_path=tmp_path,
    )

    assert writes == []
    assert journal.records == []


# --- the calibration record carries both fields ---------------------------


def test_the_calibration_record_and_journal_carry_the_cap_and_its_observation() -> None:
    """A bounce reading can separate a watchdog stall from a fix-loop exhaustion."""
    module = _module()
    calibration = _calibration()

    record = calibration.build_calibration_record(
        item=_item(),
        outcome=_cap_exhausted(),
        repo_name="repo",
        journal_records=(),
        wall_clock_seconds=12.5,
        token_cost_micros=None,
        dispatch_context_size=900,
        merged_pr_diff_size=None,
        bounce_cap=module.non_convergence_cap(outcome=_cap_exhausted(), stall_seconds=1800.0),
    )
    journal = calibration.calibration_journal_record(record=record)

    assert journal["bounced_to_regroom"] is True
    assert journal[_CAP_KEY] == module.FIX_LOOP_VISIT_CAP
    assert journal[_OBSERVED_KEY] is None


def test_an_unwired_calibration_path_records_no_cap_rather_than_a_plausible_one() -> None:
    """The default is the untriggered value, so an unwired caller journals nulls."""
    calibration = _calibration()

    record = calibration.build_calibration_record(
        item=_item(),
        outcome=_outcome(status="green", stage="done"),
        repo_name="repo",
        journal_records=(),
        wall_clock_seconds=1.0,
        token_cost_micros=None,
        dispatch_context_size=10,
        merged_pr_diff_size=None,
    )
    journal = calibration.calibration_journal_record(record=record)

    assert journal["bounced_to_regroom"] is False
    assert journal[_CAP_KEY] is None
    assert journal[_OBSERVED_KEY] is None
