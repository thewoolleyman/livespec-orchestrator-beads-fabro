"""The preflight and gate use one Definition-of-Done identity choice."""

from __future__ import annotations

import importlib
from pathlib import Path

_MODULE_PATH = Path(
    ".claude-plugin/scripts/livespec_orchestrator_beads_fabro/commands/"
    "_dispatcher_dod_judgement_preflight_reuse.py"
)


def test_a_released_spec_change_tier_uses_the_whole_tree_identity() -> None:
    """A release cannot reuse a clause-form verdict from before ratification."""
    assert _MODULE_PATH.is_file()
    reuse = importlib.import_module(
        "livespec_orchestrator_beads_fabro.commands._dispatcher_dod_judgement_preflight_reuse"
    )

    comments = (
        "livespec-spec-change-tier\n\ntier: spec-change",
        "livespec-spec-change-tier\n\ntier: none",
    )

    assert reuse.released_spec_change_tier(comments=comments) is True
