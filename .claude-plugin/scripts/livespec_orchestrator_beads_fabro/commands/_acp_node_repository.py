"""The PER-REPOSITORY adapter layer: `acp_nodes`, and the `codex_models` shorthand.

Two configuration keys feed one layer, and the relationship between them is
the whole content of this module:

- `dispatcher.acp_nodes` is the general surface -- a table keyed by node
  name whose entry is either a whole adapter STRING or a `command` / `env`
  / `args` TABLE (`_acp_node_adapters` owns why those merge differently).
- `dispatcher.codex_models` is the pre-existing Codex SHORTHAND and stays
  valid. It expands into the same layer, and an explicit `acp_nodes` entry
  for the same node WINS over the expansion, so a repository can keep its
  tier configuration while moving one node off Codex entirely.

BOTH TIERS EXPAND ONLY WHEN EXPLICITLY CONFIGURED. Each tier's overlay is
emitted ONLY when its `codex_models` entry is an explicit table -- `pr` when
`codex_models.pr` is a table, the implementer nodes when
`codex_models.implementer` is a table. Absent that table the tier contributes
NO overlay, so the node runs the workflow's own default adapter (the Claude
publish default for `pr`, the Claude implementer default for the implementer
nodes -- see contracts.md section "Codex ACP node model pins"). This is the
symmetry the v107 revision established: it moved the `pr` fleet default off a
baked Codex model onto the workflow's model-agnostic Claude adapter, so a
repository routes `pr` to Codex by writing the table and takes the Claude
default by omitting it, exactly as the implementer tier already worked.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace
from typing import Any, cast

from livespec_orchestrator_beads_fabro.commands._acp_node_adapters import (
    AcpNodeOverlay,
    overlay_from_string,
    overlay_from_table,
)
from livespec_orchestrator_beads_fabro.commands._acp_node_chains import (
    AcpNodeChain,
    parse_node_chains,
)
from livespec_orchestrator_beads_fabro.commands._codex_model_tiers import (
    codex_model_tiers_from_block,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_fabro_argv import codex_adapter

__all__: list[str] = [
    "repository_acp_chains",
    "repository_acp_overlays",
]

_ACP_NODES_KEY = "acp_nodes"
_CODEX_MODELS_KEY = "codex_models"
_IMPLEMENTER_TIER_KEY = "implementer"
_PR_TIER_KEY = "pr"

# The nodes the Codex implementer tier backs when it is explicitly
# configured. `pr` is absent on purpose: it takes the `pr` tier instead.
_IMPLEMENTER_NODES: tuple[str, ...] = ("implement", "fix", "review_fix")


def repository_acp_overlays(*, block: dict[str, Any]) -> Mapping[str, AcpNodeOverlay] | str:
    """Resolve the per-repository adapter overlays, or refuse.

    Returns one overlay per configured node, or an actionable refusal
    message naming the key -- the caller routes that as a failed dispatch
    BEFORE any Fabro run exists, so a malformed adapter table is never
    discovered by watching a node launch the wrong model.

    There is deliberately NO environment override here, matching
    `_codex_model_tiers` and `_node_timeouts`: an env seam would let an
    ad-hoc shell re-provider the whole factory with nothing in the
    committed record to show for it.
    """
    overlays = dict(_codex_shorthand_overlays(block=block))
    explicit = _explicit_overlays(block=block)
    if isinstance(explicit, str):
        return explicit
    for node, overlay in explicit.items():
        overlays[node] = _explicit_wins(shorthand=overlays.get(node), explicit=overlay)
    return overlays


def _explicit_wins(*, shorthand: AcpNodeOverlay | None, explicit: AcpNodeOverlay) -> AcpNodeOverlay:
    """Decide what an explicit entry does to the shorthand overlay beneath it.

    The pre-existing `acp_nodes`-wins rule is preserved VERBATIM for any
    entry that sets a primary field: the whole shorthand overlay is
    replaced, so a repository moving one node off Codex keeps behaving
    exactly as it did before fallback priority existed. That includes the
    known legacy cross-provider merge problem recorded as `bd-ib-5j4b`,
    which this slice deliberately preserves rather than silently decides.

    An entry that sets NONE of them is the case
    `SPECIFICATION/contracts.md` section "Factory-configurable ACP fallback
    priority" separates out: identity-only and fallback-only fields attach
    AFTER the `codex_models` shorthand resolves, and a fallback-only table
    must not shadow a `codex_models` primary or restore the workflow
    default. So the shorthand's adapter STANDS and only its
    shorthand-provenance flag is cleared -- the operator did name this
    node, so a node the workflow cannot reach must still refuse rather
    than be quietly dropped.
    """
    if explicit.declares_primary or shorthand is None:
        return explicit
    return replace(shorthand, from_shorthand=False)


def repository_acp_chains(*, block: dict[str, Any]) -> Mapping[str, AcpNodeChain] | str:
    """Read each node's fallback-priority metadata off the same table, or refuse.

    This is a SECOND, INDEPENDENT read of `dispatcher.acp_nodes`, and the
    independence is the point rather than an oversight: `repository_acp_overlays`
    above resolves the legacy `command` / `env` / `args` OVERLAY that feeds
    the three-layer merge, while this reads the identity, signature,
    pricing and `fallbacks` metadata that may only attach AFTER that merge
    has finished (the "resolve the primary before attaching the chain" rule
    of `SPECIFICATION/contracts.md` section "Factory-configurable ACP
    fallback priority"). One reader returning both would have to hand the
    merge something it must not see until afterwards.

    A non-table `acp_nodes` yields the empty mapping rather than a second
    copy of that refusal: `repository_acp_overlays` already names the key,
    and the caller resolves overlays first, so the operator gets exactly
    one message about it.
    """
    table_raw = block.get(_ACP_NODES_KEY)
    if not isinstance(table_raw, dict):
        return {}
    return parse_node_chains(
        table=cast("dict[str, Any]", table_raw), key_prefix=f"dispatcher.{_ACP_NODES_KEY}"
    )


def _explicit_overlays(*, block: dict[str, Any]) -> Mapping[str, AcpNodeOverlay] | str:
    """Parse `dispatcher.acp_nodes` into one overlay per named node."""
    table_raw = block.get(_ACP_NODES_KEY)
    if table_raw is None:
        return {}
    if not isinstance(table_raw, dict):
        return (
            f"dispatcher.{_ACP_NODES_KEY} must be a table of node name to adapter "
            f"configuration; got {table_raw!r}"
        )
    table = cast("dict[str, Any]", table_raw)
    overlays: dict[str, AcpNodeOverlay] = {}
    for node in sorted(table):
        entry: object = table[node]
        key = f"dispatcher.{_ACP_NODES_KEY}.{node}"
        if isinstance(entry, str):
            overlays[node] = overlay_from_string(text=entry)
            continue
        if not isinstance(entry, dict):
            return f"{key} must be an adapter string or a table; got {entry!r}"
        parsed = overlay_from_table(entry=cast("dict[str, Any]", entry), key=key)
        if isinstance(parsed, str):
            return parsed
        overlays[node] = parsed
    return overlays


def _codex_shorthand_overlays(*, block: dict[str, Any]) -> Mapping[str, AcpNodeOverlay]:
    """Expand `dispatcher.codex_models` into per-node adapter overlays.

    Each expanded overlay is a COMPLETE adapter (a whole rendered Codex
    command line), so it replaces the workflow default's `env` rather than
    merging with it. That matters concretely: the workflow's implementer
    default pins `ANTHROPIC_MODEL`, and merging that onto a Codex command
    line would prefix an Anthropic model onto a Codex adapter.

    A tier contributes an overlay ONLY when its `codex_models` entry is an
    explicit table. Absent the table the node keeps the workflow's own
    default adapter -- the Claude publish default for `pr`, the Claude
    implementer default for the implementer nodes -- rather than a baked
    Codex model, per contracts.md section "Codex ACP node model pins".
    """
    tiers = codex_model_tiers_from_block(block=block)
    overlays: dict[str, AcpNodeOverlay] = {}
    if _has_explicit_pr_tier(block=block):
        overlays["pr"] = overlay_from_string(
            text=codex_adapter(tier=tiers.pr), replaces_env=True, from_shorthand=True
        )
    if _has_explicit_implementer_tier(block=block):
        implementer = overlay_from_string(
            text=codex_adapter(tier=tiers.implementer), replaces_env=True, from_shorthand=True
        )
        overlays.update(dict.fromkeys(_IMPLEMENTER_NODES, implementer))
    return overlays


def _has_explicit_implementer_tier(*, block: dict[str, Any]) -> bool:
    """Whether the target explicitly routes implementer work to Codex."""
    return _has_explicit_tier(block=block, tier_key=_IMPLEMENTER_TIER_KEY)


def _has_explicit_pr_tier(*, block: dict[str, Any]) -> bool:
    """Whether the target explicitly routes the publish node to Codex."""
    return _has_explicit_tier(block=block, tier_key=_PR_TIER_KEY)


def _has_explicit_tier(*, block: dict[str, Any], tier_key: str) -> bool:
    """Whether a `codex_models` tier entry is an explicit table."""
    models_raw = block.get(_CODEX_MODELS_KEY)
    if not isinstance(models_raw, dict):
        return False
    return isinstance(cast("dict[str, Any]", models_raw).get(tier_key), dict)
