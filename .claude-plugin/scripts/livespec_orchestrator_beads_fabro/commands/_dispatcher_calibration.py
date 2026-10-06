"""Pure builder for the Dispatcher's per-dispatch calibration telemetry.

Per livespec-orchestrator-beads-fabro SPECIFICATION/contracts.md, the Dispatcher MUST
emit calibration telemetry — an outcome SIGNAL plus mechanical SIZE
PROXIES — recorded on the EXISTING Dispatcher journal (the journal →
Honeycomb leg already designed in the operability preconditions), with NO
new always-on service.

This module is the PURE derivation: it has no IO and never raises. The
Dispatcher (`dispatcher._dispatch_one`) gathers the already-observed
inputs — the work-item, the terminal `DispatchOutcome`, the per-dispatch
journal records, the derived token cost, the dispatch wall clock, the
dispatch-context size, and the merged-PR diff size — and calls
`build_calibration_record` to assemble one `CalibrationRecord`, which it
journals as a single `calibration` stage record on the existing journal.
The mechanical reflection leg (`_dispatcher_reflection.reflect`) reads
that journal back and the host-local enrich/egress stage ships it to
Honeycomb, so the calibration fields ride the SAME established path — no
new service is introduced.

The fields realize the spec's two enumerated lists exactly:

  * Outcome signal: `converged`, `fix_loop_count`, `outcome_class`,
    `wall_clock_seconds`, `token_cost_micros`, `bounced_to_regroom`.
  * Mechanical size proxies: `acceptance_count`, `merged_pr_diff_size`,
    `dependency_fan_out`, `spec_surface_touched`, `dispatch_context_size`,
    `archetype`, `repo`.

Plan slice S4 (`bd-ib-tbgxm4`) adds the provenance and shape fields each of
those two lists was missing to be USABLE rather than merely present:
`acceptance_count_source` says which text the count counted, and
`pr_open_diff_size` / `bounce_cap` / `bounce_cap_observed` are derived from
this item's own journal records for the same reason `fix_loop_count` is — the
stage that observed each one wrote it down, and re-observing it here could not
be shown to agree with what was recorded.

A proxy whose underlying signal is not (yet) observable for this dispatch
is recorded as `None` (e.g. the merged-PR diff size when fabro / gh did
not report it, or the token cost when no CC telemetry arrived) — the
calibration analysis pass treats absence as missing data, never as zero,
mirroring the cost gate's fail-soft derivation.
"""

from __future__ import annotations

from dataclasses import dataclass

