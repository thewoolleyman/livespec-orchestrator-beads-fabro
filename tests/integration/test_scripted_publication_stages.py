"""Publication is SCRIPTED for implementation and an ACP turn only for groom.

`SPECIFICATION/contracts.md` section "Definition-of-Done and Proof-of-Done
stages" -> "Scripted publication and proof-head integrity" (ratified v121)
requires `pr_refresh` and `pr` to be COMMAND stages with their own resolved
timeouts "not agent turns", and retires the implementation `pr_adapter` input.
The same clause keeps the groom-kind variant's ACP `pr` node, because what it
publishes is a FILING PLAN for the host rather than a Git branch or a pull
request, and requires that variant to declare an UNREACHABLE command
`pr_refresh` so the common per-node timeout table still resolves against it.

WHY THIS IS A DECLARATION TEST RATHER THAN A BEHAVIOUR ONE. The assertion
under grade is about which KIND of stage performs publication, and that is a
property of the committed payload: a node carrying `backend="acp"` launches an
adapter however its script would have behaved, and a node carrying `script=`
cannot launch one. Reading the payload is therefore reading the thing the
assertion is about, not a proxy for it.

WHAT THIS FILE DOES NOT GRADE, STATED PER NODE, because a reader arrives here
to decide whether the runtime behaviour is covered and a claim made loosely
FORECLOSES the check that would catch a gap. Nothing below executes a single
byte of either script. The behaviour is covered one module per node, and the
two cover different things:

- `pr`'s own bytes -- the proof-head comparison, the title and body argv, the
  ready transition, and the arming bound to the verified head -- run in
  `test_scripted_publication_execution.py`, against real Git and a stub forge.
- `pr_refresh`'s own bytes -- the ownership test, the refresh bound, the
  conflict abort, the post-rebase gate and the leased push -- run in
  `test_scripted_refresh_execution.py`, against real Git and a real local bare
  remote.

Each module's first line says which node it executes. A claim here that some
other file covers a node is only as good as that file's node selection, so
read the extraction (`graph.nodes[...]`) rather than this paragraph. The
end-to-end form against a live factory is a HOST-CAPTURED assertion of the
same work-item and is covered by neither.
"""

from __future__ import annotations

import re
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_IMPLEMENT_DIR = _REPO_ROOT / ".claude-plugin" / ".fabro" / "workflows" / "implement-work-item"
_GROOM_DIR = _REPO_ROOT / ".fabro" / "workflows" / "groom-work-item"

_PUBLICATION_ADAPTER_TOKEN = "{{ inputs.pr_adapter }}"
_COMMAND_SHAPE = "shape=parallelogram"


def _node_block(*, dot: str, name: str) -> str | None:
    """One node's attribute body, or `None` when the graph declares no such node.

    An EDGE line never matches: the name must be followed directly by the
    opening bracket, which is the same discrimination `_dispatcher_graph_render`
    relies on. The body admits no `]` of its own so a single-line declaration
    cannot swallow the block that follows it.
    """
    found = re.search(rf"(?ms)^[ \t]*{re.escape(name)}[ \t]*\[(?P<body>[^\]]*)\]", dot)
    return None if found is None else found.group("body")


def _graph(*, directory: Path) -> str:
    return (directory / "workflow.fabro").read_text(encoding="utf-8")


def _run_config(*, directory: Path) -> str:
    return (directory / "workflow.toml").read_text(encoding="utf-8")


def _edge_targets(*, dot: str, source: str) -> list[str]:
    """Every node `source` declares an outgoing edge to."""
    return re.findall(rf"(?m)^[ \t]*{re.escape(source)}[ \t]*->[ \t]*(\w+)", dot)


def _edge_sources(*, dot: str, target: str) -> list[str]:
    """Every node declaring an outgoing edge INTO `target`."""
    return re.findall(rf"(?m)^[ \t]*(\w+)[ \t]*->[ \t]*{re.escape(target)}\b", dot)


def test_implementation_renders_pr_refresh_and_pr_as_command_stages() -> None:
    """Both publication stages are commands carrying their own timeout.

    The two attributes are asserted together because either alone is
    satisfiable by an agent turn: a node can carry a `script` the engine never
    reaches while `backend="acp"` launches an adapter, and a node can carry the
    command shape with no script at all.
    """
    dot = _graph(directory=_IMPLEMENT_DIR)
    for node in ("pr_refresh", "pr"):
        body = _node_block(dot=dot, name=node)
        assert body is not None, f"{node} is not declared in the implementation graph"
        assert _COMMAND_SHAPE in body, node
        assert "script=" in body, node
        assert "timeout=" in body, node
        assert "backend=" not in body, node
        assert "acp.command" not in body, node
        assert "prompt=" not in body, node


