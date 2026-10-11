"""Per-node timeout resolution and literal rendering (Scenario 89).

Every node timeout of the `implement-work-item` graph is configuration, not
a literal nobody revisits: `dispatcher.node_timeouts` keys them by node,
`dispatcher.stall_timeout_seconds` keys the run-level watchdog, and an
unconfigured node resolves to 1800 seconds.

The rendering half is what these tests exist to pin. A `timeout` attribute
CANNOT be templated from a workflow input on the pinned Fabro build -- the
duration is typed at parse time and template expansion never re-types a
rendered string, so a templated timeout silently leaves the node with NO
timeout at all. So the Dispatcher writes resolved values into the
per-dispatch payload's copy of the graph as literal durations, and the
tests below assert that no rendered timeout attribute carries a template
opener for either a configured or a default target.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._config import resolve_node_timeouts
from livespec_orchestrator_beads_fabro.commands._dispatcher_graph_render import (
    render_workflow_graph,
)
from livespec_orchestrator_beads_fabro.commands._node_timeouts import (
    DEFAULT_FABRO_TIMEOUT_SECONDS,
    NodeTimeouts,
    default_node_timeouts,
    derive_fabro_timeout_seconds,
    node_timeouts_from_block,
    node_timeouts_journal_record,
)

_CONFIG_NAME = ".livespec.jsonc"
_TIMEOUT_ATTR_RE = re.compile(r'(?<![\w.])timeout[ \t]*=[ \t]*"(?P<value>[^"]*)"')
_TEMPLATE_OPENERS = ("{" "{", "{" "%", "{" "#")

_GRAPH = """digraph ImplementWorkItem {
    graph [
        goal="Implement one ready work-item"
        stall_timeout="7200s"
    ]

    start [shape=Mdiamond, label="Start"]

    implement [
        backend="acp"
        timeout="14400s"
        prompt="@prompts/implement.md"
    ]

    janitor [
        shape=parallelogram
        timeout="3600s"
        script="mise exec -- just check"
    ]

    review -> pr [label="approve", condition="preferred_label=approve"]
}
"""


def _write_dispatcher_config(*, cwd: Path, dispatcher: dict[str, object]) -> None:
    _ = (cwd / _CONFIG_NAME).write_text(
        json.dumps({"livespec-orchestrator-beads-fabro": {"dispatcher": dispatcher}}),
        encoding="utf-8",
    )


def _rendered_timeouts(*, text: str) -> list[str]:
    return [match.group("value") for match in _TIMEOUT_ATTR_RE.finditer(text)]


def test_unconfigured_target_resolves_every_node_to_1800_seconds(tmp_path: Path) -> None:
    """A dispatch target with no node_timeouts table renders 1800s everywhere."""
    timeouts = resolve_node_timeouts(cwd=tmp_path)
    assert isinstance(timeouts, NodeTimeouts)
    rendered = render_workflow_graph(committed_text=_GRAPH, timeouts=timeouts)
    assert not isinstance(rendered, str)
    assert _rendered_timeouts(text=rendered.text) == ["1800s", "1800s"]
    assert 'stall_timeout="7200s"' in rendered.text
    assert rendered.node_seconds == {"implement": 1800, "janitor": 1800}
    assert timeouts.layer_for(node="implement") == "default"


def test_configured_node_keeps_its_value_and_others_take_the_default(tmp_path: Path) -> None:
    """A configured implement timeout wins; every other node stays at 1800s."""
    _write_dispatcher_config(
        cwd=tmp_path,
        dispatcher={"node_timeouts": {"implement": 7200}, "stall_timeout_seconds": 9000},
    )
    timeouts = resolve_node_timeouts(cwd=tmp_path)
    assert isinstance(timeouts, NodeTimeouts)
    rendered = render_workflow_graph(committed_text=_GRAPH, timeouts=timeouts)
    assert not isinstance(rendered, str)
    assert rendered.node_seconds == {"implement": 7200, "janitor": 1800}
    assert 'timeout="7200s"' in rendered.text
    assert 'stall_timeout="9000s"' in rendered.text
    assert timeouts.layer_for(node="implement") == "repository"
    assert timeouts.layer_for(node="janitor") == "default"
    assert timeouts.stall_layer == "repository"


def test_rendered_timeouts_carry_no_template_opener(tmp_path: Path) -> None:
    """Neither a configured nor a default target renders a templated timeout."""
    _write_dispatcher_config(cwd=tmp_path, dispatcher={"node_timeouts": {"implement": 7200}})
    configured = resolve_node_timeouts(cwd=tmp_path)
    defaulted = default_node_timeouts()
    assert isinstance(configured, NodeTimeouts)
    for timeouts in (configured, defaulted):
        rendered = render_workflow_graph(committed_text=_GRAPH, timeouts=timeouts)
        assert not isinstance(rendered, str)
        for value in _rendered_timeouts(text=rendered.text):
            assert not any(opener in value for opener in _TEMPLATE_OPENERS)
            assert value.endswith("s")


def test_committed_graph_renders_every_declared_timeout(tmp_path: Path) -> None:
    """The shipped graph's timeouts are all reached by the rewrite."""
    _ = tmp_path
    graph = (
        Path(__file__).resolve().parents[3]
        / ".claude-plugin"
        / ".fabro"
        / "workflows"
        / "implement-work-item"
        / "workflow.fabro"
    )
    committed_text = graph.read_text(encoding="utf-8")
    rendered = render_workflow_graph(
        committed_text=committed_text, timeouts=default_node_timeouts()
    )
    assert not isinstance(rendered, str)
    assert set(_rendered_timeouts(text=rendered.text)) == {"1800s"}
    assert "implement" in rendered.node_seconds
    assert 'stall_timeout="7200s"' in rendered.text


