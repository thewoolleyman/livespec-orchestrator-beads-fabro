"""Three-layer, most-specific-wins resolution of every ACP node's adapter.

The layers, in ASCENDING precedence
(the adapter-configuration contract in `SPECIFICATION/contracts.md`):

1. WORKFLOW -- the declared inputs and their defaults in the workflow's own
   `workflow.toml`, so a vendored workflow carries its own defaults.
2. REPOSITORY -- the `dispatcher.acp_nodes` table in the dispatch TARGET's
   `.livespec.jsonc`, read from the target repository exactly as the Codex
   tiers already are, plus the `dispatcher.codex_models` shorthand it
   expands from.
3. DISPATCH -- an explicit `--acp-node <node>=<value>` argument on
   `dispatcher.py dispatch`, `dispatcher.py loop` and the `drive`
   operation's `impl:<id>` action.

THERE IS DELIBERATELY NO ENVIRONMENT LAYER, and that is a contract rather
than an omission. The per-dispatch layer is a RECORDED ARGUMENT precisely
so an ad-hoc shell cannot re-provider the whole factory with nothing in
the committed record or the journal to show for it -- the same rationale
`_codex_model_tiers` and `_node_timeouts` already carry.

WHY THE SUPPLYING LAYER IS TRACKED PER FIELD rather than per node. `env`
merges key by key, so one node's rendered adapter routinely mixes a
workflow-default model pin with a repository-supplied base URL. Reporting
one layer for the whole node would therefore be false for the majority of
interesting configurations, and a reader could not tell a workflow default
from an override without re-deriving the resolution by hand -- which is
the thing the record exists to spare them.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from livespec_orchestrator_beads_fabro.commands._acp_node_adapters import (
    ACP_NODES,
    NODE_INPUT_CANDIDATES,
    AcpAdapter,
    AcpNodeOverlay,
    parse_adapter_string,
    render_adapter,
    resolve_node_inputs,
)

__all__: list[str] = [
    "DISPATCH_LAYER",
    "REPOSITORY_LAYER",
    "WORKFLOW_LAYER",
    "AcpNodeResolution",
    "ResolvedAcpNode",
    "acp_nodes_journal_record",
    "resolve_acp_nodes",
]

WORKFLOW_LAYER = "workflow"
REPOSITORY_LAYER = "repository"
DISPATCH_LAYER = "dispatch"

# The workflow layer is the BASE rather than an overlay -- every node
# starts from its workflow input's declared default -- so only the two
# layers above it arrive as overlays, in ascending precedence.
_OVERLAY_LAYERS: tuple[str, ...] = (REPOSITORY_LAYER, DISPATCH_LAYER)


@dataclass(frozen=True, kw_only=True)
class ResolvedAcpNode:
    """One node's resolved adapter, with the layer behind each field."""

    adapter: AcpAdapter
    command_layer: str
    args_layer: str
    env_layers: Mapping[str, str]

    @property
    def rendered(self) -> str:
        """The exact string this node's `acp.command` receives."""
        return render_adapter(adapter=self.adapter)


@dataclass(frozen=True, kw_only=True)
class AcpNodeResolution:
    """Every ACP node's adapter resolved for one dispatch.

    `inputs` maps each node onto the workflow input its adapter rides, so
    the `--input` pairs are rendered against what the dispatched workflow
    ACTUALLY declares rather than against an assumed shape. `run_inputs`
    is those pairs, rendered and VALIDATED at resolution time so the
    launcher has nothing left to fail on.
    """

    nodes: Mapping[str, ResolvedAcpNode]
    inputs: Mapping[str, str]
    run_inputs: tuple[str, ...]


def resolve_acp_nodes(
    *,
    workflow_inputs: Mapping[str, str],
    repository: Mapping[str, AcpNodeOverlay],
    dispatch: Mapping[str, AcpNodeOverlay],
) -> AcpNodeResolution | str:
    """Merge the three layers into one adapter per node, or refuse.

    A layer that names a node the workflow has no adapter input for
    REFUSES the dispatch BEFORE any run exists, naming the node -- a
    misspelled node in configuration is otherwise indistinguishable from a
    node the operator chose not to override, and the run would go out
    silently carrying the default they meant to replace.

    A node the workflow parameterizes but nobody configures resolves to its
    workflow default. A node the workflow does NOT parameterize is absent
    from the resolution entirely, so the dispatch overrides nothing for it
    and the workflow runs whatever it declares.
    """
    inputs = resolve_node_inputs(declared=workflow_inputs)
    overlays = {REPOSITORY_LAYER: repository, DISPATCH_LAYER: dispatch}
    for layer in _OVERLAY_LAYERS:
        refusal = _unconfigurable_node(layer=layer, configured=overlays[layer], inputs=inputs)
        if refusal is not None:
            return refusal
    nodes = {
        node: _resolve_one(
            node=node,
            workflow_default=workflow_inputs[name],
            overlays=overlays,
        )
        for node, name in inputs.items()
    }
    run_inputs = _run_inputs(nodes=nodes, inputs=inputs)
    if isinstance(run_inputs, str):
        return run_inputs
    return AcpNodeResolution(nodes=nodes, inputs=inputs, run_inputs=run_inputs)


