"""Workflow-kind policy for the retired implementation `pr` ACP adapter."""

from __future__ import annotations

from livespec_orchestrator_beads_fabro.commands._dispatcher_acp_publication_policy import (
    GROOM_ONLY_ACP_NODES,
    IMPLEMENTATION_PR_NOT_APPLIED_REASON,
    PUBLICATION_ACP_NODE,
    scoped_repository_block,
)
from livespec_orchestrator_beads_fabro.commands._workflow_variant_kind import (
    WORKFLOW_KIND_GROOM,
    WORKFLOW_KIND_IMPLEMENT,
)


def test_repository_pr_is_scoped_only_for_implementation() -> None:
    """Four shapes, and only one of them loses the entry.

    The three non-dropping arms are asserted to return the block UNCHANGED
    rather than merely equal, because that identity is what keeps a groom
    dispatch — and an implementation dispatch against a repository configuring
    no `pr` — byte-identical to what it resolved before this policy existed.

    The dropping arm additionally asserts the CALLER'S mapping is untouched. The
    nested table is copied, so a caller still holding the block it read sees its
    own `pr` entry; a shallow-only copy would mutate it under them, and nothing
    downstream would report that the configuration they thought they read had
    changed.
    """
    block: dict[str, object] = {
        "acp_nodes": {"pr": {"command": "legacy"}, "review": {"command": "review"}},
        "other": "preserved",
    }

    groom, groom_audit = scoped_repository_block(block=block, workflow_kind=WORKFLOW_KIND_GROOM)
    assert groom is block
    assert groom_audit == ()

    malformed: dict[str, object] = {"acp_nodes": "invalid-but-unrelated"}
    untouched, untouched_audit = scoped_repository_block(
        block=malformed, workflow_kind=WORKFLOW_KIND_IMPLEMENT
    )
    assert untouched is malformed
    assert untouched_audit == ()

    without_pr: dict[str, object] = {"acp_nodes": {"review": {"command": "review"}}}
    no_pr, no_pr_audit = scoped_repository_block(
        block=without_pr, workflow_kind=WORKFLOW_KIND_IMPLEMENT
    )
    assert no_pr is without_pr
    assert no_pr_audit == ()

    implementation, audit = scoped_repository_block(
        block=block, workflow_kind=WORKFLOW_KIND_IMPLEMENT
    )
    assert implementation == {
        "acp_nodes": {"review": {"command": "review"}},
        "other": "preserved",
    }
    assert block["acp_nodes"] == {"pr": {"command": "legacy"}, "review": {"command": "review"}}
    assert audit == (
        {
            "layer": "repository",
            "node": "pr",
            "entry": "dispatcher.acp_nodes.pr",
            "workflow_kind": WORKFLOW_KIND_IMPLEMENT,
            "reason": IMPLEMENTATION_PR_NOT_APPLIED_REASON,
        },
    )


def test_the_groom_only_set_is_exactly_the_publication_node() -> None:
    """One node, named once, so the policy and the registries cannot diverge."""
    assert frozenset({PUBLICATION_ACP_NODE}) == GROOM_ONLY_ACP_NODES
    assert PUBLICATION_ACP_NODE == "pr"
