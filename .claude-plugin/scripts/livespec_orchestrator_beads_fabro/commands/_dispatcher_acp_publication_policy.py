"""Workflow-kind policy for the retired implementation publication adapter."""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

from livespec_orchestrator_beads_fabro.commands._dispatcher_workflow_ledger import (
    previewed_workflow_variant,
)
from livespec_orchestrator_beads_fabro.commands._workflow_variant_kind import (
    WORKFLOW_KIND_GROOM,
    is_groom_variant,
)
from livespec_orchestrator_beads_fabro.types import WorkItem

if TYPE_CHECKING:
    from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import JournalWriter

__all__: list[str] = [
    "ACP_PUBLICATION_POLICY_STAGE",
    "GROOM_ONLY_ACP_NODES",
    "IMPLEMENTATION_PR_NOT_APPLIED_REASON",
    "implementation_pr_override_refusal",
    "scoped_repository_block",
]

ACP_PUBLICATION_POLICY_STAGE = "acp-publication-policy"
IMPLEMENTATION_PR_NOT_APPLIED_REASON = "implementation-publication-is-scripted"
_ACP_NODES_KEY = "acp_nodes"
_PR_NODE = "pr"

# The ACP nodes that exist only on a GROOM-KIND workflow. The generic adapter
# registry still accepts `pr` because groom legitimately configures it; this
# dispatch policy decides whether the selected workflow kind applies it.
GROOM_ONLY_ACP_NODES: frozenset[str] = frozenset({_PR_NODE})


def scoped_repository_block(
    *, block: dict[str, object], workflow_kind: str
) -> tuple[dict[str, object], tuple[dict[str, str], ...]]:
    """Drop repository `pr` configuration only for implementation workflows.

    A shallow copy is enough because the only nested object changed is copied
    separately. The caller retains every unrelated configuration byte and gets
    the audit fact to append beside the resolved node set.
    """
    if workflow_kind == WORKFLOW_KIND_GROOM:
        return block, ()
    raw = block.get(_ACP_NODES_KEY)
    if not isinstance(raw, dict) or _PR_NODE not in raw:
        return block, ()
    table = dict(cast("dict[str, Any]", raw))
    del table[_PR_NODE]
    scoped = dict(block)
    scoped[_ACP_NODES_KEY] = table
    return scoped, (
        {
            "layer": "repository",
            "node": _PR_NODE,
            "reason": IMPLEMENTATION_PR_NOT_APPLIED_REASON,
        },
    )


def implementation_pr_override_refusal(
    *,
    args: argparse.Namespace,
    repo: Path,
    items: Sequence[WorkItem],
    journal: JournalWriter,
) -> str | None:
    """Refuse a dispatch-layer `pr` adapter for any implementation selection.

    This function is called by the shared pre-dispatch wall, before admission.
    Repository configuration is intentionally not handled here: it is a
    compatibility setting that the later resolution ignores and journals.
    """
    overrides = tuple(getattr(args, "acp_node", None) or ())
    if not any(_override_node(value=value) == _PR_NODE for value in overrides):
        return None
    explicit = getattr(args, "workflow_name", None)
    name = explicit if isinstance(explicit, str) and explicit else None
    implementation = [
        item.id
        for item in items
        if not is_groom_variant(
            repo=repo,
            variant=previewed_workflow_variant(
                repo=repo,
                work_item_id=item.id,
                name=name,
            ),
        )
    ]
    if not implementation:
        return None
    detail = (
        "--acp-node pr=... cannot apply to an implementation dispatch: `pr` is a "
        "command stage with no publication ACP adapter; remove the override "
        f"(implementation items: {', '.join(sorted(implementation))})"
    )
    journal.append(
        record={
            "stage": ACP_PUBLICATION_POLICY_STAGE,
            "work_item_ids": sorted(implementation),
            "result": "refused",
            "layer": "dispatch",
            "node": _PR_NODE,
            "reason": detail,
        }
    )
    return detail


def _override_node(*, value: str) -> str:
    """The requested node name, including malformed-value detection by name."""
    return value.partition("=")[0].strip()
