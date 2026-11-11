"""Sandbox setup as explicit command nodes, because `run.prepare` is being removed.

Upstream Fabro's run-config parser refuses `run.prepare` from `v0.396.0-nightly.0`
(`b452f498f`), and its migration guide says setup belongs in each workflow as
explicit command nodes after `start`. The plugin's setup is a CHAIN of steps --
the committed provisioning steps plus every step the Dispatcher materializes into
the overlay -- so this module is the one place that turns that chain into graph
nodes, and the one place that says how they are named, wired and failed.

THE NAMES ARE NOT FREE. Each node is `run_prepare_<N>`, `N` counting from 1 in the
order the steps ran under `run.prepare`. The carrier's re-prepare-on-reacquire fix
(`fabro-petri/src/prepare.rs`, carried from `bd-ib-ljw2xg`) recognises a run's
setup ONLY by that prefix, and keeps it on the v0.408 carrier as Fabro's own
constant; a node under any other name is not re-run when a sandbox is re-acquired
and the resumed stage finds no helper programs in it.

THE ORDER IS THE CHAIN'S. The committed steps come first and the Dispatcher's come
after them, exactly as the overlay appended them. The committed graph therefore
declares `run_prepare_1` .. `run_prepare_K`, and `splice_setup_nodes` continues
from `K + 1`, hanging the new nodes off the committed tail rather than off
`start`. That is also what lets a derived graph (a resume entered at a later node,
the proof-only arm) keep its setup: the derivations move the edge out of the tail
and the chain stays whole in front of it.

A FAILED STEP MUST END THE RUN. A command node that exits non-zero follows its
UNCONDITIONAL edge and the run goes on to succeed (measured on candidate run
01M6VWWEK8QP at `bbe6938`: a node that exited 1 was followed by the next one and
the run ended succeeded). So every setup node also carries a conditional
`outcome=failed` edge to `setup_failed`, a terminal command node that names the
failed step off the engine's own checkpoint commit and exits non-zero. The
unconditional edge stays: the engine rejects a node whose EVERY outgoing edge is
conditional (`all_conditional_edges`).

A STEP'S PAYLOAD RIDES THE RUN'S ENVIRONMENT TABLE, NOT THE NODE. A payload step keeps
its bytes in its own `env` and only a short script in its `script`, because the
engine's compact fidelity re-sends every completed command stage's full script to
every later agent request and sends no `env` (`_dispatcher_prepare_payload`). A
command node has no such table of its own that the engine is known to read, so
`hoist_step_env` moves each step's variables into the run's environment table
(`append_env_lines`) under a name unique to the step, and renames them in the step's
script to match. That table is how the overlay already delivers every other value a
command node reads, and it is the TOML's, so it costs the workflow graph nothing:
the engine refuses a workflow file over 524,288 bytes, and the payloads are most of
what the overlay weighs.

A SCRIPT IS TEMPLATE-ESCAPED. Every string attribute of a node is rendered through
MiniJinja before the node runs, and `run.prepare` was left verbatim, so a step
carrying a `{{`, `{%` or `{#` (a Python dict literal, a shell `${#var}`) would
otherwise be read as template syntax. The committed graph's own scripts avoid the
openers by hand; these come from the Dispatcher and cannot.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from itertools import pairwise
from typing import Any

import tomli

from livespec_orchestrator_beads_fabro.commands._dispatcher_dot_graph import (
    DotGraph,
    parse_dot_graph,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_minijinja_escape import (
    escape_minijinja_literal,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_overlay_input_tokens import (
    substitute_input_tokens,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_prepare_payload import (
    PrepareStep,
    env_table_line,
)
from livespec_orchestrator_beads_fabro.commands._node_timeouts import (
    NodeTimeouts,
    default_node_timeouts,
)

__all__: list[str] = [
    "SETUP_FAILURE_NODE",
    "SETUP_FAILURE_SCRIPT",
    "SETUP_NODE_PREFIX",
    "HoistedSteps",
    "SplitOverlay",
    "append_env_lines",
    "hoist_step_env",
    "is_setup_node",
    "setup_chain_tail",
    "setup_node_names",
    "splice_setup_nodes",
    "split_prepare_steps",
    "substitute_setup_node_inputs",
]

SETUP_NODE_PREFIX = "run_prepare_"
SETUP_FAILURE_NODE = "setup_failed"

# The step the failed node's checkpoint names. The engine commits one
# `fabro(<run>): <node> (<status>)` checkpoint per stage, failed ones included, and
# the newest of them when this node starts is the step that failed -- the same
# source the Definition-of-Done guard reads its starting commit from. A graph whose
# checkpoints cannot be read still ends the run, naming the shape instead.
SETUP_FAILURE_SCRIPT = (
    "step=$(git log -n 1 --format=%s 2>/dev/null"
    " | sed -n 's/^fabro([^)]*): \\(run_prepare_[0-9][0-9]*\\) (.*$/\\1/p');"
    ' echo "LIVESPEC_SETUP_STEP_FAILED: ${step:-an unidentified run_prepare_<N> step}'
    ' failed, so the run ends before any stage that needs the sandbox" >&2;'
    " exit 1"
)

_SETUP_NODE_RE = re.compile(r"^run_prepare_(?P<index>[0-9]+)$")
_STEP_HEADER = "[[run.prepare.steps]]"
_STEP_KEY_LINE_RE = re.compile(r"^(?:script|env)[ \t]*=")
_START_NODE = "start"
_ENV_TABLE_HEADER_RE = re.compile(r"(?m)^\[environments\.(?P<id>[^\]\n]+)\.env\][ \t]*$")
_TABLE_HEADER_RE = re.compile(r"(?m)^[ \t]*\[")
_FAILURE_ATTRIBUTES = '[label="Setup step failed", condition="outcome=failed"]'
_SETUP_BLOCK_RE = re.compile(r"(?ms)^(?P<node>[ \t]*run_prepare_[0-9]+[ \t]*\[.*?\])")


class SplitOverlay:
    """An overlay with its prepare steps lifted out of it."""

    __slots__ = ("overlay", "steps")

    def __init__(self, *, overlay: str, steps: tuple[PrepareStep, ...]) -> None:
        self.overlay = overlay
        self.steps = steps


def is_setup_node(*, name: str) -> bool:
    """Whether `name` is one of the numbered setup nodes."""
    return _SETUP_NODE_RE.match(name) is not None


def setup_node_names(*, graph: DotGraph) -> tuple[str, ...]:
    """The graph's setup nodes in numeric order."""
    indexed = [
        (int(found.group("index")), name)
        for name in graph.nodes
        if (found := _SETUP_NODE_RE.match(name)) is not None
    ]
    return tuple(name for _, name in sorted(indexed))


