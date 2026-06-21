"""Integration-tier acceptance for the periodic calibration analysis pass.

Binds SPECIFICATION/scenarios.md "Scenario 13 — Calibration analysis pass
proposes advisory thresholds" and the contracts.md §"Gap-detectable behavior
clauses" clause (work-item livespec-impl-beads-fh7cff, gap-hvqcpz2d):

    A periodic calibration analysis pass MUST correlate run outcomes against
    the recorded mechanical size proxies and MUST propose ceiling thresholds
    that remain advisory until a maintainer adopts them (it MUST NOT
    auto-enforce a threshold and MUST NOT run as an always-on service).

This is the top-of-pyramid behavior journey for the shared
`livespec_orchestrator_beads_fabro.calibration_analysis` primitive. It drives the pass over
a REAL on-disk Dispatcher journal seeded with the SAME flat `calibration`-stage
records behavior 6 (`commands/_dispatcher_calibration.calibration_journal_record`)
writes — the seam the pass reads in production — and asserts the two
load-bearing Scenario-13 `Then` clauses:

  * it correlates outcomes against size proxies and proposes a ceiling
    threshold (the `When` → first `Then`); and
  * the proposed thresholds stay advisory and are never auto-enforced (the
    second + third `Then`) — the returned proposal flags advisory/not-adopted,
    mutates no gate config, and the pass writes nothing back to the journal.

The `Scenario:` blocks below are the three `Then` assertions; the remaining
cases pin the empty-journal decline and the no-false-zero proxy handling.
"""

from __future__ import annotations

from pathlib import Path

