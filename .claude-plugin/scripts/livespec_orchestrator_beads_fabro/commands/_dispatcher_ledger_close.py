"""Ledger close status normalization and outcome emission for the Dispatcher.

The status-normalization note routes through `JournalFile.append` — the single
append layer of the journal invoker attribution contract in
`SPECIFICATION/contracts.md`. It used to open the journal path directly, so the
one record saying which rows the Dispatcher silently re-statused carried no
timestamp and no attribution.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, replace
from pathlib import Path

from livespec_runtime.work_items._fractional_indexing import FIError, validate_order_key
from livespec_runtime.work_items.rank import BOTTOM_SENTINEL, key_between

from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import DispatchOutcome
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import JournalFile
from livespec_orchestrator_beads_fabro.commands._dispatcher_ledger_checks import (
    LedgerFinding,
    run_ledger_checks,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_paths import store_config
from livespec_orchestrator_beads_fabro.io import write_stderr, write_stdout
from livespec_orchestrator_beads_fabro.store import (
    materialize_work_items,
    read_work_items,
    update_work_item_status,
)
from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem

__all__: list[str] = [
    "apply_native_status_remaps",
    "emit_outcomes",
    "ledger_blocked_after_normalization",
    "load_items",
    "plan_native_status_remaps",
    "project_native_status_remaps",
]


@dataclass(frozen=True, kw_only=True)
class _NativeRemap:
    """The livespec lifecycle target + rationale for one beads-native status."""

    to: str
    reason: str


# The beads-native statuses the Dispatcher self-heals onto their livespec
# lifecycle equivalent: `open` (beads' intake default a fresh `bd create`
# lands in) → `backlog`, and `in_progress` (the status a raw `bd --claim`
# stamps) → `active`. Both carry a lifecycle intent the livespec model names
# differently. `deferred` is deliberately left untouched because it is modeled
# as a parked beads-native state. Every OTHER status (hooked / pinned / closed /
# any ad-hoc or unknown value) is a KEY-miss here and is left untouched — those
# surface via the post-normalization ledger status-conformance check, never
# auto-remapped.
_NATIVE_STATUS_REMAP: dict[str, _NativeRemap] = {
    "open": _NativeRemap(to="backlog", reason="beads-native intake default"),
    "in_progress": _NativeRemap(to="active", reason="raw claim normalized to active"),
}

# The one livespec status whose rows are NOT part of the live order: a `done`
# row's key cannot be the bottom a fresh insert lands after, and the
# non-sentinel-rank invariant the adoption satisfies exempts it too.
_LIVESPEC_DONE = "done"


def plan_native_status_remaps(*, items: list[WorkItem]) -> list[dict[str, str]]:
    """Plan the beads-native → livespec status + rank adoptions for `items` (PURE).

    Returns one `{item_id, from, to, reason}` dict per row whose stored
    status is a KEY of `_NATIVE_STATUS_REMAP`; every other row (already-
    conformant, parked, hooked, ad-hoc, unknown) contributes nothing.
    A planned row whose `rank` reads back through `BOTTOM_SENTINEL` — the
    adapter's stand-in for metadata carrying no real key — additionally
    carries a `rank`: a fresh key from a single bottom-of-order insert, so the
    adopted row satisfies the "every live head has a real, non-sentinel rank"
    invariant without an on-demand `rebalance-ranks`. Successive rank-less
    rows chain off each other's fresh key, so each lands at its own position
    and NO already-ranked row is re-keyed — this is a run of single inserts,
    never a rebalance. A live row whose stored rank is MALFORMED cannot be that
    bottom (see `_bottom_live_rank`), so one unrepairable key no longer stops
    the adoption — or the pre-flight the adoption runs inside.
    Performs NO store mutation and NO journaling, so all four normalization
    cadences share identical adoption logic.
    """
    plan: list[dict[str, str]] = []
    bottom = _bottom_live_rank(items=items)
    for item in items:
        stored_status = str(item.status)
        remap = _NATIVE_STATUS_REMAP.get(stored_status)
        if remap is None:
            continue
        planned = {
            "item_id": item.id,
            "from": stored_status,
            "to": remap.to,
            "reason": remap.reason,
        }
        if item.rank == BOTTOM_SENTINEL:
            bottom = key_between(a=bottom, b=None)
            planned["rank"] = bottom
        plan.append(planned)
    return plan


def _bottom_live_rank(*, items: list[WorkItem]) -> str | None:
    """The greatest VALID key among the live rows — the bottom of the live order (PURE).

    `done` rows are excluded because they are not part of the live order, and
    every key `key_between` cannot extend is excluded because taking one as the
    bottom makes the insert REFUSE rather than land after it. That covers two
    kinds of value, and they are excluded for the same reason rather than by
    two tests. The sentinel is the ABSENCE of a key rather than one (it sorts
    after every real key precisely so a rank-less row does not crash a listing,
    so taking it as the bottom would make every fresh insert land after a value
    no row really holds). And a MALFORMED key is a stored value that is not a
    fractional-indexing key at all: `zz` sorts above every well-formed `a…`
    key, so a plain `max` picks it and `key_between` then raises — which is the
    measured defect (`FIError invalid order key: zz` from one
    `pending-approval` row killed every dispatch pre-flight on this tenant on
    2026-10-14, before any Fabro run existed). `None` — no live row carries a
    valid key — is the open start `key_between` accepts.
    """
    live = [
        item.rank
        for item in items
        if str(item.status) != _LIVESPEC_DONE and _valid_rank_key(rank=item.rank)
    ]
    return max(live) if live else None


def _valid_rank_key(*, rank: str) -> bool:
    """Whether `rank` is a key `key_between` / `n_keys_between` accept (PURE).

    Asked through the ported library's own validator rather than re-derived
    here, so this answers the question the insert will actually ask. The
    `IndexError` arm is the empty string, which `validate_order_key` indexes
    before it can reject: `rank_from_metadata` substitutes the sentinel for an
    empty stored value so no row reaches here carrying one, and a predicate
    that raised on it would reproduce the very crash class this guards.
    """
    try:
        validate_order_key(key=rank)
    except (FIError, IndexError):
        return False
    return True


def apply_native_status_remaps(
    *,
    remaps: list[dict[str, str]],
    config: StoreConfig,
) -> None:
    """Write each planned adoption through the `update_work_item_status` seam.

    The status and any assigned `rank` ride ONE call, so no call path — and no
    interrupted partial heal — can adopt a row status-only and leave it resting
    on the bottom-sentinel.
    """
    for remap in remaps:
        update_work_item_status(
            path=config,
            item_id=remap["item_id"],
            status=remap["to"],
            rank=remap.get("rank"),
        )


def project_native_status_remaps(
    *,
    items: list[WorkItem],
    remaps: list[dict[str, str]],
) -> list[WorkItem]:
    """Return `items` with each planned adoption applied in memory (PURE).

    The post-adoption view the store would read back — the dispatch path and
    the CLI dry-run both use it so residual ledger checks run against the
    same projected rows without a second store round-trip. A planned row that
    was already ranked keeps its existing key.
    """
    planned_by_id = {remap["item_id"]: remap for remap in remaps}
    return [_projected(item=item, remap=planned_by_id.get(item.id)) for item in items]


def _projected(*, item: WorkItem, remap: dict[str, str] | None) -> WorkItem:
    """One row's post-adoption view: unplanned rows pass through untouched (PURE)."""
    if remap is None:
        return item
    return replace(item, status=remap["to"], rank=remap.get("rank", item.rank))


