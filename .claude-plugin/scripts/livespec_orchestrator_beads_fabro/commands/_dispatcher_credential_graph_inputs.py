"""Workflow input projection used by credential requirement sizing."""

from __future__ import annotations

from collections.abc import Mapping

from livespec_orchestrator_beads_fabro.commands._dispatcher_integration_projection import (
    workflow_declared_inputs,
)

__all__: list[str] = ["effective_graph_inputs"]


def effective_graph_inputs(
    *, committed_text: str, policy_inputs: Mapping[str, int] | None
) -> dict[str, int]:
    """Read defaults and apply the policy values the Dispatcher renders.

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