from livespec_orchestrator_beads_fabro.calibration_analysis import (
    CalibrationProposal,
    analyze_calibration,
    load_calibration_records,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_calibration import (
    CalibrationRecord,
    calibration_journal_record,
)


def _record(
    *,
    work_item_id: str,
    converged: bool,
    dispatch_context_size: int,
    acceptance_count: int = 1,
    merged_pr_diff_size: int | None = 50,
    dependency_fan_out: int = 0,
    bounced_to_regroom: bool = False,
) -> CalibrationRecord:
    """One terminal-dispatch calibration record (behavior 6's emitted shape).

    `dispatch_context_size` is the proxy each case varies to drive the
    correlation; the other proxies default to fixed values so a single proxy's
    ceiling is the unambiguous signal under test.
    """
    return CalibrationRecord(
        work_item_id=work_item_id,
        converged=converged,
        fix_loop_count=0 if converged else 3,
        outcome_class="green" if converged else "stalled-no-progress:fabro-run",
        wall_clock_seconds=10.0,
        token_cost_micros=1000,
        bounced_to_regroom=bounced_to_regroom,
        acceptance_count=acceptance_count,
        merged_pr_diff_size=merged_pr_diff_size,
        dependency_fan_out=dependency_fan_out,
        spec_surface_touched=False,
        dispatch_context_size=dispatch_context_size,
        archetype="task",
        repo="livespec-impl-beads",
    )


def _seed_journal(*, journal_path: Path, records: list[CalibrationRecord]) -> None:
    """Write the calibration records onto a real journal exactly as the Dispatcher does.

    Each record is serialized through behavior 6's
    `calibration_journal_record` (the production flat-record builder) so the
    analysis pass reads the same on-disk JSONL the live journal → Honeycomb
    leg carries. Interleaves a non-`calibration` stage line and a
    `calibration-error` breadcrumb so the pass's record filtering is exercised
    on the real seam.
    """
    import json

    lines: list[str] = ['{"stage": "pr-view", "work_item_id": "noise"}']
    for record in records:
        lines.append(json.dumps(calibration_journal_record(record=record)))
    lines.append('{"stage": "calibration-error", "work_item_id": "x", "reason": "RuntimeError"}')
    _ = journal_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _converging_below_oversized_above() -> list[CalibrationRecord]:
    """A journal where large `dispatch_context_size` predicts non-convergence.

    Small-context dispatches converge; large-context ones do not — the exact
    correlation the analysis pass exists to surface as an advisory ceiling.
    """
    return [
        _record(work_item_id="li-s1", converged=True, dispatch_context_size=100),
        _record(work_item_id="li-s2", converged=True, dispatch_context_size=150),
        _record(work_item_id="li-s3", converged=True, dispatch_context_size=200),
        _record(
            work_item_id="li-b1",
            converged=False,
            dispatch_context_size=900,
            bounced_to_regroom=True,
            merged_pr_diff_size=None,
        ),
        _record(
            work_item_id="li-b2",
            converged=False,
            dispatch_context_size=1000,
            bounced_to_regroom=True,
            merged_pr_diff_size=None,
        ),
    ]


# --------------------------------------------------------------------------
# Scenario: the pass correlates outcomes against size proxies and proposes a
# ceiling threshold.
# --------------------------------------------------------------------------


def test_pass_proposes_a_ceiling_from_the_journalled_correlation(tmp_path: Path) -> None:
    journal_path = tmp_path / "fabro-dispatch-journal.jsonl"
    _seed_journal(journal_path=journal_path, records=_converging_below_oversized_above())

    records = load_calibration_records(journal_path=journal_path)
    proposal = analyze_calibration(records=records)

    # The five calibration records were read back (the pr-view + calibration-error
    # lines are filtered out at the seam).
    assert proposal.total_runs == 5
    assert proposal.non_converged_runs == 2

    context_threshold = next(t for t in proposal.thresholds if t.proxy == "dispatch_context_size")
    # A concrete advisory ceiling was proposed in the oversized region: the
    # converged runs sit at 100-200, the non-converged at 900-1000, so the
    # proposed cutoff lands above the converged band.
    assert context_threshold.ceiling is not None
    assert context_threshold.ceiling > 200
    # The ceiling is justified by a real lift: non-convergence above it
    # exceeds non-convergence below it.
    assert (
        context_threshold.non_convergence_rate_at_or_above
        > context_threshold.non_convergence_rate_below
    )


# --------------------------------------------------------------------------
# Scenario: the proposed thresholds stay advisory until adopted, and are
# never auto-enforced.
# --------------------------------------------------------------------------


def test_proposal_is_advisory_and_never_auto_enforced(tmp_path: Path) -> None:
    journal_path = tmp_path / "fabro-dispatch-journal.jsonl"
    seeded = _converging_below_oversized_above()
    _seed_journal(journal_path=journal_path, records=seeded)
    journal_bytes_before = journal_path.read_bytes()

    records = load_calibration_records(journal_path=journal_path)
    proposal = analyze_calibration(records=records)

    # The proposal is advisory and NOT adopted by construction — adoption is a
    # separate maintainer act this pass never performs.
    assert isinstance(proposal, CalibrationProposal)
    assert proposal.advisory is True
    assert proposal.adopted is False
    # Auto-enforcement would mean mutating the source journal (the only state
    # the pass touches) — it is byte-for-byte unchanged, proving a pure,
    # write-nothing read.
    assert journal_path.read_bytes() == journal_bytes_before


def test_pass_runs_synchronously_and_returns_without_a_service(tmp_path: Path) -> None:
    """The pass is an on-demand call that returns — not an always-on service.

    A direct synchronous call over the seeded snapshot completes and yields a
    proposal; there is no loop, scheduler, or background thread to start or
    stop. This is the "MUST NOT run as an always-on service" guarantee made
    observable: the function is total over its input and simply returns.
    """
    journal_path = tmp_path / "fabro-dispatch-journal.jsonl"
    _seed_journal(journal_path=journal_path, records=_converging_below_oversized_above())

    proposal = analyze_calibration(records=load_calibration_records(journal_path=journal_path))

    assert isinstance(proposal, CalibrationProposal)


# --------------------------------------------------------------------------
# Decline-on-no-signal: an empty / absent journal proposes no ceilings rather
# than fabricating one.
# --------------------------------------------------------------------------


def test_absent_journal_yields_an_advisory_proposal_with_no_ceilings(tmp_path: Path) -> None:
    proposal = analyze_calibration(
        records=load_calibration_records(journal_path=tmp_path / "absent.jsonl")
    )
    assert proposal.advisory is True
    assert proposal.total_runs == 0
    assert all(threshold.ceiling is None for threshold in proposal.thresholds)


def test_all_converged_journal_proposes_no_ceiling(tmp_path: Path) -> None:
    """When nothing ever failed there is no non-convergence to bound."""
    journal_path = tmp_path / "fabro-dispatch-journal.jsonl"
    _seed_journal(
        journal_path=journal_path,
        records=[
            _record(work_item_id=f"li-c{i}", converged=True, dispatch_context_size=100 * i)
            for i in range(1, 6)
        ],
    )
    proposal = analyze_calibration(records=load_calibration_records(journal_path=journal_path))
    assert proposal.non_converged_runs == 0
    assert all(threshold.ceiling is None for threshold in proposal.thresholds)


# --------------------------------------------------------------------------
# No false zero: a proxy recorded as None (unobservable) is missing data, not
# a zero that would drag a ceiling down.
# --------------------------------------------------------------------------


def test_unobservable_diff_size_is_missing_data_not_zero(tmp_path: Path) -> None:
    journal_path = tmp_path / "fabro-dispatch-journal.jsonl"
    # Every non-converged run recorded merged_pr_diff_size=None (it never
    # merged). If absence were treated as 0, the diff-size ceiling would be
    # dragged toward 0; instead the proxy simply has fewer samples and the
    # pass declines a diff-size ceiling for want of separating signal.
    _seed_journal(journal_path=journal_path, records=_converging_below_oversized_above())
    proposal = analyze_calibration(records=load_calibration_records(journal_path=journal_path))
    diff_threshold = next(t for t in proposal.thresholds if t.proxy == "merged_pr_diff_size")
    # The converged runs all share diff size 50 and the non-converged carry
    # None, so there is no high-side non-converged sample — no false-zero
    # ceiling is proposed.
    assert diff_threshold.ceiling is None


# --------------------------------------------------------------------------
# Seam robustness: a malformed (non-JSON) line and a valid-JSON-but-non-dict
# line in the journal are skipped, never crashing the read.
# --------------------------------------------------------------------------


def test_load_skips_malformed_and_non_dict_journal_lines(tmp_path: Path) -> None:
    journal_path = tmp_path / "fabro-dispatch-journal.jsonl"
    valid = calibration_journal_record(
        record=_record(work_item_id="li-ok", converged=True, dispatch_context_size=100)
    )
    import json

    lines = [
        "not-json-at-all",  # JSONDecodeError → skipped
        "[1, 2, 3]",  # valid JSON but not a dict → skipped
        json.dumps(valid),
    ]
    _ = journal_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    records = load_calibration_records(journal_path=journal_path)
    # Only the one well-formed calibration record survives.
    assert len(records) == 1
    assert records[0]["work_item_id"] == "li-ok"


# --------------------------------------------------------------------------
# Cutoff selection: when more than one candidate cutoff clears the guards, the
# pass keeps the cutoff with the strongest separation, not merely the last.
# --------------------------------------------------------------------------


def test_pass_keeps_the_strongest_separating_cutoff(tmp_path: Path) -> None:
    journal_path = tmp_path / "fabro-dispatch-journal.jsonl"
    # Converged runs at small context (100, 110), non-converged at large
    # context (800, 810, 820). Several cutoffs above 110 perfectly separate
    # the two bands, so the loop evaluates a confident threshold at more than
    # one candidate and must keep the strongest rather than overwrite with a
    # later, no-stronger one.
    records = [
        _record(work_item_id="li-c1", converged=True, dispatch_context_size=100),
        _record(work_item_id="li-c2", converged=True, dispatch_context_size=110),
        _record(
            work_item_id="li-b1",
            converged=False,
            dispatch_context_size=800,
            bounced_to_regroom=True,
            merged_pr_diff_size=None,
        ),
        _record(
            work_item_id="li-b2",
            converged=False,
            dispatch_context_size=810,
            bounced_to_regroom=True,
            merged_pr_diff_size=None,
        ),
        _record(
            work_item_id="li-b3",
            converged=False,
            dispatch_context_size=820,
            bounced_to_regroom=True,
            merged_pr_diff_size=None,
        ),
    ]
    _seed_journal(journal_path=journal_path, records=records)
    proposal = analyze_calibration(records=load_calibration_records(journal_path=journal_path))
    context_threshold = next(t for t in proposal.thresholds if t.proxy == "dispatch_context_size")
    # The strongest cutoff perfectly separates the bands: every at-or-above run
    # is non-converged, every below run converged.
    assert context_threshold.ceiling is not None
    assert context_threshold.non_convergence_rate_at_or_above == 1.0
    assert context_threshold.non_convergence_rate_below == 0.0