def setup_chain_tail(*, graph: DotGraph) -> str:
    """The node the chain ends at: its highest-numbered setup node, else `start`.

    Everything that moves "where the run goes after setup" moves the unconditional
    edge LEAVING this node, so a graph with no setup nodes keeps its original shape
    and a graph with them keeps the chain in front of whatever it now enters.
    """
    names = setup_node_names(graph=graph)
    return names[-1] if names else _START_NODE


def substitute_setup_node_inputs(
    *, graph_text: str, prepare_inputs: Mapping[str, str] | None
) -> str:
    """Render only setup-node input tokens before Fabro quotes node scripts."""
    if prepare_inputs is None:
        return graph_text
    return _SETUP_BLOCK_RE.sub(
        lambda match: substitute_input_tokens(
            text=match.group("node"), prepare_inputs=prepare_inputs
        ),
        graph_text,
    )


def split_prepare_steps(*, overlay_text: str) -> SplitOverlay | None:
    """Lift every `[[run.prepare.steps]]` block out of a rendered overlay.

    Returns `None` when the text cannot be split SAFELY, which is judged by a
    postcondition and not by the pattern that cut it: the remaining text must parse
    to exactly the original document with its `run.prepare` removed. A block shape
    the line scan did not understand (a multi-line string, a header spelled with
    inner spaces) leaves residue that fails that comparison, so it refuses instead
    of shipping an overlay that dropped a step.
    """
    try:
        document: dict[str, Any] = tomli.loads(overlay_text)
    except tomli.TOMLDecodeError:
        return None
    steps = _decoded_steps(raw=document.get("run", {}).get("prepare", {}).get("steps", []))
    remaining = _without_step_blocks(overlay_text=overlay_text)
    try:
        parsed: dict[str, Any] = tomli.loads(remaining)
    except tomli.TOMLDecodeError:
        return None
    if steps is None or parsed != _without_prepare(document=document):
        return None
    return SplitOverlay(overlay=remaining, steps=steps)


