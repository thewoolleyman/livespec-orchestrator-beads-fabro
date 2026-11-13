"""Mirror coverage for ACP chain sources."""

from livespec_orchestrator_beads_fabro.commands._dispatcher_acp_chain_sources import (
    _attached_chains,
)


def test_attached_chain_sources_are_importable() -> None:
    """The graph renderer supplies the Red/Green clones from this module."""
    assert callable(_attached_chains)
