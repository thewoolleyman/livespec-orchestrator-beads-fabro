"""Workflow-kind policy for the retired implementation publication adapter.

`SPECIFICATION/contracts.md` section "ACP node adapter configuration" ->
"Publication adapter by selected workflow kind" is the whole of this module's
brief, and it draws the line by WORKFLOW KIND rather than by node name: a
repository-level `dispatcher.acp_nodes.pr` entry "applies only to a groom-kind
workflow's ACP filing-plan node", and for an implementation workflow it "MUST be
ignored and journaled as not-applied, naming the entry and the selected workflow
kind" while creating no candidate chain and requiring no provider credentials.

WHY IGNORED-AND-JOURNALED RATHER THAN REFUSED. The entry is COMPATIBILITY
configuration. One repository can register both an implementation workflow and a
groom-kind variant, and the groom variant's `pr` node legitimately needs that
entry; refusing an implementation dispatch because the repository configures its
groom publisher would make the two workflows unable to share one configuration
file. So the implementation path drops the entry and says so on the record. A
PER-DISPATCH override is the opposite case and refuses, because nothing about it
is shared: it was typed for this dispatch, and this dispatch has no adapter to
apply it to.

THE SCOPING CUTS IN ONE DIRECTION ONLY. Dropping the entry is what keeps the
downstream resolver from minting a candidate chain -- and therefore from
grading, pricing and acquiring credentials for -- a node that is a command
stage. Nothing here widens what a groom dispatch sees.
"""

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
    "PUBLICATION_ACP_NODE",
    "implementation_pr_override_refusal",
    "scoped_repository_block",
]

ACP_PUBLICATION_POLICY_STAGE = "acp-publication-policy"
IMPLEMENTATION_PR_NOT_APPLIED_REASON = "implementation-publication-is-scripted"
PUBLICATION_ACP_NODE = "pr"

_ACP_NODES_KEY = "acp_nodes"

# The ACP nodes that exist only on a GROOM-KIND workflow. The generic adapter
# registry still accepts `pr` because groom legitimately configures it; this
# dispatch policy is what decides whether the selected workflow kind applies it.
GROOM_ONLY_ACP_NODES: frozenset[str] = frozenset({PUBLICATION_ACP_NODE})


def scoped_repository_block(
    *, block: dict[str, object], workflow_kind: str
) -> tuple[dict[str, object], tuple[dict[str, str], ...]]:
    """Drop repository `pr` configuration only for implementation workflows.

    A SHALLOW copy of the block plus a fresh copy of the one nested table is
    enough, and is deliberate: the caller keeps every unrelated configuration
    byte it read, while the mutation cannot reach the mapping the caller still
    holds. Returning the block UNCHANGED when there is nothing to drop is what
    keeps a groom dispatch, and an implementation dispatch against a repository
    that configures no `pr`, byte-identical to what they resolved before this
    policy existed.

    The second element is the audit fact the caller appends beside the resolved
    node set. It names the ENTRY and the SELECTED KIND because the clause
    requires both: the kind alone does not say what was ignored, and the entry
    alone does not say why ignoring it was correct.

    THE ENTRY IS NAMED BY ITS CONFIGURATION KEY, NEVER BY ITS VALUE, and that is
    a containment requirement rather than brevity. An `acp_nodes` entry carries
    a declared adapter `env` table, which is exactly where a repository puts a
    provider token; serializing the ignored entry would copy that value into the
    dispatch journal — the one record written to say the entry was NOT used. The
    dotted key identifies the entry uniquely inside `acp_nodes`, which is all
    "naming the entry" can mean for a table keyed by node.
    """
    if workflow_kind == WORKFLOW_KIND_GROOM:
        return block, ()
    raw = block.get(_ACP_NODES_KEY)
    if not isinstance(raw, dict) or PUBLICATION_ACP_NODE not in raw:
        return block, ()
    table = dict(cast("dict[str, Any]", raw))
    del table[PUBLICATION_ACP_NODE]
    scoped = dict(block)
    scoped[_ACP_NODES_KEY] = table
    return scoped, (
        {
            "layer": "repository",
            "node": PUBLICATION_ACP_NODE,
            "entry": f"dispatcher.{_ACP_NODES_KEY}.{PUBLICATION_ACP_NODE}",
            "workflow_kind": workflow_kind,
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

    Called by the shared pre-dispatch wall, so the refusal lands BEFORE
    admission: the item is never claimed, no assignee is set, and no factory run
    exists to reap. That position is the whole requirement — the resolver one
    stage later already rejects the override, but by then the claim has happened
    and the operator is left with an `active` row nobody is working.

    THE SELECTION IS GRADED PER ITEM, which is what the clause asks for in a
    mixed-workflow loop: each item's own recorded variant decides its kind, so a
    wave carrying both kinds refuses on account of its implementation items and
    names exactly those. A selection that resolves entirely to groom-kind
    variants returns `None`, because every one of them has an ACP `pr` node the
    override legitimately configures.

    REPOSITORY CONFIGURATION IS DELIBERATELY NOT HANDLED HERE. It is the
    compatibility setting `scoped_repository_block` ignores and journals; a
    refusal here would make one configuration file unable to serve both kinds.

    The node name is read from the override's own LEFT-HAND SIDE, before any
    `=`, so a malformed value naming `pr` is refused for naming `pr` rather than
    falling through to the generic malformed-entry refusal one stage later —
    which would again be after the claim.
    """
    overrides = tuple(getattr(args, "acp_node", None) or ())
    if not any(_override_node(value=value) == PUBLICATION_ACP_NODE for value in overrides):
        return None
    explicit = getattr(args, "workflow_name", None)
    name = explicit if isinstance(explicit, str) and explicit else None
    implementation = sorted(
        item.id
        for item in items
        if not is_groom_variant(
            repo=repo,
            variant=previewed_workflow_variant(repo=repo, work_item_id=item.id, name=name),
        )
    )
    if not implementation:
        return None
    detail = (
        f"--acp-node {PUBLICATION_ACP_NODE}=... cannot apply to an implementation "
        f"dispatch: `{PUBLICATION_ACP_NODE}` is a command stage with no publication "
        "ACP adapter; remove the override "
        f"(implementation items: {', '.join(implementation)})"
    )
    journal.append(
        record={
            "stage": ACP_PUBLICATION_POLICY_STAGE,
            "work_item_ids": implementation,
            "result": "refused",
            "layer": "dispatch",
            "node": PUBLICATION_ACP_NODE,
            "reason": detail,
        }
    )
    return detail


def _override_node(*, value: str) -> str:
    """The node name one `--acp-node` value addresses, however malformed."""
    return value.partition("=")[0].strip()
