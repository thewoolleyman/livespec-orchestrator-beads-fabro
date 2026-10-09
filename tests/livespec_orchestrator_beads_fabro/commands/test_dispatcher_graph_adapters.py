"""Literal `acp.command` rendering for the dispatch payload's ACP nodes.

Plan `fabro-currency` P4 (`bd-ib-hti4zf`). Measured 2026-10-08 against the
Petri-era candidate `v0.378.0-nightly.0` and the pinned 0.254 production
engine (research notes 007 and 008): `backend="acp"` plus a LITERAL
`acp.command` string -- the adapter command with its leading `KEY=value`
environment prefix -- launches an ACP agent on BOTH engines, while a
TEMPLATED `acp.command` launches only on pinned and kills the agent before
the protocol completes on the candidate. So the engine-agnostic rendering
for every agent node is a literal, and the template indirection the
committed graph carries has to be resolved by the generator before
`fabro run` sees the graph.

The module import is deferred into each test body via `importlib`, and the
first assertion is a genuine check on the module path, so the Red of this
slice fails on an assertion rather than at collection.
"""

from __future__ import annotations

import importlib
import re
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[3]
_MODULE_NAME = "livespec_orchestrator_beads_fabro.commands._dispatcher_graph_adapters"
_MODULE_PATH = (
    _REPO_ROOT
    / ".claude-plugin"
    / "scripts"
    / "livespec_orchestrator_beads_fabro"
    / "commands"
    / "_dispatcher_graph_adapters.py"
)
_COMMITTED_GRAPH = (
    _REPO_ROOT
    / ".claude-plugin"
    / ".fabro"
    / "workflows"
    / "implement-work-item"
    / "workflow.fabro"
)

# The template opener written as a character class rather than as the literal
# pair, because the literal pair poisons ledger and goal rendering wherever
# this file's text is quoted (the fleet convention of livespec-dev-tooling-9yb4).
_OPENER_RE = re.compile(r"\{[{#%]")
_NODE_BLOCK_RE = re.compile(r"(?ms)^[ \t]*(?P<name>\w+)[ \t]*\[(?P<body>[^\]]*)\]")
_ACP_COMMAND_RE = re.compile(r'(?<![\w.])acp\.command[ \t]*=[ \t]*"(?P<value>[^"]*)"')

# One resolved adapter per input the committed graph's ACP nodes ride. The
# `review`-tier entries carry a leading `KEY=value` prefix, which is the half
# of the rendering the launch measurement turned on.
_CLAUDE = "npx -y @agentclientprotocol/claude-agent-acp"
_PREFIXED = f"ANTHROPIC_MODEL=claude-opus-4-8 CLAUDE_CODE_EFFORT_LEVEL=high {_CLAUDE}"
_ADAPTERS = {
    "dod_gate_adapter": _PREFIXED,
    "implement_adapter": _PREFIXED,
    "fix_adapter": _PREFIXED,
    "pr_adapter": _CLAUDE,
    "review_adapter": _PREFIXED,
    "disposition_adapter": _CLAUDE,
    "review_fix_adapter": _PREFIXED,
    "proof_capture_adapter": _PREFIXED,
    "proof_verify_adapter": _PREFIXED,
}

# A probe graph whose single ACP node's command is substituted by REPLACE
# rather than by `str.format`: DOT is full of braces, so a format call reads
# the graph's own syntax as field references and dies on it.
_COMMAND_SLOT = "COMMAND_SLOT"
_SYNTHETIC = """digraph Probe {
    graph [
        goal="probe"
    ]

    start [shape=Mdiamond, label="Start"]

    agent [
        label="Agent"
        backend="acp"
        acp.command="COMMAND_SLOT"
        timeout="1800s"
    ]

    gate [
        shape=parallelogram
        script="exit 0"
    ]

    start -> agent
    agent -> gate
    gate -> exit
}
"""

_TOKEN = "{" + "{ inputs.probe_adapter }" + "}"

