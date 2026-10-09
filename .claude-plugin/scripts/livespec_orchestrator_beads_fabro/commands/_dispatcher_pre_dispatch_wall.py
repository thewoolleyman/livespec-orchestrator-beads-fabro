"""The pre-dispatch wall: every refusal that lands after selection, before claim.

The ONE wall both dispatch paths run — the single `dispatch` and the queue-
draining `loop`. It was two byte-identical private functions, one per command
module, differing only in which item sequence each handed down; the duplicate is
what made "both paths refuse" a claim about two sequences that could drift, and
what required every new refusal to be wired twice. It moved out when the Codex
credential gate became the fourth refusal in each and pushed the single-dispatch
command module past its file LLOC ceiling — the seam was already there.

WHAT THE WALL IS. Four refusals plus one mutation, sharing one POSITION and one
guarantee: each runs after selection and BEFORE admission, so a refused item is
never claimed, no `active` row is left behind, and no factory run exists to reap.
Reading them as one decision is also what keeps each command entry point's return
count honest — the alternative was suppressing the too-many-returns rule, which
would have hidden the fact that the entry point had grown another exit.

The DRAIN reaches it after its `--dry-run` return, deliberately: a dry run creates
no run, so it stays a reporting surface that shows the operator exactly which
candidate needs criteria.
"""

from __future__ import annotations

import argparse
import os
from collections.abc import Sequence
from pathlib import Path

from returns.unsafe import unsafe_perform_io

