"""Repository-preflight verdicts are durable, reusable package decisions."""

from __future__ import annotations

import importlib
from pathlib import Path

_MODULE_PATH = Path(
    ".claude-plugin/scripts/livespec_orchestrator_beads_fabro/commands/"
    "_dod_preflight_judgement.py"
)


def test_a_passing_repository_preflight_records_its_taking() -> None:
    """The package seam owns the record a successful preflight leaves behind."""
    assert _MODULE_PATH.is_file()

    judgement = importlib.import_module(
        "livespec_orchestrator_beads_fabro.commands._dod_preflight_judgement"
    )

    assert hasattr(judgement, "repository_preflight_reading")
