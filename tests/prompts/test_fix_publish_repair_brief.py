"""A fix turn entered on a publish_draft repair brief knows how to repair the refused push.

Binds the prompt half of work-item ``bd-ib-7owmkq`` (Scenario 329, ``contracts.md``
"Publish repair"): the fix agent alone removes an oversize path from the run's
unpublished commits or repairs the hook's failed targets, so what it is told is the
deliverable. The graph and the stage are bound in
``tests/integration/test_workflow_publish_repair_scenario329.py``.
"""

from __future__ import annotations

import re
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_FIX_PROMPT = (
    _REPO_ROOT
    / ".claude-plugin"
    / ".fabro"
    / "workflows"
    / "implement-work-item"
    / "prompts"
    / "fix.md"
)
_HEADING = "## When the refresh-repair brief names `stage: publish_draft` with a refused head"
_SECTION = re.compile(
    rf"^{re.escape(_HEADING)}\n.*?(?=\n## |\n\nThis node uses|\Z)", re.DOTALL | re.MULTILINE
)

_REQUIRED_DIRECTIONS = (
    "`refused-head:`",
    "`oversize-paths:`",
    "GH001",
    "Remove each named path from EVERY",
    "commit of this run that origin does not already hold",
    "MUST NOT be rewritten",
    "`failed-gate-targets:`",
    "last 80 lines of the hook's own output",
    "NEVER hand-edit or forge a",
    "Redo Red-Green for that commit",
    "Never pass `--no-verify`, never use bare force",
    "`publish_draft`, then `proof_capture`",
    "two refresh-repair rounds in total",
)


def test_the_fix_prompt_carries_the_publish_repair_protocol() -> None:
    """The section names the brief's fields, the removal rule and the trailer rule."""
    sections = _SECTION.findall(_FIX_PROMPT.read_text(encoding="utf-8"))
    assert len(sections) == 1, f"expected one publish-repair section, got {len(sections)}"

    for direction in _REQUIRED_DIRECTIONS:
        assert direction in sections[0], f"the publish-repair protocol omits {direction!r}"
