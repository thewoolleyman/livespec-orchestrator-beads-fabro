"""The pre-dispatch wall: every refusal that lands after selection, before claim.

The ONE wall both dispatch paths run — the single `dispatch` and the queue-
draining `loop`. It was two byte-identical private functions, one per command
module, differing only in which item sequence each handed down; the duplicate is
what made "both paths refuse" a claim about two sequences that could drift, and
what required every new refusal to be wired twice. It moved out when the Codex
credential gate became the fourth refusal in each and pushed the single-dispatch
command module past its file LLOC ceiling — the seam was already there.

WHAT THE WALL IS. A table of refusals sharing one POSITION and one guarantee: each runs
after selection and BEFORE admission, so a refused item is never claimed, no
`active` row is left behind, and no factory run exists to reap. Reading them as one
decision is also what keeps each command entry point's return count honest — the
alternative was suppressing the too-many-returns rule, which would have hidden the
fact that the entry point had grown another exit.

The DRAIN reaches it after its `--dry-run` return, deliberately: a dry run creates
no run, so it stays a reporting surface that shows the operator exactly which
candidate needs criteria.

THIS MODULE ALSO OWNS THE ONE PRE-RUN MUTATION, and it sits on the OTHER side of
admission. `post_admission_publish_branch_reclaim` is the publish-branch reclaim,
which each LAUNCH path calls for exactly the items admission selected to launch. It
used to close this wall, and that position was the defect `bd-ib-huoyk7` repairs:
the reclaim deletes a remote ref, and the wall cannot yet know whether the
selection will get a slot. Its own docstring carries the measurement. What matters
here is that NOTHING in the wall below mutates anything, so "a refused selection
leaves the world exactly as it found it" is a property of the wall rather than of
the order its rows happen to be in.
"""

from __future__ import annotations

import argparse
import os
from collections.abc import Callable, Sequence
from pathlib import Path

from returns.unsafe import unsafe_perform_io

