"""Review-fix avoids duplicate aggregate checks and delegates a live commit.

Scenario 255 assigns the review-fix turn the affected-tests gate and reserves
the one full aggregate for the following janitor visit.  A separate settle
node owns a commit-runner job that outlives the turn, so the prompt must not
spend the ACP timeout polling that job after all other work is complete.
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

_AFFECTED_TESTS_RULE = (
    "Run only the tests your change touches; the commit hook runs the affected-tests gate."
)
_JANITOR_AGGREGATE_RULE = "Leave the one full check aggregate to the following janitor visit."
_LIVE_COMMIT_HANDOFF = (
    "end the turn as succeeded, name that commit run's id in your final message, "
    "and leave it for `review_fix_commit_settle` to wait out"
)


def _review_fix_prompt() -> str:
    """Read the one prompt the committed review-fix graph node dispatches."""
    files: list[str] = []
    for block in _NODE_BLOCK.finditer(_GRAPH.read_text(encoding="utf-8")):
        if block.group("name") != "review_fix":
            continue
        prompt = _PROMPT_ATTR.search(block.group("body"))
        assert prompt is not None, "the review-fix node declares no prompt"
        files.append(prompt.group("file"))
    assert files == ["review-fix.md"], f"review-fix names unexpected prompts: {files}"
    return (_PROMPTS / files[0]).read_text(encoding="utf-8")


def test_review_fix_runs_only_affected_tests_and_leaves_the_aggregate_to_janitor() -> None:
    """The turn does not duplicate the one full aggregate owned by janitor."""
    prompt = _review_fix_prompt()

    assert _AFFECTED_TESTS_RULE in prompt
    assert _JANITOR_AGGREGATE_RULE in prompt
    assert "Re-run the repository's check suite" not in prompt


def test_review_fix_hands_a_only_remaining_live_commit_run_to_the_settle_node() -> None:
    """A live hook does not consume the review-fix ACP turn's remaining timeout."""
    prompt = _review_fix_prompt()

    assert _LIVE_COMMIT_HANDOFF in prompt
