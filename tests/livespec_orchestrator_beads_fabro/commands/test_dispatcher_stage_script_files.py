"""The publication stages execute committed scripts, not prompt-sized bodies."""

from __future__ import annotations

import re
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands import dispatcher

_PLUGIN_ROOT = Path(dispatcher.__file__).resolve().parents[3]
_WORKFLOW_DIR = _PLUGIN_ROOT / ".fabro" / "workflows" / "implement-work-item"
_NODES = ("publish_draft", "pr_refresh", "pr", "pr_refresh_head")


def test_publication_nodes_invoke_their_committed_stage_scripts() -> None:
    """The full graph retains only short, template-expanded file invocations."""
    graph = (_WORKFLOW_DIR / "workflow.fabro").read_text(encoding="utf-8")
    for node in _NODES:
        match = re.search(rf'(?ms)^    {node} \[.*?^        script="(?P<script>[^\n]*)"$', graph)
        assert match is not None
        assert len(match.group("script")) < 500
        assert f"/livespec-stage-scripts/{node}.sh" in match.group("script")
        assert (_WORKFLOW_DIR / "stages" / f"{node}.sh").is_file()
