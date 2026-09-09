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
from typing import Any, cast

from livespec_orchestrator_beads_fabro.commands._acp_node_adapters import (
    AcpNodeOverlay,
    overlay_from_string,
    overlay_from_table,
)
from livespec_orchestrator_beads_fabro.commands._codex_model_tiers import (
    codex_model_tiers_from_block,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_fabro_argv import codex_adapter

__all__: list[str] = [
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
    overlays.update(explicit)
    return overlays


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