from livespec_orchestrator_beads_fabro.commands._config_cycle_ceilings import (
    resolve_adopted_cycle_ceilings,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_acceptance_eligibility import (
    pre_dispatch_criteria_refusal,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_codex_credential_gate import (
    codex_credential_refusal_for_items,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_command_common import (
    EXIT_PRECONDITION_ERROR,
    EXIT_UNGRADEABLE_CRITERIA,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_credential_deadline import (
    CredentialLifetimeRequirement,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_credential_requirement import (
    WorkflowFaultDeferral,
    effective_policy_inputs,
    resolve_credential_lifetime_requirement,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_credential_wrapper import (
    credential_wrapper_text,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_credentials import (
    read_dispatch_labels,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import (
    JournalFile,
    ShellCommandRunner,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_policy_overrides import (
    effective_review_fix_cap,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_policy_settings import (
    DEFAULT_REVIEW_FIX_CAP,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_proof_credential_gate import (
    proof_credentials_refusal_for_items,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_proof_precondition import (
    proof_assets_refusal_for_items,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_publish_branch_reclaim import (
    reclaim_stale_publish_branches,
)
from livespec_orchestrator_beads_fabro.effects import AttemptFailure, attempt
from livespec_orchestrator_beads_fabro.errors import (
    ConnectionPrefixMissingError,
    LivespecConfigUnreadableError,
)
from livespec_orchestrator_beads_fabro.io import write_stderr
from livespec_orchestrator_beads_fabro.types import WorkItem

__all__: list[str] = [
    "pre_dispatch_wall_exit",
    "runtime_ceiling_policy_refusal",
    "selection_credential_requirement",
]


def pre_dispatch_wall_exit(
    *,
    args: argparse.Namespace,
    repo: Path,
    items: Sequence[WorkItem],
    journal: JournalFile,
    reclaim_publish_branches: bool = True,
) -> int | None:
    """The whole wall, as ONE decision: an exit code, or None to proceed.

    `items` is the selection this pass would claim — exactly one target for the
    single dispatch, the whole admitted-candidate wave for the drain. Nothing
    below branches on which caller it is, which is the point: a refusal that
    fired for one path and not the other was a defect waiting to happen.

    The criteria wall is first and is variant-aware: it is handed this dispatch's
    explicit `--workflow-name`, resolves which graph the selection would run, and
    exempts a groom-kind dispatch, whose acceptance is the human approval of the
    draft.

    The proof-ASSETS gate follows (S5 / bd-ib-b4u6b7): an item carrying a
    `factory_captured` assertion needs this repository's standing proof-assets
    prerelease to exist before its capture stage can store an image, so the
    Dispatcher creates it here and refuses naming the tag when it still does not.
    Its exit code is the generic precondition one rather than a dedicated code:
    the fault is a missing repository-level resource, which is the same class
    every other pre-dispatch precondition reports.

    The proof-CREDENTIAL gate follows (S8 / bd-ib-77vny7), in the same position
    and for the same reason: an unusable `dispatcher.proof_credentials`
    declaration must refuse before a run exists, because the overlay each of
    these items is about to materialize would otherwise project it. It reads the
    environment here rather than resolving one of its own, so the values it
    grades are the ones the overlay will actually read. That declaration is
    repository-level, so one refusal covers the whole selection, while the
    journal records are written per item.

    The Codex credential gate closes the refusing sequence (bd-ib-tyqklx) and is
    the newest of the four for a reason worth recording: its decision was already
    being made, inside `materialize_overlay`, which `dispatch_one` reaches only
    AFTER `admit_and_select` has moved the item `ready -> active` and set its
    assignee — so a credential that could not be renewed above the floor left an
    `active` row nobody was working. It is also the only wall that spends a
    PROVIDER REQUEST, the one bounded in-place renewal, so its position is what
    decides whether that request's answer can still change what happens: before
    the claim it can refuse the selection, after it cannot. Like the
    proof-credential declaration it is a HOST-level fact, so one refusal covers
    the whole selection rather than reading as one fault per item.

    The publish-branch reclaim closes the wall and refuses NOTHING
    (bd-ib-yebrb7): a dead run's surviving publish branch is what makes a
    re-dispatch's `publish_draft` push non-fast-forward, and clearing it here --
    once its head is preserved by reference -- is what lets the recovery publish
    and reach proof capture. It is per ITEM, because a publish branch is per
    item, and it runs last because it MUTATES a remote ref: a selection this wall
    is about to refuse must leave the remote exactly as it found it.
    The RUNTIME-CEILING policy refusal opens the wall (S6 / bd-ib-z2y4ca), ahead
    of the criteria wall, and its position is what the clause buys: "invalid
    policy MUST refuse before claim or lifecycle mutation". It is a pure read of
    committed configuration with no IO and no provider cost, and an invalid
    ceiling means the runtime convergence gate this dispatch would be measured
    against cannot be resolved at all — so there is nothing later in the wall
    whose answer could still matter. Like the proof-credential declaration it is
    REPOSITORY-level, so it grades even an empty selection: a broken committed
    ceiling is broken whether or not work is queued, and a drain that passed it
    silently on idle passes would surface the fault only once something was
    about to be claimed.
    """
    ceiling_refusal = runtime_ceiling_policy_refusal(repo=repo)
    if ceiling_refusal is not None:
        _ = write_stderr(text=ceiling_refusal)
        return EXIT_PRECONDITION_ERROR
    ungradeable = pre_dispatch_criteria_refusal(
        items=items, cwd=repo, workflow_name=args.workflow_name
    )
    if ungradeable is not None:
        _ = write_stderr(text=ungradeable)
        return EXIT_UNGRADEABLE_CRITERIA
    proof_refusal = proof_assets_refusal_for_items(
        runner=ShellCommandRunner(), repo=repo, items=items, journal=journal
    )
    if proof_refusal is not None:
        _ = write_stderr(text=proof_refusal)
        return EXIT_PRECONDITION_ERROR
    work_item_ids = [item.id for item in items]
    credentials_refusal = proof_credentials_refusal_for_items(
        repo=repo,
        environ=os.environ,
        wrapper_text=credential_wrapper_text(repo=repo),
        work_item_ids=work_item_ids,
        journal=journal,
    )
    if credentials_refusal is not None:
        _ = write_stderr(text=credentials_refusal)
        return EXIT_PRECONDITION_ERROR
    requirement = selection_credential_requirement(args=args, repo=repo, items=items)
    # A WORKFLOW FAULT is not this wall's refusal to make, so the credential gate
    # is SKIPPED rather than answered. The derivation reads the selected
    # workflow's registry entry, run config, graph and node-timeout policy, so it
    # is the first thing to NOTICE an unregistered variant, an unreadable config,
    # a missing [workflow] graph or an invalid timeout — and it used to report
    # each as a credential refusal, which answered first and silenced the stage
    # that owns the diagnostic: Scenario 89's invalid timeout exited
    # EXIT_PRECONDITION_ERROR instead of its own code, and a registry fault wrote
    # no outcome record at all because this wall returned before the stage that
    # writes one.
    #
    # Skipping cannot admit ungraded credential use, which is what makes it safe:
    # each deferred fault is a fault in configuration a dispatch must read before
    # it can launch anything, so the owning stage refuses before any Fabro run
    # exists and no credential is ever projected. A bound that genuinely cannot
    # be established for a well-formed workflow is NOT deferred — it arrives here
    # as a refusal string and still refuses, which is what keeps Scenario 19.
    if not isinstance(requirement, WorkflowFaultDeferral):
        codex_refusal = codex_credential_refusal_for_items(
            work_item_ids=work_item_ids,
            requirement=requirement,
            journal=journal,
        )
        if codex_refusal is not None:
            _ = write_stderr(text=f"{codex_refusal}\n")
            return EXIT_PRECONDITION_ERROR
    # A RESUME passes False, and the clause requires it: "It MUST NOT run the
    # stale publish-branch reclaim above: the surviving publish branch is the
    # branch the run resumes on, and no preservation ref is created." The two
    # routes are exclusive per dispatch — one KEEPS the dead run's work by
    # finishing it, the other makes a fresh start possible by clearing it — and
    # running both would preserve the head to a ref and delete the very branch
    # the resumed run was about to check out.
    #
    # It is a parameter rather than a second wall because every OTHER refusal
    # here applies to a resume unchanged, and a resume-specific copy of this
    # sequence is exactly the drift the one-wall consolidation retired.
    if reclaim_publish_branches:
        reclaim_stale_publish_branches(args=args, repo=repo, items=items, journal=journal)
    return None


def runtime_ceiling_policy_refusal(*, repo: Path) -> str | None:
    """The refusal for an invalid committed runtime ceiling, or None.

    `None` covers both a repository that adopts neither ceiling and one whose
    adoption is valid — the wall only needs to know whether to refuse, and the
    resolved values are read again at the evaluation boundaries that use them.

    An UNREADABLE `.livespec.jsonc` is reported as a refusal rather than allowed
    to escape: `resolve_adopted_cycle_ceilings` deliberately lets that raise so
    it cannot be mistaken for "no ceiling adopted", and this is the frame that
    owns turning it into a diagnostic. Both expected error types are named
    narrowly, so a genuine bug still propagates.
    """
    resolved = attempt(
        action=lambda: resolve_adopted_cycle_ceilings(cwd=repo),
        exceptions=(LivespecConfigUnreadableError, ConnectionPrefixMissingError),
    )
    if isinstance(resolved, AttemptFailure):
        return f"ERROR: cannot resolve the adopted per-cycle runtime ceilings: {resolved.error}\n"
    if isinstance(resolved, str):
        return f"ERROR: invalid committed runtime-ceiling policy: {resolved}\n"
    return None


def selection_credential_requirement(
    *,
    args: argparse.Namespace,
    repo: Path,
    items: Sequence[WorkItem],
) -> CredentialLifetimeRequirement | str | WorkflowFaultDeferral:
    """The credential requirement covering EVERY item this pass would claim.

    One host credential covers the whole wave, so the figure has to cover the
    WIDEST review-fix loop in it: the widest loop is the longest execution the
    credential may have to outlive, and sizing against a narrower item would
    admit a credential the widest one cannot finish on. The cap is the item's
    EFFECTIVE one, so a `review-fix-cap:<n>` label raises this selection's floor
    exactly as it raises what the dispatch renders.

    A ledger label read that FAILS degrades to the repository-level default,
    which is the same degradation `_dispatcher_loop_plan` makes when it renders
    the input (`.value_or(DEFAULT_REVIEW_FIX_CAP)`). That identity is the point:
    the two surfaces are wrong together or right together, and a figure derived
    here that the dispatch then contradicted would be worse than either.
    """
    return resolve_credential_lifetime_requirement(
        repo=repo,
        workflow_override=getattr(args, "workflow", None),
        workflow_name=getattr(args, "workflow_name", None),
        policy_inputs=effective_policy_inputs(
            review_fix_cap=_widest_review_fix_cap(repo=repo, items=items)
        ),
    )


def _widest_review_fix_cap(*, repo: Path, items: Sequence[WorkItem]) -> int:
    """The largest effective review-fix cap across the selection.

    An EMPTY selection takes the repository default. The credential gate returns
    before grading anything on an empty selection, so this value is never used
    there; it exists so this function is total rather than relying on a caller's
    ordering to stay correct.
    """
    caps = [_review_fix_cap(repo=repo, item=item) for item in items]
    return max(caps) if caps else DEFAULT_REVIEW_FIX_CAP


def _review_fix_cap(*, repo: Path, item: WorkItem) -> int:
    """One item's effective cap, degrading to the default on an unreadable read.

    The label read is wrapped because it resolves the ledger CONNECTION before it
    reaches the ledger, and that resolution raises on a repository whose
    `connection.prefix` is unset or whose `.livespec.jsonc` is unreadable —
    errors `read_dispatch_labels` does not route as data because its own
    `exceptions` tuple covers only the beads calls past that point. Unwrapped,
    those escaped the credential derivation as a traceback from inside the
    pre-dispatch wall, which is a BUG-class escape on the path whose whole
    purpose is rendering actionable refusals.
    """
    labels = attempt(
        action=lambda: read_dispatch_labels(repo=repo, item=item),
        exceptions=(ConnectionPrefixMissingError, LivespecConfigUnreadableError),
    )
    resolved = () if isinstance(labels, AttemptFailure | str) else labels
    return unsafe_perform_io(
        effective_review_fix_cap(
            item=item,
            cwd=repo,
            raw_labels=resolved,
        ).value_or(DEFAULT_REVIEW_FIX_CAP)
    )
