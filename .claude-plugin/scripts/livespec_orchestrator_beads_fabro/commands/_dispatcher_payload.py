"""Per-dispatch materialization of the self-contained workflow payload.

The Dispatcher already ships a self-contained payload per run: the committed
`workflow.toml`, the workflow graph, and the prompt files travel together
(`SPECIFICATION/contracts.md` section "Self-contained plugin dispatch"). Node
timeouts are configuration that CANNOT be templated into the graph -- the
pinned Fabro build silently drops a templated `timeout`, see
`_dispatcher_graph_render` -- so the resolved values are written into the
payload's own copy of the graph as literal durations instead.

EACH ACP NODE'S ADAPTER COMMAND IS WRITTEN IN FOR A SEPARATE REASON, settled by
launching agents against both engines rather than by reading either one's
source: a TEMPLATED `acp.command` kills the agent before the ACP protocol
completes on the Petri-era engine, while a literal one launches on both it and
the pinned build. `_dispatcher_graph_adapters` owns that rewrite and the
measurement behind it; this module is only where the two rewrites compose, and
they compose in that order so the adapter rewrite's no-template-token
guarantee covers the graph the run actually receives.

WHY THE WHOLE DIRECTORY IS COPIED rather than just the rewritten graph: the
graph references its prompts relatively (`@prompts/implement.md`) and Fabro
resolves those against THE GRAPH FILE'S OWN PATH. A rendered graph written
anywhere else would resolve its prompts nowhere, so the payload moves as the
unit it already is.
"""

from __future__ import annotations