def _unconfigurable_node(
    *,
    layer: str,
    configured: Mapping[str, AcpNodeOverlay],
    inputs: Mapping[str, str],
) -> str | None:
    """Refuse when a layer configures a node the dispatch cannot reach.

    Two distinct mistakes, and the message separates them because the
    remedies differ: a name that is not an ACP node at all is a typo in the
    configuration, while a real node the workflow never parameterized needs
    an adapter input added to the WORKFLOW before any configuration of it
    can take effect.

    An overlay the `codex_models` shorthand expanded is exempt from the
    second check -- see `AcpNodeOverlay.from_shorthand`. It is a default
    nobody asked for, so an unreachable one is dropped rather than made
    fatal.
    """
    unknown = sorted(set(configured) - set(ACP_NODES))
    if unknown:
        return (
            f"{layer} layer configures unknown ACP node {unknown[0]!r}; "
            f"known nodes are {', '.join(ACP_NODES)}"
        )
    unreachable = sorted(
        node
        for node, overlay in configured.items()
        if node not in inputs and not overlay.from_shorthand
    )
    if unreachable:
        node = unreachable[0]
        return (
            f"{layer} layer configures ACP node {node!r}, but the workflow declares no "
            f"adapter input for it; expected one of {', '.join(NODE_INPUT_CANDIDATES[node])}"
        )
    return None


def _run_inputs(
    *,
    nodes: Mapping[str, ResolvedAcpNode],
    inputs: Mapping[str, str],
) -> tuple[str, ...] | str:
    """Render the `--input <name>=<adapter>` pairs, or refuse.

    Several nodes can ride ONE workflow input -- a four-input graph shares
    `acp_adapter` across `implement`, `fix` and `review_fix` -- and one
    input cannot carry two values. When such nodes resolve differently this
    REFUSES rather than picking a winner: silently dropping one node's
    configured adapter would leave the operator reading a journal that says
    their override was honoured while the run used the other node's. The
    message names the input and the disagreeing nodes, because the remedy
    is to give each of them its own adapter input in the workflow.
    """
    by_input: dict[str, dict[str, str]] = {}
    for node, name in inputs.items():
        by_input.setdefault(name, {})[node] = nodes[node].rendered
    pairs: list[str] = []
    for name in sorted(by_input):
        rendered_by_node = by_input[name]
        distinct = sorted(set(rendered_by_node.values()))
        if len(distinct) > 1:
            shared = ", ".join(sorted(rendered_by_node))
            return (
                f"workflow input {name!r} is shared by nodes {shared}, which resolved "
                "to different adapters; give each node its own adapter input"
            )
        pairs.append(f"{name}={distinct[0]}")
    return tuple(pairs)


def acp_nodes_journal_record(
    *,
    resolution: AcpNodeResolution,
    redacted: Mapping[str, Mapping[str, object]] | None = None,
) -> dict[str, object]:
    """Project the resolved adapters for the dispatch record.

    Every node reports the RENDERED string it will actually run plus the
    layer behind each of `command`, `args` and each `env` key, so a reader
    can tell a workflow default from a repository override from a
    per-dispatch override without re-deriving the resolution.

    A node named in `redacted` reports its STRUCTURAL form instead of that
    rendered string. `SPECIFICATION/contracts.md` section
    "Factory-configurable ACP fallback priority" narrows the journal rule
    for a fallback-enabled node -- command and args, env KEY NAMES and
    their layers, plus the deterministic digests, and never raw env values
    -- while a no-fallback legacy node keeps this record verbatim. That is
    why the substitution is per node and why the default is empty: the
    narrowing applies exactly where the operator opted into the new
    grammar, and nowhere else.
    """
    structural = redacted or {}
    return {
        "acp_nodes": {
            node: {"input": resolution.inputs[node], **structural[node]}
            if node in structural
            else {
                "input": resolution.inputs[node],
                "adapter": resolved.rendered,
                "layers": {
                    "command": resolved.command_layer,
                    "args": resolved.args_layer,
                    "env": dict(sorted(resolved.env_layers.items())),
                },
            }
            for node, resolved in sorted(resolution.nodes.items())
        }
    }


def _resolve_one(
    *,
    node: str,
    workflow_default: str,
    overlays: Mapping[str, Mapping[str, AcpNodeOverlay]],
) -> ResolvedAcpNode:
    """Fold every layer's overlay for one node onto the workflow default."""
    base = parse_adapter_string(text=workflow_default)
    command = base.command
    args = base.args
    env = dict(base.env)
    command_layer = WORKFLOW_LAYER
    args_layer = WORKFLOW_LAYER
    env_layers = dict.fromkeys(env, WORKFLOW_LAYER)
    for layer in _OVERLAY_LAYERS:
        overlay = overlays[layer].get(node)
        if overlay is None:
            continue
        if overlay.command is not None:
            command = overlay.command
            command_layer = layer
        if overlay.args is not None:
            args = overlay.args
            args_layer = layer
        if overlay.env_replaces:
            env = {}
            env_layers = {}
        env.update(overlay.env)
        env_layers.update(dict.fromkeys(overlay.env, layer))
    return ResolvedAcpNode(
        adapter=AcpAdapter(command=command, env=env, args=args),
        command_layer=command_layer,
        args_layer=args_layer,
        env_layers=env_layers,
    )
