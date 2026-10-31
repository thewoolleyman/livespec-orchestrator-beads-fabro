"""Parse the per-dispatch ACP adapter and context declarations.

This is deliberately separate from `_dispatcher_acp_nodes`: that module
orchestrates the three layers and the journal, while this one owns the grammar
of the most-specific command-line layer.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import replace

from livespec_orchestrator_beads_fabro.commands._acp_catalogs import AcpCatalogs
from livespec_orchestrator_beads_fabro.commands._acp_node_adapters import (
    AcpNodeOverlay,
    loads_from_object,
    overlay_from_string,
)
from livespec_orchestrator_beads_fabro.commands._acp_structured_render import READ_ONLY_NODES
from livespec_orchestrator_beads_fabro.commands._acp_structured_text import (
    is_structured_text,
    rendered_structured_text,
)

__all__: list[str] = ["dispatch_acp_overlays"]


def dispatch_acp_overlays(
    *, overrides: tuple[str, ...], catalogs: AcpCatalogs
) -> Mapping[str, AcpNodeOverlay] | str:
    """Parse `--acp-node <node>=<value>` values into per-node overlays."""
    overlays: dict[str, AcpNodeOverlay] = {}
    for override in overrides:
        node, separator, value = override.partition("=")
        if separator == "" or node.strip() == "" or value.strip() == "":
            return f"--acp-node expects <node>=<adapter command>; got {override!r}"
        if node in overlays:
            return f"--acp-node names node {node!r} more than once"
        parsed = _dispatch_overlay(node=node, value=value, catalogs=catalogs)
        if isinstance(parsed, str):
            return parsed
        overlays[node] = parsed
    return overlays


def _dispatch_overlay(*, node: str, value: str, catalogs: AcpCatalogs) -> AcpNodeOverlay | str:
    """Parse one manual or structured dispatch-layer declaration."""
    if not is_structured_text(value=value):
        return overlay_from_string(text=value)
    rendered, refusal = rendered_structured_text(
        value=value,
        key=f"--acp-node {node}",
        catalogs=catalogs,
        read_only=node in READ_ONLY_NODES,
    )
    if refusal is not None:
        return refusal
    # `rendered_structured_text` above has already parsed this exact text; a
    # second malformed-JSON branch here would be unreachable and misleading.
    parsed = json.loads(value)
    loads = loads_from_object(value=parsed.get("loads"), key=f"--acp-node {node}.loads")
    if isinstance(loads, str):
        return loads
    return replace(overlay_from_string(text=rendered, replaces_env=True), loads=loads)
