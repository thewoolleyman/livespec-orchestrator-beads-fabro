"""The re-GRADE arm of the `reconcile-merged` valve.

An item whose pull request merged green and whose post-merge acceptance then
FAILED is stamped `rework:pending` and left `active`. When that failure was the
CRITERIA's rather than the code's — a prohibition-shaped fragment no correct
implementation can evidence — every route back to a verdict is closed. The
plain reconcile valve refuses the marker (its disposition already ran and chose
rework), the human `accept` valve refuses the `active` source state, and the
designated rework re-dispatch re-IMPLEMENTS work that is already on the default
branch, so it cuts an empty branch, fails the changed-tree stage, and spends an
`acceptance_rework_cap` attempt — converting a recoverable state into
`blocked` / needs-human on the last one.

This arm is that missing route, and it is deliberately a RE-GRADE rather than a
carve-out. It disposes of nothing on an operator's say-so: it proceeds only
when the merged pull request RESOLVES from the forge and its merge commit is an
ancestor of the default branch's tip — two facts about the repository an
invocation cannot fabricate — and it then runs the SAME acceptance pass the
dispatch path runs, against the item's CURRENT effective criteria. Passing
`--regrade` selects the arm; it never supplies the evidence.

A pass that grades anything other than PASS leaves the item exactly as it found
it — status, labels and `acceptance_failed_ai_passes` alike. A re-grade is not
a second chance to fail: an operator who mis-repaired the criteria must be able
to try again, and an arm that charged the rework cap for looking would burn the
item it exists to recover.

It never launches a Fabro run, cuts a branch, or re-runs the post-merge
janitor. The janitor already ran for this item — that is how the merge got
there — and re-running it would spend a full checkout to answer a question
about criteria text.

BOTH DISPOSITIONS ARE CLAIM-CHANGING WRITES BY A HUMAN VALVE
(`SPECIFICATION/contracts.md`, "Claim tokens"): the arm is an attributed
operator act that parks the item in `acceptance` or closes it. Once
`dispatcher.claim_tokens` is true each is made only after winning the item's
current token, and only while the item still rests where the arm read it,
still carrying `rework:pending`, under the claim row `run_regrade` read before
anything else. The park is one guarded write. The close is two: `bd close`
cannot name a successor token, so the arm first wins the token in a write that
names the successor and changes nothing else, and closes only after that write
landed. An arm that does not win has written nothing, and reports the
protocol's outcome on a failed result. Both writes, guarded and unguarded,
are made in `_dispatcher_reconcile_regrade_claims`, because this module is at
its size ceiling.
"""

from __future__ import annotations

from collections.abc import Callable
from functools import partial
from pathlib import Path

from returns.unsafe import unsafe_perform_io

