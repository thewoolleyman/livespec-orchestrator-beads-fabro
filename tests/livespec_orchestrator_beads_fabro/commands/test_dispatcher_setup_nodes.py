"""Sandbox setup as explicit command nodes (work-item bd-ib-dpsiwz).

Upstream Fabro refuses `run.prepare` from `v0.396.0-nightly.0`, so the plugin's
setup chain -- the committed provisioning steps plus every step the Dispatcher
materializes into the overlay -- has to be graph nodes after `start`. These cases
bind the shape `_dispatcher_setup_nodes` gives them: the names the carrier's
re-prepare recognises, the order the steps ran in, the failure route that ends the
run, and the lifting of the steps out of a rendered overlay without losing one.
"""

from __future__ import annotations

import re

import pytest
from livespec_orchestrator_beads_fabro.commands._dispatcher_dot_graph import (
    DotGraph,
    parse_dot_graph,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_minijinja_escape import (
    escape_minijinja_literal,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_prepare_payload import PrepareStep
from livespec_orchestrator_beads_fabro.commands._dispatcher_setup_nodes import (
    SETUP_FAILURE_NODE,
    SETUP_FAILURE_SCRIPT,
    is_setup_node,
    setup_chain_tail,
    setup_node_names,
    splice_setup_nodes,
    split_prepare_steps,
)
from livespec_orchestrator_beads_fabro.commands._node_timeouts import (
    WORKFLOW_DEFAULT_LAYER,
    NodeTimeouts,
)

_GRAPH = """digraph G {
    graph [goal="g", default_max_retries=0, stall_timeout="7200s"]
    start [shape=Mdiamond, label="Start"]
    exit [shape=Msquare, label="Exit"]
    dod_gate [
        label="gate"
        timeout="1800s"
        script="echo gate"
    ]
    start -> dod_gate
    dod_gate -> exit
}
"""

_CHAINED = """digraph G {
    graph [goal="g", default_max_retries=0, stall_timeout="7200s"]
    start [shape=Mdiamond, label="Start"]
    exit [shape=Msquare, label="Exit"]
    run_prepare_2 [label="b", shape=parallelogram, timeout="1800s", script="echo b"]
    run_prepare_10 [label="c", shape=parallelogram, timeout="1800s", script="echo c"]
    run_prepare_1 [label="a", shape=parallelogram, timeout="1800s", script="echo a"]
    setup_failed [label="f", shape=parallelogram, timeout="600s", script="exit 1"]
    dod_gate [label="gate", timeout="1800s", script="echo gate"]
    start -> run_prepare_1
    run_prepare_1 -> run_prepare_2
    run_prepare_2 -> run_prepare_10
    run_prepare_10 -> dod_gate
    run_prepare_1 -> setup_failed [label="x", condition="outcome=failed"]
    dod_gate -> exit
}
"""

_OPENERS = re.compile(r'\{\{ "(\{\{|\{%|\{#)" \}\}')


def _parsed(*, text: str) -> DotGraph:
    graph = parse_dot_graph(text=text)
    assert not isinstance(graph, str), graph
    return graph


def _rendered(*, value: str) -> str:
    """What the engine's template pass hands the node: the escaped openers, restored."""
    return _OPENERS.sub(lambda found: found.group(1), value)


def _unconditional(*, graph: DotGraph, source: str) -> list[str]:
    return [
        edge.destination
        for edge in graph.edges
        if edge.source == source and "condition" not in edge.attributes
    ]


def _spliced(
    *, steps: list[PrepareStep], text: str = _GRAPH, timeouts: NodeTimeouts | None = None
) -> DotGraph:
    result = splice_setup_nodes(graph_text=text, steps=steps, timeouts=timeouts)
    assert result is not None
    return _parsed(text=result)


def test_the_new_nodes_run_between_start_and_the_old_destination_in_step_order() -> None:
    graph = _spliced(steps=[PrepareStep(script="one"), PrepareStep(script="two")])
    assert setup_node_names(graph=graph) == ("run_prepare_1", "run_prepare_2")
    assert _unconditional(graph=graph, source="start") == ["run_prepare_1"]
    assert _unconditional(graph=graph, source="run_prepare_1") == ["run_prepare_2"]
    assert _unconditional(graph=graph, source="run_prepare_2") == ["dod_gate"]
    assert graph.nodes["run_prepare_1"]["script"] == "one"
    assert graph.nodes["run_prepare_2"]["script"] == "two"


def test_every_new_node_routes_a_failure_to_the_terminal_setup_node() -> None:
    graph = _spliced(steps=[PrepareStep(script="one"), PrepareStep(script="two")])
    for name in ("run_prepare_1", "run_prepare_2"):
        failures = [
            edge
            for edge in graph.edges
            if edge.source == name and edge.attributes.get("condition") == "outcome=failed"
        ]
        assert [edge.destination for edge in failures] == [SETUP_FAILURE_NODE]
        assert len(_unconditional(graph=graph, source=name)) == 1
    terminal = graph.nodes[SETUP_FAILURE_NODE]
    assert terminal["script"] == SETUP_FAILURE_SCRIPT
    assert [edge for edge in graph.edges if edge.source == SETUP_FAILURE_NODE] == []


def test_a_new_node_is_a_command_node_carrying_its_timeout_before_its_script() -> None:
    result = splice_setup_nodes(graph_text=_GRAPH, steps=[PrepareStep(script="one")])
    assert result is not None
    block = result.split("run_prepare_1 [", 1)[1].split("]\n", 1)[0]
    assert block.index("timeout=") < block.index("script=")
    node = _parsed(text=result).nodes["run_prepare_1"]
    assert node["shape"] == "parallelogram"
    assert node["timeout"] == "1800s"


def test_a_configured_timeout_for_a_setup_node_name_is_what_the_node_receives() -> None:
    timeouts = NodeTimeouts(
        configured={"run_prepare_2": 90},
        stall_seconds=7200,
        stall_layer=WORKFLOW_DEFAULT_LAYER,
    )
    graph = _spliced(steps=[PrepareStep(script="a"), PrepareStep(script="b")], timeouts=timeouts)
    assert graph.nodes["run_prepare_1"]["timeout"] == "1800s"
    assert graph.nodes["run_prepare_2"]["timeout"] == "90s"


def test_the_chain_continues_after_the_committed_tail_in_numeric_order() -> None:
    graph = _spliced(steps=[PrepareStep(script="x"), PrepareStep(script="y")], text=_CHAINED)
    assert setup_chain_tail(graph=_parsed(text=_CHAINED)) == "run_prepare_10"
    assert setup_node_names(graph=graph)[-2:] == ("run_prepare_11", "run_prepare_12")
    assert _unconditional(graph=graph, source="run_prepare_10") == ["run_prepare_11"]
    assert _unconditional(graph=graph, source="run_prepare_12") == ["dod_gate"]
    assert graph.nodes["run_prepare_11"]["script"] == "x"


def test_a_graph_that_already_declares_the_terminal_node_keeps_exactly_one() -> None:
    result = splice_setup_nodes(graph_text=_CHAINED, steps=[PrepareStep(script="x")])
    assert result is not None
    assert len(re.findall(rf"(?m)^\s*{SETUP_FAILURE_NODE} \[", result)) == 1
    assert _parsed(text=result).nodes[SETUP_FAILURE_NODE]["script"] == "exit 1"


def test_a_value_is_stored_so_the_engine_renders_it_back_verbatim() -> None:
    script = 'echo "a\\b"; printf \'%s\' "{{ x }} {% y %} {# z #} ${#v}"\nsecond line'
    graph = _spliced(steps=[PrepareStep(script=script)])
    stored = graph.nodes["run_prepare_1"]["script"]
    assert stored == escape_minijinja_literal(text=script)
    assert _rendered(value=stored) == script


def test_no_steps_leave_the_graph_text_untouched() -> None:
    assert splice_setup_nodes(graph_text=_GRAPH, steps=[]) == _GRAPH


@pytest.mark.parametrize(
    "text",
    [
        'digraph G {\n start [shape=Mdiamond]\n exit [shape=Msquare]\n start -> exit [label="x"]\n}\n',
        "digraph G {\n start [shape=Mdiamond]\n start -> ghost\n}\n",
        "not a graph",
    ],
    ids=["no-unconditional-tail-edge", "edge-to-an-undeclared-node", "unparseable"],
)
def test_a_graph_the_chain_cannot_be_hung_on_is_refused(text: str) -> None:
    assert splice_setup_nodes(graph_text=text, steps=[PrepareStep(script="a")]) is None


def test_is_setup_node_accepts_only_the_numbered_names() -> None:
    assert is_setup_node(name="run_prepare_7")
    assert not any(
        is_setup_node(name=name)
        for name in ("run_prepare_", "run_prepare_x", "run_prepare_1b", "xrun_prepare_1", "start")
    )


def test_a_graph_with_no_setup_nodes_has_start_for_its_tail() -> None:
    assert setup_chain_tail(graph=_parsed(text=_GRAPH)) == "start"


_OVERLAY = """[workflow]
graph = "workflow.fabro"

[run.environment]
id = "sandbox"

[[run.prepare.steps]]
script = "git fetch"

# a comment that belongs to the next block
[[run.prepare.steps]]
# a comment inside a block
script = "write"
env = { LIVESPEC_PREPARE_PAYLOAD = "p {{ q }}", Z = "z" }

[environments.sandbox.env]
CLAUDE_CODE_OAUTH_TOKEN = "t"
"""


def test_split_lifts_every_step_in_order_with_its_env() -> None:
    split = split_prepare_steps(overlay_text=_OVERLAY)
    assert split is not None
    assert [step.script for step in split.steps] == ["git fetch", "write"]
    assert split.steps[0].env == {}
    assert dict(split.steps[1].env) == {"LIVESPEC_PREPARE_PAYLOAD": "p {{ q }}", "Z": "z"}


def test_split_leaves_the_rest_of_the_overlay_exactly_as_it_was() -> None:
    split = split_prepare_steps(overlay_text=_OVERLAY)
    assert split is not None
    assert "run.prepare" not in split.overlay
    assert "[workflow]" in split.overlay
    assert "[environments.sandbox.env]" in split.overlay
    assert 'CLAUDE_CODE_OAUTH_TOKEN = "t"' in split.overlay
    assert "a comment that belongs to the next block" in split.overlay
    assert "a comment inside a block" not in split.overlay


def test_an_overlay_with_no_steps_splits_to_itself_and_no_steps() -> None:
    text = '[workflow]\ngraph = "workflow.fabro"\n'
    split = split_prepare_steps(overlay_text=text)
    assert split is not None
    assert (split.overlay, split.steps) == (text, ())


def test_an_overlay_whose_run_table_held_only_steps_still_splits() -> None:
    split = split_prepare_steps(overlay_text='[[run.prepare.steps]]\nscript = "x"\n')
    assert split is not None
    assert split.overlay == ""
    assert [step.script for step in split.steps] == ["x"]


@pytest.mark.parametrize(
    "text",
    [
        '[[run.prepare.steps]]\nscript = "x"\ntimeout = "5m"\n',
        '[[run.prepare.steps]]\nenv = { A = "1" }\n',
        '[[run.prepare.steps]]\nscript = """\nmulti\n"""\n',
        '[[ run.prepare.steps ]]\nscript = "x"\n',
        "this is = not [toml",
    ],
    ids=["unmodelled-key", "no-script", "multi-line-string", "unrecognised-header", "invalid"],
)
def test_split_refuses_text_it_cannot_remove_without_losing_a_step(text: str) -> None:
    assert split_prepare_steps(overlay_text=text) is None