# The quote-and-backslash-bearing shape the built-in Codex adapter resolves to:
# a SINGLE-quoted JSON object whose keys and values carry double quotes, and a
# JSON-escaped backslash inside one of them. Both forms are written as RAW
# strings so each one reads as the exact bytes it stands for -- the intent the
# dispatch record must report, and the DOT escString form the attribute must
# carry. `bd-ib-4gkfaa`: this pair used to be a refusal that blocked every
# dispatch of a repository whose adapter command carries a quote.
_QUOTED_INTENT = r"""CODEX_CONFIG='{"approval_policy":"never","path":"a\\b"}' codex-acp"""
_QUOTED_ESCAPED = (
    r"""CODEX_CONFIG='{\"approval_policy\":\"never\",\"path\":\"a\\\\b\"}' codex-acp"""
)


def _synthetic(*, command: str) -> str:
    """The probe graph with its one ACP node declaring `command`."""
    return _SYNTHETIC.replace(_COMMAND_SLOT, command, 1)


def _module() -> object:
    """The module under test, imported only once its file exists."""
    return importlib.import_module(_MODULE_NAME)


def _acp_bodies(*, text: str) -> dict[str, str]:
    """Each node block body that declares an `acp.command`, by node name."""
    return {
        match.group("name"): match.group("body")
        for match in _NODE_BLOCK_RE.finditer(text)
        if match.group("name") != "graph"
        and _ACP_COMMAND_RE.search(match.group("body")) is not None
    }


def test_the_renderer_module_exists_at_its_mirrored_path() -> None:
    """The generator half of the port is its own module, beside the timeout rewrite."""
    assert _MODULE_PATH.is_file()


def test_every_acp_node_renders_backend_acp_and_a_literal_command() -> None:
    """The committed graph's ACP nodes each resolve to their adapter, verbatim."""
    assert _MODULE_PATH.is_file()
    module = _module()
    rendered = module.render_acp_commands(  # pyright: ignore[reportAttributeAccessIssue]
        graph_text=_COMMITTED_GRAPH.read_text(encoding="utf-8"),
        adapters=_ADAPTERS,
    )
    assert not isinstance(rendered, str), rendered
    bodies = _acp_bodies(text=rendered.text)
    assert set(bodies) == set(rendered.node_commands)
    assert bodies != {}
    for node, body in bodies.items():
        assert 'backend="acp"' in body, node
        declared = _ACP_COMMAND_RE.search(body)
        assert declared is not None, node
        assert declared.group("value") == rendered.node_commands[node], node
        assert declared.group("value") in _ADAPTERS.values(), node


def test_no_template_token_survives_in_any_acp_node_attribute() -> None:
    """The whole point of the rewrite: an ACP node block carries no opener at all."""
    assert _MODULE_PATH.is_file()
    module = _module()
    rendered = module.render_acp_commands(  # pyright: ignore[reportAttributeAccessIssue]
        graph_text=_COMMITTED_GRAPH.read_text(encoding="utf-8"),
        adapters=_ADAPTERS,
    )
    assert not isinstance(rendered, str), rendered
    for node, body in _acp_bodies(text=rendered.text).items():
        assert _OPENER_RE.search(body) is None, node


def test_a_prefixed_adapter_keeps_its_leading_key_value_assignments() -> None:
    """The `KEY=value` prefix is what the engine peels into the agent's environment."""
    assert _MODULE_PATH.is_file()
    module = _module()
    rendered = module.render_acp_commands(  # pyright: ignore[reportAttributeAccessIssue]
        graph_text=_synthetic(command=_TOKEN),
        adapters={"probe_adapter": _PREFIXED},
    )
    assert not isinstance(rendered, str), rendered
    assert rendered.node_commands == {"agent": _PREFIXED}
    assert f'acp.command="{_PREFIXED}"' in rendered.text


def test_an_already_literal_command_is_left_exactly_as_declared() -> None:
    """A graph carrying no indirection renders to itself, not to a refusal."""
    assert _MODULE_PATH.is_file()
    module = _module()
    rendered = module.render_acp_commands(  # pyright: ignore[reportAttributeAccessIssue]
        graph_text=_synthetic(command=_CLAUDE),
        adapters={},
    )
    assert not isinstance(rendered, str), rendered
    assert rendered.text == _synthetic(command=_CLAUDE)
    assert rendered.node_commands == {"agent": _CLAUDE}


