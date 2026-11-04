"""The pre-claim check that every `--acp-node` override resolves.

A row of the pre-dispatch wall: it lands after selection and before admission, so
an override the resolution grammar refuses leaves the item exactly as selection
found it -- same status, same assignee, no dispatch lock and no Fabro run. The
refusal used to surface only at stage `acp-nodes`, which runs after `ledger-admit`
has set the item `active`; each refused dispatch then stranded a claim with no run
behind it and the item had to be released by hand.

WHAT IS CHECKED HERE IS ONLY WHAT THE ARGUMENTS AND THE COMMITTED CONFIGURATION
DECIDE. The admission-verdict selection and the factory-capability gate need the
claimed dispatch's evaluation and stay with `prepare_acp_nodes`.

AN UNREADABLE WORKFLOW IS NOT THIS ROW'S REFUSAL. The variant and payload stages
own that diagnostic and name their own stage, so a selection whose workflow
config cannot be read is passed through rather than reported as an override fault.
"""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from pathlib import Path
from typing import TYPE_CHECKING

from livespec_orchestrator_beads_fabro.commands._dispatcher_acp_nodes import acp_override_refusal
from livespec_orchestrator_beads_fabro.commands._dispatcher_paths import workflow_toml
from livespec_orchestrator_beads_fabro.commands._dispatcher_workflow_ledger import (
    previewed_workflow_variant,
)
from livespec_orchestrator_beads_fabro.types import WorkItem

if TYPE_CHECKING:
    from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import JournalWriter

__all__: list[str] = [
    "ACP_OVERRIDE_REFUSAL_STAGE",
    "acp_node_override_refusal",
]

ACP_OVERRIDE_REFUSAL_STAGE = "acp-node-override-refusal"


def acp_node_override_refusal(
    *,
    args: argparse.Namespace,
    repo: Path,
    items: Sequence[WorkItem],
    journal: JournalWriter,
) -> str | None:
    """Refuse the selection when its `--acp-node` overrides fail to resolve.

    Each item is graded against the workflow variant it WOULD run, because the
    variant decides the committed workflow whose adapter inputs the overrides
    layer over. The first refusing item refuses the selection, which is what the
    wall's other rows do for a fault in the shared invocation.
    """
    overrides = tuple(getattr(args, "acp_node", None) or ())
    if not overrides:
        return None
    explicit = getattr(args, "workflow_name", None)
    name = explicit if isinstance(explicit, str) and explicit else None
    for item in items:
        variant = previewed_workflow_variant(repo=repo, work_item_id=item.id, name=name)
        committed = workflow_toml(args=args, variant_directory=variant.directory)
        if not committed.is_file():
            continue
        refusal = acp_override_refusal(repo=repo, committed=committed, overrides=overrides)
        if refusal is None:
            continue
        detail = f"{item.id}: {refusal}"
        journal.append(
            record={
                "stage": ACP_OVERRIDE_REFUSAL_STAGE,
                "work_item_id": item.id,
                "result": "refused",
                "reason": refusal,
            }
        )
        return detail
    return None
