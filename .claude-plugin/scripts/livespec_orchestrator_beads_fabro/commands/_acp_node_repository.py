"""The PER-REPOSITORY adapter layer: `dispatcher.acp_nodes`, and nothing else.

`dispatcher.acp_nodes` is the whole surface -- a table keyed by node name whose
entry is either a whole adapter STRING, a `command` / `env` / `args` TABLE
(`_acp_node_adapters` owns why those merge differently), or a STRUCTURED entry
naming an `agent` and a `model` (`_acp_structured_render` owns how that becomes
the manual form before anything downstream can tell the difference).

ONE LAYER, ONE KEY. `dispatcher.codex_models` used to expand a class-shaped
shorthand into this same layer, and the precedence between the two was the
bulk of this module. `SPECIFICATION/contracts.md` section "Built-in ACP node
defaults" retired it: "No shorthand expands into this layer." A repository now
routes a node to Codex by writing a structured entry whose `agent` is
`codex-acp` for THAT node, so the expansion, its explicit-wins precedence rule
and the shorthand provenance flag that exempted an expanded overlay from the
unreachable-node refusal are all gone rather than merely unused.
`_acp_codex_models_retired` turns the retired key into a refusal carrying the
equivalent per-node entries, and this module consults it FIRST -- before any
`acp_nodes` parsing -- so a repository configuring both is told about the
retired key rather than about whichever `acp_nodes` fault it happens to hit.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, cast

from livespec_orchestrator_beads_fabro.commands._acp_candidate_forms import (
    is_structured_entry,
    parse_structured_entry,
)
from livespec_orchestrator_beads_fabro.commands._acp_catalogs import AcpCatalogs
from livespec_orchestrator_beads_fabro.commands._acp_codex_models_retired import (
    codex_models_retirement_refusal,
)
from livespec_orchestrator_beads_fabro.commands._acp_node_adapters import (
    AcpNodeOverlay,
    overlay_from_string,
    overlay_from_table,
)
from livespec_orchestrator_beads_fabro.commands._acp_node_chains import (
    AcpNodeChain,
    parse_node_chains,
)
from livespec_orchestrator_beads_fabro.commands._acp_structured_render import (
    READ_ONLY_NODES,
    render_structured_entry,
)

__all__: list[str] = [
    "repository_acp_chains",
    "repository_acp_overlays",
]

_ACP_NODES_KEY = "acp_nodes"


def repository_acp_overlays(
    *, block: dict[str, Any], catalogs: AcpCatalogs
) -> Mapping[str, AcpNodeOverlay] | str:
    """Resolve the per-repository adapter overlays, or refuse.

    Returns one overlay per configured node, or an actionable refusal
    message naming the key -- the caller routes that as a failed dispatch
    BEFORE any Fabro run exists, so a malformed adapter table is never
    discovered by watching a node launch the wrong model.

    There is deliberately NO environment override here, matching
    `_node_timeouts`: an env seam would let an ad-hoc shell re-provider the
    whole factory with nothing in the committed record to show for it.

    The retired `codex_models` key is checked BEFORE `acp_nodes` is parsed, so
    a repository carrying both is told to migrate the retired key rather than
    being handed a refusal about the surface it is migrating TO.
    """
    retired = codex_models_retirement_refusal(block=block)
    if retired is not None:
        return retired
    return _explicit_overlays(block=block, catalogs=catalogs)


def repository_acp_chains(
    *, block: dict[str, Any], catalogs: AcpCatalogs
) -> Mapping[str, AcpNodeChain] | str:
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
        table=cast("dict[str, Any]", table_raw),
        key_prefix=f"dispatcher.{_ACP_NODES_KEY}",
        catalogs=catalogs,
    )


def _explicit_overlays(
    *, block: dict[str, Any], catalogs: AcpCatalogs
) -> Mapping[str, AcpNodeOverlay] | str:
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
        parsed = _one_overlay(node=node, entry=table[node], catalogs=catalogs)
        if isinstance(parsed, str):
            return parsed
        overlays[node] = parsed
    return overlays


def _one_overlay(*, node: str, entry: object, catalogs: AcpCatalogs) -> AcpNodeOverlay | str:
    """One node's overlay from whichever form its entry is written in.

    A STRING entry is the legacy whole-adapter spelling and stays valid. A TABLE
    is either of the two ratified forms, discriminated on the presence of
    `agent` -- which is safe because the closed grammar refuses an object
    carrying `agent` together with any manual field, so the two cannot overlap.
    """
    key = f"dispatcher.{_ACP_NODES_KEY}.{node}"
    if isinstance(entry, str):
        return overlay_from_string(text=entry)
    if not isinstance(entry, dict):
        return f"{key} must be an adapter string or a table; got {entry!r}"
    table = cast("dict[str, Any]", entry)
    if not is_structured_entry(entry=table):
        return overlay_from_table(entry=table, key=key)
    return _structured_overlay(node=node, table=table, catalogs=catalogs, key=key)


def _structured_overlay(
    *, node: str, table: Mapping[str, Any], catalogs: AcpCatalogs, key: str
) -> AcpNodeOverlay | str:
    """Render a structured entry and hand the merge an ORDINARY overlay.

    This is where `SPECIFICATION/contracts.md` section "ACP node adapter
    configuration"'s "render ... before any layer merge" becomes structural:
    what leaves this function is indistinguishable from a hand-written manual
    entry, so every downstream rule applies to the rendered candidate unchanged
    without any of them having to know the structured form exists.

    `env_replaces` is set because a rendered structured entry is a COMPLETE
    adapter. Merging the workflow default's environment into it would prefix one
    provider's model pin onto another provider's command -- a Claude
    `ANTHROPIC_MODEL` landing on a Codex command line, which is the defect the
    retired shorthand's expansion set the same flag to avoid.
    """
    parsed = parse_structured_entry(entry=table, key=key)
    if isinstance(parsed, str):
        return parsed
    rendered = render_structured_entry(
        entry=parsed, catalogs=catalogs, key=key, read_only=node in READ_ONLY_NODES
    )
    if isinstance(rendered, str):
        return rendered
    return AcpNodeOverlay(
        command=rendered.adapter.command,
        env=rendered.adapter.env,
        args=rendered.adapter.args,
        env_replaces=True,
    )
