"""Literal-adapter rendering of the dispatch payload's ACP node commands.

WHY THE COMMAND IS WRITTEN IN RATHER THAN TEMPLATED, and why this is not
re-litigable from the source: it was settled by launching agents against both
engines on 2026-10-08 (plan `fabro-currency`, research notes 007 and 008).
`backend="acp"` plus a LITERAL `acp.command` string -- the adapter command with
its leading `KEY=value` environment prefix -- launches an ACP agent on BOTH the
pinned 0.254 production engine and the Petri-era candidate
`v0.378.0-nightly.0`. A TEMPLATED `acp.command` launches only on pinned: on the
candidate the agent process exits before the protocol completes, because
upstream fabro 474 de-templated that attribute. And the `acp.config` JSON form
is the mirror image, launching only on the candidate. So the ONE rendering that
runs on both engines through the parallel-rollout overlap is a literal
`acp.command`, which is what this module writes.

GRAPH VALIDITY CANNOT ANSWER THIS. `fabro validate` on the candidate accepted
every ACP shape tried -- the JSON form, an unknown `acp.config` key, a templated
command and a literal one. A graph that validates therefore says nothing about
whether its agents launch, which is why the rewrite is enforced here by
refusal rather than left to the validator.

FAIL-CLOSED, PER NODE BLOCK. Every refusal below happens before any Fabro run
exists. A node declaring `acp.command` without `backend="acp"` is refused
because the candidate fails such a node at run creation ("backend=api cannot
use acp configuration"); and a template shape this rewrite does not understand
is refused rather than passed through, because an un-expanded token reaching
the engine is exactly the dead-agent case above.

A DOUBLE QUOTE OR A BACKSLASH IS ESCAPED, NOT REFUSED (`bd-ib-4gkfaa`). This
module used to refuse such a command on the ground that a value it could not
write VERBATIM is not the command the dispatch record claims the run received.
That ground was wrong: a DOT attribute string has a defined escape form -- a
backslash before a double quote or a backslash -- so the value IS writable, and
measured 2026-10-09 `fabro validate` accepts a graph carrying both escapes on
the candidate `v0.378.0-nightly.0` and on the pinned 0.254 client. The refusal
meanwhile blocked EVERY dispatch of a repository whose adapter command carries
a quote, which the built-in Codex adapter's single-quoted `CODEX_CONFIG` JSON
prefix requires.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from livespec_orchestrator_beads_fabro.commands._dispatcher_credential_use_guard import (
    guarded_adapter_string,
)

__all__: list[str] = [
    "ACP_BACKEND_ATTRIBUTE",
    "RenderedAcpCommands",
    "guarded_adapter_commands",
    "render_acp_commands",
]

# The attribute the candidate engine fails an agent node without, declared
# here as the exact text the graph carries so the check and the graph cannot
# drift into disagreeing about its spelling.
ACP_BACKEND_ATTRIBUTE = 'backend="acp"'

# A node's attribute list: a bare name at line start, then a bracketed body.
# The body admits no `]` of its own, which is what keeps a SINGLE-LINE node
# declaration (`start [shape=Mdiamond, ...]`) from swallowing the multi-line
# block that follows it. Edge lines (`a -> b [label=...]`) never match: the
# name must be followed directly by the bracket. This is the one shape proven
# against the committed graph, and it is deliberately the same pattern
# `_dispatcher_graph_render` scans with.
_NODE_BLOCK_RE = re.compile(r"(?ms)^[ \t]*(?P<name>\w+)[ \t]*\[(?P<body>[^\]]*)\]")

# The negative lookbehind keeps this from matching a longer attribute name
# that happens to end in `acp.command`.
_ACP_COMMAND_RE = re.compile(r'(?<![\w.])acp\.command[ \t]*=[ \t]*"(?P<value>[^"]*)"')

# A whole-value reference to one workflow input, which is the only template
# shape the committed graph's ACP nodes declare.
_INPUT_TOKEN_RE = re.compile(r"\{\{[ \t]*inputs\.(?P<name>\w+)[ \t]*\}\}")

# Any template opener, written as a character class rather than as the literal
# pair so quoting this module's text into a ledger comment or a run goal cannot
# poison the rendering (the fleet convention of livespec-dev-tooling-9yb4).
_OPENER_RE = re.compile(r"\{[{%#]")

_GRAPH_BLOCK_NAME = "graph"


def _dot_escaped(*, value: str) -> str:
    """`value` as a DOT escString: a backslash before each backslash and quote.

    The backslash substitution runs FIRST, so the backslash it introduces in
    front of a quote is not then escaped a second time.
    """
    return value.replace("\\", "\\\\").replace('"', '\\"')


@dataclass(frozen=True, kw_only=True)
class RenderedAcpCommands:
    """A workflow graph whose ACP nodes carry literal adapter commands.

    `node_commands` is what each ACP node's attribute actually received, so a
    caller reporting the rendering reports what was written rather than a
    re-derivation of it.
    """

    text: str
    node_commands: Mapping[str, str]


@dataclass(frozen=True, kw_only=True)
class _NodeRender:
    """One ACP node's rewritten attribute body and the command it received."""

    body: str
    command: str


