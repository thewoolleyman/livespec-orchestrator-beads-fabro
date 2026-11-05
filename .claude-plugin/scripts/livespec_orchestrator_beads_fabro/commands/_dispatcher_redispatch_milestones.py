"""A run's progress milestone, ordered by the workflow graph's own dependencies.

`SPECIFICATION/contracts.md` section "Across-dispatch required-result progress"
requires progress to "use the actual workflow dependency ordering of successful
milestones, not lexical stage names or retry numbers". The order of a node is
therefore its shortest dependency distance from the graph's entry marker, read
from the same committed graph the Dispatcher launches. A node on a repair loop
keeps the rank of its first arrival, so a retry of an early stage can never look
like progress, and a visit number is never consulted: `fabro_node_outcomes`
already collapses a node to its newest visit.

A run whose succeeded nodes are not all declared by the graph ran a different
workflow variant, and is reported under a different identity so the progress
decision demands a diagnosis instead of comparing incomparable positions. The
engine's own name for the entry marker, `setup`, is not such a node: it names
the Mdiamond marker the graph declares as `start`.
"""

from __future__ import annotations

import argparse
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from livespec_orchestrator_beads_fabro.commands._acp_workflow_graph import (
    START_SHAPE,
    WorkflowGraph,
    parse_workflow_graph,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_overlay import workflow_graph_path
from livespec_orchestrator_beads_fabro.commands._dispatcher_paths import workflow_toml
from livespec_orchestrator_beads_fabro.commands._fabro_port_checkpoints import (
    fabro_inspect_checkpoints,
)
from livespec_orchestrator_beads_fabro.commands._fabro_port_node_outcomes import (
    fabro_node_outcomes,
    fabro_stage_node,
)
from livespec_orchestrator_beads_fabro.commands._fabro_port_records import fabro_inspect_record
from livespec_orchestrator_beads_fabro.effects import AttemptFailure, attempt

__all__: list[str] = [
    "NO_MILESTONE",
    "RunMilestone",
    "committed_node_ranks",
    "run_milestone",
]

NO_MILESTONE = "(no successful milestone)"
_ENGINE_ENTRY_MARKER = "setup"
_SUCCEEDED = "succeeded"
_DECLARED_IDENTITY = "committed-graph"


@dataclass(frozen=True, kw_only=True)
class RunMilestone:
    """The furthest succeeded node of one run, its graph rank, and its variant."""

    name: str
    order: int
    workflow_identity: str


def committed_node_ranks(*, repo: Path) -> dict[str, int] | None:
    """Each node's dependency distance from the entry marker, or `None` if unreadable."""
    manifest_path = workflow_toml(args=argparse.Namespace(workflow=None, repo=repo))
    manifest = attempt(
        action=lambda: manifest_path.read_text(encoding="utf-8"),
        exceptions=(OSError, UnicodeDecodeError),
    )
    if isinstance(manifest, AttemptFailure):
        return None
    graph_path = workflow_graph_path(committed_text=manifest, workflow_dir=manifest_path.parent)
    if graph_path is None:
        return None
    text = attempt(
        action=lambda: graph_path.read_text(encoding="utf-8"),
        exceptions=(OSError, UnicodeDecodeError),
    )
    if isinstance(text, AttemptFailure):
        return None
    ranks = _ranks(graph=parse_workflow_graph(text=text))
    return ranks or None


def run_milestone(*, payload: object | None, ranks: dict[str, int]) -> RunMilestone | None:
    """The run's milestone, or `None` when its record grades nothing at all."""
    record = fabro_inspect_record(payload=payload)
    if record is None:
        return None
    checkpoints = fabro_inspect_checkpoints(record=record)
    checkpoint: dict[str, Any] = checkpoints[-1] if checkpoints else {}
    outcomes = fabro_node_outcomes(record=record, checkpoint=checkpoint)
    if not outcomes:
        return None
    succeeded = [
        fabro_stage_node(stage=stage)
        for stage, outcome in outcomes.items()
        if outcome.get("status") == _SUCCEEDED
    ]
    undeclared = sorted(
        {node for node in succeeded if node not in ranks and node != _ENGINE_ENTRY_MARKER}
    )
    identity = _DECLARED_IDENTITY if not undeclared else f"undeclared:{','.join(undeclared)}"
    furthest = max(
        (node for node in succeeded if node in ranks), key=ranks.__getitem__, default=None
    )
    if furthest is None:
        return RunMilestone(name=NO_MILESTONE, order=-1, workflow_identity=identity)
    return RunMilestone(name=furthest, order=ranks[furthest], workflow_identity=identity)


def _ranks(*, graph: WorkflowGraph) -> dict[str, int]:
    ranks: dict[str, int] = {}
    queue: deque[str] = deque()
    for start in graph.with_shape(shape=START_SHAPE):
        ranks[start] = 0
        queue.append(start)
    while queue:
        node = queue.popleft()
        for successor in graph.successors(node=node):
            if successor not in ranks:
                ranks[successor] = ranks[node] + 1
                queue.append(successor)
    return ranks