def _without_step_blocks(*, overlay_text: str) -> str:
    """The overlay with each step header and the `script`/`env` lines under it removed.

    Comment and blank lines between a header and its keys belong to that step and go
    with it; the ones AFTER its last key belong to whatever follows and stay. They
    are held back until the next line says which they were.
    """
    kept: list[str] = []
    held: list[str] = []
    inside = False
    for line in overlay_text.splitlines(keepends=True):
        stripped = line.strip()
        if stripped == _STEP_HEADER:
            kept += held
            held, inside = [], True
        elif inside and (not stripped or stripped.startswith("#")):
            held.append(line)
        elif inside and _STEP_KEY_LINE_RE.match(stripped) is not None:
            held = []
        else:
            kept += held
            held, inside = [], False
            kept.append(line)
    return "".join(kept + held)


def _decoded_steps(*, raw: Sequence[Mapping[str, Any]]) -> tuple[PrepareStep, ...] | None:
    """Each decoded step, or `None` when one carries a key this module does not model."""
    steps: list[PrepareStep] = []
    for entry in raw:
        if set(entry) - {"script", "env"} or not isinstance(entry.get("script"), str):
            return None
        env = {str(name): str(value) for name, value in dict(entry.get("env", {})).items()}
        steps.append(PrepareStep(script=entry["script"], env=env))
    return tuple(steps)


def _without_prepare(*, document: Mapping[str, Any]) -> dict[str, Any]:
    """`document` with `run.prepare` removed, and `run` itself removed when that empties it."""
    reduced: dict[str, Any] = {key: value for key, value in document.items() if key != "run"}
    run = {key: value for key, value in document.get("run", {}).items() if key != "prepare"}
    if run:
        reduced["run"] = run
    return reduced


class HoistedSteps:
    """Setup steps with their payload variables lifted into uniquely named environment entries."""

    __slots__ = ("env", "steps")

    def __init__(self, *, steps: tuple[PrepareStep, ...], env: dict[str, str]) -> None:
        self.steps = steps
        self.env = env


def hoist_step_env(*, steps: Sequence[PrepareStep]) -> HoistedSteps:
    """Move every step's `env` into one flat mapping, renaming the variables to stay unique.

    Several steps reuse one variable name (`LIVESPEC_PREPARE_PAYLOAD` is the payload
    of a dozen of them), which a step-local table allowed and a run-wide one does
    not. Each variable becomes `LIVESPEC_SETUP_<position>__<name>` -- the step's
    1-based position in `steps` -- and the step's script is rewritten to read the
    new name. The match is on whole names only, so `LIVESPEC_PREPARE_PAYLOAD` never
    rewrites the front of `LIVESPEC_PREPARE_PAYLOAD_0`.
    """
    hoisted: list[PrepareStep] = []
    env: dict[str, str] = {}
    for position, step in enumerate(steps, start=1):
        renamed = {name: f"LIVESPEC_SETUP_{position}__{name}" for name in step.env}
        for name, value in step.env.items():
            env[renamed[name]] = value
        hoisted.append(PrepareStep(script=_with_names(script=step.script, renamed=renamed)))
    return HoistedSteps(steps=tuple(hoisted), env=env)


def _with_names(*, script: str, renamed: Mapping[str, str]) -> str:
    """`script` with each whole variable name in `renamed` replaced by its new name."""
    if not renamed:
        return script
    alternatives = "|".join(re.escape(name) for name in sorted(renamed, key=len, reverse=True))
    return re.sub(
        rf"(?<![A-Z0-9_])(?:{alternatives})(?![A-Z0-9_])",
        lambda found: renamed[found.group(0)],
        script,
    )


def append_env_lines(*, overlay_text: str, env: Mapping[str, str]) -> str | None:
    """`overlay_text` with `env` appended to its run environment table, or `None` when it cannot be.

    The table is the overlay's LAST one (`render_run_config_overlay` ends with it),
    so the lines are appended to the end of the text and the result is parsed back:
    every name must read back under that table with the value handed in. An overlay
    with no environment table, one the table is not last in, or a value or name the
    renderer refuses answers `None`, because a payload that never reached the table
    would fail its own `${VAR:?}` guard minutes into the run instead of here.
    """
    if not env:
        return overlay_text
    headers = list(_ENV_TABLE_HEADER_RE.finditer(overlay_text))
    if not headers or _TABLE_HEADER_RE.search(overlay_text, headers[-1].end()) is not None:
        return None
    try:
        lines = "".join(env_table_line(name=name, value=value) for name, value in env.items())
    except ValueError:
        return None
    appended = overlay_text if overlay_text.endswith("\n") else overlay_text + "\n"
    appended += lines
    try:
        document: dict[str, Any] = tomli.loads(appended)
    except tomli.TOMLDecodeError:
        return None
    table: Mapping[str, Any] = (
        document.get("environments", {}).get(headers[-1].group("id"), {}).get("env", {})
    )
    return appended if all(table.get(name) == value for name, value in env.items()) else None


