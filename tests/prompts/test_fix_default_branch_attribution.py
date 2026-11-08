"""A fix turn verifies default-branch attribution before it can rest a run.

The fix agent alone decides whether an incoming red belongs to the default
branch or to the run it is repairing.  This is therefore a prompt-tier
contract: the graph can preserve the reported reason, but cannot establish
whether the agent ever ran the failed targets against both trees.
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

_ATTRIBUTION_HEADING = "## Default-branch attribution is evidence, never a guess"
_SECTION = re.compile(
    rf"^{re.escape(_ATTRIBUTION_HEADING)}\n.*?(?=\n## |\Z)",
    re.DOTALL | re.MULTILINE,
)

_REQUIRED_DIRECTIONS = (
    "run EVERY failed test named by the janitor aggregate or refresh-repair brief",
    "against the default branch's own tree in this sandbox",
    "see that test FAIL there",
    "PASSES on the default branch's tree and FAILS on this run's tree",
    "caused by this run's own work, including the integration a refresh-repair round performs",
    "Fix it inside this turn; do NOT route it to needs_human",
    "name EACH failed test together with its result on the default branch's tree",
    "its result on this run's tree",
    "Account for EVERY failed target named by the janitor aggregate or refresh-repair brief",
    "Do NOT stop a still-running check-suite worker",
)


def _fix_prompt_text() -> str:
    """Read the prompt the committed graph actually dispatches for `fix`."""
    graph = _GRAPH.read_text(encoding="utf-8")
    filenames: list[str] = []
    for block in _NODE_BLOCK.finditer(graph):
        if block.group("name") != "fix":
            continue
        attribute = _PROMPT_ATTR.search(block.group("body"))
        assert attribute is not None, "the fix graph node declares no prompt"
        filenames.append(attribute.group("file"))
    assert filenames == ["fix.md"], f"unexpected fix prompt mapping: {filenames}"
    return (_PROMPTS_DIR / filenames[0]).read_text(encoding="utf-8")


def test_the_fix_prompt_makes_default_branch_attribution_a_two_tree_test() -> None:
    """An inherited reason has per-target evidence and never abandons a run-owned red."""
    sections = _SECTION.findall(_fix_prompt_text())
    assert (
        len(sections) == 1
    ), f"expected one default-branch attribution section, got {len(sections)}"

    for direction in _REQUIRED_DIRECTIONS:
        assert direction in sections[0], f"the attribution protocol omits {direction!r}"
