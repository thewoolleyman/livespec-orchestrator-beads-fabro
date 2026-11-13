"""Mirror entry point for node-timeout coverage."""

from livespec_orchestrator_beads_fabro.commands._node_timeouts import default_node_timeouts


def test_default_node_timeouts_are_available() -> None:
    """The dispatcher timeout tests cover the detailed resolution branches."""
    assert default_node_timeouts().seconds_for(node="red") > 0