def guarded_adapter_commands(*, run_inputs: Sequence[str]) -> Mapping[str, str]:
    """Each resolved `<input>=<adapter>` pair as input name to GUARDED command.

    The guard is spliced in here for the same reason the launch renderer
    splices it into its `--input` pairs: it wraps the exec that actually starts
    a coding agent, so the absolute credential-use deadline binds whichever
    route the engine takes to the adapter. Rendering the literal into the graph
    without it would create a second, unguarded launch path.
    """
    commands: dict[str, str] = {}
    for pair in run_inputs:
        name, _, rendered = pair.partition("=")
        commands[name] = guarded_adapter_string(rendered=rendered)
    return commands


def render_acp_commands(
    *, graph_text: str, adapters: Mapping[str, str]
) -> RenderedAcpCommands | str:
    """Rewrite every ACP node's `acp.command` to its resolved literal command.

    Returns the rendered graph, or an actionable refusal message naming the
    node that defeated the rewrite. A node declaring no `acp.command` is left
    untouched, which is what keeps the command nodes and the two graph-shape
    declarations out of this.
    """
    pieces: list[str] = []
    node_commands: dict[str, str] = {}
    cursor = 0
    for match in _NODE_BLOCK_RE.finditer(graph_text):
        name = match.group("name")
        body = match.group("body")
        if name != _GRAPH_BLOCK_NAME:
            rendered = _rendered_node(node=name, body=body, adapters=adapters)
            if isinstance(rendered, str):
                return rendered
            if rendered is not None:
                body = rendered.body
                node_commands[name] = rendered.command
        pieces.append(graph_text[cursor : match.start("body")])
        pieces.append(body)
        cursor = match.end("body")
    pieces.append(graph_text[cursor:])
    return RenderedAcpCommands(text="".join(pieces), node_commands=node_commands)


def _rendered_node(
    *, node: str, body: str, adapters: Mapping[str, str]
) -> _NodeRender | str | None:
    """This node's rewritten body, a refusal, or None when it is not an ACP node."""
    declared = _ACP_COMMAND_RE.search(body)
    if declared is None:
        return None
    if ACP_BACKEND_ATTRIBUTE not in body:
        return (
            f"workflow graph is not renderable: ACP node {node!r} declares an "
            f"acp.command without {ACP_BACKEND_ATTRIBUTE}, which the Petri-era "
            f"engine fails at run creation"
        )
    command = _resolved_command(node=node, declared=declared.group("value"), adapters=adapters)
    if isinstance(command, str):
        return command
    rewritten = f'{body[: declared.start()]}acp.command="{command.written}"{body[declared.end() :]}'
    if _OPENER_RE.search(rewritten) is not None:
        return (
            f"workflow graph is not renderable: ACP node {node!r} still carries a "
            f"template token after its acp.command was resolved, so the node would "
            f"reach the engine un-expanded"
        )
    return _NodeRender(body=rewritten, command=command.value)


@dataclass(frozen=True, kw_only=True)
class _Command:
    """One resolved adapter command in both forms, apart from a refusal string.

    `value` is the command as the adapter resolution produced it, which is what
    the dispatch record reports; `written` is the DOT escString form the
    attribute carries. The two differ only for a command carrying a double
    quote or a backslash, and keeping them apart is the whole reason the record
    does not claim the agent received the escapes. A command DECLARED literally
    in the committed graph is already graph bytes and passes through unchanged
    in both.
    """

    value: str
    written: str


def _resolved_command(*, node: str, declared: str, adapters: Mapping[str, str]) -> _Command | str:
    """The literal command this node's declared value resolves to, or a refusal."""
    token = _INPUT_TOKEN_RE.fullmatch(declared)
    if token is None:
        if _OPENER_RE.search(declared) is not None:
            return (
                f"workflow graph is not renderable: ACP node {node!r} declares an "
                f"acp.command template this rewrite does not understand; only a "
                f"whole-value workflow input reference resolves"
            )
        return _Command(value=declared, written=declared)
    name = token.group("name")
    if name not in adapters:
        return (
            f"workflow graph is not renderable: ACP node {node!r} rides workflow "
            f"input {name!r}, which this dispatch resolved no adapter for"
        )
    resolved = adapters[name]
    return _Command(value=resolved, written=_dot_escaped(value=resolved))
