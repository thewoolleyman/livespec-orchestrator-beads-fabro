"""Pure builder for the Dispatcher's per-dispatch calibration telemetry.

Per livespec-orchestrator-beads-fabro SPECIFICATION/contracts.md §"Grooming and
slice-size calibration" → §"Dispatcher grooming behavior" and
§"Calibration telemetry and the single Fabro tweak", the Dispatcher MUST
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

A proxy whose underlying signal is not (yet) observable for this dispatch
is recorded as `None` (e.g. the merged-PR diff size when fabro / gh did
not report it, or the token cost when no CC telemetry arrived) — the
calibration analysis pass treats absence as missing data, never as zero,
mirroring the cost gate's fail-soft derivation.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import DispatchOutcome
from livespec_orchestrator_beads_fabro.types import WorkItem

__all__: list[str] = [
    "CalibrationRecord",
    "acceptance_count",
    "build_calibration_record",
    "calibration_journal_record",
    "fix_loop_count",
    "spec_surface_touched",
]

# A second `pr-view` for the same item, or any `pr-update-branch`, is the
# mechanical retry/fix-loop signal the journal exposes for one item (the
# same signal the mechanical reflection scan keys its `stage-retry`
# finding off). The first `pr-view` is the baseline confirmation; each
# additional poll re-view plus each `pr-update-branch` is one fix-loop.
_BASELINE_PR_VIEWS = 1

# Acceptance-criteria proxy: a leading-dash / leading-asterisk bullet or a
# "Scenario:" / "Given/When/Then" Gherkin marker in the description is one
# acceptance signal. The spec's Definition-of-Ready requires "exactly one
# coherent done" — this counts the ENUMERATED acceptance lines as a
# mechanical proxy for how the item's done-condition was specified.
_ACCEPTANCE_BULLET_RE = re.compile(r"(?m)^\s*[-*]\s+\S")
_ACCEPTANCE_GHERKIN_RE = re.compile(
    r"(?im)^\s*(?:scenario|given|when|then)\b",
)


@dataclass(frozen=True, kw_only=True)
class CalibrationRecord:
    """One dispatch's calibration telemetry (outcome signal + size proxies).

    Every field is a plain scalar (or `None` when its underlying signal is
    not observable for this dispatch) so the record serializes straight
    onto the existing JSONL journal and the mechanical reflection leg ships
    it to Honeycomb unchanged. The field set is the spec's two enumerated
    lists, one-to-one.
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
    merged_pr_diff_size: int | None
    dependency_fan_out: int
    spec_surface_touched: bool
    dispatch_context_size: int
    archetype: str
    repo: str


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
        acceptance_count=acceptance_count(item=item),
        merged_pr_diff_size=merged_pr_diff_size,
        dependency_fan_out=len(item.depends_on),
        spec_surface_touched=spec_surface_touched(item=item),
        dispatch_context_size=dispatch_context_size,
        archetype=item.type,
        repo=repo_name,
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
    """Whether this dispatch is a non-convergence bounce back to `needs-regroom`.

    Per §"Dispatcher grooming behavior", factory non-convergence routes
    the item to `needs-regroom`. The mechanical signal for that is a
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


def acceptance_count(*, item: WorkItem) -> int:
    """Mechanical acceptance-criteria proxy from the item's description.

    Counts enumerated acceptance signals — leading bullet lines plus
    Gherkin `Scenario:` / `Given` / `When` / `Then` markers — as a size
    proxy for how the done-condition was specified. A bare prose item with
    no enumerated acceptance reads as 0; the count is a proxy, not a
    semantic parse of the acceptance itself.
    """
    bullets = len(_ACCEPTANCE_BULLET_RE.findall(item.description))
    gherkin = len(_ACCEPTANCE_GHERKIN_RE.findall(item.description))
    return bullets + gherkin


def spec_surface_touched(*, item: WorkItem) -> bool:
    """Whether the item touches spec surface (the spec-surface size proxy).

    Mechanical: a gap-tied item (it answers a spec→impl gap) or one paired
    to a spec commitment (`spec_commitment_hint`) touches spec surface; a
    pure freeform impl task does not. Derived from the schema fields, never
    a content scan.
    """
    return item.gap_id is not None or item.spec_commitment_hint is not None


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
        "merged_pr_diff_size": record.merged_pr_diff_size,
        "dependency_fan_out": record.dependency_fan_out,
        "spec_surface_touched": record.spec_surface_touched,
        "dispatch_context_size": record.dispatch_context_size,
        "archetype": record.archetype,
        "repo": record.repo,
    }
