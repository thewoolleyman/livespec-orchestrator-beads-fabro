"""Mirror coverage for ACP adapter selection."""

from livespec_orchestrator_beads_fabro.commands._acp_node_adapters import (
    NODE_INPUT_CANDIDATES,
)


def test_red_and_green_inherit_the_implement_adapter_candidates() -> None:
    """The split stays on the implement stage's selected adapter."""
    assert NODE_INPUT_CANDIDATES["red"] == NODE_INPUT_CANDIDATES["implement"]
    assert NODE_INPUT_CANDIDATES["green"] == NODE_INPUT_CANDIDATES["implement"]
