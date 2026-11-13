"""Fleet integration defaults used by completed-cycle measurement."""

from __future__ import annotations

from livespec_orchestrator_beads_fabro.commands._dispatcher_integration_defaults import (
    FLEET_SOURCE_TREE_DECLARATION_SECTION,
    FLEET_SOURCE_TREE_KEY,
)


def test_source_tree_declaration_location_is_the_shared_fleet_contract() -> None:
    """Completed-cycle sizing reads the same declaration as the product gates."""
    assert FLEET_SOURCE_TREE_DECLARATION_SECTION == (
        "tool",
        "livespec_dev_tooling",
        "mirror_pairings",
    )
    assert FLEET_SOURCE_TREE_KEY == "source_tree"