def splice_setup_nodes(
    *,
    graph_text: str,
    steps: Sequence[PrepareStep],
    timeouts: NodeTimeouts | None = None,
) -> str | None:
    """`graph_text` with `steps` appended to its setup chain, or `None` when it cannot be.

    The new nodes hang off the chain's TAIL: the unconditional edge leaving it is
    rewritten to enter the first new node, and the last new node takes over that
    edge's old destination. A tail with no such edge, a step still carrying an `env`
    (a node has nowhere to put one; see `hoist_step_env`), or a result that does not
    re-parse to exactly the nodes intended, answers `None`.
    """
    if not steps:
        return graph_text
    graph = parse_dot_graph(text=graph_text)
    if isinstance(graph, str) or any(step.env for step in steps):
        return None
    tail = setup_chain_tail(graph=graph)
    edge = re.search(
        rf"(?m)^(?P<indent>[ \t]*){re.escape(tail)}[ \t]*->[ \t]*(?P<target>\w+)[ \t]*$",
        graph_text,
    )
    if edge is None:
        return None
    resolved = default_node_timeouts() if timeouts is None else timeouts
    existing = setup_node_names(graph=graph)
    first = int(existing[-1].removeprefix(SETUP_NODE_PREFIX)) + 1 if existing else 1
    names = [f"{SETUP_NODE_PREFIX}{first + offset}" for offset in range(len(steps))]
    indent = edge.group("indent")
    route = [tail, *names, edge.group("target")]
    lines = [f"{indent}{source} -> {target}" for source, target in pairwise(route)]
    lines += [f"{indent}{name} -> {SETUP_FAILURE_NODE} {_FAILURE_ATTRIBUTES}" for name in names]
    blocks = [
        _node_block(name=name, step=step, seconds=resolved.seconds_for(node=name), indent=indent)
        for name, step in zip(names, steps, strict=True)
    ]
    if SETUP_FAILURE_NODE not in graph.nodes:
        blocks.append(_failure_block(indent=indent))
    closing = graph_text.rfind("}")
    spliced = (
        graph_text[: edge.start()]
        + "\n".join(lines)
        + graph_text[edge.end() : closing]
        + "\n".join(blocks)
        + "\n"
        + graph_text[closing:]
    )
    return _validated(text=spliced, expected=frozenset(names))


def _validated(*, text: str, expected: frozenset[str]) -> str | None:
    """`text` when it re-parses with every new node declared and every edge resolving."""
    graph = parse_dot_graph(text=text)
    if isinstance(graph, str) or not expected <= frozenset(graph.nodes):
        return None
    if any(
        endpoint not in graph.nodes
        for edge in graph.edges
        for endpoint in (edge.source, edge.destination)
    ):
        return None
    return text


def _quoted(*, value: str) -> str:
    """A DOT double-quoted string, MiniJinja-escaped first so the engine renders it verbatim."""
    escaped = escape_minijinja_literal(text=value).replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def _node_block(*, name: str, step: PrepareStep, seconds: int, indent: str) -> str:
    """One setup node's declaration; `timeout` precedes the long values, as the renderer expects."""
    index = name.removeprefix(SETUP_NODE_PREFIX)
    return (
        f"{indent}{name} [\n"
        f'{indent}    label="Setup step {index}"\n'
        f"{indent}    shape=parallelogram\n"
        f'{indent}    timeout="{seconds}s"\n'
        f"{indent}    script={_quoted(value=step.script)}\n"
        f"{indent}]"
    )


def _failure_block(*, indent: str) -> str:
    """The terminal node a failed setup step routes to, for a graph that declares none."""
    return (
        f"{indent}{SETUP_FAILURE_NODE} [\n"
        f'{indent}    label="Setup failed: a setup step exited non-zero, so the run ends here"\n'
        f"{indent}    shape=parallelogram\n"
        f'{indent}    timeout="600s"\n'
        f"{indent}    script={_quoted(value=SETUP_FAILURE_SCRIPT)}\n"
        f"{indent}]"
    )