from livespec_orchestrator_beads_fabro.commands._dispatcher_acceptance_ai import (
    AcceptancePassResult,
    run_acceptance_pass,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_acceptance_park import (
    park_in_acceptance,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_command_common import (
    EXIT_PRECONDITION_ERROR,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_completion_close import (
    close_dispatch_item,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import (
    CommandRunner,
    DispatchOutcome,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_incident_closure import (
    incident_acceptance_for,
    incident_holds,
    incident_proof_pointer,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import JournalFile
from livespec_orchestrator_beads_fabro.commands._dispatcher_item_ledger_reads import (
    read_dispatch_labels,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_paths import store_config
from livespec_orchestrator_beads_fabro.commands._dispatcher_plan import (
    DispatchPlan,
    PrView,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_reconcile_merged_pr import (
    resolve_merged_pr,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_reconcile_regrade_claims import (
    RegradeClaim,
    refused_regrade_outcome,
    regrade_claim,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_reconcile_regrade_containment import (
    UNMERGED_REFUSAL,
    merge_containment_refusal,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_valves import (
    DEFAULT_ACCEPTANCE_POLICY,
    effective_acceptance_policy,
)
from livespec_orchestrator_beads_fabro.io import write_stderr
from livespec_orchestrator_beads_fabro.types import WorkItem

__all__: list[str] = [
    "REGRADE_STAGE",
    "run_regrade",
]

REGRADE_STAGE = "regrade"


def run_regrade(
    *,
    repo: Path,
    item: WorkItem,
    plan: DispatchPlan,
    runner: CommandRunner,
    journal: JournalFile,
) -> DispatchOutcome | int:
    """Re-grade a merged, rework-pending item against its current criteria.

    Returns the terminal `DispatchOutcome` for the caller to journal and emit —
    green at `done` when the re-grade PASSES and the item closes, failed at
    `regrade` when it reaches any other verdict and the item is untouched — or
    an exit code when the merge evidence the arm keys on does not hold.
    """
    # Read FIRST, ahead of the merge evidence and the grading pass: it is what the
    # arm's disposition is later bound to.
    claim = regrade_claim(repo=repo, item=item, journal=journal)
    merged = resolve_merged_pr(plan=plan, item=item, runner=runner, journal=journal)
    if isinstance(merged, str):
        _ = write_stderr(text=merged)
        return EXIT_PRECONDITION_ERROR
    if merged is None:
        _ = write_stderr(text=UNMERGED_REFUSAL.format(item_id=item.id))
        return EXIT_PRECONDITION_ERROR
    containment = merge_containment_refusal(
        plan=plan, item=item, merged=merged, runner=runner, journal=journal
    )
    if containment is not None:
        _ = write_stderr(text=containment)
        return EXIT_PRECONDITION_ERROR
    return _grade_and_dispose(
        repo=repo, item=item, merged=merged, runner=runner, journal=journal, claim=claim
    )


def _grade_and_dispose(
    *,
    repo: Path,
    item: WorkItem,
    merged: PrView,
    runner: CommandRunner,
    journal: JournalFile,
    claim: RegradeClaim,
) -> DispatchOutcome:
    """Run the acceptance pass over the verified merge and dispose on a clear PASS.

    The outcome handed to the pass reports `green` because the merge evidence
    the arm just verified is what the telemetry leg asks about, and it is the
    STRONGER form of it: a run status is a claim about a process that has since
    exited, while the ancestry is a fact about the branch this repository can
    read. Every other leg — the merged diff, the effective criteria — the pass
    reads for itself, so nothing here is asserted on the arm's behalf.

    The effective `acceptance_policy` is journaled and deliberately does NOT
    gate the disposition. `--regrade` is an attributed operator act rather than
    an automatic pass, so the invocation IS the human judgement a `human-only`
    item asks for, and the graded criteria are the evidence behind it.
    """
    outcome = DispatchOutcome(
        work_item_id=item.id,
        status="green",
        stage=REGRADE_STAGE,
        pr_number=merged.number,
        merge_sha=merged.merge_sha,
        detail=f"re-grading against merged PR #{merged.number}",
    )
    # The item's declared ledger markers carry the change-optional exemption; an
    # unreadable label set is NOT a declaration, so it fails closed to the empty
    # marker set exactly as the dispatch-path acceptance valve does.
    labels = read_dispatch_labels(repo=repo, item=item)
    config = store_config(repo=repo)
    incident = incident_acceptance_for(config=config, item_id=item.id, merged_pr=merged.number)
    result = run_acceptance_pass(
        repo=repo,
        item=item,
        outcome=outcome,
        runner=runner,
        raw_labels=() if isinstance(labels, str) else labels,
        # The re-grade builds its own outcome, so it carries no Fabro run id; the
        # journal is the only place either identifier of the merging dispatch
        # survives into this process.
        journal_path=journal.path,
        incident=incident.scope,
    )
    # `unsafe_perform_io` is required: `IOResult.value_or` returns `IO[value]`.
    policy = unsafe_perform_io(
        effective_acceptance_policy(item=item, cwd=repo).value_or(DEFAULT_ACCEPTANCE_POLICY)
    )
    journal.append(record=result.journal_record(work_item_id=item.id, policy=policy))
    # The literal matches the dispatch-path acceptance valve's own comparison;
    # a named constant here reads to the lint rule set as a hardcoded secret.
    if result.verdict != "PASS":
        return _leave_regraded_item(item=item, outcome=outcome, verdict=result.verdict)
    # The pointer is made to name the pull request this pass graded, which the plain
    # pass does on every disposition: `accept` reads the pull request OFF the pointer,
    # so one left on a superseded pull request refuses a valid replay on the graded one.
    # It is written only once the claim check has passed, inside the park or the close,
    # because a refused re-grade writes nothing and must not redirect the pointer.
    write_pointer = partial(
        incident_proof_pointer,
        repo=repo,
        item=item,
        outcome=outcome,
        proof=result.proof,
        journal=journal,
        incident=incident,
    )
    # A PASS on an incident that still owes final normal proof parks rather than closes.
    if incident_holds(incident=incident, journal=journal, route="regrade") or (
        result.proof is not None
        and (result.proof.pending_host_captured or result.proof.pending_human_attested)
    ):
        return _park_regraded_item(
            repo=repo,
            item=item,
            outcome=outcome,
            policy=policy,
            result=result,
            journal=journal,
            claim=claim,
            write_pointer=write_pointer,
        )
    return _close_regraded_item(
        repo=repo,
        item=item,
        outcome=outcome,
        journal=journal,
        claim=claim,
        write_pointer=write_pointer,
    )


def _park_regraded_item(  # noqa: PLR0913 — kw-only; the pass's facts and the claim it rests on.
    *,
    repo: Path,
    item: WorkItem,
    outcome: DispatchOutcome,
    policy: str,
    result: AcceptancePassResult,
    journal: JournalFile,
    claim: RegradeClaim,
    write_pointer: Callable[[], None],
) -> DispatchOutcome:
    """Park a passing re-grade whose host or human proof leg is still pending."""
    lost = claim.park()
    if lost is not None:
        return refused_regrade_outcome(item=item, outcome=outcome, refusal=lost)
    write_pointer()
    park_in_acceptance(
        repo=repo,
        item_id=item.id,
        policy=policy,
        acceptance_pass=result,
        outcome=outcome,
        journal=journal,
    )
    return DispatchOutcome(
        work_item_id=item.id,
        status="green",
        stage="acceptance",
        pr_number=outcome.pr_number,
        merge_sha=outcome.merge_sha,
        detail="re-graded PASS; parked pending proof verification",
    )


def _close_regraded_item(
    *,
    repo: Path,
    item: WorkItem,
    outcome: DispatchOutcome,
    journal: JournalFile,
    claim: RegradeClaim,
    write_pointer: Callable[[], None],
) -> DispatchOutcome:
    """Close a re-graded PASS, which is what clears the `rework:pending` marker.

    The marker is NOT cleared by a second write of its own. Every lifecycle
    write seam carries `rework_pending_label_removals`, so the close that lands
    `done` removes the label in the SAME mutation — that is the structural
    guarantee `_store_rework_mutations` exists to give, and a disposition that
    cleared the marker by hand would be re-asserting what the seam already
    holds, in a second write that can fail on its own.
    """
    lost = claim.hold()
    if lost is not None:
        return refused_regrade_outcome(item=item, outcome=outcome, refusal=lost)
    write_pointer()
    close_dispatch_item(
        repo=repo,
        item=item,
        outcome=outcome,
        resolution="completed",
        reason=(
            f"reconcile-merged --regrade: acceptance re-graded PASS against merged "
            f"PR #{outcome.pr_number} ({outcome.merge_sha})"
        ),
    )
    journal.append(record={"stage": "ledger-regrade-accept", "work_item_id": item.id})
    return DispatchOutcome(
        work_item_id=item.id,
        status="green",
        stage="done",
        pr_number=outcome.pr_number,
        merge_sha=outcome.merge_sha,
        detail="re-graded PASS, rework:pending cleared and item closed",
    )


def _leave_regraded_item(
    *, item: WorkItem, outcome: DispatchOutcome, verdict: str
) -> DispatchOutcome:
    """Report a non-PASS re-grade, having written nothing at all.

    There is no ledger call on this path, which is the whole point: the item's
    status, its `rework:pending` marker and its `acceptance_failed_ai_passes`
    metadata stay exactly as the ORIGINAL failing disposition wrote them, and a
    re-grade that could not clear the item must not charge it for the attempt.
    """
    _ = write_stderr(
        text=(
            f"SURFACE: work-item {item.id} re-graded {verdict} against merged PR "
            f"#{outcome.pr_number}; left unchanged at {item.status} with rework:pending "
            "and its acceptance_failed_ai_passes intact. Repair the effective "
            "acceptance criteria and re-run --regrade.\n"
        )
    )
    return DispatchOutcome(
        work_item_id=item.id,
        status="failed",
        stage=REGRADE_STAGE,
        pr_number=outcome.pr_number,
        merge_sha=outcome.merge_sha,
        detail=f"re-graded {verdict}; item left unchanged",
    )
