"""Completion, acceptance, and bounce dispositions for the Dispatcher.

The pre-launch host-only refusal that used to sit alongside these lives in
`_dispatcher_host_only_refusal.py`; it is re-exported here because the
Dispatcher's admission layer selects it from this module.
"""

from __future__ import annotations

from pathlib import Path

from returns.unsafe import unsafe_perform_io

from livespec_orchestrator_beads_fabro.commands._dispatcher_acceptance_ai import (
    NEEDS_ATTENTION_VERDICT,
    NO_CHANGE_NEEDED_VERDICT,
    run_acceptance_pass,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_acceptance_park import (
    park_in_acceptance,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_acceptance_result import (
    AcceptanceDisposition,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_acceptance_rework import (
    AI_DISPOSITIVE_ACCEPTANCE_POLICIES,
    rework_or_block_failed_acceptance,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_blocked import (
    escalate_needs_human_block,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_completion_close import (
    close_dispatch_item,
    no_change_needed_reason,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_credentials import (
    read_dispatch_labels,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_decision_journal import (
    auto_disposition_journal_record,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_effective_criteria import (
    effective_criteria,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import DispatchOutcome
from livespec_orchestrator_beads_fabro.commands._dispatcher_host_only_refusal import (
    host_only_refusal,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import JournalFile
from livespec_orchestrator_beads_fabro.commands._dispatcher_lifecycle_writes import (
    write_work_item_status_and_reconcile,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_paths import store_config
from livespec_orchestrator_beads_fabro.commands._dispatcher_plan import (
    is_non_convergence_outcome,
    item_sizing_warnings,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_proof_pointer_write import (
    write_proof_pointer,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_valves import (
    DEFAULT_ACCEPTANCE_POLICY,
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
from livespec_orchestrator_beads_fabro.store import update_work_item_status
from livespec_orchestrator_beads_fabro.types import WorkItem

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
_NO_CHANGE_NEEDED_RESOLUTION = "no-longer-applicable"


def complete_and_accept(
    *,
    repo: Path,
    item: WorkItem,
    outcome: DispatchOutcome,
    journal: JournalFile,
) -> AcceptanceDisposition:
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

    A NEEDS_ATTENTION verdict short-circuits every disposition branch and parks
    under EVERY `acceptance_policy`, `ai-only` included: the pass could not
    observe what a judgment needs, and absence of evidence disposes of nothing.

    RETURNS the disposition so the dispatch RESULT can report it. The parking
    verdict clause governs the result as well as the ledger, and the run terminal
    this is handed says `green` at `done` because the janitor built it before the
    valve ran — so a caller that reported that terminal unchanged would report a
    parked item as a completed close, which is exactly finding F7(b).
    """
    config = store_config(repo=repo)
    write_work_item_status_and_reconcile(path=config, item_id=item.id, status="acceptance")
    journal.append(record={"stage": "ledger-complete", "work_item_id": item.id})
    # An unreadable `.livespec.jsonc` falls back to the documented default
    # policy, visibly and here rather than inside the reader.
    # `unsafe_perform_io` is required: `IOResult.value_or` returns
    # `IO[value]`, not the value.
    policy = unsafe_perform_io(
        effective_acceptance_policy(item=item, cwd=repo).value_or(DEFAULT_ACCEPTANCE_POLICY)
    )
    # The item's declared ledger markers carry the change-optional exemption.
    # An unreadable label set is NOT a declaration, so it fails closed to the
    # empty marker set and the pass classifies the item change-implying.
    labels = read_dispatch_labels(repo=repo, item=item)
    acceptance_pass = run_acceptance_pass(
        repo=repo,
        item=item,
        outcome=outcome,
        raw_labels=() if isinstance(labels, str) else labels,
        # The journal is where the proof leg recovers the merging dispatch's
        # identifiers: the dispatch id lives only in the `dispatch-id` record, and
        # the reconcile valve reaches here with an outcome carrying no run id.
        journal_path=journal.path,
    )
    journal.append(record=acceptance_pass.journal_record(work_item_id=item.id, policy=policy))
    # The pointer is written BEFORE any disposition branch, because every branch
    # is a possible end state for the item and the pointer is provenance of the
    # merge rather than of the verdict: an item that parks keeps the record its
    # pass read, and one that closes carries the pointer into `done`.
    write_proof_pointer(
        repo=repo,
        item=item,
        outcome=outcome,
        proof=acceptance_pass.proof,
        journal=journal,
    )
    decision = acceptance_decision(policy=policy)
    if acceptance_pass.verdict == NEEDS_ATTENTION_VERDICT:
        # A cannot-judge verdict NEVER disposes, under EVERY acceptance_policy
        # including `ai-only`: the delegation `ai-only` grants is the authority
        # to act ON evidence, not the authority to act without it. So this
        # returns before the close / rework branches below — the item is not
        # accepted, not routed to rework, not stamped `rework:pending`, and
        # `acceptance_rework_cap` is not consumed. It parks for the human
        # `accept` / `reject` valves instead.
        park_in_acceptance(
            repo=repo,
            item_id=item.id,
            policy=decision.policy,
            acceptance_pass=acceptance_pass,
            outcome=outcome,
            journal=journal,
        )
        return AcceptanceDisposition(verdict=acceptance_pass.verdict, closed=False)
    if acceptance_pass.verdict == NO_CHANGE_NEEDED_VERDICT and decision.to_done:
        close_dispatch_item(
            repo=repo,
            item=item,
            outcome=outcome,
            resolution=_NO_CHANGE_NEEDED_RESOLUTION,
            reason=no_change_needed_reason(outcome=outcome),
            audit_merge=False,
        )
        journal.append(record={"stage": "ledger-accept-no-change-needed", "work_item_id": item.id})
        auto_disposition = auto_disposition_journal_record(
            work_item_id=item.id,
            disposition="ai-auto-no-change-needed",
            governing_settings=("acceptance_mode",),
        )
        auto_disposition["deferred"] = "pre-dispatch staleness detection"
        journal.append(record=auto_disposition)
        return AcceptanceDisposition(verdict=acceptance_pass.verdict, closed=True)
    if acceptance_pass.verdict == "FAIL" and policy in AI_DISPOSITIVE_ACCEPTANCE_POLICIES:
        # The merge sha is the dispatch's merge evidence: it is stamped only by
        # the post-merge janitor path off a resolved merged pull request, so its
        # presence is what tells the disposition whether re-implementing this
        # item could publish anything at all.
        rework_or_block_failed_acceptance(
            repo=repo,
            item=item,
            policy=policy,
            merged=outcome.merge_sha is not None,
            journal=journal,
        )
        return AcceptanceDisposition(verdict=acceptance_pass.verdict, closed=False)
    # The human-attested leg rests the item in `acceptance` "regardless of
    # policy", so it is read here from the ONE criteria primitive rather than
    # from the pass's verdict: the pass genuinely did PASS — its factory leg is
    # green and the human assertions are listed as pending — and turning that
    # into a non-PASS verdict would report a healthy run as unjudgeable. The
    # host-side wall already refuses `ai-only` for such an item before dispatch;
    # this is the second gate, for the item whose policy was edited after it.
    if (
        decision.to_done
        and acceptance_pass.verdict == "PASS"
        and not effective_criteria(item=item).human_attested_assertions
    ):
        close_dispatch_item(
            repo=repo,
            item=item,
            outcome=outcome,
            resolution="completed",
            reason=f"Fabro dispatch landed PR #{outcome.pr_number} ({outcome.detail})",
        )
        journal.append(record={"stage": "ledger-accept", "work_item_id": item.id})
        journal.append(
            record=auto_disposition_journal_record(
                work_item_id=item.id,
                disposition="ai-auto-accept",
                governing_settings=("acceptance_mode",),
            )
        )
        return AcceptanceDisposition(verdict=acceptance_pass.verdict, closed=True)
    park_in_acceptance(
        repo=repo,
        item_id=item.id,
        policy=decision.policy,
        acceptance_pass=acceptance_pass,
        outcome=outcome,
        journal=journal,
    )
    return AcceptanceDisposition(verdict=acceptance_pass.verdict, closed=False)


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
