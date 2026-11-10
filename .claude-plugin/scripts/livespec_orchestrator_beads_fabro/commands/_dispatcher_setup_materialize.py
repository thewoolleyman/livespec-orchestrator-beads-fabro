"""Moving a rendered overlay's prepare steps into the per-dispatch graph.

`_dispatcher_setup_nodes` knows how to turn steps into nodes; this module is the
one place that does it to a REAL dispatch's artifacts, because the two halves have
to change together or not at all. The overlay is rendered whole -- committed steps
first, then every block the Dispatcher materializes, in the order they always ran
-- and then split: the steps leave the written run config (upstream Fabro refuses
`run.prepare`) and arrive in the dispatch's own copy of the graph.

WHY IT IS DONE ON THE RENDERED TEXT AND NOT BY CHANGING THE TWENTY-ONE EMITTERS.
Each emitter owns a rationale for one step's content and position, and none of them
cares which carrier the step travels in. Re-expressing every emitter as a node
would have moved the order, the escaping and the payload split into twenty-one
places that could drift apart; splitting once, at the end, keeps them as they were.

A GRAPH WITH NO `start` NODE IS LEFT ALONE, steps and all. Such a graph is not a
workflow graph: every engine rejects it at run-create time, before any run exists,
so there is no run whose setup could silently not happen, and splicing nodes into
text that cannot run would only add a second thing to explain when it is rejected.
A graph that DOES declare `start` and gives the chain nothing to hang on is another
matter -- the engine accepts a graph shaped like that only by accident -- and refuses.

EVERY REFUSAL HERE PRECEDES THE LAUNCH. A step that cannot be lifted out of the
overlay, a graph that cannot take the chain, or a graph that cannot be written
would otherwise start a run whose setup silently did not happen -- the one failure
that looks exactly like success until the first stage that needs the sandbox.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_dot_graph import parse_dot_graph
from livespec_orchestrator_beads_fabro.commands._dispatcher_prepare_payload import PrepareStep
from livespec_orchestrator_beads_fabro.commands._dispatcher_setup_nodes import (
    SETUP_NODE_PREFIX,
    append_env_lines,
    hoist_step_env,
    splice_setup_nodes,
    split_prepare_steps,
)
from livespec_orchestrator_beads_fabro.commands._node_timeouts import NodeTimeouts

__all__: list[str] = [
    "SetupRefusal",
    "materialize_setup_nodes",
    "overlay_with_setup_nodes",
]

_START_NODE = "start"


@dataclass(frozen=True, kw_only=True)
class SetupRefusal:
    """Why a dispatch's setup could not be carried as command nodes."""

    message: str


def overlay_with_setup_nodes(
    *,
    rendered: str,
    graph: Path | None,
    timeouts: NodeTimeouts | None,
    release: Callable[[], object],
) -> str | SetupRefusal:
    """`rendered` with its steps moved into `graph`; a dispatch with no graph keeps them.

    `release` runs when the setup is refused, because by then the dispatch holds
    credentials minted for a run that will never exist: the run-teardown revoke is
    only reached once a run starts, so a refusal has to give them back itself.
    """
    if graph is None:
        return rendered
    outcome = materialize_setup_nodes(overlay_text=rendered, graph=graph, timeouts=timeouts)
    if isinstance(outcome, SetupRefusal):
        _ = release()
    return outcome


def materialize_setup_nodes(
    *, overlay_text: str, graph: Path, timeouts: NodeTimeouts | None
) -> str | SetupRefusal:
    """The overlay without its prepare steps, after writing them into `graph` as nodes.

    The graph file is rewritten in place -- it is this dispatch's own copy -- and
    only when there is a step to carry, so an overlay with none leaves it untouched.
    A graph that is not a workflow graph at all leaves the overlay untouched too,
    steps and all, for the reason the module docstring gives. The payload variables
    of the steps move into the overlay's environment table, and that is settled
    BEFORE the graph is written, so a refusal never leaves a graph carrying nodes
    whose payloads went nowhere.
    """
    split = split_prepare_steps(overlay_text=overlay_text)
    if split is None:
        return SetupRefusal(
            message=(
                "the run config's prepare steps could not be separated from the rest of it, "
                f"so they cannot become {SETUP_NODE_PREFIX}<N> setup nodes"
            )
        )
    if not split.steps:
        return split.overlay
    hoisted = hoist_step_env(steps=split.steps)
    carried = append_env_lines(overlay_text=split.overlay, env=hoisted.env)
    if carried is None:
        return SetupRefusal(
            message=(
                "the run config's environment table could not take the setup payloads, "
                f"so the {SETUP_NODE_PREFIX}<N> setup nodes would find them absent"
            )
        )
    written = _write_chain(graph=graph, steps=hoisted.steps, timeouts=timeouts)
    if isinstance(written, SetupRefusal):
        return written
    return carried if written else overlay_text


def _write_chain(
    *, graph: Path, steps: Sequence[PrepareStep], timeouts: NodeTimeouts | None
) -> bool | SetupRefusal:
    """Write `steps` into `graph` as nodes; False when the graph is not a workflow graph."""
    try:
        graph_text = graph.read_text(encoding="utf-8")
    except OSError as error:
        return SetupRefusal(message=f"the workflow graph {graph} cannot be read: {error}")
    declared = parse_dot_graph(text=graph_text)
    if isinstance(declared, str) or _START_NODE not in declared.nodes:
        return False
    spliced = splice_setup_nodes(graph_text=graph_text, steps=steps, timeouts=timeouts)
    if spliced is None:
        return SetupRefusal(
            message=(
                f"the workflow graph {graph} has no unconditional edge out of its setup chain "
                f"to hang the {SETUP_NODE_PREFIX}<N> setup nodes on, so the sandbox setup "
                "would not run"
            )
        )
    try:
        _ = graph.write_text(spliced, encoding="utf-8")
    except OSError as error:
        return SetupRefusal(message=f"the workflow graph {graph} cannot be written: {error}")
    return True