from livespec_orchestrator_beads_fabro.commands._dispatcher_acceptance_eligibility import (
    pre_dispatch_criteria_refusal,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_acp_publication_policy import (
    implementation_pr_override_refusal,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_app_reach_preflight import (
    app_reach_refusal,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_codex_credential_gate import (
    codex_credential_refusal_for_items,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_codex_routing import (
    codex_routing_for_dispatch,
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
from livespec_orchestrator_beads_fabro.commands._dispatcher_definition_of_done_workflow import (
    definition_of_done_workflow_refusal,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_dod_judgement_wall import (
    dod_judgement_refusal,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_fabro_currency_gate import (
    fabro_currency_refusal,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import (
    JournalFile,
    ShellCommandRunner,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_item_ledger_reads import (
    read_dispatch_labels,
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
from livespec_orchestrator_beads_fabro.commands._spec_change_tier_wall import (
    spec_change_tier_refusal,
)
from livespec_orchestrator_beads_fabro.effects import AttemptFailure, attempt
from livespec_orchestrator_beads_fabro.errors import (
    ConnectionPrefixMissingError,
    LivespecConfigUnreadableError,
)
from livespec_orchestrator_beads_fabro.io import write_stderr
from livespec_orchestrator_beads_fabro.types import WorkItem

__all__: list[str] = [
    "post_admission_publish_branch_reclaim",
    "pre_dispatch_wall_exit",
    "selection_credential_requirement",
]


def pre_dispatch_wall_exit(
    *,
    args: argparse.Namespace,
    repo: Path,
    items: Sequence[WorkItem],
    journal: JournalFile,
) -> int | None:
    """The whole wall, as ONE decision: an exit code, or None to proceed.

    `items` is the selection this pass would claim — exactly one target for the
    single dispatch, the whole admitted-candidate wave for the drain. Nothing
    below branches on which caller it is, which is the point: a refusal that
    fired for one path and not the other was a defect waiting to happen.

    The PUBLICATION-ADAPTER wall is first, and it is first because it is the one
    refusal here that spends NOTHING at all: it reads this dispatch's own
    arguments and each item's recorded variant, asks no factory and no provider,
    and an explicit implementation `pr` override cannot apply now that
    publication is scripted. A groom selection stays eligible because its `pr`
    node still publishes a filing plan through ACP.

    The APP-REACH preflight is next, and it precedes the currency gate for a
    RELEVANCE reason rather than a cost one — the two spend comparably. Its
    answer is a property of the (serving App, target repository) PAIR, so like
    the currency gate nothing about the selection has to be read before it can be
    settled; and where the currency gate asks whether the serving ENGINE is
    admissible, this asks whether that server can reach the target AT ALL. An
    engine's currency is moot on a server whose App cannot see the repository, so
    grading currency first pays a forge read and an engine read to answer a
    question about a server that cannot serve this dispatch either way.

    The FABRO CURRENCY gate is next, and its position is load-bearing rather
    than tidy. It is a refusal whose answer is a property of the FACTORY rather
    than of the items, so nothing about the selection has to be read before it
    can be settled; and the two refusals that would otherwise precede it both
    SPEND something — the proof-assets gate creates a repository prerelease, the
    Codex credential gate spends a bounded provider renewal — so refusing an
    unadmissible ENGINE after either would pay for a dispatch that could never
    run on it.

    The criteria wall follows and is variant-aware: it is handed this dispatch's
    explicit `--workflow-name`, resolves which graph the selection would run, and
    exempts a groom-kind dispatch, whose acceptance is the human approval of the
    draft.

    The Definition-of-Done JUDGEMENT follows it, which is the SEMANTIC half of
    the same gate: the criteria wall above parses the section, and this asks
    whether what it says is gradeable at all. It shares that wall's exit code,
    because the clause ratifies one code for both. Its position is between the
    two for the same cheap-first reason the rest of this table is ordered: it
    spends a model call, so it must run after every free parse that could
    already have refused the selection, and before the two rows that spend more
    than it does — the proof-assets gate, which CREATES a repository
    prerelease, and the Codex gate, which spends a bounded provider renewal.

    The SPEC-CHANGE-TIER row follows, and it is the last of the free reads. It
    refuses a held item with the same exit code the two criteria rows carry,
    because the exit-code enumeration ratifies one code for all three. Its
    position is cheap-first like the rest of this table and ALSO fail-closed by
    construction: it spends no model call and reaches no provider — the clause
    makes the hold "a read of the spec history [that] needs no model" — so it
    cannot be weakened by an outage, and putting it ahead of the two rows that
    spend more than it does keeps a dispatch that can never run from creating a
    repository prerelease or a bounded provider renewal first.

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

    AND THAT IS THE WHOLE WALL: every row above is a refusal, and none of them
    mutates anything. The publish-branch reclaim used to close this sequence and
    now sits past admission, in `post_admission_publish_branch_reclaim` below.
    """
    work_item_ids = [item.id for item in items]
    refusing = _refusing_sequence(
        args=args, repo=repo, items=items, journal=journal, work_item_ids=work_item_ids
    )
    for ask, exit_code, newline in refusing:
        refusal = ask()
        if refusal is not None:
            _ = write_stderr(text=f"{refusal}\n" if newline else refusal)
            return exit_code
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
            # WHICH DISPATCHES THE GATE COVERS, resolved here because the wall
            # is the surface both dispatch paths run and the routing is a
            # property of the dispatch rather than of any item in it. Handed
            # down as a THUNK so the drain's common idle pass — an empty
            # selection, which the gate returns on before anything else — pays
            # neither this resolution's reads nor the credential's.
            codex_routing=lambda: codex_routing_for_dispatch(repo=repo),
            journal=journal,
        )
        if codex_refusal is not None:
            _ = write_stderr(text=f"{codex_refusal}\n")
            return EXIT_PRECONDITION_ERROR
    return None


def post_admission_publish_branch_reclaim(
    *,
    args: argparse.Namespace,
    repo: Path,
    items: Sequence[WorkItem],
    journal: JournalFile,
) -> None:
    """The publish-branch reclaim, for the items admission SELECTED TO LAUNCH.

    It refuses NOTHING (bd-ib-yebrb7): a dead run's surviving publish branch is
    what makes a re-dispatch's `publish_draft` push non-fast-forward, and
    clearing it — once its head is preserved by reference — is what lets the
    recovery publish and reach proof capture. It is per ITEM, because a publish
    branch is per item.

    THE CALLER IS EACH LAUNCH PATH, handing this exactly what it is about to
    launch: `_dispatcher_loop_wave` hands it the wave's picked items and
    `_dispatcher_run_commands` hands it the one target it launches, each after
    the valve has written `ready -> active` and before any run exists. That
    POSITION is the point of the entry point, and it is a separate one rather
    than a flag on the wall above for the reason `bd-ib-huoyk7` records: the
    reclaim MUTATES origin, so it must not be reachable from a position that
    does not yet know whether the selection will run.

    A RESUME CALLS IT NOT AT ALL, and the clause requires that: "It MUST NOT run
    the stale publish-branch reclaim above: the surviving publish branch is the
    branch the run resumes on, and no preservation ref is created." The two
    routes are exclusive per dispatch — one KEEPS the dead run's work by
    finishing it, the other makes a fresh start possible by clearing it — and
    running both would preserve the head to a ref and delete the very branch the
    resumed run was about to check out.
    """
    reclaim_stale_publish_branches(args=args, repo=repo, items=items, journal=journal)


def _refusing_sequence(
    *,
    args: argparse.Namespace,
    repo: Path,
    items: Sequence[WorkItem],
    journal: JournalFile,
    work_item_ids: list[str],
) -> tuple[tuple[Callable[[], str | None], int, bool], ...]:
    """Every refusal this wall makes before the credential gate, IN ORDER.

    A TABLE rather than a chain of early returns, and the reason is the one this
    module's docstring already gives: reading the wall as ONE decision is what
    keeps each command entry point's return count honest, and a sixth refusal
    chained inline pushed `pre_dispatch_wall_exit` past the too-many-returns
    rule. Suppressing that rule was the alternative, and it is exactly what the
    docstring rejects — it would hide the fact that the wall had grown another
    exit. As a table the ORDER is data a reader can see at a glance, and adding a
    refusal is adding a row rather than another branch.

    EVERY ROW IS A THUNK, AND THAT IS A CORRECTNESS REQUIREMENT RATHER THAN A
    STYLE CHOICE. These refusals are not all pure: the proof-assets gate CREATES
    this repository's standing prerelease, and the Fabro currency gate spends a
    forge read and an engine read. Evaluating the table eagerly would perform
    both for a selection an EARLIER row has already refused — minting a release
    for a dispatch that never runs, and paying a round trip to answer a question
    nobody asked. Deferring each row preserves the whole point of the ordering,
    which is that the cheapest refusal able to decide the selection decides it
    and nothing further is spent.

    The third element says whether the refusal's own text ends in a newline. Two
    of these surfaces return one and the rest do not, and normalizing that here
    would change the bytes an operator reads from one group or the other.
    """
    return (
        (
            lambda: implementation_pr_override_refusal(
                args=args, repo=repo, items=items, journal=journal
            ),
            EXIT_PRECONDITION_ERROR,
            True,
        ),
        (
            lambda: app_reach_refusal(repo=repo, items=items, journal=journal),
            EXIT_PRECONDITION_ERROR,
            False,
        ),
        (
            lambda: fabro_currency_refusal(args=args, repo=repo, items=items, journal=journal),
            EXIT_PRECONDITION_ERROR,
            False,
        ),
        (
            lambda: pre_dispatch_criteria_refusal(
                items=items, cwd=repo, workflow_name=args.workflow_name
            ),
            EXIT_UNGRADEABLE_CRITERIA,
            False,
        ),
        (
            lambda: dod_judgement_refusal(repo=repo, items=items, workflow_name=args.workflow_name),
            EXIT_UNGRADEABLE_CRITERIA,
            False,
        ),
        (
            lambda: definition_of_done_workflow_refusal(args=args, repo=repo, items=items),
            EXIT_PRECONDITION_ERROR,
            False,
        ),
        (
            lambda: spec_change_tier_refusal(repo=repo, items=items),
            EXIT_UNGRADEABLE_CRITERIA,
            False,
        ),
        (
            lambda: proof_assets_refusal_for_items(
                runner=ShellCommandRunner(), repo=repo, items=items, journal=journal
            ),
            EXIT_PRECONDITION_ERROR,
            False,
        ),
        (
            lambda: proof_credentials_refusal_for_items(
                repo=repo,
                environ=os.environ,
                wrapper_text=credential_wrapper_text(repo=repo),
                work_item_ids=work_item_ids,
                journal=journal,
            ),
            EXIT_PRECONDITION_ERROR,
            False,
        ),
    )


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
