"""Whether a protected workflow's declared launches can be guarded at all.

WHY THIS EXISTS, and it is the repair of a measured defect rather than a
precaution. The launch renderer wraps every adapter it passes as a `fabro run
--input` pair, and that covers every launch in the graphs this repository ships,
because each of their ACP nodes declares `acp.command="{{ inputs.<node>_adapter
}}"`. It does NOT follow that every ACP node in every acceptable graph consumes
such an input. A node declaring a LITERAL command, or declaring its process
through `acp.config` instead, never reads the wrapped input at all -- so wrapping
the input protects nothing, and the agent runs unbounded.

That was MEASURED, not reasoned about: a control that took the shipped workflow
and replaced one node's `acp.command` input reference with a literal command saw
the requirement resolve, the guard install, the startup check pass, and the
literal command then execute 1.003 seconds AFTER the absolute deadline, exit 0.
The projection and the wrap were both working; the graph simply did not route
through them.

SO THE RULE IS FAIL-CLOSED ON ANYTHING UNRECOGNISED. A protected dispatch is
admitted only when EVERY ACP node declares exactly one launch attribute,
`acp.command`, and that value is one of exactly TWO recognised shapes: a
reference to an adapter input THIS dispatch wrapped, or a literal command whose
own executable position IS the projected guard. Every other shape is refused by
name before launch:

- a LITERAL command that does NOT run behind the guard, which the wrap never
  sees;
- a literal running behind the guard whose leading `KEY=value` prefix declares
  one of the credential-use enforcement variables, which would let the node hand
  itself any deadline it liked -- the same hazard `_acp_node_layers` refuses for
  a configured adapter, refused here for the rendered launch;
- `acp.config`, the pinned engine's JSON stdio form (`fabro-acp/src/command.rs`
  accepts either), which carries its own command, args and env;
- any other `acp.*` attribute, which includes graph-declared fallback candidates
  -- the pinned `acp_fallback/chain.rs` requires candidate zero's command to be
  byte-equal to the node's, and `acp.rs` builds a fresh process spec from EACH
  candidate's command, so wrapping only the primary would leave the rest
  unguarded;
- a reference to an input the dispatch did not wrap, which reaches the engine as
  the workflow's own unwrapped default.

REFUSING IS HONEST HERE AND SILENCE WOULD NOT BE. The alternative to a refusal is
not "a slightly weaker bound" -- it is a run that holds a live credential with no
enforcement while every surface reports the enforcement as present. A graph shape
this module cannot recognise may well be safe; what it may not be is COUNTED as
safe. An adopter who needs one of these shapes extends this recognition
deliberately, which is a change a reviewer can see.

WHY THE STRICT PARSER AND NOT THE ATTRIBUTE READER BESIDE IT. An earlier draft of
this module read the graph through `_acp_workflow_graph`, which is a FIRST-WINS
REGEX READER built for a different question, and that made it unsound for this one
in a way a control found immediately: appending a second `implement
[acp.command="/usr/bin/true"]` declaration to the shipped graph left this module
returning None -- admitted -- while the engine would launch `/usr/bin/true`. DOT
permits a node to be declared more than once, the pinned
`fabro-graphviz/src/parser/semantic.rs` `apply_node_stmt` UPDATES an existing
node's attributes, so a late declaration is a real launch route; the first-wins
reader skips it, and it is likewise not sound about same-line statements, escaped
brackets or comments. `parse_dot_graph` tokenizes properly and merges repeated
declarations last-wins, which is the engine's own semantics, so the attributes
graded here are the EFFECTIVE ones.

AND A NODE'S BACKEND IS NOT NECESSARILY WRITTEN ON THE NODE, which is the second
unsoundness a control found in this module. The pinned engine applies the graph's
`model_stylesheet` to every property a node leaves undeclared, and `backend` is
one of them, so `backend: acp` can arrive from a CSS-like rule. Keyed on the
literal attribute, this module read a stylesheet-selected ACP node as an ordinary
command node: removing only `implement`'s explicit `backend="acp"` from the
shipped graph, pointing its `acp.command` at a literal and adding
`model_stylesheet="#implement { backend: acp; }"` left the dispatch ADMITTED while
the engine would launch the literal unguarded. `nodes_with_effective_backend`
resolves that ladder -- and refuses an unreadable stylesheet or an undecidable
shape selector -- so the backend graded here is the EFFECTIVE one.

AND AN UNPARSEABLE GRAPH IS A REFUSAL, not an empty one. The reader it replaced was
total by construction -- a text it recognised nothing in yielded an empty graph --
which for this question means "no ACP nodes to check" and therefore admission. A
graph this module cannot read is a graph whose launches it cannot enumerate, and
that is exactly when it must not claim they are bounded.

WHY THE LITERAL SHAPE IS RECOGNISED AT ALL, since the paragraphs above exist
because a literal was the measured hole. It was added by plan `fabro-currency`
P4, which made the literal the ONLY launch shape that works: a TEMPLATED
`acp.command` kills the agent before the ACP protocol completes on the
Petri-era engine (upstream fabro 474 de-templated the attribute), so the
Dispatcher now renders each node's resolved, ALREADY-GUARDED adapter command
into the payload graph as a literal. Recognising it is not a relaxation -- it
is STRICTLY STRONGER evidence than the templated form, which only shows that
the wrap WOULD apply to whatever the input carried. This arm reads the
executable position of the command that will actually be exec'd and requires
the guard to be it, so a literal is admitted only when the guard is provably
first.

This module decides nothing about WHETHER protection is owed -- that is the
caller's, and it is owed exactly when a Codex credential is projected.
"""

