"""Pin the explicit inventory for prompts shipped ahead of graph wiring."""

from __future__ import annotations

import runpy
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_INVENTORY_TEST = _REPO_ROOT / "tests" / "prompts" / "test_acp_node_turn_end_discipline.py"


def test_red_and_green_are_declared_pending_graph_prompts() -> None:
    """The bundle control must distinguish the two pre-wiring prompts from orphans."""
    inventory = runpy.run_path(str(_INVENTORY_TEST))

    assert inventory.get("_PENDING_GRAPH_PROMPT_FILES") == ("green.md", "red.md")
