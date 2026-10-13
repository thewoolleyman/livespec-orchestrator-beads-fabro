"""A failed `fix` or `review_fix` stage ends through the needs-human terminal.

Binds the FIRST Definition-of-Done assertion of work-item `bd-ib-qhv7qs`
against `SPECIFICATION/scenarios.md` "Scenario 103 — A needs-human outcome
terminates the run and routes the decision to the ledger": a stage whose agent
turn times out — leaving, in the measured incidents, a half-authored Red-Green
pair at the branch head — ends the run through the STRUCTURED needs-human
ending with the tree preserved by reference, rather than as a deterministic
workflow error.

WHY THE EDGE IS THE WHOLE MECHANISM. Every other ACP node in the graph names
its failure route with a `condition="outcome=failed"` edge to the terminal and
lets the ordinary route be the unconditional fallthrough; `fix` and
`review_fix` were the only two that did not, so a failure there had NO
failure-handling edge at all. Measured twice on hp — run
01M44GMSVM66GX4P0A0D5PD1FP for `bd-ib-gp2nt5` and run
01M4HA8YVAAH21T5ZR1TVBDQYP for `bd-ib-4ipmub` — a `review_fix` turn that timed
out with a Red commit open ended the run `workflow_error` / `deterministic`,
pushed NO needs-human ref, and left the item `active` with no blocked reason.

TWO CONTROLS CARRY THIS MODULE, because the positive assertion alone is
satisfied by edits that break the factory or the ordinary route.

The UNCONDITIONAL FALLTHROUGH is asserted to survive, and to be the ONLY
unconditional out-edge each node declares. `fabro` rejects a node whose every
outgoing edge carries a condition (`all_conditional_edges`) — the defect that
took the whole factory down twice, on `review` in 2026-07-16 and on
`pr`/`verify_pr` in release 0.146.0, each time dying before any node ran — so
an edge added by consuming the fallthrough would route this ending correctly
and publish a graph no dispatch can load.

And the TARGET is asserted to be the terminal that actually PRESERVES: the
assertion under test is about an ending with the tree preserved by reference,
and an edge pointing at a node that merely exits non-zero would satisfy a
`-> needs_human` string match while losing the work the ending exists to save.
"""

from __future__ import annotations

import re
from pathlib import Path

_WORKFLOW_DOT = Path(".claude-plugin/.fabro/workflows/implement-work-item/workflow.fabro")
_TERMINAL = "needs_human"
_SENTINEL = "LIVESPEC_NEEDS_HUMAN"
_PRESERVED_REF_PREFIX = "refs/heads/needs-human/"
_FAILURE_CONDITION = 'condition="outcome=failed"'
# The two nodes the item names, each with the ordinary route it must keep.
_TIMEOUT_PRONE_STAGES = (("fix", "janitor"), ("review_fix", "janitor"))
_EDGE_RE = re.compile(r"^(?P<source>\w+)\s*->\s*(?P<target>\w+)\s*(?:\[(?P<attrs>.*)\])?$")


def _dot() -> str:
    assert _WORKFLOW_DOT.is_file()
    return _WORKFLOW_DOT.read_text(encoding="utf-8")


def _code_lines(text: str) -> list[str]:
    return [line.strip() for line in text.splitlines() if not line.strip().startswith("//")]


def _node_body(text: str, node: str) -> str | None:
    match = re.search(rf"^\s*{node}\s*\[(?P<body>.*?)^\s*\]", text, re.DOTALL | re.MULTILINE)
    return None if match is None else match.group("body")


def _out_edges(*, source: str) -> list[tuple[str, str]]:
    """Every out-edge the committed graph declares for one node, as (target, attrs).

    Parsed off the committed bytes rather than off a built plan, because the
    engine reads these bytes and an assertion about a derived structure cannot
    see an edge the DOT parse would drop.
    """
    edges: list[tuple[str, str]] = []
    for line in _code_lines(_dot()):
        match = _EDGE_RE.match(line)
        if match is None or match.group("source") != source:
            continue
        edges.append((match.group("target"), match.group("attrs") or ""))
    return edges


def test_a_failed_fix_or_review_fix_stage_routes_to_the_needs_human_terminal() -> None:
    """Each node names the terminal on an `outcome=failed` edge, as every sibling does."""
    for source, _ in _TIMEOUT_PRONE_STAGES:
        routed = [
            attrs
            for target, attrs in _out_edges(source=source)
            if target == _TERMINAL and _FAILURE_CONDITION in attrs
        ]
        assert routed != [], source


def test_each_routed_node_keeps_exactly_one_unconditional_ordinary_route() -> None:
    """The `all_conditional_edges` control: the fallthrough survives and still targets the loop."""
    for source, ordinary in _TIMEOUT_PRONE_STAGES:
        fallthrough = [
            target for target, attrs in _out_edges(source=source) if "condition=" not in attrs
        ]
        assert fallthrough == [ordinary], source


def test_the_routed_terminal_is_the_one_that_preserves_the_tree_by_reference() -> None:
    """The target preserves and emits the sentinel, so the ending is the structured one."""
    body = _node_body(_dot(), _TERMINAL)

    assert body is not None
    assert _PRESERVED_REF_PREFIX in body
    assert _SENTINEL in body
    assert not any(re.match(rf"^{_TERMINAL}\s*->", line) for line in _code_lines(_dot()))