def _normalize_native_statuses(
    *,
    items: list[WorkItem],
    config: StoreConfig,
    journal: JournalFile,
) -> list[WorkItem]:
    remaps = plan_native_status_remaps(items=items)
    if not remaps:
        return items
    apply_native_status_remaps(remaps=remaps, config=config)
    _append_normalization_note(journal=journal, normalized=remaps)
    return project_native_status_remaps(items=items, remaps=remaps)


def _append_normalization_note(
    *,
    journal: JournalFile,
    normalized: list[dict[str, str]],
) -> None:
    journal.append(record={"stage": "status-normalization", "normalized": normalized})


def _malformed_live_ranks(*, items: list[WorkItem]) -> list[dict[str, str]]:
    """One `{item_id, rank}` dict per live row whose stored rank is malformed (PURE).

    `done` rows are out of scope because they are not part of the live order,
    and the bottom-sentinel is NOT malformed: it is the adapter's sanctioned
    stand-in for metadata carrying no key, so reporting it would name every
    rank-less legacy row as needing a repair it does not need. What is left is
    exactly the set of stored values that are neither a key nor the absence of
    one, which is the set an operator has to repair.
    """
    return [
        {"item_id": item.id, "rank": item.rank}
        for item in items
        if str(item.status) != _LIVESPEC_DONE
        and item.rank != BOTTOM_SENTINEL
        and not _valid_rank_key(rank=item.rank)
    ]


def ledger_blocked_after_normalization(
    *,
    items: list[WorkItem],
    config: StoreConfig,
    journal: JournalFile,
) -> bool:
    _report_malformed_live_ranks(items=items, journal=journal)
    items[:] = _normalize_native_statuses(items=items, config=config, journal=journal)
    return _ledger_blocked(items=items, journal=journal)


def _report_malformed_live_ranks(*, items: list[WorkItem], journal: JournalFile) -> None:
    """Journal + surface each malformed live rank; REFUSE nothing.

    Runs BEFORE normalization, because the normalization is what the malformed
    key used to kill and a report emitted after it would be absent on exactly
    the runs that most needed it. It reports rather than blocks: a rank the
    insert can no longer be asked to extend makes no dispatch unsafe, and
    refusing here would reinstate the tenant-wide stall under a tidier name.
    Both surfaces carry the id AND the rank — the journal because it is the
    durable record, stderr because it is what the operator driving the dispatch
    reads.
    """
    malformed = _malformed_live_ranks(items=items)
    if not malformed:
        return
    journal.append(record={"stage": "malformed-rank", "rows": malformed})
    for row in malformed:
        _ = write_stderr(
            text=(
                f"LEDGER: malformed-rank  {row['item_id']}  stored rank "
                f"{row['rank']!r} is not a valid fractional-indexing key; "
                "repair it through rebalance-ranks\n"
            ),
        )