def test_an_unresolvable_adapter_input_refuses_naming_the_node_and_input() -> None:
    """No run is created on a half-rendered graph: the dispatch refuses first."""
    assert _MODULE_PATH.is_file()
    module = _module()
    refusal = module.render_acp_commands(  # pyright: ignore[reportAttributeAccessIssue]
        graph_text=_synthetic(command=_TOKEN),
        adapters={},
    )
    assert isinstance(refusal, str)
    assert "agent" in refusal
    assert "probe_adapter" in refusal


def test_a_template_shape_this_rewrite_cannot_resolve_refuses() -> None:
    """An opener that is not an `inputs.<name>` reference is refused, never shipped."""
    assert _MODULE_PATH.is_file()
    module = _module()
    refusal = module.render_acp_commands(  # pyright: ignore[reportAttributeAccessIssue]
        graph_text=_synthetic(command="{" + "{ secrets.TOKEN }" + "}"),
        adapters={},
    )
    assert isinstance(refusal, str)
    assert "agent" in refusal


def test_an_acp_command_without_the_acp_backend_refuses() -> None:
    """`backend="acp"` is the attribute the candidate engine fails the node without."""
    assert _MODULE_PATH.is_file()
    module = _module()
    graph = _synthetic(command=_CLAUDE).replace('        backend="acp"\n', "", 1)
    refusal = module.render_acp_commands(  # pyright: ignore[reportAttributeAccessIssue]
        graph_text=graph,
        adapters={},
    )
    assert isinstance(refusal, str)
    assert "agent" in refusal
    assert "acp" in refusal


def test_a_resolved_command_carrying_a_quote_renders_dot_escaped() -> None:
    """A quote or a backslash is escaped into the attribute, not refused."""
    assert _MODULE_PATH.is_file()
    module = _module()
    rendered = module.render_acp_commands(  # pyright: ignore[reportAttributeAccessIssue]
        graph_text=_synthetic(command=_TOKEN),
        adapters={"probe_adapter": _QUOTED_INTENT},
    )
    assert not isinstance(rendered, str), rendered
    assert f'acp.command="{_QUOTED_ESCAPED}"' in rendered.text


def test_the_record_reports_the_escaped_command_unescaped() -> None:
    """The escape is a DOT transport detail, so the record reports the intent."""
    assert _MODULE_PATH.is_file()
    module = _module()
    rendered = module.render_acp_commands(  # pyright: ignore[reportAttributeAccessIssue]
        graph_text=_synthetic(command=_TOKEN),
        adapters={"probe_adapter": _QUOTED_INTENT},
    )
    assert not isinstance(rendered, str), rendered
    assert rendered.node_commands == {"agent": _QUOTED_INTENT}


def test_a_surviving_opener_elsewhere_in_an_acp_block_refuses() -> None:
    """The guarantee is per BLOCK, so an opener in a sibling attribute still refuses."""
    assert _MODULE_PATH.is_file()
    module = _module()
    templated_timeout = '        timeout="{' + "{ inputs.agent_timeout }" + '}"'
    graph = _synthetic(command=_TOKEN).replace('        timeout="1800s"', templated_timeout, 1)
    refusal = module.render_acp_commands(  # pyright: ignore[reportAttributeAccessIssue]
        graph_text=graph,
        adapters={"probe_adapter": _CLAUDE},
    )
    assert isinstance(refusal, str)
    assert "agent" in refusal


def test_resolved_run_inputs_become_guarded_commands_by_input_name() -> None:
    """The mapping the generator consumes is the SAME resolution the launch renders."""
    assert _MODULE_PATH.is_file()
    module = _module()
    commands = module.guarded_adapter_commands(  # pyright: ignore[reportAttributeAccessIssue]
        run_inputs=(f"probe_adapter={_PREFIXED}",)
    )
    assert set(commands) == {"probe_adapter"}
    guarded = commands["probe_adapter"]
    assert guarded.startswith("ANTHROPIC_MODEL=claude-opus-4-8 ")
    assert guarded != _PREFIXED
