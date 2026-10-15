"""Integration-tier acceptance for the stall-watchdog cancel routing.

Binds SPECIFICATION/scenarios.md "Scenario 172 — A stall-watchdog cancel is
never non-convergence: a first cancel is released and recovered, a second rests
for a human" and the `contracts.md` section "Dispatcher progress watchdog"
paragraphs "Not non-convergence", "A first stall cancel is released and
recovered" and "A second consecutive stall cancel rests for a human".

WHY THE NOT-NON-CONVERGENCE CASE IS ASSERTED FROM BOTH ENDS. The defect this
module is the acceptance surface for is that one predicate answered two
questions: `is_non_convergence_outcome` graded the watchdog's
`stalled-no-progress` status as a fix-loop-cap exhaustion, so a hung sandbox and
a slice that genuinely would not converge produced the identical disposition —
the item went to `backlog` and the calibration pass counted a non-convergence
observation. Measured 2026-10-12: all six `watchdog-stall-cancel` rows since
2026-10-08 were followed within two seconds by a `non-convergence-bounce` row.
So the predicate is asserted directly AND the bounce it drives is asserted
against a live journal: the predicate alone passes on a build whose bounce reads
the status itself, and the bounce alone passes on a build that bounces nothing at
all.
"""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro._beads_client import reset_fake_singleton
from livespec_orchestrator_beads_fabro.commands._dispatcher_calibration import (
    build_calibration_record,
    calibration_journal_record,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_completion import (
    bounce_non_convergence_to_backlog,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import DispatchOutcome
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import JournalFile
from livespec_orchestrator_beads_fabro.commands._dispatcher_non_convergence_cap import (
    BOUNCE_CAP_KEY,
    BOUNCE_CAP_OBSERVED_KEY,
    FIX_LOOP_VISIT_CAP,
    NON_CONVERGENCE_BOUNCE_STAGE,
    UNTRIGGERED_NON_CONVERGENCE_CAP,
    non_convergence_cap,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_plan import (
    NON_CONVERGED_MARKER,
    is_non_convergence_outcome,
)
from livespec_orchestrator_beads_fabro.store import (
    append_work_item,
    materialize_work_items,
    read_work_items,
)
from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem

_ITEM_ID = "bd-ib-stall1"


@pytest.fixture(autouse=True)
def _fresh_tenant(monkeypatch: pytest.MonkeyPatch) -> object:
    """A fresh in-memory tenant per case, which is the hermetic CI backend.

    `LIVESPEC_BEADS_FAKE` is the ONLY seam that flips the store onto it, and the
    dispatcher resolves its own connection internally, so the toggle has to be
    set in the environment rather than passed down.
    """
    monkeypatch.setenv("LIVESPEC_BEADS_FAKE", "1")
    reset_fake_singleton()
    yield
    reset_fake_singleton()


def _config() -> StoreConfig:
    return StoreConfig(
        tenant="livespec-impl-beads",
        prefix="bd-ib",
        server_user="livespec-impl-beads",
        database="livespec-impl-beads",
        bd_path="bd",
        fake=True,
    )


def _repo(*, tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    _ = (repo / ".livespec.jsonc").write_text(
        '{"livespec-orchestrator-beads-fabro": {"connection": {"prefix": "bd-ib"}}}',
        encoding="utf-8",
    )
    return repo


def _item(**overrides: object) -> WorkItem:
    base = WorkItem(
        id=_ITEM_ID,
        type="bug",
        status="active",
        title="A dispatched slice the watchdog cancelled",
        description="Implement the slice.",
        origin="freeform",
        gap_id=None,
        rank="a0",
        assignee="fabro",
        depends_on=(),
        captured_at="2026-10-12T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
        admission_policy="auto",
        acceptance_policy="ai-only",
        acceptance_criteria="The dispatched slice is verified green by the check suite.",
    )
    return replace(base, **overrides)


def _outcome(*, status: str, stage: str = "fabro-run", detail: str = "") -> DispatchOutcome:
    return DispatchOutcome(
        work_item_id=_ITEM_ID,
        status=status,
        stage=stage,
        pr_number=None,
        merge_sha=None,
        detail=detail,
        fabro_run_id="01STALLRUN",
    )


def _journal(*, tmp_path: Path) -> JournalFile:
    """A journal whose file EXISTS before the first append.

    Pre-created so `_journal_records` needs no absent-file arm: a disposition
    that writes nothing leaves no file at all, and a helper branching on that
    would carry an arm no case in this module exercises.
    """
    path = tmp_path / "journal.jsonl"
    _ = path.write_text("", encoding="utf-8")
    return JournalFile(path=path)


def _journal_records(*, path: Path) -> list[dict[str, object]]:
    """Every record the journal file holds, as the dispatch wrote them."""
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def _stored() -> dict[str, WorkItem]:
    return materialize_work_items(records=read_work_items(path=_config()))


def test_a_stall_cancel_is_not_a_non_convergence_outcome() -> None:
    """The watchdog's own status is NOT the fix-loop-cap signal.

    A hang and a false kill are neither "a slice that repeatedly fails the
    janitor gate within the fix-loop cap", so the predicate that drives the
    `backlog` bounce must not recognise the watchdog status at all. The
    fix-loop-cap sentinel is asserted alongside it because a predicate that
    answered False for everything would satisfy the first assertion on its own.
    """
    assert not is_non_convergence_outcome(outcome=_outcome(status="stalled-no-progress"))
    assert is_non_convergence_outcome(
        outcome=_outcome(
            status="failed",
            detail=f"output\n{NON_CONVERGED_MARKER}: fix-loop cap hit without converging",
        )
    )


def test_a_stall_cancelled_dispatch_is_neither_bounced_nor_journaled_as_one(
    tmp_path: Path,
) -> None:
    """The item stays where the dispatch left it and the journal carries no bounce row.

    Both halves are asserted because they fail independently: a build that
    journals the row but skips the ledger write, and one that moves the item
    while journaling nothing, each satisfy exactly one of them.
    """
    repo = _repo(tmp_path=tmp_path)
    item = _item()
    append_work_item(path=_config(), item=item)
    journal = _journal(tmp_path=tmp_path)

    bounce_non_convergence_to_backlog(
        repo=repo,
        item=item,
        outcome=_outcome(status="stalled-no-progress"),
        journal=journal,
    )

    stages = [record.get("stage") for record in _journal_records(path=journal.path)]
    assert NON_CONVERGENCE_BOUNCE_STAGE not in stages
    assert _stored()[_ITEM_ID].status == "active"


def _calibration_row(*, outcome: DispatchOutcome) -> dict[str, object]:
    """The journal row the calibration analysis pass reads for one terminal.

    Built through the SAME pure derivation `emit_calibration` uses, with the
    stall window the dispatch would have resolved handed in — the cap
    classification is pure precisely so this reading needs no repository on
    disk, and handing in a real window is what stops a build that still named
    it from passing for one that declines to.
    """
    return calibration_journal_record(
        record=build_calibration_record(
            item=_item(),
            outcome=outcome,
            repo_name="livespec-orchestrator-beads-fabro",
            journal_records=(),
            wall_clock_seconds=12.0,
            token_cost_micros=None,
            dispatch_context_size=0,
            merged_pr_diff_size=None,
            bounce_cap=non_convergence_cap(outcome=outcome, stall_seconds=7200.0),
        )
    )


def test_the_calibration_pass_counts_the_fix_loop_cap_and_not_a_stall_cancel() -> None:
    """One non-convergence observation for the fix-loop cap, none for a stall.

    The two rows are asserted TOGETHER because each alone is vacuous: a pass
    that counted nothing would satisfy the stall half, and one that counted
    everything would satisfy the fix-loop half. Both the observation flag and
    the cap identity are read, because they are independent fields and a build
    that cleared the flag while still naming the stall window reports a
    dispatch that tripped a cap it was not bounced for.
    """
    stalled = _calibration_row(outcome=_outcome(status="stalled-no-progress"))
    assert stalled["bounced_to_regroom"] is False
    assert stalled[BOUNCE_CAP_KEY] is None
    assert stalled[BOUNCE_CAP_OBSERVED_KEY] is None

    exhausted = _calibration_row(
        outcome=_outcome(
            status="failed",
            detail=f"{NON_CONVERGED_MARKER}: janitor fix-loop cap hit without converging",
        )
    )
    assert exhausted["bounced_to_regroom"] is True
    assert exhausted[BOUNCE_CAP_KEY] == FIX_LOOP_VISIT_CAP


def test_a_stall_cancel_trips_no_cap_at_all() -> None:
    """The classification itself declines, so no caller can report a stall cap.

    Asserted on the classification as well as on the row above because the cap
    rides two surfaces — the bounce record and the calibration span — and a
    row-only assertion passes for a build that merely stopped projecting it.
    """
    cap = non_convergence_cap(outcome=_outcome(status="stalled-no-progress"), stall_seconds=7200.0)

    assert cap == UNTRIGGERED_NON_CONVERGENCE_CAP
