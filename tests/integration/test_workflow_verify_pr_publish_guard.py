"""The publish breaker: a pr stage that publishes nothing must not finish green.

Binds work-item `bd-ib-32xd` (the `bd-ib-loks` tail). The `pr` node is an ACP
node, and the pinned fabro build can report an ACP turn that ERRORED as
`outcome=succeeded` -- measured 2026-09-08/09, when an unsupported pr-tier model
slug drew an HTTP 400: the turn died, the node reported succeeded, the run took
`pr -> exit` and finished GREEN, and no publish branch and no pull request
existed. The Dispatcher's downstream report was a generic "no PR found for
branch", which reads as a defect in the WORK ITEM rather than in the pr stage.

The acceptance target is the SHIPPED graph at
`.claude-plugin/.fabro/workflows/implement-work-item/workflow.fabro`, read the
same way the `dead_implementer` breaker's own acceptance reads it, plus the two
production seams that consume a node: the Dispatcher's literal-duration graph
render, and the `fabro run` subprocess ceiling derived from the graph's
worst-case path.

TWO ASSERTIONS HERE EXIST BECAUSE THE OBVIOUS CHECK CANNOT FAIL. `verify_pr` is
worthless if `pr -> exit` survives beside it, so the exit edge is asserted to be
verify_pr's ALONE rather than merely present -- an added node with the old edge
left in place satisfies "the node exists" and changes nothing. And the node's
`script` is asserted to survive `render_workflow_graph`, because that rewrite
matches a node block with `[^\\]]*`: a `]` anywhere in a script body silently
truncates the block, the node's timeout never resolves, and the dispatch is
refused by a count mismatch that names no node.
"""

from __future__ import annotations

import re
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_graph_render import (
    RenderedGraph,
    render_workflow_graph,
)
from livespec_orchestrator_beads_fabro.commands._node_timeouts import (
    DEFAULT_FABRO_TIMEOUT_SECONDS,
    NodeTimeouts,
    default_node_timeouts,
    derive_fabro_timeout_seconds,
)

_REPO_ROOT = Path(__file__).resolve().parents[2]
_WORKFLOW_DOT = (
    _REPO_ROOT
    / ".claude-plugin"
    / ".fabro"
    / "workflows"
    / "implement-work-item"
    / "workflow.fabro"
)

_NOT_CREATED = "LIVESPEC_PR_NOT_CREATED"
_CHECK_FAILED = "LIVESPEC_PR_NOT_CREATED_CHECK_FAILED"


def _dot_text() -> str:
    return _WORKFLOW_DOT.read_text(encoding="utf-8")


def _verify_pr_body() -> str:
    """The `verify_pr` node's attribute body, or an empty string when absent."""
    block = re.search(r"\bverify_pr\s*\[(?P<body>[^\]]*)\]", _dot_text())
    return "" if block is None else block.group("body")


def test_verify_pr_is_a_script_breaker_in_the_existing_dot_vocabulary() -> None:
    """The guard is a plain script node, like the `implementation_diff` breaker."""
    body = _verify_pr_body()

    assert body != ""
    assert "shape=parallelogram" in body
    assert "script=" in body


def test_verify_pr_asserts_the_publish_branch_carries_this_runs_work() -> None:
    """The check reads origin, and matches a `feat/` head against this run's HEAD.

    Ancestry rather than sha equality is the load-bearing part: fabro commits a
    stage checkpoint once a node completes, so HEAD moves past the sha the pr
    node pushed and an equality test would fail every healthy run.
    """
    body = _verify_pr_body()

    assert "git ls-remote --heads origin" in body
    assert "refs/heads/feat/" in body
    assert "git merge-base --is-ancestor" in body


def test_verify_pr_emits_the_not_created_sentinel_when_nothing_was_published() -> None:
    """A reachable origin carrying no such branch fails with the sentinel.

    Matched WITH its trailing colon, because the unreachable-origin sentinel
    below has this one as a prefix: a bare substring probe passes on the wrong
    arm alone and could never report the missing one.
    """
    body = _verify_pr_body()

    assert f"{_NOT_CREATED}:" in body
    assert "exit 1" in body


def test_an_unanswerable_lookup_is_not_reported_as_an_unpublished_run() -> None:
    """An origin that could not answer carries its OWN sentinel and exit status.

    Both arms fail closed, so a single-sentinel design would pass a naive
    presence check while telling an operator the wrong thing about the run.
    """
    body = _verify_pr_body()

    assert f"{_CHECK_FAILED}:" in body


def test_the_pr_success_edge_routes_through_verify_pr_before_exit() -> None:
    """pr's success edge reaches verify_pr, and pr no longer reaches exit itself."""
    text = _dot_text()

    assert (
        re.search(r'\bpr\s*->\s*verify_pr\b[^\n]*condition="outcome=succeeded"', text) is not None
    )
    assert re.search(r"^\s*pr\s*->\s*exit\b", text, re.MULTILINE) is None


def test_verify_pr_owns_the_only_edge_into_exit() -> None:
    """Nothing else reaches exit, so the breaker cannot be routed around.

    The control that matters: `verify_pr` existing beside a surviving
    `pr -> exit` would satisfy every other assertion in this module and change
    nothing about the failure this guard exists to catch.
    """
    text = _dot_text()
    sources = set(re.findall(r"^\s*(\w+)\s*->\s*exit\b", text, re.MULTILINE))

    assert sources == {"verify_pr"}
    assert (
        re.search(r'\bverify_pr\s*->\s*exit\b[^\n]*condition="outcome=succeeded"', text) is not None
    )


def test_a_failed_verify_pr_routes_to_the_human_gate() -> None:
    """The breaker's failure lands the item at blocked / needs-human."""
    text = _dot_text()

    assert (
        re.search(
            r'\bverify_pr\s*->\s*needs_human\b[^\n]*condition="outcome=failed"',
            text,
        )
        is not None
    )


def test_the_dispatcher_resolves_a_literal_timeout_for_verify_pr() -> None:
    """The node survives the payload's literal-duration rewrite.

    A `]` in the script body would truncate the node block, leaving the node
    with no resolved timeout and refusing the dispatch on a count mismatch that
    names no node -- so this is the assertion that proves the graph is
    dispatchable, not merely well-worded.
    """
    rendered = render_workflow_graph(
        committed_text=_dot_text(),
        timeouts=default_node_timeouts(),
    )

    assert isinstance(rendered, RenderedGraph)
    assert rendered.node_seconds["verify_pr"] == 1800


def test_the_subprocess_ceiling_budgets_the_verify_pr_node() -> None:
    """The `fabro run` ceiling follows the graph, so a new main-path node counts."""
    lengthened = NodeTimeouts(
        configured={"verify_pr": 3600},
        stall_seconds=default_node_timeouts().stall_seconds,
        stall_layer="repository",
    )

    assert derive_fabro_timeout_seconds(timeouts=lengthened) > DEFAULT_FABRO_TIMEOUT_SECONDS
