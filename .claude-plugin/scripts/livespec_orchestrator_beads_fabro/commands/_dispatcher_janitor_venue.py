"""WHERE the post-merge and reconcile janitor provisions its fresh checkout.

Split out of `_dispatcher_engine_janitor` along the seam between DRIVING the
post-merge flow -- the lock, the primary refresh, the janitor run, the cleanup,
all of which stay there -- and PROVISIONING the venue that flow runs in: which
ref the fresh checkout is made at, and the stages that create it.

THE VENUE IS THE MERGED DEFAULT-BRANCH TIP, NEVER THE ITEM'S HISTORICAL MERGE
SHA. Pinning the venue to the merge sha makes a janitor-environment fix that
lands AFTER an item's merge unable to EVER clear that item: every reconcile
re-provisions a checkout from before the fix existed and fails identically, a
deterministic deadlock whose only in-band exit is a one-off `--janitor`
override. Measured on the `homelab` adopter 2026-08-29: `hl-cid234` merged as
`16fe3ac`, the recipe that would have let its janitor pass landed one commit
later as `918c6cf`, and two reconcile attempts -- the second AFTER pull-primary
had already fast-forwarded the primary checkout past the fix -- both
provisioned at `16fe3ac` and failed on a recipe that cannot exist at that sha.

PROVISIONING AT THE TIP KEEPS THE GUARANTEE THE SHA PIN WAS BOUGHT WITH, BUT
ONLY ONCE IT IS CONFIRMED. The tip proves the item's merge is present because
the tip CONTAINS it -- which is a property to be CHECKED, not assumed. A
resolved tip that does not contain the item's merge is a DEGRADED post-merge
outcome carrying the missing point and the remedy, never a silent proceed
against a venue that cannot prove the work landed.

The branch itself is READ OFF THE PLAN'S RESOLVED INTEGRATION CONTRACT, whose
`default_branch` field carries what the ratified two-route resolution answered
at plan build. So an adopter whose primary branch is `main` gets its own tip
rather than the `master` literal this fleet happens to use, and the venue cannot
name a different branch than the dispatch record journaled -- which a second
probe here, taken minutes later against a repository whose `origin/HEAD` may
have been re-pointed in between, could. A branch nobody could name is not a
venue either: when both resolution routes were silent the field resolves to its
sentinel and the venue degrades rather than guessing at a ref.

THE BOOTSTRAP SEAM HAS TWO LEGS, BECAUSE A CHECKOUT HAS TWO KINDS OF STATE.
The hook-install recipe installs into the SHARED `.git/hooks`, so it is run from
the primary and reaches every worktree at once -- correct, and the whole of what
the shipped step did. Nothing then provisioned the fresh checkout's OWN
per-worktree state, which the venue's check suite reads: the worktree-discipline
pack is gitignored, so a newly added worktree carries none of it by
construction, the suite fails `worktree_pack_absent` on a fully conformant
repository, and an already-merged GREEN item strands in `active` until an
operator hand-installs the pack. The second leg therefore runs a checkout-scoped
provisioning recipe with `cwd` set to the janitor checkout. The fleet default
check-suite hides this by installing the pack inside the suite itself, which is
why the gap only ever surfaced on a repository that DECLARED a check-suite of
its own -- so the provisioning belongs at the venue, where it is true of every
check-suite, rather than inside anybody's check command.

BOTH LEGS JOURNAL BOTH STREAMS. A bootstrap that fails loudly is already
visible; one that FAILS OPEN -- exits 0 having provisioned nothing, with its
diagnosis on the stream the exit code did not select -- journals a record
indistinguishable from a step that worked, and the only later evidence is the
check-suite failure it was meant to prevent.

AND THE TRUST STEP IS A PREMISE OF THE VENUE'S COMMANDS, NOT A STEP EVERY
REPOSITORY OWES. Provisioning used to run this fleet's per-path trust command in
every fresh checkout, on the reasoning that it warns and exits 0 where there is
no config to trust. That reasoning assumed the tool was INSTALLED, which is true
of a fleet member and of nothing else -- on a host carrying none of this fleet's
tooling the step simply fails, and degrades a post-merge outcome for a premise
that repository never declared. It now rides the resolution ARM of the
host-janitor points, so it is emitted exactly where the fleet toolchain is what
the venue is about to run.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from livespec_orchestrator_beads_fabro.commands._dispatcher_core_provisioning_view import (
    janitor_core_provisioning_defect,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine_journal import run_stage
from livespec_orchestrator_beads_fabro.commands._dispatcher_integration_defaults import (
    UNRESOLVED_NAME,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_integration_resolver import (
    FleetDefault,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_integration_schema import (
    JANITOR_BOOTSTRAP_RECIPE_FIELD,
    JANITOR_CHECK_SUITE_FIELD,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_janitor_degraded import (
    DegradedStep,
    degraded_step,
    merged_degraded_for_plan,
    tip_without_merge_step,
    unresolved_branch_step,
    unresolved_core_step,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_plan import (
    janitor_bootstrap_argv,
    janitor_checkout_provision_argv,
    janitor_core_clone_argv,
    janitor_trust_argv,
    janitor_venue_contains_merge_argv,
    janitor_worktree_add_argv,
    janitor_worktree_remove_argv,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_step_ids import JANITOR_BOOTSTRAP

if TYPE_CHECKING:
    from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import (
        CommandRunner,
        DispatchOutcome,
        JournalWriter,
    )
    from livespec_orchestrator_beads_fabro.commands._dispatcher_hook_install_recipe import (
        JanitorBootstrapRecipe,
    )
    from livespec_orchestrator_beads_fabro.commands._dispatcher_plan import DispatchPlan, PrView

__all__: list[str] = [
    "UNRESOLVED_VENUE",
    "JanitorVenue",
    "fleet_toolchain_is_the_host_janitor_premise",
    "provision_janitor_checkout",
    "resolve_janitor_venue",
]

_GIT_TIMEOUT_SECONDS = 600.0
_VENUE_TIMEOUT_SECONDS = 30.0

# What a venue that could not be resolved renders as. A sentinel rather than a
# branch literal, for the reason the whole module exists: the wrong answer here
# is a ref we guessed at, and prose naming `origin/master` would tell an adopter
# on `main` that we looked for a branch they do not have.
UNRESOLVED_VENUE = "<unresolved>"


@dataclass(frozen=True, kw_only=True)
class JanitorVenue:
    """The ref the janitor provisions at, or the degradation that stands in for it.

    `ref` is `UNRESOLVED_VENUE` on every arm carrying a `defect`, so a caller
    that ignores the defect provisions at a sentinel that cannot resolve rather
    than at a plausible-looking ref -- except on the tip-lacks-the-merge arm,
    which carries the resolved tip precisely because naming it is what makes the
    degradation actionable.
    """

    ref: str
    defect: DegradedStep | None = None


def resolve_janitor_venue(
    *, plan: DispatchPlan, runner: CommandRunner, merge_sha: str | None
) -> JanitorVenue:
    """The default-branch tip containing `merge_sha`, or the degradation replacing it.

    A `merge_sha` of None is not a degradation: the caller has no merge to
    confirm, so the tip is the venue with nothing left to prove about it.

    The branch is READ OFF THE PLAN'S RESOLVED CONTRACT rather than probed here.
    The repository's own git/forge state is what declares it, that declaration
    is one of the contract's REQUIRED fields, and the ratified
    resolve-once-project-everywhere rule puts the single probe at plan build --
    so a venue resolved for the janitor and a default branch journaled with the
    dispatch record cannot name two different branches. An unresolvable branch
    arrives as the name sentinel, which is the same REQUIRED-field refusal every
    other unresolvable point earns, never a `master` literal guessed at.
    """
    branch = plan.integration.contract.default_branch
    if branch == UNRESOLVED_NAME:
        return JanitorVenue(ref=UNRESOLVED_VENUE, defect=unresolved_branch_step(plan=plan))
    tip = f"origin/{branch}"
    if merge_sha is None:
        return JanitorVenue(ref=tip)
    contains = runner.run(
        argv=janitor_venue_contains_merge_argv(plan=plan, tip=tip, merge_sha=merge_sha),
        cwd=plan.repo,
        timeout_seconds=_VENUE_TIMEOUT_SECONDS,
    )
    if contains.exit_code != 0:
        return JanitorVenue(ref=tip, defect=tip_without_merge_step(tip=tip, merge_sha=merge_sha))
    return JanitorVenue(ref=tip)


def fleet_toolchain_is_the_host_janitor_premise(*, plan: DispatchPlan) -> bool:
    """Whether the host-janitor venue's own steps rest on THIS fleet's toolchain.

    The venue provisions a fresh checkout and then runs two commands in it: the
    hook-install recipe and the check-suite. Where either resolved to the
    `FleetDefault` arm the repository declared nothing there and inherited this
    fleet's own invocation, so the fleet toolchain IS the premise of the venue
    and its per-path trust step is part of provisioning it. Where BOTH resolved
    `Declared`, the venue runs the repository's own commands and this fleet's
    tooling is not a premise of anything about it -- so imposing a trust step
    would run a tool the repository never carried, and on a host without it
    would degrade the post-merge outcome for a premise nobody asked for.

    The ARM is what is read, never the VALUE: a repository is free to declare
    exactly the fleet convention, and a value comparison would then read a
    deliberate declaration as an inheritance. Both arms come off the plan's ONE
    resolved contract, so this cannot disagree with the resolution the dispatch
    record journaled.
    """
    return any(
        isinstance(plan.integration.resolutions[field.attribute], FleetDefault)
        for field in (JANITOR_CHECK_SUITE_FIELD, JANITOR_BOOTSTRAP_RECIPE_FIELD)
    )


def provision_janitor_checkout(
    *,
    outcome_type: type[DispatchOutcome],
    plan: DispatchPlan,
    runner: CommandRunner,
    journal: JournalWriter,
    merged: PrView,
    recipe: JanitorBootstrapRecipe,
) -> DispatchOutcome | None:
    if recipe.defect is not None:
        # A present-but-unusable declaration resolves NO command, so the
        # bootstrap stage would hand the runner an empty argv -- a crash, after
        # the merge has already landed, where the design has a named degraded
        # outcome. The pre-dispatch re-verification refuses on the same defect,
        # but only once a degradation stands: on a FIRST dispatch this is the
        # one place the defect is caught, so it is caught before anything is
        # provisioned for a bootstrap that cannot run.
        return merged_degraded_for_plan(
            outcome_type=outcome_type,
            plan=plan,
            merged=merged,
            step=DegradedStep(
                description=(
                    f"resolving the commit-refuse-hook install recipe to bootstrap in {plan.repo}"
                ),
                reason=recipe.defect,
                step_id=JANITOR_BOOTSTRAP,
            ),
            recipe=recipe,
        )
    core_defect = janitor_core_provisioning_defect(
        ref=plan.janitor_core_ref, repo_url=plan.janitor_core_repo_url
    )
    if core_defect is not None:
        # Caught on the same principle as the recipe defect above, and one step
        # earlier than the clone would fail: an unresolved ref reaches `git
        # clone --branch` as a sentinel, whose stderr would name a branch the
        # repository never declared instead of the declaration it is missing.
        return merged_degraded_for_plan(
            outcome_type=outcome_type,
            plan=plan,
            merged=merged,
            step=unresolved_core_step(plan=plan, defect=core_defect),
            recipe=recipe,
        )
    # Resolved BEFORE the preclean, on the same principle as the recipe defect
    # above: a venue that cannot be named, or that cannot be shown to carry the
    # item's merge, degrades with nothing provisioned for it.
    venue = resolve_janitor_venue(plan=plan, runner=runner, merge_sha=merged.merge_sha)
    if venue.defect is not None:
        return merged_degraded_for_plan(
            outcome_type=outcome_type,
            plan=plan,
            merged=merged,
            step=venue.defect,
            recipe=recipe,
        )
    _ = run_stage(
        runner=runner,
        journal=journal,
        plan=plan,
        stage="janitor-checkout-preclean",
        command=(janitor_worktree_remove_argv(plan=plan), plan.repo, _GIT_TIMEOUT_SECONDS, None),
    )
    core_step = (
        f"provisioning livespec core at {plan.janitor_core_checkout} (ref {plan.janitor_core_ref})"
    )
    trust_step = (
        f"trusting the fleet toolchain config in the janitor checkout {plan.janitor_checkout}"
    )
    checkout_bootstrap_step = (
        f"provisioning the janitor checkout {plan.janitor_checkout} itself, so the "
        "per-worktree dev-tooling pack its check suite reads is installed there"
    )
    # The trust step and the per-checkout bootstrap leg are both PREMISES of the
    # fleet-default host-janitor commands, so they ride the same resolution those
    # commands do rather than running on every governed repository. An adopter
    # whose venue runs its own commands end to end carries neither step: the pack
    # is this fleet's dev-tooling artifact, and installing it would mean running a
    # tool that repository never carried.
    fleet_premise = fleet_toolchain_is_the_host_janitor_premise(plan=plan)
    trust = (
        (("janitor-checkout-trust", janitor_trust_argv(), plan.janitor_checkout, trust_step, None),)
        if fleet_premise
        else ()
    )
    checkout_bootstrap = (
        (
            (
                "janitor-checkout-bootstrap-in-checkout",
                janitor_checkout_provision_argv(),
                plan.janitor_checkout,
                checkout_bootstrap_step,
                None,
            ),
        )
        if fleet_premise
        else ()
    )
    steps = (
        (
            "janitor-checkout-add",
            janitor_worktree_add_argv(plan=plan, tip=venue.ref),
            plan.repo,
            (
                f"provisioning the fresh janitor checkout at {plan.janitor_checkout} "
                f"(merged default-branch tip {venue.ref})"
            ),
            None,
        ),
        *trust,
        (
            "janitor-checkout-bootstrap",
            janitor_bootstrap_argv(recipe=recipe),
            plan.repo,
            f"installing commit-refuse hooks via `{recipe.text}` in {plan.repo}",
            JANITOR_BOOTSTRAP,
        ),
        *checkout_bootstrap,
        (
            "janitor-core-provision",
            janitor_core_clone_argv(plan=plan),
            plan.janitor_checkout,
            core_step,
            None,
        ),
    )
    for stage, argv, cwd, step, step_id in steps:
        result = run_stage(
            runner=runner,
            journal=journal,
            plan=plan,
            stage=stage,
            command=(argv, cwd, _GIT_TIMEOUT_SECONDS, None),
            streams=True,
            # The venue's own provisioning commands are covered by the
            # retention clause alongside the check suite, because a bootstrap
            # or core-provision failure is diagnosed from the same disposable
            # checkout and disappears with it. The PRECLEAN above is not: its
            # non-zero exit is the ordinary answer when there is no worktree to
            # remove, carries no verdict, and is discarded by this caller.
            retention=plan.janitor_retention,
        )
        if result.exit_code != 0:
            return merged_degraded_for_plan(
                outcome_type=outcome_type,
                plan=plan,
                merged=merged,
                step=degraded_step(description=step, result=result, step_id=step_id),
                recipe=recipe,
            )
    return None
