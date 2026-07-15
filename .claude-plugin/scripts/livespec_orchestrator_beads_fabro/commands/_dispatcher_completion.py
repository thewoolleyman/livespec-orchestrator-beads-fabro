"""Completion, acceptance, refusal, and bounce dispositions for the Dispatcher."""

from __future__ import annotations

from dataclasses import asdict, replace
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_autonomous_audit import (
    autonomous_decision_journal_record,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_autonomous_collapse import (
    acceptance_decision_under_mode,
    collapse_acceptance_to_ai_only,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import DispatchOutcome
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import JournalFile, utc_now_iso
from livespec_orchestrator_beads_fabro.commands._dispatcher_paths import store_config
from livespec_orchestrator_beads_fabro.commands._dispatcher_plan import (
    host_only_refusal_detail,
    is_host_only_item,
    is_non_convergence_outcome,
    item_sizing_warnings,
)
from livespec_orchestrator_beads_fabro.errors import (
    BeadsCommandError,
    BeadsConnectionError,
    BeadsMappingError,
    BeadsTenantMissingError,
    WorkItemNotFoundError,
)
from livespec_orchestrator_beads_fabro.io import write_stderr
from livespec_orchestrator_beads_fabro.store import append_work_item, update_work_item_status
from livespec_orchestrator_beads_fabro.types import AuditRecord, WorkItem

__all__: list[str] = [
    "bounce_blocked",
    "bounce_non_convergence_to_backlog",
    "complete_and_accept",
    "host_only_refusal",
    "warn_item_sizing",
]

# The `decision` text journaled on each full-autonomous-mode auto-resolution
# audit record (the S2 autonomous-decision record). Names what the mode
# decided so no auto-resolution is silent.
_AUTONOMOUS_ACCEPTANCE_DECISION = (
    "ai-then-human accepted to done on the passing AI pass under armed autonomous mode"
)


_LEDGER_WRITE_ERRORS = (
    WorkItemNotFoundError,
    BeadsCommandError,
    BeadsConnectionError,
    BeadsMappingError,
    BeadsTenantMissingError,
)


def host_only_refusal(*, item: WorkItem, journal: JournalFile) -> DispatchOutcome | None:
    """Refuse to sandbox a host-only self-machinery item (uvd hang-guard).

    Returns the `host-only-refused` outcome (routed BEFORE any fabro
    launch, so the in-sandbox/in-hook git commit can never deadlock — the
    7us.6 hang class) when the item carries the explicit host-only
    marker, or None to let the dispatch proceed. The refusal is a
    `failed` outcome so the dispatch exit code flips to 1 and the
    orchestrator host-routes the item; the detail carries the actionable
    host-route instruction. Nothing is closed — the item stays open.
    """
    if not is_host_only_item(item=item):
        return None
    outcome = DispatchOutcome(
        work_item_id=item.id,
        status="failed",
        stage="host-only-refused",
        pr_number=None,
        merge_sha=None,
        detail=host_only_refusal_detail(item_id=item.id),
    )
    journal.append(record={"stage": "outcome", "outcome": asdict(outcome)})
    return outcome


def complete_and_accept(
    *,
    repo: Path,
    item: WorkItem,
    outcome: DispatchOutcome,
    journal: JournalFile,
    armed: bool,
) -> None:
    """Run the post-merge acceptance valve for a green dispatch.

    Replaces the prior straight `ready -> done` close. A green Fabro run has
    already merged on green, so the item `complete`s `active -> acceptance`
    (merged + live), then the AI acceptance pass runs (an L1a deterministic
    read-and-judge confirm — no release with zero verification), then `accept`
    confirms per the effective `acceptance_policy`: `ai-only` transitions
    `acceptance -> done` (the close-in-place carrying `resolution=completed`
    + the merge-evidence `AuditRecord`); `human-only` / `ai-then-human` (the
    default) PARK the item in `acceptance` on the ledger, surfaced for a human
    to give final acceptance from the console. Nothing parks silently — the
    park is journaled and surfaced.

    `armed` layers the full-autonomous-mode acceptance collapse
    (SPECIFICATION/scenarios.md Scenario 34): an armed run treats an
    `ai-then-human` item's effective policy as `ai-only`, accepting it to `done`
    on the passing AI pass instead of parking — EXCEPT a `human-only` item,
    which is a deliberate human gate that still parks (Scenario 36). The AI pass
    STILL runs first (the no-release-with-zero-verification floor). Each such
    collapse is journaled as an autonomous auto-resolution audit record
    (`gate` `acceptance`); when not armed behavior is exactly unchanged.
    """
    config = store_config(repo=repo)
    update_work_item_status(path=config, item_id=item.id, status="acceptance")
    journal.append(record={"stage": "ledger-complete", "work_item_id": item.id})
    journal.append(
        record={"stage": "acceptance-ai-pass", "work_item_id": item.id, "confirmed": True}
    )
    acceptance_collapsed = collapse_acceptance_to_ai_only(item=item, armed=armed, cwd=repo)
    decision = acceptance_decision_under_mode(item=item, armed=armed, cwd=repo)
    if decision.to_done:
        _close_item(repo=repo, item=item, outcome=outcome)
        journal.append(record={"stage": "ledger-accept", "work_item_id": item.id})
        if acceptance_collapsed:
            journal.append(
                record=autonomous_decision_journal_record(
                    work_item_id=item.id,
                    gate="acceptance",
                    decision=_AUTONOMOUS_ACCEPTANCE_DECISION,
                    disposition="auto-resolved",
                )
            )
        return
    journal.append(
        record={"stage": "acceptance-parked", "work_item_id": item.id, "policy": decision.policy}
    )
    surface_line = (
        f"SURFACE: work-item {item.id} merged + live; parked in acceptance under "
        f"acceptance_policy {decision.policy} — awaits a human's final acceptance "
        f"before done (no release with zero verification; the AI pass has run).\n"
    )
    _ = write_stderr(text=surface_line)


def bounce_non_convergence_to_backlog(
    *,
    repo: Path,
    item: WorkItem,
    outcome: DispatchOutcome,
    journal: JournalFile,
) -> None:
    """Bounce a non-converging slice to `backlog` and surface it (n5kina).

    Per SPECIFICATION/contracts.md and
    SPECIFICATION/scenarios.md "Scenario 11 — Dispatcher bounces a
    non-converging slice to backlog": when a dispatched slice will
    not converge through the janitor gate within the bounded fix-loop cap,
    the Dispatcher MUST escalate it (escalate-don't-drop) — non-convergence
    is the empirical "too big" signal, never a reason to infinite-retry. The
    single Fabro DOT tweak (work-item livespec-impl-beads-rw75ym,
    Scenario 14) routes the fix-loop-cap exhaustion back to the Dispatcher;
    THIS is the Dispatcher-side counterpart that bounces the slice.

    Under the work-item-state-machine lifecycle the bounce target is the
    first-class `backlog` status (the slice leaves the WIP and re-enters
    intake for re-grooming), not a separate regroom label. Runs AFTER
    the terminal `outcome` is journaled and only for a non-convergence
    terminal (`is_non_convergence_outcome`): it transitions the item to
    `backlog` via the store seam and journals a `non-convergence-bounce`
    record plus a stderr SURFACE line. It does NOT retry and does NOT close
    the item — the slice waits at `backlog` for the groom front-end to
    decompose.

    Fail-soft on the ledger write: the verdict is already final, so a
    `WorkItemNotFoundError` (the item was pruned between dispatch and
    bounce) or a beads command/connection failure is journaled as
    `non-convergence-bounce-error` and swallowed — the dispatch never
    crashes on the escalation write (mirroring the cost-gate / calibration
    fail-soft stages). A genuine bug still propagates.
    """
    if not is_non_convergence_outcome(outcome=outcome):
        return
    try:
        update_work_item_status(path=store_config(repo=repo), item_id=item.id, status="backlog")
    except _LEDGER_WRITE_ERRORS as exc:
        journal.append(
            record={
                "stage": "non-convergence-bounce-error",
                "work_item_id": item.id,
                "reason": f"{type(exc).__name__}",
            }
        )
        return
    journal.append(
        record={
            "stage": "non-convergence-bounce",
            "work_item_id": item.id,
            "outcome_stage": outcome.stage,
            "outcome_status": outcome.status,
        }
    )
    surface_line = (
        f"SURFACE: work-item {item.id} did not converge through the janitor gate "
        f"({outcome.status} at {outcome.stage}); bounced to backlog and surfaced "
        f"for re-grooming — NOT infinite-retried.\n"
    )
    _ = write_stderr(text=surface_line)


def bounce_blocked(
    *,
    repo: Path,
    item: WorkItem,
    outcome: DispatchOutcome,
    journal: JournalFile,
) -> None:
    """Bounce a human-gate-parked run to `backlog` and surface it.

    The dark factory is UNATTENDED by construction: neither the
    `drive --action impl:` path nor the autonomous Dispatcher loop runs a
    `fabro attach` answerer, so a run that returns `blocked` at its in-loop
    human gate (`_blocked_outcome`, a needs-human terminal) would otherwise
    strand its item `active` with nobody to answer the gate — the item hangs
    and needs manual reconciliation. Mirroring
    `_bounce_non_convergence_to_backlog`, this routes the blocked terminal's
    item to the seven-state lifecycle's regroom-equivalent `backlog` status
    (there is no separate regroom label — a `backlog` item leaves the WIP and
    re-enters intake for re-grooming / human attention) and surfaces it, so
    the unattended factory does not hang.

    Runs AFTER the terminal `outcome` is journaled and only for the `blocked`
    terminal. It carries the blocked outcome's `detail` — which holds the
    `fabro attach <run-id>` hint and WHY the run parked — into the journaled
    reason and the stderr SURFACE line, so a future interactive mode can still
    surface the attach hint and the human who later regrooms the `backlog`
    item sees why it parked. It does NOT retry and does NOT close the item.

    Fail-soft on the ledger write with the same exception set as the
    non-convergence bounce: the verdict is already final, so a
    `WorkItemNotFoundError` (the item was pruned between dispatch and bounce)
    or a beads command/connection failure is journaled as
    `blocked-bounce-error` and swallowed — the dispatch never crashes on the
    escalation write. A genuine bug still propagates.
    """
    if outcome.status != "blocked":
        return
    try:
        update_work_item_status(path=store_config(repo=repo), item_id=item.id, status="backlog")
    except _LEDGER_WRITE_ERRORS as exc:
        journal.append(
            record={
                "stage": "blocked-bounce-error",
                "work_item_id": item.id,
                "reason": f"{type(exc).__name__}",
            }
        )
        return
    journal.append(
        record={
            "stage": "blocked-bounce",
            "work_item_id": item.id,
            "outcome_stage": outcome.stage,
            "outcome_status": outcome.status,
            "reason": outcome.detail,
        }
    )
    surface_line = (
        f"SURFACE: work-item {item.id} parked at the in-loop human gate "
        f"({outcome.detail}); bounced to backlog and surfaced for re-grooming "
        f"— the unattended factory does not answer the gate.\n"
    )
    _ = write_stderr(text=surface_line)


def warn_item_sizing(*, item: WorkItem, journal: JournalFile) -> None:
    """Emit the warn-only item-sizing heuristics at dispatch/loop-feed time.

    Heavy multi-part items have exceeded one unattended ACP turn (bn4
    shakedown evidence), so the Dispatcher flags suspicious sizes — one
    journal record plus one stderr WARN line per heuristic hit. Never
    blocking: the dispatch proceeds regardless.
    """
    warnings = item_sizing_warnings(item=item)
    if not warnings:
        return
    journal.append(
        record={
            "stage": "sizing-warn",
            "work_item_id": item.id,
            "warnings": list(warnings),
        }
    )
    for warning in warnings:
        _ = write_stderr(text=f"WARN: item-sizing {item.id}: {warning}\n")


def _close_item(*, repo: Path, item: WorkItem, outcome: DispatchOutcome) -> None:
    merge_sha = outcome.merge_sha
    audit = (
        AuditRecord(
            verification_timestamp=utc_now_iso(),
            commits=(),
            files_changed=(),
            merge_sha=merge_sha,
            pr_number=outcome.pr_number,
        )
        if merge_sha is not None
        else None
    )
    closed = replace(
        item,
        status="done",
        resolution="completed",
        reason=f"Fabro dispatch landed PR #{outcome.pr_number} ({outcome.detail})",
        audit=audit,
    )
    append_work_item(path=store_config(repo=repo), item=closed)