def test_implementation_declares_and_references_no_publication_adapter() -> None:
    """The retired `pr_adapter` input is rendered nowhere and consumed nowhere.

    Both halves matter: a lingering `[run.inputs]` declaration would keep the
    Dispatcher rendering an adapter no node reads, and a lingering token would
    keep a node reading an adapter nothing renders.
    """
    assert "pr_adapter" not in _run_config(directory=_IMPLEMENT_DIR)
    assert _PUBLICATION_ADAPTER_TOKEN not in _graph(directory=_IMPLEMENT_DIR)
    prompts = _IMPLEMENT_DIR / "prompts"
    assert not (prompts / "pr.md").exists(), "the retired publication prompt is still shipped"


def test_implementation_routes_a_changed_head_back_through_capture() -> None:
    """A refresh that republished the branch cannot reach `pr` unproven.

    The spec forbids publication from reusing a verified record from before a
    head change, so the graph -- not a script's good intentions -- is what has
    to carry the route back to `proof_capture`.

    SINCE v156 THE REPLAY REACHES THE REFRESH THROUGH `proof_grade`
    (bd-ib-kcq6pu), so the first leg is asserted in two hops rather than one.
    The claim is unchanged: a `verified` verdict reaches the refresh and nothing
    else does.
    """
    dot = _graph(directory=_IMPLEMENT_DIR)
    assert "proof_grade" in _edge_targets(dot=dot, source="proof_verify")
    assert "pr_refresh" in _edge_targets(dot=dot, source="proof_grade")
    assert "proof_capture" in _edge_targets(dot=dot, source="pr_refresh_head")
    assert "pr" in _edge_targets(dot=dot, source="pr_refresh_head")
    assert _edge_sources(dot=dot, target="pr") == ["pr_refresh_head"]
    # Every touched node keeps an UNCONDITIONAL outgoing edge: the pinned engine
    # rejects a node whose every outgoing edge carries a condition, before any
    # node runs.
    for source in ("proof_grade", "pr_refresh", "pr_refresh_head"):
        unconditional = re.findall(rf"(?m)^[ \t]*{source}[ \t]*->[ \t]*\w+[ \t]*$", dot)
        assert unconditional, source


def test_groom_retains_its_acp_filing_plan_publisher() -> None:
    """The groom variant's `pr` node is still an agent turn on `pr_adapter`.

    What it publishes is a filing plan for host-side filing, so it pushes no
    branch and opens no pull request -- which is why publication-adapter
    retirement does not reach it.
    """
    body = _node_block(dot=_graph(directory=_GROOM_DIR), name="pr")
    assert body is not None
    assert 'backend="acp"' in body
    assert _PUBLICATION_ADAPTER_TOKEN in body
    assert "pr_adapter" in _run_config(directory=_GROOM_DIR)


def test_groom_declares_an_unreachable_command_pr_refresh() -> None:
    """Declared so the common timeout table resolves; unreachable by its edges.

    The groom variant files slices and publishes no Git branch, so a reachable
    refresh would be meaningless; the DECLARATION is what the per-node timeout
    table and the node-name layers address, and an absent node would make them
    name something that is not there.
    """
    dot = _graph(directory=_GROOM_DIR)
    body = _node_block(dot=dot, name="pr_refresh")
    assert body is not None, "the groom variant declares no pr_refresh"
    assert _COMMAND_SHAPE in body
    assert "script=" in body
    assert "timeout=" in body
    assert _edge_sources(dot=dot, target="pr_refresh") == []


def test_groom_pr_refresh_carries_the_reserved_command_and_input_references() -> None:
    """Identical script bytes, so one refresh recipe cannot drift into two.

    The spec requires the unreachable declaration to carry "the same command
    and input references as the reserved `pr_refresh`"; comparing the rendered
    script attribute is what makes that a property rather than an intention.
    """
    reserved = _node_block(dot=_graph(directory=_IMPLEMENT_DIR), name="pr_refresh")
    groom = _node_block(dot=_graph(directory=_GROOM_DIR), name="pr_refresh")
    assert reserved is not None
    assert groom is not None
    script = re.compile(r'(?s)script="(?P<value>.*)"\s*$')
    reserved_script = script.search(reserved.strip())
    groom_script = script.search(groom.strip())
    assert reserved_script is not None
    assert groom_script is not None
    assert groom_script.group("value") == reserved_script.group("value")
