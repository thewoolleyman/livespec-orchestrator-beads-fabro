"""Resolving one dispatch's credential requirement from the workflow it will run.

THE IMPURE HALF of `_dispatcher_credential_deadline`, split from it for the
usual reason: the arithmetic relating an allowance, a margin and an absolute
deadline is a pure function of three numbers and is reachable from a test with
no filesystem, while FINDING those numbers means resolving which workflow this
dispatch selected, reading its committed run config and its graph, and reading
the dispatch target's own node-timeout policy.

WHAT THIS FIGURE IS, STATED PRECISELY, BECAUSE AN EARLIER DRAFT OVERSTATED IT.
It is an ALLOWANCE: a sum over per-operation bounds the engine enforces -- visit
caps, retry budgets, retry presets, edge conditions, configured node timeouts --
plus the per-attempt costs that sit outside a node timeout. It is NOT the graph's
maximum wall clock and must not be described as one. Two measured mechanisms
already falsify that reading: `fabro-core`'s executor takes a `retry_target` jump
no DOT edge expresses, and inter-stage work (checkpoints, artifact-context
resolution, edge selection) runs outside every deadline a derivation multiplies.
What turns this allowance into a real maximum CREDENTIAL-USE duration is the
worker enforcement paired with it -- the absolute deadline the in-sandbox launch
guard measures itself against -- and nothing else.

WHAT GOES INTO THE ALLOWANCE. `_dispatcher_execution_budget` composes the
enforced per-operation bounds and takes the per-attempt costs that sit OUTSIDE a
node timeout as a caller-supplied input. This module is that caller, and it
composes the input from engine behaviour measured on the pinned revision rather
than from a round number:

- The CHECKPOINT. `fabro-sandbox/src/sandbox_git.rs` spends `commit_timeout_ms`
  independently on `git add`, on `git diff --cached` and on `git commit`, then
  another ten seconds resolving the head SHA. So the ceiling is three times the
  configured budget plus ten, not the budget itself -- which is why that value is
  READ from the run config rather than assumed: a repository that raises
  `commit_timeout` to survive its own hooks raises this cost threefold, and a
  hand-written constant here would silently under-count exactly the repositories
  that needed it most.
- The CHANGED-FILE SCANS. `acp.rs` runs one on each side of `run_acp_turn`
  (thirty seconds apiece in `changed_files.rs`) plus an optional five-second
  last-file lookup.
- The TURN-ENTRY MINT, thirty seconds, bounded separately from the node timeout.
- The RETRY BACKOFF, whose capped sixty-second delay is multiplied by the
  `[0.5, 1.5)` jitter in `fabro-util/src/backoff.rs`, so ninety is its ceiling.

These are billed per ATTEMPT, which over-counts the checkpoint -- checkpoints
happen between stages, so a node's retries inside one visit share one. That
direction is correct for a credential floor and wrong for a forecast; do not
reuse this figure as one.

WHY THE EFFECTIVE POLICY INPUTS ARE AN INPUT AND NOT A FILE READ. The shipped
graph writes its review loop's guard as `{{ inputs.review_fix_visit_cap }}`, and
the Dispatcher renders that input from the item's EFFECTIVE review-fix cap --
which a repository key or a per-item label may raise above the committed default.
A derivation reading the committed default alone would therefore describe a
smaller loop than the dispatch actually renders, and would do it silently,
because both readings produce a perfectly well-formed finite figure. So the
effective inputs are passed IN, by the surface that resolved them, and they
override the committed defaults. `review_fix_visit_cap_for` is the single
spelling of the cap-to-guard conversion, shared with the plan builder that
renders it, so the two cannot drift by one.

WHY AN UNRESOLVABLE BOUND REFUSES, AND WHAT IT MUST NOT DO INSTEAD. Every arm
that cannot establish a finite bound returns a refusal STRING naming what
defeated it. The one forbidden move is to fall back to another graph's
allowance: a dispatch that selected a variant the registry does not define has
an UNKNOWN allowance, and presenting the reserved graph's figure in its place
would report one graph's allowance as another graph's bound. The reserved
workflow is resolved only when the reserved workflow is what was selected.
"""

from __future__ import annotations

import argparse
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from returns.unsafe import unsafe_perform_io