from __future__ import annotations

import re
import shlex
from collections.abc import Mapping
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._acp_workflow_graph import ACP_BACKEND
from livespec_orchestrator_beads_fabro.commands._dispatcher_credential_use_guard import (
    CREDENTIAL_EXPIRY_ENV_VAR,
    CREDENTIAL_REQUIRED_REMAINING_ENV_VAR,
    CREDENTIAL_USE_DEADLINE_ENV_VAR,
    guarded_acp_command,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_dot_graph import parse_dot_graph
from livespec_orchestrator_beads_fabro.commands._dispatcher_graph_stylesheet import (
    nodes_with_effective_backend,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_overlay import workflow_graph_path

__all__: list[str] = [
    "selected_graph_launch_refusal",
    "unguardable_launch_refusal",
]

# The ONE launch shape the wrap reaches: the node's command IS the adapter input,
# with nothing around it. A value merely CONTAINING the reference is refused —
# surrounding text would reach the engine as part of the command line, so the
# guard would no longer be the first thing executed.
_TEMPLATED_INPUT_RE = re.compile(r"^\{\{\s*inputs\.(?P<name>\w+)\s*\}\}$")

_LAUNCH_ATTRIBUTE = "acp.command"
_ACP_ATTRIBUTE_PREFIX = "acp."

# An env assignment as POSIX tokenization recognizes one. Spelled here rather
# than imported from the guard module for the reason that module spells its own:
# the pattern is three characters of syntax, and reaching across for it buys
# nothing while coupling two modules that otherwise share only constants.
_ENV_ASSIGNMENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")

# The exact token sequence `guarded_acp_command` puts in front of an adapter's
# argv, derived from that function rather than spelled, so a change to the wrap
# cannot leave this recognition asserting a prefix nothing produces any more.
_GUARD_PREFIX: tuple[str, ...] = tuple(guarded_acp_command(argv=[]))

# The variables the guard itself reads. A launch whose own env prefix sets one
# would be choosing its own deadline, which is not a bound.
_ENFORCEMENT_ENV_VARS = frozenset(
    {
        CREDENTIAL_EXPIRY_ENV_VAR,
        CREDENTIAL_REQUIRED_REMAINING_ENV_VAR,
        CREDENTIAL_USE_DEADLINE_ENV_VAR,
    }
)

_GUIDANCE = (
    "A protected dispatch projects a live Codex credential, so every ACP node's "
    "launch must run behind the projected credential-use guard. Two shapes carry "
    'it: acp.command="{{ inputs.<adapter-input> }}", which the launch renderer '
    "wraps, and a literal command whose executable position is the guard itself "
    f"({' '.join(_GUARD_PREFIX)} ...), which the payload generator renders. "
    "Declare the node one of those ways, or dispatch this workflow without a "
    "Codex credential projection."
)


def unguardable_launch_refusal(*, graph_text: str, adapter_inputs: frozenset[str]) -> str | None:
    """Refuse when a protected graph declares a launch the guard cannot reach.

    `adapter_inputs` is the set of workflow input names whose values this dispatch
    WRAPPED. It is the dispatch's own resolution rather than a convention, because
    a node referencing an input nobody supplied runs the workflow's unwrapped
    default — which looks identical in the graph to a node that is protected.

    Returns None when every ACP node is guardable, or one message naming the first
    offending node and what it declared. One node is enough to refuse, and naming
    the first keeps the message actionable; a caller that fixed them in bulk would
    be told about the next one on its next attempt.
    """
    graph = parse_dot_graph(text=graph_text)
    if isinstance(graph, str):
        return (
            f"the selected workflow graph could not be parsed, so this dispatch "
            f"cannot establish how its coding agents launch: {graph}. {_GUIDANCE}"
        )
    nodes = nodes_with_effective_backend(graph=graph)
    if isinstance(nodes, str):
        return (
            f"the selected workflow graph's effective backends could not be "
            f"established, so this dispatch cannot enumerate its coding-agent "
            f"launches: {nodes}. {_GUIDANCE}"
        )
    for node, attributes in sorted(nodes.items()):
        # The EFFECTIVE attributes: merged across every declaration of this node,
        # and carrying the backend a `model_stylesheet` supplies when the node
        # declares none of its own.
        if attributes.get("backend") != ACP_BACKEND:
            continue
        refusal = _node_launch_refusal(
            node=node, attributes=attributes, adapter_inputs=adapter_inputs
        )
        if refusal is not None:
            return refusal
    return None


def _node_launch_refusal(
    *, node: str, attributes: Mapping[str, str], adapter_inputs: frozenset[str]
) -> str | None:
    """Grade ONE ACP node's declared launch, or None when the guard reaches it.

    Split from the enumeration above so each function answers one question: that one
    decides WHICH nodes launch a coding agent, this one decides whether a given
    launch is reachable by the wrap. Every refusal names the node, because the
    caller reports only the first and an unnamed one is not actionable.
    """
    unrecognised = sorted(
        key
        for key in attributes
        if key.startswith(_ACP_ATTRIBUTE_PREFIX) and key != _LAUNCH_ATTRIBUTE
    )
    if unrecognised:
        return (
            f"ACP node {node!r} declares {', '.join(unrecognised)}, which the "
            f"credential-use guard does not wrap. {_GUIDANCE}"
        )
    command = attributes.get(_LAUNCH_ATTRIBUTE)
    if command is None:
        return (
            f"ACP node {node!r} declares no {_LAUNCH_ATTRIBUTE}, so this "
            f"dispatch cannot establish how it launches. {_GUIDANCE}"
        )
    match = _TEMPLATED_INPUT_RE.match(command.strip())
    if match is None:
        return _literal_launch_refusal(node=node, command=command)
    name = match.group("name")
    if name not in adapter_inputs:
        wrapped = ", ".join(sorted(adapter_inputs)) or "none"
        return (
            f"ACP node {node!r} launches from workflow input {name!r}, which "
            f"this dispatch did not wrap, so it would run the workflow's own "
            f"unwrapped default. Wrapped inputs: {wrapped}. {_GUIDANCE}"
        )
    return None


def _peeled_env_prefix(*, tokens: list[str]) -> tuple[list[str], list[str]]:
    """Split a tokenized command line into its LEADING env assignments and its argv.

    Leading, and the first non-assignment ends the prefix -- exactly as the
    engine's own POSIX tokenization treats it, so a later token that happens to
    look like an assignment is an ARGUMENT and never environment.
    """
    for index, token in enumerate(tokens):
        if _ENV_ASSIGNMENT_RE.match(token) is None:
            return tokens[:index], tokens[index:]
    return tokens, []


def _literal_launch_refusal(*, node: str, command: str) -> str | None:
    """Grade a LITERAL launch: None only when the guard is provably its executable.

    Separate from the templated arm because the question is different in kind.
    There, the evidence is that the dispatch wrapped the input the node reads;
    here, the command IS what the engine execs, so the evidence has to be read
    out of the command line itself -- the guard in the executable position, and
    no enforcement variable in the env prefix that precedes it.
    """
    try:
        tokens = shlex.split(command)
    except ValueError:
        return (
            f"ACP node {node!r} declares a {_LAUNCH_ATTRIBUTE} ({command!r}) that "
            f"does not tokenize as a shell command line, so this dispatch cannot "
            f"establish what it launches. {_GUIDANCE}"
        )
    prefix, argv = _peeled_env_prefix(tokens=tokens)
    declared = sorted(
        token.partition("=")[0]
        for token in prefix
        if token.partition("=")[0] in _ENFORCEMENT_ENV_VARS
    )
    if declared:
        return (
            f"ACP node {node!r} declares {', '.join(declared)} ahead of its "
            f"{_LAUNCH_ATTRIBUTE} executable, which would let the launch choose "
            f"its own credential-use deadline instead of the one this dispatch "
            f"projected. {_GUIDANCE}"
        )
    if tuple(argv[: len(_GUARD_PREFIX)]) != _GUARD_PREFIX or len(argv) <= len(_GUARD_PREFIX):
        return (
            f"ACP node {node!r} declares a literal {_LAUNCH_ATTRIBUTE} "
            f"({command!r}) whose executable is not the projected guard, so "
            f"its launch would not run behind it. {_GUIDANCE}"
        )
    return None


def selected_graph_launch_refusal(
    *,
    committed: Path,
    graph_override: Path | None,
    adapter_inputs: frozenset[str],
) -> str | None:
    """Grade the graph THIS dispatch will actually run.

    The IO half of the decision above, kept here rather than at the call site so the
    question "which graph does this dispatch run" is answered once, beside the rule
    that grades it.

    The PER-DISPATCH RENDERED PAYLOAD wins when one was materialized, because that
    is the file `fabro run` is pointed at — grading the committed graph instead would
    grade a file the run does not read. Absent an override (a direct caller that
    materialized no payload) the committed graph is the one that runs.
    """
    graph = (
        workflow_graph_path(
            committed_text=committed.read_text(encoding="utf-8"),
            workflow_dir=committed.parent.resolve(),
        )
        if graph_override is None
        else graph_override
    )
    return unguardable_launch_refusal(
        # An unresolvable graph yields empty text, which the parser refuses — the
        # fail-closed direction, and the same answer an unreadable graph deserves.
        graph_text="" if graph is None else graph.read_text(encoding="utf-8"),
        adapter_inputs=adapter_inputs,
    )