import shutil
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from livespec_orchestrator_beads_fabro.commands._config import dispatcher_block
from livespec_orchestrator_beads_fabro.commands._dispatcher_credential_queue_allowance import (
    credential_queue_allowance_from_block,
    credential_queue_allowance_journal_record,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_graph_adapters import (
    render_acp_commands,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_graph_render import (
    render_workflow_graph,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_overlay import workflow_graph_path
from livespec_orchestrator_beads_fabro.commands._dispatcher_resume_entry import graph_entered_at
from livespec_orchestrator_beads_fabro.commands._dispatcher_run_wall_budget import (
    DEFAULT_RUN_WALL_BUDGET,
    RunWallBudget,
    node_timeout_conflict,
    run_wall_budget_from_block,
    run_wall_budget_journal_record,
)
from livespec_orchestrator_beads_fabro.commands._node_timeouts import (
    NodeTimeouts,
    node_timeouts_from_block,
    node_timeouts_journal_record,
)
from livespec_orchestrator_beads_fabro.effects import AttemptFailure, attempt

if TYPE_CHECKING:
    from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import JournalWriter

__all__: list[str] = [
    "WorkflowPayload",
    "materialize_workflow_payload",
    "prepare_workflow_payload",
    "remove_workflow_payload",
]

_NODE_TIMEOUTS_STAGE = "node-timeouts"
_COPY_ERRORS = (OSError, shutil.Error)


@dataclass(frozen=True, kw_only=True)
class WorkflowPayload:
    """One dispatch's materialized workflow payload.

    `graph` is the RENDERED graph inside `payload_dir`, which is what the
    run-config overlay points Fabro at; `node_seconds` is what each node's
    timeout attribute actually received, and `node_commands` what each ACP
    node's `acp.command` attribute received, so the dispatch record reports
    the rendered values rather than a re-derivation of them.

    `run_wall_budget` is the whole-run wall budget resolved from the SAME read
    of the dispatch target's configuration the timeouts came from. It rides the
    payload rather than being resolved again at plan build for the reason the
    timeouts do: the refusal that compares the two was graded against ONE
    reading, so a second read could plan a dispatch under a budget the
    admission never saw. It defaults to the fully-defaulted budget so a caller
    that materializes a payload directly carries the documented default rather
    than None.
    """

    payload_dir: Path
    graph: Path
    timeouts: NodeTimeouts
    node_seconds: Mapping[str, int]
    node_commands: Mapping[str, str]
    run_wall_budget: RunWallBudget = DEFAULT_RUN_WALL_BUDGET


def prepare_workflow_payload(  # noqa: PLR0913 — kw-only; adapters and entry_node are two independent rendering inputs.
    *,
    repo: Path,
    committed: Path,
    payload_dir: Path,
    journal: JournalWriter,
    work_item_id: str,
    adapters: Mapping[str, str],
    entry_node: str | None = None,
    run_wall_budget_argument: str | None = None,
) -> WorkflowPayload | str:
    """Resolve node timeouts and the wall budget, materialize, and journal.

    Returns the payload, or an actionable refusal message the caller reports
    as a failed dispatch. Every refusal happens BEFORE any Fabro run exists,
    which is the whole point of validating here: a non-positive or
    non-integer timeout is a config typo, and the honest place to discover
    one is the dispatch that would have run without a timeout.

    BOTH POLICIES COME FROM ONE READ of the dispatch target's configuration,
    which is why the block is read here rather than through two `resolve_*`
    seams. The wall budget is refused when it is smaller than a node timeout
    resolved for the same dispatch, so the two numbers have to come from one
    reading or the refusal could grade a budget against timeouts the run never
    received -- and both readings produce a well-formed answer, so nothing
    would announce the divergence.

    THE CONFLICT IS GRADED AFTER THE RENDER and before the journal append,
    because `payload.node_seconds` is what each node's timeout attribute
    ACTUALLY received. Grading it earlier would compare the budget against the
    configured table alone, which names no value for a node that takes the
    default -- so the refusal would have to name a key rather than the node the
    budget would have cancelled.
    """
    block = dispatcher_block(cwd=repo)
    timeouts = node_timeouts_from_block(block=block)
    if isinstance(timeouts, str):
        return timeouts
    budget = run_wall_budget_from_block(block=block, argument=run_wall_budget_argument)
    if isinstance(budget, str):
        return budget
    # The queue allowance is graded BESIDE the wall budget and from the same
    # block read, because the two are summed into the bounded credential-use
    # window: resolved from two reads, a dispatch could launch against a window
    # neither key's refusal would describe, and both reads produce a well-formed
    # figure so nothing would announce the divergence.
    queue_allowance = credential_queue_allowance_from_block(block=block)
    if isinstance(queue_allowance, str):
        return queue_allowance
    payload = materialize_workflow_payload(
        committed=committed,
        payload_dir=payload_dir,
        timeouts=timeouts,
        adapters=adapters,
        entry_node=entry_node,
        run_wall_budget=budget,
    )
    if isinstance(payload, str):
        return payload
    conflict = node_timeout_conflict(budget=budget, nodes=payload.node_seconds)
    if conflict is not None:
        return conflict
    journal.append(
        record={
            "stage": _NODE_TIMEOUTS_STAGE,
            "work_item_id": work_item_id,
            **node_timeouts_journal_record(timeouts=timeouts, nodes=payload.node_seconds),
            **run_wall_budget_journal_record(budget=budget),
            **credential_queue_allowance_journal_record(allowance=queue_allowance),
        }
    )
    return payload


def materialize_workflow_payload(
    *,
    committed: Path,
    payload_dir: Path,
    timeouts: NodeTimeouts,
    adapters: Mapping[str, str],
    entry_node: str | None = None,
    run_wall_budget: RunWallBudget = DEFAULT_RUN_WALL_BUDGET,
) -> WorkflowPayload | str:
    """Copy the committed workflow payload and render its graph literally.

    `entry_node` is the RESUMED-AT stage of a resume, and it is applied to the
    payload's own copy of the graph for exactly the reason the timeouts are: the
    derived graph is this one run's, never a registered variant and never
    recorded as the item's workflow. A node the graph does not declare refuses
    here, before any run exists, rather than failing validation at run-create
    with an error naming a graph the operator never wrote.
    """
    committed_graph = _committed_graph(committed=committed)
    if isinstance(committed_graph, str):
        return committed_graph
    rendered = _rendered_graph(
        committed_graph=committed_graph,
        timeouts=timeouts,
        adapters=adapters,
        entry_node=entry_node,
    )
    if isinstance(rendered, str):
        return rendered
    graph = payload_dir / committed_graph.name
    copied = attempt(
        action=lambda: _copy_payload(
            source=committed_graph.parent,
            payload_dir=payload_dir,
            graph=graph,
            text=rendered.text,
        ),
        exceptions=_COPY_ERRORS,
    )
    if isinstance(copied, AttemptFailure):
        return f"workflow payload {payload_dir} is not materializable: {copied.error}"
    return WorkflowPayload(
        payload_dir=payload_dir,
        graph=graph,
        timeouts=timeouts,
        node_seconds=rendered.node_seconds,
        node_commands=rendered.node_commands,
        # Carried THROUGH rather than written into the graph: the workflow
        # graph declares no budget, because the Dispatcher's own host-side
        # watchdog enforces it and the engine knows nothing about it.
        run_wall_budget=run_wall_budget,
    )


@dataclass(frozen=True, kw_only=True)
class _RenderedGraph:
    """The payload graph text as the run will see it, with what each render set."""

    text: str
    node_seconds: Mapping[str, int]
    node_commands: Mapping[str, str]


def _rendered_graph(
    *,
    committed_graph: Path,
    timeouts: NodeTimeouts,
    adapters: Mapping[str, str],
    entry_node: str | None,
) -> _RenderedGraph | str:
    """Read the committed graph and apply the three renders in their fixed order.

    Timeouts first, then the literal ACP commands, then the resume derivation:
    the derivation runs on the ADAPTER-RENDERED text, so a resumed run ships
    the same literal `acp.command` values an ordinary dispatch does.
    """
    graph_text = attempt(
        action=lambda: committed_graph.read_text(encoding="utf-8"),
        exceptions=(OSError,),
    )
    if isinstance(graph_text, AttemptFailure):
        return f"workflow graph {committed_graph} is unreadable: {graph_text.error}"
    rendered = render_workflow_graph(committed_text=graph_text, timeouts=timeouts)
    if isinstance(rendered, str):
        return rendered
    commands = render_acp_commands(graph_text=rendered.text, adapters=adapters)
    if isinstance(commands, str):
        return commands
    entered = _entered_text(text=commands.text, entry_node=entry_node)
    if entered is None:
        return (
            f"workflow graph {committed_graph} declares no node {entry_node!r} to"
            " resume at, or carries no unconditional `start` edge to move onto it"
        )
    return _RenderedGraph(
        text=entered, node_seconds=rendered.node_seconds, node_commands=commands.node_commands
    )


def remove_workflow_payload(*, payload_dir: Path | None) -> None:
    """Tear down a materialized payload when the run returns.

    A None `payload_dir` is the caller that materialized none, not an
    error. Removal is best-effort for the same reason the overlay's is: a
    payload that cannot be removed must not turn a completed dispatch into
    a failed one, and the next dispatch replaces the directory wholesale.
    """
    if payload_dir is not None:
        shutil.rmtree(payload_dir, ignore_errors=True)


def _entered_text(*, text: str, entry_node: str | None) -> str | None:
    """The graph as the run will see it: derived for a resume, unchanged otherwise.

    An ordinary dispatch returns the rendered text ITSELF rather than a copy
    passed through the derivation, so the resume path cannot change a byte of
    what every other dispatch ships.
    """
    if entry_node is None:
        return text
    return graph_entered_at(graph_text=text, node=entry_node)


def _committed_graph(*, committed: Path) -> Path | str:
    """The committed graph path declared by the committed run config."""
    config_text = attempt(
        action=lambda: committed.read_text(encoding="utf-8"),
        exceptions=(OSError,),
    )
    if isinstance(config_text, AttemptFailure):
        return f"workflow config {committed} is unreadable: {config_text.error}"
    graph = workflow_graph_path(committed_text=config_text, workflow_dir=committed.parent.resolve())
    if graph is None:
        return f'workflow config {committed} declares no [workflow] graph = "..."'
    return graph


def _copy_payload(*, source: Path, payload_dir: Path, graph: Path, text: str) -> None:
    """Replace `payload_dir` with a fresh copy of `source`, graph rendered.

    The destination is removed first so a payload left behind by an earlier
    dispatch of the same work-item can never contribute a stale prompt or a
    stale graph to this run.
    """
    shutil.rmtree(payload_dir, ignore_errors=True)
    # A sibling dispatch can remove its lock after copytree enumerates it.
    # Skip vanished files individually so the rest of the payload is copied;
    # permission errors still reach the materialization refusal above.
    _ = shutil.copytree(
        source,
        payload_dir,
        copy_function=lambda src, dst: attempt(
            action=lambda: shutil.copy2(src, dst),
            exceptions=(FileNotFoundError,),
        ),
    )
    _ = graph.write_text(text, encoding="utf-8")