def test_non_positive_timeout_is_rejected_naming_the_key() -> None:
    """A zero timeout refuses, and the refusal names the offending key."""
    refusal = node_timeouts_from_block(block={"node_timeouts": {"implement": 0}})
    assert isinstance(refusal, str)
    assert "dispatcher.node_timeouts.implement" in refusal


def test_non_integer_timeout_is_rejected_naming_the_key() -> None:
    """A non-integer timeout refuses, booleans included."""
    for value in ("1800", 1800.5, True):
        refusal = node_timeouts_from_block(block={"node_timeouts": {"fix": value}})
        assert isinstance(refusal, str)
        assert "dispatcher.node_timeouts.fix" in refusal


def test_non_table_node_timeouts_is_rejected() -> None:
    """A node_timeouts value that is not a table refuses, naming the key."""
    refusal = node_timeouts_from_block(block={"node_timeouts": 1800})
    assert isinstance(refusal, str)
    assert "dispatcher.node_timeouts" in refusal


def test_invalid_stall_timeout_is_rejected_naming_the_key() -> None:
    """A non-positive stall timeout refuses before any run exists."""
    refusal = node_timeouts_from_block(block={"stall_timeout_seconds": -1})
    assert isinstance(refusal, str)
    assert "dispatcher.stall_timeout_seconds" in refusal


def test_subprocess_ceiling_follows_the_resolved_graph() -> None:
    """A longer resolved node lengthens the derived ceiling by its own budget."""
    default_ceiling = derive_fabro_timeout_seconds(timeouts=default_node_timeouts())
    assert default_ceiling == DEFAULT_FABRO_TIMEOUT_SECONDS
    longer = NodeTimeouts(
        configured={"implement": 14400},
        stall_seconds=7200,
        stall_layer="default",
    )
    # `implement` carries two worst-case attempts, so the ceiling grows by
    # twice the increase over the 1800-second default.
    assert derive_fabro_timeout_seconds(timeouts=longer) == default_ceiling + 2 * (14400 - 1800)


def test_ceiling_never_falls_below_the_stall_watchdog() -> None:
    """A stall window longer than the whole graph still fits under the ceiling."""
    stalling = NodeTimeouts(configured={}, stall_seconds=200_000, stall_layer="repository")
    assert derive_fabro_timeout_seconds(timeouts=stalling) > 200_000


def test_journal_record_names_the_supplying_layer_per_node() -> None:
    """The dispatch record reports rendered seconds and the layer behind them."""
    timeouts = NodeTimeouts(
        configured={"implement": 7200},
        stall_seconds=7200,
        stall_layer="default",
    )
    record = node_timeouts_journal_record(
        timeouts=timeouts,
        nodes={"implement": 7200, "janitor": 1800},
    )
    assert record["node_timeouts"] == {
        "implement": {"seconds": 7200, "layer": "repository"},
        "janitor": {"seconds": 1800, "layer": "default"},
    }
    assert record["stall_timeout"] == {"seconds": 7200, "layer": "default"}
    assert record["fabro_timeout_seconds"] == derive_fabro_timeout_seconds(timeouts=timeouts)


def test_graph_without_a_stall_timeout_is_refused() -> None:
    """A graph the rewrite does not understand refuses rather than half-renders."""
    refusal = render_workflow_graph(
        committed_text='digraph G {\n    implement [\n        timeout="60s"\n    ]\n}\n',
        timeouts=default_node_timeouts(),
    )
    assert isinstance(refusal, str)
    assert "stall_timeout" in refusal


def test_timeout_outside_any_node_block_is_refused() -> None:
    """A timeout the node scan cannot reach refuses the dispatch."""
    orphaned = (
        'digraph G {\n    graph [\n        stall_timeout="7200s"\n    ]\n    timeout="60s"\n}\n'
    )
    refusal = render_workflow_graph(committed_text=orphaned, timeouts=default_node_timeouts())
    assert isinstance(refusal, str)
    assert "timeout attributes are declared" in refusal