from livespec_orchestrator_beads_fabro.commands._dispatcher_assertion_count import (
    assertion_count_for,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import DispatchOutcome
from livespec_orchestrator_beads_fabro.commands._dispatcher_pr_open_diff import (
    PR_OPEN_DIFF_SIZE_KEY,
    PR_OPEN_DIFF_STAGE,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_tdd_signals import (
    UNOBSERVED_TDD_SIGNALS,
    TddSignals,
    tdd_signal_fields,
)
from livespec_orchestrator_beads_fabro.commands._plan_anchor import is_spec_commitment
from livespec_orchestrator_beads_fabro.types import WorkItem

__all__: list[str] = [
    "CalibrationRecord",
    "acceptance_count",
    "build_calibration_record",
    "calibration_journal_record",
    "fix_loop_count",
    "pr_open_diff_size",
    "spec_surface_touched",
]

# A second `pr-view` for the same item, or any `pr-update-branch`, is the
# mechanical retry/fix-loop signal the journal exposes for one item (the
# same signal the mechanical reflection scan keys its `stage-retry`
# finding off). The first `pr-view` is the baseline confirmation; each
# additional poll re-view plus each `pr-update-branch` is one fix-loop.
_BASELINE_PR_VIEWS = 1


@dataclass(frozen=True, kw_only=True)
class CalibrationRecord:
    """One dispatch's calibration telemetry (outcome signal + size proxies).

    Every field is a plain scalar (or `None` when its underlying signal is
    not observable for this dispatch) so the record serializes straight
    onto the existing JSONL journal and the mechanical reflection leg ships
    it to Honeycomb unchanged. The scalar field set is the spec's two
    enumerated lists, one-to-one.

    `tdd` is the ONE structured field: plan slice S3's TDD order signals,
    held as a value rather than eight more scalars so the key names and
    their source semantics live in one place (`_dispatcher_tdd_signals`).
    It FLATTENS to its own dotted sibling keys in
    `calibration_journal_record`, so the journal stays a flat record and the
    enrich stage still promotes each key to a span attribute without
    unwrapping a nested map. It defaults to the fully-unobserved value, so a
    path that does not gather the signals journals explicit nulls rather
    than plausible zeros.
    """

    # The dispatched item, carried for per-item correlation on the journal
    # → Honeycomb leg (the reflection scan and the OTLP enrich stage key
    # records by `work.item.id`).
    work_item_id: str
    # --- outcome signal ---
    converged: bool
    fix_loop_count: int
    outcome_class: str
    wall_clock_seconds: float | None
    token_cost_micros: int | None
    bounced_to_regroom: bool
    # --- mechanical size proxies ---
    acceptance_count: int
    # WHICH text the count counted. A legacy `criteria-field` /
    # `description-exit-criteria` item declares no proof mode and carries no
    # Definition of Done section, so a reading that could not separate those
    # records would average two populations; and the value is the one
    # `parse_display()` names, so the record and the filing display cannot
    # disagree about provenance.
    acceptance_count_source: str
    merged_pr_diff_size: int | None
    # The branch-versus-base churn as the pull request OPENED, which a run keeps
    # whatever terminal follows. `merged_pr_diff_size` above is read only for a
    # green outcome, so it was absent on every non-converged run — present on
    # 292 of 292 converged and 0 of 153 non-converged across this repository's
    # own records, which is a proxy the outcome decides rather than predicts.
    pr_open_diff_size: int | None
    dependency_fan_out: int
    spec_surface_touched: bool
    dispatch_context_size: int
    archetype: str
    repo: str
    fabro_failure_cause: str | None = None
    fabro_failure_category: str | None = None
    fabro_failure_signature: str | None = None
    # --- TDD order signals (plan slice S3) ---
    tdd: TddSignals = UNOBSERVED_TDD_SIGNALS


def build_calibration_record(  # noqa: PLR0913 — kw-only pure builder; each field is an independent observed input.
    *,
    item: WorkItem,
    outcome: DispatchOutcome,
    repo_name: str,
    journal_records: tuple[dict[str, object], ...],
    wall_clock_seconds: float | None,
    token_cost_micros: int | None,
    dispatch_context_size: int,
    merged_pr_diff_size: int | None,
    tdd: TddSignals = UNOBSERVED_TDD_SIGNALS,
) -> CalibrationRecord:
    """Assemble the calibration record from already-observed dispatch inputs.

    Pure function of its inputs (no IO, never raises). `outcome` carries
    the terminal verdict; `journal_records` are the per-dispatch records
    the engine already appended (the fix-loop count is derived from their
    poll/retry pattern for THIS item); `token_cost_micros` is the derived
    CC-token cost (or `None` when unobservable); `dispatch_context_size`
    is the goal/comment context the Dispatcher fed the run; and
    `merged_pr_diff_size` is the merged-PR diff size (or `None` when the
    run did not merge or the size was not observed).
    """
    converged = outcome.status == "green"
    # Resolved ONCE and read for both fields: a second resolution could not be
    # shown to agree with the first, and a count paired with another read's
    # source is the exact mismatch this projection exists to retire.
    assertions = assertion_count_for(item=item)
    return CalibrationRecord(
        work_item_id=item.id,
        converged=converged,
        fix_loop_count=fix_loop_count(
            records=journal_records,
            work_item_id=item.id,
        ),
        outcome_class=outcome_class(outcome=outcome),
        wall_clock_seconds=wall_clock_seconds,
        token_cost_micros=token_cost_micros,
        bounced_to_regroom=bounced_to_regroom(outcome=outcome),
        acceptance_count=assertions.count,
        acceptance_count_source=assertions.source,
        merged_pr_diff_size=merged_pr_diff_size,
        pr_open_diff_size=pr_open_diff_size(
            records=journal_records,
            work_item_id=item.id,
        ),
        dependency_fan_out=len(item.depends_on),
        spec_surface_touched=spec_surface_touched(item=item),
        dispatch_context_size=dispatch_context_size,
        archetype=item.type,
        repo=repo_name,
        fabro_failure_cause=outcome.fabro_failure_cause,
        fabro_failure_category=outcome.fabro_failure_category,
        fabro_failure_signature=outcome.fabro_failure_signature,
        tdd=tdd,
    )


def outcome_class(*, outcome: DispatchOutcome) -> str:
    """The terminal outcome class — the verdict status refined by stage.

    `green` collapses to the status; every non-green status is reported as
    `<status>:<stage>` so a `failed` at `janitor-post-merge` reads distinctly
    from a `failed` at `host-only-refused`, giving the calibration analysis
    a stable, mechanical class key without a bespoke enum.
    """
    if outcome.status == "green":
        return "green"
    return f"{outcome.status}:{outcome.stage}"


def bounced_to_regroom(*, outcome: DispatchOutcome) -> bool:
    """Whether this dispatch is a non-convergence bounce back to `backlog`.

    Per SPECIFICATION/contracts.md, factory non-convergence routes
    the item to `backlog`. The mechanical signal for that is a
    `stalled-no-progress` terminal — the watchdog-confirmed non-convergence
    the Dispatcher escalates rather than infinite-retries.
    """
    return outcome.status == "stalled-no-progress"


def fix_loop_count(*, records: tuple[dict[str, object], ...], work_item_id: str) -> int:
    """Derive the dispatch's fix-loop count from this item's journal records.

    The journal exposes the verify→fix / merge-poll retry pattern for one
    item: each `pr-update-branch` and each `pr-view` beyond the first
    baseline confirmation is one loop. A clean single-pass dispatch yields
    0. Mechanical and message-free (the same poll/retry signal the
    mechanical reflection scan reads), so it never churns on text.
    """
    pr_views = 0
    update_branches = 0
    for record in records:
        if record.get("work_item_id") != work_item_id:
            continue
        stage = record.get("stage")
        if stage == "pr-view":
            pr_views += 1
        elif stage == "pr-update-branch":
            update_branches += 1
    extra_views = max(0, pr_views - _BASELINE_PR_VIEWS)
    return extra_views + update_branches


def pr_open_diff_size(*, records: tuple[dict[str, object], ...], work_item_id: str) -> int | None:
    """The branch-versus-base churn this dispatch recorded when its PR opened.

    Read back off the journal rather than probed again, for the reason
    `fix_loop_count` is: the stage that OBSERVED the value wrote it down, and a
    second observation here could not be shown to agree with what was recorded —
    the pull request may have gained commits since, or been merged, or closed.

    The MOST RECENT matching record wins. The journal accumulates across every
    dispatch in the repository, so a re-dispatched item carries one record per
    attempt and the newest is this dispatch's; taking the first would report a
    previous attempt's size as this one's.

    `None` when no record was written (the run opened no pull request) or when
    the recorded value is unusable — absent, never a false zero.
    """
    return _journaled_int(
        records=records,
        work_item_id=work_item_id,
        stage=PR_OPEN_DIFF_STAGE,
        key=PR_OPEN_DIFF_SIZE_KEY,
    )


def _journaled_int(
    *, records: tuple[dict[str, object], ...], work_item_id: str, stage: str, key: str
) -> int | None:
    """One integer field off this item's most recent record of a stage.

    `bool` is rejected explicitly because it is an `int` subclass: a stray
    boolean on the journal would otherwise read as the size 1 or 0.
    """
    value = _journaled_field(records=records, work_item_id=work_item_id, stage=stage, key=key)
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value


def _journaled_field(
    *, records: tuple[dict[str, object], ...], work_item_id: str, stage: str, key: str
) -> object | None:
    """The raw value of one key on this item's most recent record of a stage."""
    for record in reversed(records):
        if record.get("work_item_id") == work_item_id and record.get("stage") == stage:
            return record.get(key)
    return None


def acceptance_count(*, item: WorkItem) -> int:
    """The item's gradeable assertion count, through the sanctioned parser.

    Plan slice S4's repair. This counted leading-bullet and Gherkin markers in
    the item's DESCRIPTION, which is neither the text the acceptance evaluator
    grades nor the number the filing display shows an operator — so it
    over-counted a description whose bullets sit outside its Definition of Done
    section, and under-counted to ZERO an item whose criteria live in the
    criteria field. Measured across 445 of this repository's own calibration
    records, its median was zero on both the converged and the non-converged
    side, so the proxy carried no signal for the analysis pass to correlate.

    It now reads `_dispatcher_assertion_count`, the ONE projection intake also
    reads, so the two ends of a dispatch report the same number and the same
    source by construction. A bare prose item with no section and no criteria
    field still reads 0 — that is an item with nothing gradeable, which is a
    finding rather than a measurement artifact.
    """
    return assertion_count_for(item=item).count


def spec_surface_touched(*, item: WorkItem) -> bool:
    """Whether the item touches spec surface (the spec-surface size proxy).

    Mechanical: a gap-tied item (it answers a spec→impl gap) or one paired
    to a spec commitment (`spec_commitment_hint`) touches spec surface; a
    pure freeform impl task does not. Derived from the schema fields, never
    a content scan.

    A PLAN ANCHOR MARKER IS NOT A SPEC COMMITMENT even though it rides the
    same field, so the pairing half asks `is_spec_commitment` rather than
    testing the hint for presence — a plan epic touches no spec surface.
    """
    return item.gap_id is not None or is_spec_commitment(spec_id=item.spec_commitment_hint)


def calibration_journal_record(*, record: CalibrationRecord) -> dict[str, object]:
    """Build the `calibration` journal record from a `CalibrationRecord`.

    The single dict the Dispatcher appends to the existing journal so the
    mechanical reflection leg reads it back and ships it to Honeycomb. The
    `stage` key names it `calibration` (the journal's stage vocabulary);
    every calibration field rides as a sibling key so the OTLP enrich stage
    can promote each to a span attribute without unwrapping a nested map.
    """
    return {
        "stage": "calibration",
        "work_item_id": record.work_item_id,
        "converged": record.converged,
        "fix_loop_count": record.fix_loop_count,
        "outcome_class": record.outcome_class,
        "wall_clock_seconds": record.wall_clock_seconds,
        "token_cost_micros": record.token_cost_micros,
        "bounced_to_regroom": record.bounced_to_regroom,
        "acceptance_count": record.acceptance_count,
        "acceptance_count_source": record.acceptance_count_source,
        "merged_pr_diff_size": record.merged_pr_diff_size,
        PR_OPEN_DIFF_SIZE_KEY: record.pr_open_diff_size,
        "dependency_fan_out": record.dependency_fan_out,
        "spec_surface_touched": record.spec_surface_touched,
        "dispatch_context_size": record.dispatch_context_size,
        "archetype": record.archetype,
        "repo": record.repo,
        "fabro.failure.cause": record.fabro_failure_cause,
        "fabro.failure.category": record.fabro_failure_category,
        "fabro.failure.signature": record.fabro_failure_signature,
        **tdd_signal_fields(signals=record.tdd),
    }
