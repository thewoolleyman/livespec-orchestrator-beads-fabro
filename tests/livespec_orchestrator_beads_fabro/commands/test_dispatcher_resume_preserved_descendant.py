"""A preserved descendant must refuse a resume before it can discard work."""

from __future__ import annotations

import importlib
from pathlib import Path
from typing import Any

_MODULE_NAME = "livespec_orchestrator_beads_fabro.commands._dispatcher_resume_preserved_descendant"
_MODULE_PATH = Path(
    ".claude-plugin/scripts/livespec_orchestrator_beads_fabro/commands/"
    "_dispatcher_resume_preserved_descendant.py"
)


def test_a_descending_preservation_refusal_names_the_ref_tip_head_and_plain_dispatch() -> None:
    """The remedial dispatch cannot hide which preserved work would be lost."""
    assert _MODULE_PATH.is_file()
    module: Any = importlib.import_module(_MODULE_NAME)

    refusal = module.descending_preservation_refusal(
        preservation_ref="refs/heads/needs-human/run-1",
        preservation_tip="b" * 40,
        published_head="a" * 40,
    )

    assert "refs/heads/needs-human/run-1" in refusal
    assert "b" * 40 in refusal
    assert "a" * 40 in refusal
    assert "dispatch" in refusal
