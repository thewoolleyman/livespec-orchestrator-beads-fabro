"""Per-dispatch materialization of the self-contained workflow payload.

The Dispatcher already ships a self-contained payload per run: the committed
`workflow.toml`, the workflow graph, and the prompt files travel together
(`SPECIFICATION/contracts.md` section "Self-contained plugin dispatch"). Node
timeouts are configuration that CANNOT be templated into the graph -- the
pinned Fabro build silently drops a templated `timeout`, see
`_dispatcher_graph_render` -- so the resolved values are written into the
payload's own copy of the graph as literal durations instead.

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

from livespec_orchestrator_beads_fabro.commands._config import resolve_node_timeouts
from livespec_orchestrator_beads_fabro.commands._dispatcher_graph_render import (
    render_workflow_graph,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_overlay import workflow_graph_path
from livespec_orchestrator_beads_fabro.commands._dispatcher_resume_entry import graph_entered_at
from livespec_orchestrator_beads_fabro.commands._node_timeouts import (
    NodeTimeouts,
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
    timeout attribute actually received, so the dispatch record reports the
    rendered values rather than a re-derivation of them.
    """

    payload_dir: Path
    graph: Path
    timeouts: NodeTimeouts
    node_seconds: Mapping[str, int]


def prepare_workflow_payload(
    *,
    repo: Path,
    committed: Path,
    payload_dir: Path,
    journal: JournalWriter,
    work_item_id: str,
    entry_node: str | None = None,
) -> WorkflowPayload | str:
    """Resolve node timeouts, materialize the payload, and journal the result.

    Returns the payload, or an actionable refusal message the caller reports
    as a failed dispatch. Every refusal happens BEFORE any Fabro run exists,
    which is the whole point of validating here: a non-positive or
    non-integer timeout is a config typo, and the honest place to discover
    one is the dispatch that would have run without a timeout.
    """
    timeouts = resolve_node_timeouts(cwd=repo)
    if isinstance(timeouts, str):
        return timeouts
    payload = materialize_workflow_payload(
        committed=committed,
        payload_dir=payload_dir,
        timeouts=timeouts,
        entry_node=entry_node,
    )
    if isinstance(payload, str):
        return payload
    journal.append(
        record={
            "stage": _NODE_TIMEOUTS_STAGE,
            "work_item_id": work_item_id,
            **node_timeouts_journal_record(timeouts=timeouts, nodes=payload.node_seconds),
        }
    )
    return payload


def materialize_workflow_payload(
    *,
    committed: Path,
    payload_dir: Path,
    timeouts: NodeTimeouts,
    entry_node: str | None = None,
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
    graph_text = attempt(
        action=lambda: committed_graph.read_text(encoding="utf-8"),
        exceptions=(OSError,),
    )
    if isinstance(graph_text, AttemptFailure):
        return f"workflow graph {committed_graph} is unreadable: {graph_text.error}"
    rendered = render_workflow_graph(committed_text=graph_text, timeouts=timeouts)
    if isinstance(rendered, str):
        return rendered
    entered = _entered_text(text=rendered.text, entry_node=entry_node)
    if entered is None:
        return (
            f"workflow graph {committed_graph} declares no node {entry_node!r} to"
            " resume at, or carries no unconditional `start` edge to move onto it"
        )
    graph = payload_dir / committed_graph.name
    copied = attempt(
        action=lambda: _copy_payload(
            source=committed_graph.parent,
            payload_dir=payload_dir,
            graph=graph,
            text=entered,
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
    _ = shutil.copytree(source, payload_dir)
    _ = graph.write_text(text, encoding="utf-8")
