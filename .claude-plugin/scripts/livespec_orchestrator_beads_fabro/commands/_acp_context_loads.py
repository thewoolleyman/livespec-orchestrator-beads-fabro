"""Validation for declared ACP node context that must be delivered at launch."""

from __future__ import annotations

from livespec_orchestrator_beads_fabro.commands._acp_node_layers import AcpNodeResolution

__all__: list[str] = ["context_load_refusal"]


def context_load_refusal(*, resolution: AcpNodeResolution) -> str | None:
    """Refuse declarations the isolated ACP launch cannot faithfully deliver."""
    for node, resolved in sorted(resolution.nodes.items()):
        loads = resolved.loads
        if loads is None:
            continue
        for field_name, values in (
            ("skills", loads.skills),
            ("plugins", loads.plugins),
            ("mcp_servers", loads.mcp_servers),
        ):
            if values:
                return (
                    f"node {node!r} declares {field_name} entry {values[0]!r}, but this "
                    "ACP launch can only deliver an isolated instruction-file context"
                )
    return None
