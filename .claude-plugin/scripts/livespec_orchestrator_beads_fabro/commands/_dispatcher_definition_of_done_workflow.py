"""Pre-claim validation of the Definition-of-Done nodes in one workflow graph.

The effective-criteria and Definition-of-Done judgement walls prove that an
item is fit to run.  This module proves the other half of that contract: the
resolved implement workflow still carries the stages that make the proof
possible.  A target-local reserved workflow takes precedence over the bundle,
so validating the bundled graph alone would silently admit the broken fork this
gate exists to stop.
"""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from pathlib import Path
from typing import cast

from livespec_orchestrator_beads_fabro.commands._dispatcher_dot_graph import (
    DotGraph,
    parse_dot_graph,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_overlay import workflow_graph_path
from livespec_orchestrator_beads_fabro.commands._dispatcher_paths import workflow_toml
from livespec_orchestrator_beads_fabro.commands._dispatcher_workflow_ledger import (
    previewed_workflow_variant,
)
from livespec_orchestrator_beads_fabro.commands._workflow_variant_kind import (
    WORKFLOW_KIND_GROOM,
    variant_kind,
)
from livespec_orchestrator_beads_fabro.types import WorkItem

__all__: list[str] = [
    "definition_of_done_workflow_refusal",
]

_REQUIRED_NODES = ("dod_gate", "proof_capture", "proof_verify")
_REQUIRED_NODES_BY_KIND = {
    WORKFLOW_KIND_GROOM: (),
}


def definition_of_done_workflow_refusal(
    *, args: argparse.Namespace, repo: Path, items: Sequence[WorkItem]
) -> str | None:
    """Refuse the first selected implement workflow missing a proof-stage node.

    The previewed variant is deliberately non-pinning: this runs before the
    admission valve, so recording a workflow choice here would leave provenance
    for a dispatch the wall itself refused.  `workflow_toml` is the launcher's
    precedence authority, which keeps target-local and bundled validation on
    the exact manifest the eventual Fabro run would materialize.
    """
    return next(
        (
            refusal
            for item in items
            if (refusal := _workflow_refusal(args=args, repo=repo, item=item)) is not None
        ),
        None,
    )


def _workflow_refusal(*, args: argparse.Namespace, repo: Path, item: WorkItem) -> str | None:
    variant = previewed_workflow_variant(
        repo=repo, work_item_id=item.id, name=getattr(args, "workflow_name", None)
    )
    committed = workflow_toml(args=args, variant_directory=variant.directory)
    graph_path = cast(
        Path,
        workflow_graph_path(
            committed_text=committed.read_text(encoding="utf-8"),
            workflow_dir=committed.parent.resolve(),
        ),
    )
    graph = cast(DotGraph, parse_dot_graph(text=graph_path.read_text(encoding="utf-8")))
    required = _REQUIRED_NODES_BY_KIND.get(
        variant_kind(repo=repo, variant=variant), _REQUIRED_NODES
    )
    missing = tuple(node for node in required if node not in graph.nodes)
    if not missing:
        return None
    return (
        f"REFUSED: resolved implement workflow {committed} (graph {graph_path}) is missing "
        f"required Definition-of-Done node(s): {', '.join(missing)}; no claim was taken "
        "and no Fabro run was created."
    )
