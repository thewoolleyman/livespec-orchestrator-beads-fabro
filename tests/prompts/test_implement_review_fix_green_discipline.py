"""The commit discipline shared by the implement and review-fix stage briefs.

The stage prompts, rather than host code, tell an agent how to shape its Red
and Green commits.  Each assertion here is therefore a prompt-tier contract.
Both prompt paths are derived from the committed workflow graph: a literal path
would keep passing if a stage were repointed at a different prompt.
"""

from __future__ import annotations

import re
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_WORKFLOW_DIR = _REPO_ROOT / ".claude-plugin" / ".fabro" / "workflows" / "implement-work-item"
_PROMPTS_DIR = _WORKFLOW_DIR / "prompts"
_GRAPH = _WORKFLOW_DIR / "workflow.fabro"

_NODE_BLOCK = re.compile(
    r"^[ \t]*(?P<name>\w+)[ \t]*\[$(?P<body>.*?)^[ \t]*\]$",
    re.DOTALL | re.MULTILINE,
)
_PROMPT_ATTR = re.compile(r'prompt="@prompts/(?P<file>[\w.-]+\.md)"')
_STAGES = ("implement", "review_fix")


def _stage_prompts() -> dict[str, Path]:
    """The prompt each governed stage's committed graph node names."""
    found: dict[str, Path] = {}
    for block in _NODE_BLOCK.finditer(_GRAPH.read_text(encoding="utf-8")):
        stage = block.group("name")
        if stage not in _STAGES:
            continue
        prompt = _PROMPT_ATTR.search(block.group("body"))
        assert prompt is not None, f"node {stage} declares no prompt"
        assert stage not in found, f"graph declares {stage} more than once"
        found[stage] = _PROMPTS_DIR / prompt.group("file")
    return found


_PROMPTS = _stage_prompts()


def _prompt_text(*, stage: str) -> str:
    return _PROMPTS[stage].read_text(encoding="utf-8")


def test_the_graph_derives_both_governed_stage_prompts_on_disk() -> None:
    """Control: each prompt assertion below has a prompt it can actually read."""
    assert set(_PROMPTS) == set(_STAGES)
    for stage, prompt in _PROMPTS.items():
        assert prompt.is_file(), f"node {stage} names absent prompt {prompt}"


def test_review_fix_requires_one_test_file_and_no_product_file_at_red() -> None:
    prompt = _prompt_text(stage="review_fix")

    assert "stage exactly one test file and no product file" in prompt


def test_both_prompts_require_touched_tests_to_pass_before_green() -> None:
    """A Green commit is gated on every test file the change touches."""
    for stage in _STAGES:
        assert (
            "Before every Green commit or Green amend, run every test file the "
            "change touches and see each one pass."
        ) in _prompt_text(stage=stage)