from livespec_orchestrator_beads_fabro.commands._config import dispatcher_block
from livespec_orchestrator_beads_fabro.commands._dispatcher_credential_allowance import (
    commit_timeout_seconds,
    per_attempt_overhead_seconds,
    requirement_detail,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_credential_deadline import (
    CredentialLifetimeRequirement,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_execution_budget import execution_budget
from livespec_orchestrator_beads_fabro.commands._dispatcher_integration_projection import (
    workflow_declared_inputs,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_overlay import (
    workflow_graph_path,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_paths import workflow_toml
from livespec_orchestrator_beads_fabro.commands._dispatcher_policy_overrides import (
    review_fix_visit_cap_for,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_policy_settings import (
    DEFAULT_REVIEW_FIX_CAP,
    resolve_review_fix_cap,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_projection import (
    CODEX_FRESHNESS_MARGIN_SECONDS,
)
from livespec_orchestrator_beads_fabro.commands._node_timeouts import node_timeouts_from_block
from livespec_orchestrator_beads_fabro.commands._workflow_variants import (
    RESERVED_WORKFLOW_NAME,
    workflow_variant_from_block,
)
from livespec_orchestrator_beads_fabro.effects import AttemptFailure, attempt

__all__: list[str] = [
    "REVIEW_FIX_VISIT_CAP_INPUT",
    "WorkflowFaultDeferral",
    "credential_lifetime_requirement_for",
    "effective_policy_inputs",
    "operator_credential_requirement",
    "requirement_refusal_text",
    "resolve_credential_lifetime_requirement",
]


@dataclass(frozen=True, kw_only=True)
class WorkflowFaultDeferral:
    """A requirement unresolvable because the WORKFLOW ITSELF is faulty.

    Returned INSTEAD of a refusal string when the reason no allowance could be
    derived is that the selected workflow is unregistered, unreadable, declares
    no graph, or carries an invalid node timeout -- faults that a LATER, more
    specific dispatch stage already owns and already reports with its own
    diagnostic and its own exit code.

    WHY THIS IS A SEPARATE TYPE rather than a string the caller inspects. The
    credential wall runs EARLY, so when it treated these faults as its own
    refusal it answered FIRST and the owning stage never spoke: Scenario 89's
    invalid node timeout reported a credential refusal at
    `EXIT_PRECONDITION_ERROR` instead of a timeout refusal at the dispatch exit
    code, and a registry fault wrote no outcome record at all because the wall
    returned before the stage that writes one. The fault was never a credential
    fault; the credential derivation merely NOTICED it first. Discriminating by
    substring over the refusal prose would make the classification a property of
    wording that any later edit silently breaks, which is the same defect class
    as deriving a bound from a graph comment -- so the class is decided AT THE
    SITE THAT KNOWS IT and carried in the type.

    DEFERRING HERE CANNOT ADMIT UNGRADED CREDENTIAL USE, which is the property
    that makes it safe rather than merely quieter. Every fault routed this way is
    a fault in the workflow configuration a dispatch must read before it can
    launch anything, so the owning stage refuses BEFORE any Fabro run exists and
    no credential is ever projected into a sandbox -- which is exactly what the
    two scenario tests guarding this assert by name ("refuses before any run
    exists"). A bound that genuinely cannot be established for a READABLE,
    well-formed workflow -- an unbounded cycle, an unknown `retry_policy`, an
    unparseable checkpoint declaration -- is NOT routed here: it stays a refusal
    string and still refuses at the gate, which is what preserves Scenario 19.
    """

    message: str


# The ONE policy input the shipped graph's own edge guards read. Named rather
# than spelled at each call site because three surfaces compose it -- the
# pre-claim gate, the overlay projection and the operator status command -- and
# a typo in any of them would leave that edge UNGUARDED, which `execution_budget`
# treats as the conservative direction and therefore reports as a plausible
# larger figure rather than as a fault.
REVIEW_FIX_VISIT_CAP_INPUT = "review_fix_visit_cap"


def requirement_refusal_text(*, outcome: str | WorkflowFaultDeferral) -> str:
    """The operator-facing text of a resolution that yielded no requirement.

    The two no-requirement members read IDENTICALLY to a surface that has no
    later stage owning the fault -- the operator status and manual-renewal
    commands, and the post-claim projection, each of which runs with nothing
    behind it that could report a workflow fault more specifically. Those
    surfaces call this and refuse.

    Only `_dispatcher_pre_dispatch_wall` distinguishes the two members, because
    only the wall has owning stages behind it to defer to. That asymmetry is the
    whole reason the distinction is a TYPE rather than a flag every caller has to
    remember to read: a surface that should refuse on both cannot accidentally
    admit by forgetting one, and the one surface that must defer says so
    explicitly.
    """
    return outcome if isinstance(outcome, str) else outcome.message


def effective_policy_inputs(*, review_fix_cap: int) -> dict[str, int]:
    """The policy inputs a dispatch RENDERS, as the derivation must read them.

    Built from the EFFECTIVE cap -- the repository's `dispatcher.review_fix_cap`
    as a per-item `review-fix-cap:<n>` label may raise it -- rather than from the
    committed workflow default, because the default is not what the dispatch
    sends. A derivation reading the default alone describes a smaller review loop
    than the run actually gets, and reports that smaller figure as the bound.
    """
    return {REVIEW_FIX_VISIT_CAP_INPUT: review_fix_visit_cap_for(review_fix_cap=review_fix_cap)}


def operator_credential_requirement(
    *,
    repo: Path,
    workflow_override: str | None = None,
    workflow_name: str | None = None,
    review_fix_cap: int | None = None,
) -> CredentialLifetimeRequirement | str | WorkflowFaultDeferral:
    """The requirement the OPERATOR surfaces grade against, or a refusal.

    `codex-cred-status` and `codex-cred-refresh` hold no work item, so by DEFAULT
    the selection they resolve is the one an ordinary dispatch makes: the reserved
    workflow, and the REPOSITORY-level `dispatcher.review_fix_cap` -- the same
    value `effective_review_fix_cap` returns for an item carrying no
    `review-fix-cap:` label, which is every ordinary item.

    WHY THE SELECTION IS OVERRIDABLE. Those defaults are the common case, not the
    only case, and an operator runs these commands to answer "will the next
    dispatch be admitted?". A dispatch can select a registered VARIANT whose
    graph is longer, and a per-item `review-fix-cap:<n>` label can raise the loop
    bound the dispatch renders; in either case a reading taken for the default
    selection answers confidently about a DIFFERENT dispatch than the one being
    predicted. `workflow_name` and `review_fix_cap` name the selection, and the
    requirement is resolved FOR it -- which is what makes the operator figure and
    the dispatch figure the same figure, rather than two readings that agree only
    while nothing was overridden.

    `workflow_override` is the same raw-path escape hatch `dispatch --workflow
    <path>` offers, and it carries the SAME precedence `workflow_toml`
    documents: an explicit path outranks a named variant, and supplying both
    refuses nothing. Without it a selection the dispatch surface accepts could
    not be asked of these commands at all -- and, worse, argparse's prefix
    abbreviation read `--workflow <path>` as `--workflow-name <path>` and
    refused the path as an unregistered variant.

    Explicit context does NOT make this surface permissive: an unregistered
    `workflow_name` still refuses to be sized off the reserved graph, exactly as
    the dispatch path refuses. And `detail` names the inputs the figure used, so
    an operator comparing this reading against a dispatch refusal can see which
    cap each one took rather than having to guess.

    An unreadable `.livespec.jsonc` degrades to the documented default, which is
    what `resolve_review_fix_cap`'s own failure track means; the alternative would
    make a status command unable to report anything because a config file was
    briefly unreadable. An EXPLICIT cap skips that read entirely, because the
    caller already holds the effective value.
    """
    effective_cap = (
        review_fix_cap
        if review_fix_cap is not None
        else unsafe_perform_io(resolve_review_fix_cap(cwd=repo).value_or(DEFAULT_REVIEW_FIX_CAP))
    )
    return resolve_credential_lifetime_requirement(
        repo=repo,
        workflow_override=workflow_override,
        workflow_name=workflow_name,
        policy_inputs=effective_policy_inputs(review_fix_cap=effective_cap),
    )


def resolve_credential_lifetime_requirement(
    *,
    repo: Path,
    workflow_override: str | None = None,
    workflow_name: str | None = None,
    policy_inputs: Mapping[str, int] | None = None,
) -> CredentialLifetimeRequirement | str | WorkflowFaultDeferral:
    """Resolve the requirement for the workflow THIS dispatch selected, or refuse.

    `workflow_override` is an explicit `--workflow <path>` and `workflow_name` an
    explicit `--workflow-name <variant>`; both are passed as plain values rather
    than as the caller's `argparse.Namespace` so the two surfaces that hold no
    Namespace -- the operator status and manual-renewal commands -- resolve the
    same requirement through the same function.

    `policy_inputs` is this dispatch's EFFECTIVE rendered policy inputs, from
    `effective_policy_inputs`. A caller that holds items passes the widest cap in
    its selection, because one credential covers the whole wave and the widest
    loop is the one it has to outlive. A caller with no item -- the operator
    status and manual-renewal surfaces -- passes the repository-level effective
    cap, and `detail` names the inputs the figure used so an operator can see
    that a per-item label would raise it rather than having to guess.

    The Namespace built below is the ONE resolver `_dispatcher_paths` owns for
    "where does this dispatch's committed workflow live", reached with the two
    attributes it reads. Re-deriving that precedence here would give the
    credential floor its own idea of which file the dispatch runs.
    """
    block = dispatcher_block(cwd=repo)
    variant = workflow_variant_from_block(block=block, name=workflow_name)
    if variant.name != RESERVED_WORKFLOW_NAME and variant.directory is None:
        return _unregistered_variant_refusal(name=variant.name)
    committed = workflow_toml(
        args=argparse.Namespace(workflow=workflow_override, repo=str(repo)),
        variant_directory=variant.directory,
    )
    return credential_lifetime_requirement_for(
        committed=committed,
        block=block,
        workflow_name=variant.name,
        policy_inputs=policy_inputs,
    )


def credential_lifetime_requirement_for(
    *,
    committed: Path,
    block: dict[str, Any],
    workflow_name: str = RESERVED_WORKFLOW_NAME,
    policy_inputs: Mapping[str, int] | None = None,
) -> CredentialLifetimeRequirement | str | WorkflowFaultDeferral:
    """The requirement for an ALREADY-RESOLVED committed workflow, or a refusal.

    The entry point for the post-claim side, which has already resolved exactly
    which workflow file and which variant this dispatch runs: re-resolving it
    from configuration there would let the projection size itself against a
    second read of the same precedence, and nothing could prove the two agreed.
    """
    # `UnicodeDecodeError` counts as unreadable alongside `OSError`, which is
    # exactly what "unreadable" has always promised here. A run config holding
    # non-UTF-8 bytes is undecodable, not a crash, and letting that error escape
    # turns this derivation into a traceback from inside the pre-dispatch wall --
    # the same defect already repaired in `read_host_codex_auth`, whose own
    # docstring records it.
    committed_text = attempt(
        action=lambda: committed.read_text(encoding="utf-8"),
        exceptions=(OSError, UnicodeDecodeError),
    )
    if isinstance(committed_text, AttemptFailure):
        return _unreadable_refusal(what=f"run config {committed}", error=committed_text.error)
    graph_path = workflow_graph_path(
        committed_text=committed_text, workflow_dir=committed.parent.resolve()
    )
    if graph_path is None:
        return WorkflowFaultDeferral(
            message=(
                f"credential lifetime requirement unresolved: the selected workflow's run "
                f"config {committed} declares no [workflow] graph, so there is no graph "
                f"whose credential-use allowance could be derived. A credential floor is "
                f"NOT sized against another workflow in its place."
            )
        )
    graph_text = attempt(
        action=lambda: graph_path.read_text(encoding="utf-8"),
        exceptions=(OSError, UnicodeDecodeError),
    )
    if isinstance(graph_text, AttemptFailure):
        return _unreadable_refusal(what=f"workflow graph {graph_path}", error=graph_text.error)
    return _requirement_from_graph(
        graph_text=graph_text,
        committed_text=committed_text,
        block=block,
        workflow_name=workflow_name,
        policy_inputs=policy_inputs,
    )


def _requirement_from_graph(
    *,
    graph_text: str,
    committed_text: str,
    block: dict[str, Any],
    workflow_name: str,
    policy_inputs: Mapping[str, int] | None,
) -> CredentialLifetimeRequirement | str | WorkflowFaultDeferral:
    """Compose the allowance from the graph, the timeouts and the checkpoint."""
    timeouts = node_timeouts_from_block(block=block)
    if isinstance(timeouts, str):
        # The node-timeout validator OWNS this diagnostic and refuses at its own
        # stage with its own exit code (Scenario 89); the credential derivation
        # only reads the same block and so happens to see it first.
        return WorkflowFaultDeferral(
            message=f"credential lifetime requirement unresolved: {timeouts}"
        )
    commit_timeout = commit_timeout_seconds(committed_text=committed_text)
    if isinstance(commit_timeout, str):
        return commit_timeout
    overhead = per_attempt_overhead_seconds(commit_timeout_seconds=commit_timeout)
    inputs = _graph_inputs(committed_text=committed_text, policy_inputs=policy_inputs)
    budget = execution_budget(
        graph_text=graph_text,
        timeouts=timeouts,
        per_attempt_overhead_seconds=overhead,
        graph_inputs=inputs,
    )
    if isinstance(budget, str):
        return (
            f"credential lifetime requirement unresolved for workflow "
            f"{workflow_name!r}: {budget}. No stand-in allowance is used in its "
            f"place, because a figure this derivation could not establish is not a "
            f"bound however plausible it looks."
        )
    return CredentialLifetimeRequirement(
        allowance_seconds=budget.seconds,
        margin_seconds=CODEX_FRESHNESS_MARGIN_SECONDS,
        detail=requirement_detail(
            workflow_name=workflow_name,
            allowance_seconds=budget.seconds,
            overhead_seconds=overhead,
            inputs=inputs,
        ),
    )


def _graph_inputs(
    *, committed_text: str, policy_inputs: Mapping[str, int] | None
) -> dict[str, int]:
    """The integer graph inputs this dispatch RENDERS, for its templated guards.

    The committed `[run.inputs]` defaults are the base, and the caller's
    EFFECTIVE policy inputs override them -- that direction, because the
    Dispatcher's rendered value is what the run receives and the committed
    default is only what a bare `fabro run` would see. Reading the default where
    the dispatch renders something wider would describe a smaller loop than the
    run gets, silently and with a well-formed figure.

    An input neither source names leaves its edge UNGUARDED, which
    `execution_budget` treats as the conservative direction.
    """
    declared = {
        name: int(value.strip())
        for name, value in workflow_declared_inputs(committed_text=committed_text).items()
        if value.strip().isdigit()
    }
    return declared if policy_inputs is None else {**declared, **policy_inputs}


def _unregistered_variant_refusal(*, name: str) -> WorkflowFaultDeferral:
    """A variant the registry does not define: the registry stage's fault, deferred.

    Deferred for the same reason the other four are, and measured the same way:
    `workflow-variant-unregistered` is a real journal stage that names the variant
    and writes an outcome record, and this derivation resolves the registry only
    because it has to know WHICH graph to size. Treating the miss as a credential
    refusal answered first and left that stage silent, which is how a registry
    fault came to write no outcome record at all.

    The message is unchanged, so the operator reads the same sentence either way;
    what changes is which surface is allowed to be the one that refuses.
    """
    return WorkflowFaultDeferral(
        message=(
            f"credential lifetime requirement unresolved: this dispatch selected workflow "
            f"variant {name!r}, which the dispatch target's dispatcher.workflows registry "
            f"does not define, so the maximum duration that graph can spend using a "
            f"credential is unknown. The reserved implement-work-item graph's allowance is "
            f"NOT used in its place: that would present one graph's allowance as another "
            f"graph's maximum. Register the variant's directory under "
            f"dispatcher.workflows, or dispatch the reserved workflow."
        )
    )


def _unreadable_refusal(*, what: str, error: Exception) -> WorkflowFaultDeferral:
    return WorkflowFaultDeferral(
        message=(
            f"credential lifetime requirement unresolved: the selected workflow's {what} "
            f"is unreadable ({error}), so the maximum duration a worker can spend using a "
            f"credential could not be derived at all."
        )
    )
