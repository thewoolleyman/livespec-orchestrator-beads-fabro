"""Stage-targeted dispatch rider briefs (Scenario 268)."""

from __future__ import annotations

import importlib
from pathlib import Path
from types import ModuleType

from livespec_orchestrator_beads_fabro.store import WorkItemComment

_MODULE = "livespec_orchestrator_beads_fabro.commands._dispatcher_stage_riders"


def _module() -> ModuleType:
    package = importlib.import_module("livespec_orchestrator_beads_fabro")
    expected = Path(package.__file__ or "").parent / "commands" / "_dispatcher_stage_riders.py"
    assert expected.is_file(), f"{expected} does not exist yet"
    return importlib.import_module(_MODULE)


def _comment(*, text: str) -> WorkItemComment:
    return WorkItemComment(text=text, author="operator", created_at="2026-11-12T00:00:00Z")


def test_riders_reach_only_their_named_stage_or_the_tree_changing_default() -> None:
    module = _module()
    sections = module.stage_rider_sections(
        comments=(
            _comment(text="FOR implement ONLY: IMPLEMENT-RIDER"),
            _comment(text="FOR review_fix ONLY: REVIEW-FIX-RIDER"),
            _comment(text="UNSCOPED-RIDER"),
        ),
        claim_at=None,
    )

    assert "IMPLEMENT-RIDER" in sections["implement"]
    assert "IMPLEMENT-RIDER" not in sections["review"]
    assert "IMPLEMENT-RIDER" not in sections["proof_capture"]
    assert "IMPLEMENT-RIDER" not in sections["proof_verify"]
    assert "REVIEW-FIX-RIDER" in sections["review_fix"]
    assert "UNSCOPED-RIDER" in sections["implement"]
    assert "UNSCOPED-RIDER" in sections["review_fix"]
    assert "UNSCOPED-RIDER" not in sections["review"]
    assert "UNSCOPED-RIDER" not in sections["proof_capture"]
    assert "UNSCOPED-RIDER" not in sections["proof_verify"]