def _ledger_blocked(*, items: list[WorkItem], journal: JournalFile) -> bool:
    findings = run_ledger_checks(items=items)
    if not findings:
        return False
    journal.append(
        record={
            "stage": "ledger-check",
            "findings": [asdict(finding) for finding in findings],
        }
    )
    _write_findings(findings=findings)
    return True


def _write_findings(*, findings: list[LedgerFinding]) -> None:
    for finding in findings:
        _ = write_stderr(
            text=f"LEDGER: {finding.check}  {finding.item_id}  {finding.message}\n",
        )
    _ = write_stderr(text="ERROR: pre-dispatch ledger checks failed; dispatch blocked\n")


def load_items(*, repo: Path) -> list[WorkItem]:
    records = read_work_items(path=store_config(repo=repo))
    return list(materialize_work_items(records=records).values())


def emit_outcomes(*, outcomes: list[DispatchOutcome], as_json: bool) -> None:
    if as_json:
        payload = [_outcome_payload(outcome=outcome) for outcome in outcomes]
        _ = write_stdout(text=json.dumps(payload, indent=2, sort_keys=True) + "\n")
        return
    if not outcomes:
        _ = write_stdout(text="(nothing dispatched)\n")
        return
    for outcome in outcomes:
        pr_part = f" PR#{outcome.pr_number}" if outcome.pr_number is not None else ""
        line = f"{outcome.work_item_id}  {outcome.status} at {outcome.stage}{pr_part}"
        _ = write_stdout(text=f"{line}  {outcome.detail}\n")


# Optional outcome fields that are DROPPED from the emitted payload when unset,
# so an ordinary outcome does not carry a column of nulls for the three shapes
# that populate them: a fabro failure, a degraded step outcome, and a
# dead-implementer truncation.
_OPTIONAL_OUTCOME_FIELDS: tuple[str, ...] = (
    # The three readings the overtaken-arming ending measured, which only that
    # ending carries. Dropped on the same terms as the needs-human verdict
    # below, and for the same reason sharpened once more: the field's PRESENCE
    # is what identifies the ending, so an explicit null on every other
    # outcome would put the key on dispatches that are not that ending and
    # leave a consumer discriminating by its value instead of its presence.
    "base_advanced",
    "dead_implementer_condition",
    "fabro_failure_cause",
    "fabro_failure_category",
    "fabro_failure_signature",
    "missing_integration_point",
    # The three-way needs-human verdict, which only a Fabro needs-human
    # terminal carries. Dropping it when unset keeps every other outcome's
    # payload the shape it has always been — and it matters more here than for
    # the siblings above, because this field is read as an ATTRIBUTION: an
    # explicit null on a green or failed outcome would invite a consumer to
    # read "this ending was not attributed" off an outcome that was never a
    # needs-human ending in the first place.
    "needs_human_kind",
    # The stages that verdict attributed the ending to, dropped on the same
    # terms and for a sharper version of the same reason: this field is None
    # rather than empty when no verdict was taken, so dropping it keeps "no
    # verdict" distinguishable from "a verdict that found no failed stage".
    "needs_human_stages",
    # The terminal's own reason line, dropped on the same terms. The sharper
    # reason here is that its absence is AMBIGUOUS in a way a reader must not
    # resolve: a terminal that printed no reason and a run whose output never
    # reached the parser are both None, so an explicit null would read as a
    # positive finding about a terminal nobody observed.
    "needs_human_reason",
    # The hook-over-limit event, dropped on the same terms. The reason is the
    # ATTRIBUTION one again, and at its sharpest: an explicit null here would
    # read as "this run's hooks stayed inside their limits", which is a positive
    # finding about an observation that is only ever taken inside `publish_draft`
    # and is therefore absent from every other outcome for reasons that have
    # nothing to do with hooks.
    "hook_over_limit",
    "needs_human_preservation",
    "provider_usage_limit_provider",
    "remedy",
    "step",
    # The acceptance verdict, which only an outcome that reached the post-merge
    # acceptance valve carries. Dropping it when unset keeps every pre-merge and
    # failed outcome's payload the shape it has always been.
    "verdict",
)


def _outcome_payload(*, outcome: DispatchOutcome) -> dict[str, object]:
    payload = asdict(outcome)
    for name in _OPTIONAL_OUTCOME_FIELDS:
        if payload.get(name) is None:
            _ = payload.pop(name)
    _ = payload.pop("provider_usage_limit", None)
    return payload
