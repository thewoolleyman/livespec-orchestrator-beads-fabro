"""Pre-claim validation of the Definition-of-Done nodes in one workflow graph.

The effective-criteria and Definition-of-Done judgement walls prove that an
item is fit to run.  This module proves the other half of that contract: the
resolved implement workflow still carries the stages that make the proof
possible.  A target-local reserved workflow takes precedence over the bundle,
so validating the bundled graph alone would silently admit the broken fork this
gate exists to stop.

THE VARIANT IS RESOLVED THROUGH `criteria_wall_variant`, the shared wrapper the
two preceding wall rows already use for this exact question, and never through
`previewed_workflow_variant` directly.  That wrapper exists to catch the
`_UNRESOLVABLE` set -- the beads command, connection, credential, mapping and
tenant errors, an unset `connection.prefix`, an unreadable `.livespec.jsonc`,
any `OSError` -- and to fail toward the ARMED side.  Reaching past it puts a
bug-class traceback on the one path whose whole purpose is rendering actionable
refusals: those faults are live rather than hypothetical here, because the
fleet's credential wrapper has a measured cache-poisoning failure that makes
every tenant refuse at once.  It also keeps the kind EXEMPTION stated once:
`CriteriaWallVariant.exempt` is the wall's own answer to "is this a groom
dispatch", and a second copy behind the wall is how two surfaces come to
disagree about which variant one dispatch runs.

EVERY INPUT FAULT IS A REFUSAL AND NEVER A TRACEBACK, which is the other half
of the same discipline.  Both of this gate's dependencies MODEL their failures
-- `workflow_graph_path` answers None for a run config declaring no
`[workflow] graph`, and `parse_dot_graph` answers a string naming the construct
that defeated it -- and both files are read off a repository this gate does not
own, so either read can fail.  A fork maintained by hand is exactly where those
faults arrive: the openbrain and homelab forks this gate was filed for are
hand-written target-local graphs, so a construct the shared parser deliberately
refuses crashed this gate rather than being refused by it.  The shape below
mirrors `credential_lifetime_requirement_for`, which reads the same two files
one row up in the same wall, so the two cannot drift about what "unreadable"
means.
"""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_criteria_wall_variant import (
    criteria_wall_variant,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_dot_graph import (
    DotGraph,
    parse_dot_graph,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_overlay import workflow_graph_path
from livespec_orchestrator_beads_fabro.commands._dispatcher_paths import workflow_toml
from livespec_orchestrator_beads_fabro.effects import AttemptFailure, attempt
from livespec_orchestrator_beads_fabro.types import WorkItem

__all__: list[str] = [
    "definition_of_done_workflow_refusal",
]

_REQUIRED_NODES = ("dod_gate", "proof_capture", "proof_verify")

# What every refusal here promises, which is the whole value of refusing BEFORE
# the admission valve rather than after it.
_UNCLAIMED = "no claim was taken and no Fabro run was created."


def definition_of_done_workflow_refusal(
    *, args: argparse.Namespace, repo: Path, items: Sequence[WorkItem]
) -> str | None:
    """Refuse the first selected implement workflow missing a proof-stage node.

    The resolution is deliberately non-pinning: this runs before the admission
    valve, so recording a workflow choice here would leave provenance for a
    dispatch the wall itself refused.  `workflow_toml` is the launcher's
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
    variant = criteria_wall_variant(
        repo=repo, work_item_id=item.id, workflow_name=getattr(args, "workflow_name", None)
    )
    # The groom exemption, read off the wall's own resolution rather than
    # restated: a groom variant's acceptance is the human approval of its draft
    # and it terminates at needs-human by construction, so it runs none of the
    # three proof stages and owes none of them.
    if variant.exempt:
        return None
    committed = workflow_toml(args=args, variant_directory=variant.directory)
    resolved = _resolved_graph(committed=committed)
    if isinstance(resolved, str):
        return resolved
    graph_path, graph = resolved
    missing = tuple(node for node in _REQUIRED_NODES if node not in graph.nodes)
    if not missing:
        return None
    return (
        f"REFUSED: resolved implement workflow {committed} (graph {graph_path}) is missing "
        f"required Definition-of-Done node(s): {', '.join(missing)}; {_UNCLAIMED}"
    )


def _resolved_graph(*, committed: Path) -> tuple[Path, DotGraph] | str:
    """The graph this dispatch would run, or the refusal naming what stopped it.

    Four faults, four refusals, each naming the FILE it is about: an operator
    reading one has to know whether to fix the run config, create the graph, or
    repair a construct inside it, and those are three different edits.
    """
    committed_text = _read(path=committed)
    if committed_text is None:
        return (
            f"REFUSED: the resolved implement workflow's run config {committed} could not "
            f"be read, so its Definition-of-Done nodes cannot be established; {_UNCLAIMED}"
        )
    graph_path = workflow_graph_path(
        committed_text=committed_text, workflow_dir=committed.parent.resolve()
    )
    if graph_path is None:
        return (
            f"REFUSED: resolved implement workflow {committed} declares no [workflow] graph, "
            f"so it has no graph whose Definition-of-Done nodes could be read; {_UNCLAIMED}"
        )
    graph_text = _read(path=graph_path)
    if graph_text is None:
        return (
            f"REFUSED: resolved implement workflow {committed} declares the graph "
            f"{graph_path}, which could not be read; {_UNCLAIMED}"
        )
    graph = parse_dot_graph(text=graph_text)
    if isinstance(graph, str):
        return (
            f"REFUSED: resolved implement workflow {committed} declares the graph "
            f"{graph_path}, which could not be parsed, so its Definition-of-Done nodes "
            f"cannot be established: {graph}; {_UNCLAIMED}"
        )
    return (graph_path, graph)


def _read(*, path: Path) -> str | None:
    """One file's text, or None when this gate could not read it.

    `UnicodeDecodeError` rides alongside `OSError` because it is a `ValueError`
    rather than an `OSError`: a hand-maintained graph holding non-UTF-8 bytes is
    undecodable, which is an unreadable input and not a crash.
    """
    read = attempt(
        action=lambda: path.read_text(encoding="utf-8"),
        exceptions=(OSError, UnicodeDecodeError),
    )
    return None if isinstance(read, AttemptFailure) else read
