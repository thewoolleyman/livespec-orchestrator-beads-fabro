"""Render the complete input projection passed to one Fabro run."""

from __future__ import annotations

from livespec_orchestrator_beads_fabro.commands._dispatcher_credential_use_guard import (
    guarded_adapter_string,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_plan import DispatchPlan

__all__: list[str] = ["dispatch_fabro_run_inputs"]


def _guarded_adapter_input(*, pair: str) -> str:
    """Re-render one `<input>=<adapter>` pair with its launch behind the guard."""
    name, _, rendered = pair.partition("=")
    return f"{name}={guarded_adapter_string(rendered=rendered)}"


def dispatch_fabro_run_inputs(*, plan: DispatchPlan) -> tuple[str, ...]:
    """Render the `--input` pairs for one dispatch's `fabro run`.

    Every ACP node's adapter comes from `plan.acp_nodes`, already resolved
    through the workflow / repository / per-dispatch layers and already
    journaled — this function only renders what resolved, so the record and
    the run cannot disagree. NO adapter string, model or provider appears
    here as a literal: which provider a node runs is configuration, per
    `SPECIFICATION/contracts.md`.

    A plan carrying NO resolution passes no adapter input at all, leaving
    the workflow's own declared defaults standing — layer 1 applied by
    fabro rather than by us, not a fallback provider choice.

    `plan.integration_inputs` carries the same discipline for the repository
    integration contract: the sandbox-facing fields are PROJECTIONS of the one
    contract the plan resolved and the dispatch record journaled, already
    intersected with the input names the dispatched workflow declares. They are
    rendered here rather than resolved here for exactly the reason the adapters
    are — the record and the run must not be able to disagree.

    The three PER-ITEM POLICY inputs at the end are rendered on EVERY dispatch
    rather than intersected with what the payload declares, because they are
    projections of the item's own effective policy rather than of the
    repository's contract: an item is dispatched with a review-fix cap, a
    merge-on-review-cap outcome and a merge hold whatever else is true of it.
    `merge_hold` spells its boolean the way the run config declares it, so the
    value the workflow's own default carries and the value a dispatch renders
    are the same word.
    """
    # EVERY adapter launch is wrapped here, which is what makes the absolute
    # credential-use deadline bind the thing that actually execs a coding agent.
    # This is the one chokepoint that reaches all of them: the graphs declare
    # `acp.command="{{ inputs.<node>_adapter }}"`, so the built-in catalog
    # adapters, a repository's `dispatcher.acp_nodes` overlay and a per-dispatch
    # `--acp-node` override all arrive as these pairs. Wrapping per adapter
    # IDENTITY would leave whichever route nobody remembered unguarded.
    #
    # Unconditional, because a launch cannot be reached without the guard being
    # installed: `dispatch_one` materializes the overlay first, that step reads the
    # host Codex credential UNCONDITIONALLY and refuses the dispatch when it
    # cannot, and a credential projected without enforcement renders no overlay at
    # all. An installed guard is therefore an invariant of reaching this line — and
    # if that ever stops being true the launch fails loudly on a missing script
    # rather than quietly running unguarded.
    adapters = (
        ()
        if plan.acp_nodes is None
        else tuple(_guarded_adapter_input(pair=pair) for pair in plan.acp_nodes.run_inputs)
    )
    return (
        *adapters,
        *plan.integration_inputs,
        f"review_fix_visit_cap={plan.review_fix_visit_cap}",
        f"merge_on_review_cap_outcome={plan.merge_on_review_cap_outcome}",
        f"merge_hold={'true' if plan.merge_hold else 'false'}",
    )
