"""The committing repair prompts hand a still-running runner commit to settle.

Scenario 179 makes this prompt instruction observable at the runner boundary:
`fix` and `review_fix` may wait once for a commit run, but must finish their
turn instead of polling when that wait reports `running`.  The two prompts are
derived from their committed graph nodes, so a later prompt rewire cannot leave
one stage untested.
"""

from __future__ import annotations

import re
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_WORKFLOW = _REPO_ROOT / ".claude-plugin" / ".fabro" / "workflows" / "implement-work-item"
_GRAPH = _WORKFLOW / "workflow.fabro"
_PROMPTS = _WORKFLOW / "prompts"

_NODE_BLOCK = re.compile(
    r"^[ \t]*(?P<name>\w+)[ \t]*\[$(?P<body>.*?)^[ \t]*\]$",
    re.DOTALL | re.MULTILINE,
)
_PROMPT_ATTR = re.compile(r'prompt="@prompts/(?P<file>[\w.-]+\.md)"')
_STAGES = {"fix": "fix_commit_settle", "review_fix": "review_fix_commit_settle"}


def _prompt(*, stage: str) -> str:
    """The prompt bytes the committed graph dispatches for one repair stage."""
    matches = [
        _PROMPT_ATTR.search(block.group("body"))
        for block in _NODE_BLOCK.finditer(_GRAPH.read_text(encoding="utf-8"))
        if block.group("name") == stage
    ]
    assert len(matches) == 1 and matches[0] is not None, f"{stage} has no unique prompt"
    return (_PROMPTS / matches[0].group("file")).read_text(encoding="utf-8")


def test_repair_prompts_wait_once_then_leave_a_running_commit_to_their_settle() -> None:
    """A hook outlasting one tool call cannot turn either repair stage into a poller."""
    for stage, settle in _STAGES.items():
        prompt = _prompt(stage=stage)

        assert "Wait at most once on each commit run you start." in prompt
        assert (
            "If that wait reports `running`, do not call `wait` again and do not stop it." in prompt
        )
        assert f"End the turn and leave it for `{settle}` to wait out." in prompt
