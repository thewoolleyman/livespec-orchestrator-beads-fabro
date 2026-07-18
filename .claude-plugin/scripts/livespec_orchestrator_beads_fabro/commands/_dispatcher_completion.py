"""Completion, acceptance, refusal, and bounce dispositions for the Dispatcher."""

from __future__ import annotations

from dataclasses import asdict, replace
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_acceptance_ai import (
    run_acceptance_pass,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_acceptance_rework import (
    AI_DISPOSITIVE_ACCEPTANCE_POLICIES,
    rework_or_block_failed_acceptance,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_blocked import (
    escalate_needs_human_block,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_decision_journal import (
    auto_disposition_journal_record,
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
from livespec_orchestrator_beads_fabro.commands._dispatcher_valves import (
    acceptance_decision,
    effective_acceptance_policy,
)
from livespec_orchestrator_beads_fabro.effects import AttemptFailure, attempt
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
    "bounce_non_convergence_to_backlog",
    "complete_and_accept",
    "escalate_needs_human_block",
    "host_only_refusal",
    "warn_item_sizing",
]

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
    _ = write_stderr(text=f"SURFACE: {outcome.detail}\n")
    return outcome


def complete_and_accept(
    *,
    repo: Path,
    item: WorkItem,
    outcome: DispatchOutcome,
    journal: JournalFile,
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

    """
    config = store_config(repo=repo)
    update_work_item_status(path=config, item_id=item.id, status="acceptance")
    journal.append(record={"stage": "ledger-complete", "work_item_id": item.id})
    policy = effective_acceptance_policy(item=item, cwd=repo)
    acceptance_pass = run_acceptance_pass(repo=repo, item=item, outcome=outcome)
    journal.append(record=acceptance_pass.journal_record(work_item_id=item.id, policy=policy))
    decision = acceptance_decision(policy=policy)
    if acceptance_pass.verdict == "FAIL" and policy in AI_DISPOSITIVE_ACCEPTANCE_POLICIES:
        rework_or_block_failed_acceptance(repo=repo, item=item, policy=policy, journal=journal)
        return
    if decision.to_done and acceptance_pass.verdict == "PASS":
        _close_item(repo=repo, item=item, outcome=outcome)
        journal.append(record={"stage": "ledger-accept", "work_item_id": item.id})
        journal.append(
            record=auto_disposition_journal_record(
                work_item_id=item.id,
                disposition="ai-auto-accept",
                governing_settings=("acceptance_mode",),
            )
        )
        return
    journal.append(
        record={
            "stage": "acceptance-parked",
            "work_item_id": item.id,
            "policy": decision.policy,
            "advisory": decision.policy == "human-only",
            "acceptance_verdict": acceptance_pass.verdict,
        }
    )
    surface_line = (
        f"SURFACE: work-item {item.id} merged + live; parked in acceptance under "
        f"acceptance_policy {decision.policy} — awaits a human's final acceptance "
        f"before done (no release with zero verification; the AI pass verdict was "
        f"{acceptance_pass.verdict}).\n"
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
    updated = attempt(
        action=lambda: update_work_item_status(
            path=store_config(repo=repo),
            item_id=item.id,
            status="backlog",
        ),
        exceptions=_LEDGER_WRITE_ERRORS,
    )
    if isinstance(updated, AttemptFailure):
        journal.append(
            record={
                "stage": "non-convergence-bounce-error",
                "work_item_id": item.id,
                "reason": f"{type(updated.error).__name__}",
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
