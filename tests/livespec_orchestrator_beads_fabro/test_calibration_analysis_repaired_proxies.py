"""The calibration analysis pass over plan slice S4's repaired proxies.

Plan slice S4 (`bd-ib-tbgxm4`). The pass itself was never wrong; it had nothing
to correlate on. Measured across 445 of this repository's own records (plan
research,
`plan/factory-test-first-enforcement/research/opening-research-2026-09-30.md`):
`acceptance_count` had a median of ZERO on both the converged and the
non-converged side, `merged_pr_diff_size` was present on all 292 converged runs
and none of the 153 non-converged ones, and `bounced_to_regroom` was true on
NONE of them. Three of the four inputs the predictive gate depends on carried no
signal, and the one ceiling the pass did propose was noise.

This file covers the consumption side of the repair: the pass reads the repaired
assertion count, the PR-open diff size and the bounce signal, and it does so
WITHOUT acquiring either power the ratified design withholds from it. It writes
no lifecycle state — asserted structurally, because an absent store import is
the only thing that makes "it writes nothing" checkable rather than merely
observed on the cases a test happened to run — and it adopts nothing, so every
ceiling it proposes stays advisory exactly as `Scenario 13` requires.
"""

from __future__ import annotations

import ast
from pathlib import Path

from livespec_orchestrator_beads_fabro.calibration_analysis import (
    CalibrationProposal,
    analyze_calibration,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_calibration import (
    build_calibration_record,
    calibration_journal_record,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import DispatchOutcome
from livespec_orchestrator_beads_fabro.commands._dispatcher_non_convergence_cap import (
    non_convergence_cap,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_plan import NON_CONVERGED_MARKER
from livespec_orchestrator_beads_fabro.types import WorkItem

_ANALYSIS_PATH = (
    Path(__file__).resolve().parents[2]
    / ".claude-plugin"
    / "scripts"
    / "livespec_orchestrator_beads_fabro"
    / "calibration_analysis.py"
)
# Four gradeable assertions, so the repaired count is an unambiguous 4 while the
# retired description regex would have read this item as 0.
_CRITERIA = "- First thing.\n- Second thing.\n- Third thing.\n- Fourth thing.\n"


def _item(**overrides: object) -> WorkItem:
    base: dict[str, object] = {
        "id": "bd-ib-tbgxm4",
        "type": "feature",
        "status": "active",
        "title": "Repair factory sizing telemetry",
        "description": "Plain prose with no Definition of Done section.",
        "origin": "freeform",
        "gap_id": None,
        "rank": "a3",
        "assignee": "fabro",
        "depends_on": (),
        "captured_at": "2026-10-06T00:00:00Z",
        "resolution": None,
        "reason": None,
        "audit": None,
        "superseded_by": None,
        "acceptance_criteria": _CRITERIA,
    }
    base.update(overrides)
    return WorkItem(**base)  # pyright: ignore[reportArgumentType]


def _outcome(*, status: str, stage: str, detail: str = "") -> DispatchOutcome:
    return DispatchOutcome(
        work_item_id="bd-ib-tbgxm4",
        status=status,
        stage=stage,
        pr_number=7,
        merge_sha=None,
        detail=detail,
    )


def _journalled(*, outcome: DispatchOutcome, pr_open_diff_size: int | None) -> dict[str, object]:
    """One calibration record as the Dispatcher actually journals it.

    Built through the production builder and serializer rather than hand-written,
    so the keys the pass consumes are the keys the Dispatcher emits. A literal
    dict here would let the two drift and the test would still pass.
    """
    records: tuple[dict[str, object], ...] = ()
    if pr_open_diff_size is not None:
        records = (
            {
                "work_item_id": "bd-ib-tbgxm4",
                "stage": "pr-open-diff-size",
                "pr_open_diff_size": pr_open_diff_size,
            },
        )
    return calibration_journal_record(
        record=build_calibration_record(
            item=_item(),
            outcome=outcome,
            repo_name="repo",
            journal_records=records,
            wall_clock_seconds=10.0,
            token_cost_micros=None,
            dispatch_context_size=900,
            merged_pr_diff_size=None,
            bounce_cap=non_convergence_cap(outcome=outcome, stall_seconds=1800.0),
        )
    )


def _green(*, pr_open_diff_size: int) -> dict[str, object]:
    return _journalled(
        outcome=_outcome(status="green", stage="done"),
        pr_open_diff_size=pr_open_diff_size,
    )


def _bounced(*, pr_open_diff_size: int) -> dict[str, object]:
    return _journalled(
        outcome=_outcome(
            status="failed",
            stage="fabro-run",
            detail=f"{NON_CONVERGED_MARKER}: janitor fix-loop cap hit",
        ),
        pr_open_diff_size=pr_open_diff_size,
    )


def _threshold(*, proposal: CalibrationProposal, proxy: str) -> object:
    matching = [entry for entry in proposal.thresholds if entry.proxy == proxy]
    assert len(matching) == 1, f"expected one {proxy!r} threshold, got {len(matching)}"
    return matching[0]


def _imported_modules(*, source: str) -> set[str]:
    """Every module name one source file imports, in either statement form.

    BOTH forms, deliberately. `from x import y` is the only form this package
    uses today, so a scan that read only that form would be a scan a plain
    `import livespec_orchestrator_beads_fabro.store` walks straight past — and it
    would report the same clean answer it reports now.
    """
    imported: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        if isinstance(node, ast.ImportFrom) and node.module is not None:
            imported.add(node.module)
    return imported


def _lifecycle_writing_modules(*, imported: set[str]) -> set[str]:
    """The imported names that could write lifecycle state."""
    return {
        name
        for name in imported
        if name.endswith((".store", "._beads_client", ".commands")) or ".commands." in name
    }


# --- the three repaired inputs reach the correlation -----------------------


def test_the_pass_correlates_the_pr_open_diff_size() -> None:
    """The proxy a failed run now carries is one the pass can propose over."""
    records = (
        _green(pr_open_diff_size=10),
        _green(pr_open_diff_size=20),
        _bounced(pr_open_diff_size=900),
        _bounced(pr_open_diff_size=1000),
    )

    proposal = analyze_calibration(records=records)
    threshold = _threshold(proposal=proposal, proxy="pr_open_diff_size")

    assert threshold.ceiling == 900
    assert threshold.runs_at_or_above == 2
    assert threshold.runs_below == 2
    assert threshold.non_convergence_rate_at_or_above == 1.0
    assert threshold.non_convergence_rate_below == 0.0


def test_the_pass_consumes_the_repaired_assertion_count_the_dispatcher_emits() -> None:
    """Four criteria-field assertions, which the retired regex read as zero."""
    records = (_green(pr_open_diff_size=10),)

    assert records[0]["acceptance_count"] == 4
    assert records[0]["acceptance_count_source"] == "criteria-field"
    # And the pass still offers a threshold slot for it, so the repaired number
    # is correlated rather than merely recorded.
    proposal = analyze_calibration(records=records)
    assert _threshold(proposal=proposal, proxy="acceptance_count") is not None


def test_the_pass_reads_a_cap_triggered_bounce_as_non_convergence() -> None:
    """The bounce signal the repair made true is the correlation target."""
    bounced = _bounced(pr_open_diff_size=900)
    assert bounced["bounced_to_regroom"] is True

    proposal = analyze_calibration(records=(_green(pr_open_diff_size=10), bounced))

    assert proposal.total_runs == 2
    assert proposal.non_converged_runs == 1


def test_a_green_run_that_was_nonetheless_bounced_counts_as_non_convergence() -> None:
    """The flag is consumed in its own right, not as a restatement of `converged`."""
    green_but_bounced = {**_green(pr_open_diff_size=10), "bounced_to_regroom": True}

    proposal = analyze_calibration(records=(green_but_bounced,))

    assert proposal.non_converged_runs == 1


def test_an_absent_pr_open_diff_size_is_missing_data_rather_than_zero() -> None:
    """A run that opened no pull request must not pull a ceiling down to zero.

    FOUR runs carry a size and a fifth does not. The partition therefore sums to
    four: were absence read as a zero sample it would sum to five, and the extra
    zero would sit below every cutoff. That is the control — the ceiling alone
    would be the same either way.
    """
    records = (
        _journalled(outcome=_outcome(status="green", stage="done"), pr_open_diff_size=None),
        _green(pr_open_diff_size=10),
        _green(pr_open_diff_size=20),
        _bounced(pr_open_diff_size=900),
        _bounced(pr_open_diff_size=1000),
    )

    assert records[0]["pr_open_diff_size"] is None
    threshold = _threshold(proposal=analyze_calibration(records=records), proxy="pr_open_diff_size")

    assert threshold.runs_at_or_above + threshold.runs_below == 4
    assert threshold.ceiling == 900


# --- neither power the ratified design withholds ---------------------------


def test_every_proposal_stays_advisory_and_unadopted() -> None:
    """Scenario 13: proposed ceilings are advisory until a maintainer adopts one."""
    proposal = analyze_calibration(
        records=(
            _green(pr_open_diff_size=10),
            _green(pr_open_diff_size=20),
            _bounced(pr_open_diff_size=900),
            _bounced(pr_open_diff_size=1000),
        )
    )

    assert proposal.advisory is True
    assert proposal.adopted is False
    # A ceiling WAS proposed, so this is not passing by proposing nothing.
    assert any(entry.ceiling is not None for entry in proposal.thresholds)


def test_the_scan_for_a_lifecycle_write_can_actually_return_a_hit() -> None:
    """The positive control for the structural check below.

    A clean answer from a scan that COULD NOT have found anything is worth
    nothing, and this package imports exclusively in the `from x import y` form —
    so the plain-`import` arm is the one that would silently never fire. This
    exercises both arms against a control source that should convict.
    """
    control = "import livespec_orchestrator_beads_fabro.store\nfrom a.commands.b import c\n"

    imported = _imported_modules(source=control)

    assert _lifecycle_writing_modules(imported=imported) == {
        "livespec_orchestrator_beads_fabro.store",
        "a.commands.b",
    }


def test_the_pass_imports_no_ledger_or_store_surface() -> None:
    """It cannot change lifecycle state: it holds no module that could.

    Structural rather than behavioural on purpose. "It wrote nothing" observed
    over the cases a test happened to run is consistent with a write on the case
    it did not; an absent import is not.
    """
    imported = _imported_modules(source=_ANALYSIS_PATH.read_text(encoding="utf-8"))

    assert _lifecycle_writing_modules(imported=imported) == set()
    # And the scan saw a non-empty import set, so it was pointed at real source.
    assert imported != set()
