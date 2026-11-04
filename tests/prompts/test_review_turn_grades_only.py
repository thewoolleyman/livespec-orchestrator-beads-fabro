"""The review prompt tells the reviewer it grades the published diff and nothing else.

Work-item `bd-ib-azxvoo`. Run 01M5Y3EGXZSS (work-item `bd-ib-davaxq`, 2026-10-27)
lost its review turn to its 1800 s allowance: the reviewer rebased the run branch
and started the whole check suite, and the run ended at `needs_human` with no
verdict although everything before it had succeeded. The hook that refuses those
commands is covered by `test_dispatcher_review_guard.py`; this module binds the
PROMPT half, because a refusal the reviewer was never told to expect reads as a
broken sandbox rather than as the rule it is.

WHY A PROMPT TEST. The instruction is prose the `review` agent follows and no
Python caller renders it, exactly as the proof-record disciplines beside this
module record.

THE PROMPT IS DERIVED FROM THE GRAPH's `review` node rather than named by path,
so this asserts about the file that node actually dispatches. WHITESPACE IS
COLLAPSED BEFORE EVERY PROBE: the prose is hard-wrapped, and a needle straddling
a line break would fail while the prose says exactly the thing.
"""

from __future__ import annotations

import re
from pathlib import Path

_WORKFLOW_DIR = (
    Path(__file__).resolve().parents[2] / ".claude-plugin" / ".fabro" / "workflows"
) / "implement-work-item"
_NODE_BLOCK = re.compile(
    r"^[ \t]*(?P<name>\w+)[ \t]*\[$(?P<body>.*?)^[ \t]*\]$",
    re.DOTALL | re.MULTILINE,
)
_PROMPT_ATTR = re.compile(r'prompt="@prompts/(?P<file>[\w.-]+\.md)"')
_SECTION = re.compile(
    r"^## The review turn grades\b[^\n]*$.*?(?=^## |\Z)", re.DOTALL | re.MULTILINE
)


def _review_prompt() -> str:
    graph = (_WORKFLOW_DIR / "workflow.fabro").read_text(encoding="utf-8")
    files = [
        found.group("file")
        for block in _NODE_BLOCK.finditer(graph)
        if block.group("name") == "review"
        for found in [_PROMPT_ATTR.search(block.group("body"))]
        if found is not None
    ]
    assert len(files) == 1, files
    return (_WORKFLOW_DIR / "prompts" / files[0]).read_text(encoding="utf-8")


def _section() -> str:
    found = _SECTION.search(_review_prompt())
    assert found is not None, "the review prompt carries no 'The review turn grades' section"
    return " ".join(found.group(0).split())


def test_the_review_prompt_states_what_the_reviewer_grades() -> None:
    section = _section()
    assert "published diff" in section
    assert "latest recorded proof" in section


def test_the_review_prompt_forbids_branch_edits_and_names_the_rebase_owner() -> None:
    section = _section()
    for needle in ("Make no branch edits", "git rebase", "git commit", "git push", "pr_refresh"):
        assert needle in section, needle
    assert "head after your turn must equal the head before it" in section


def test_the_review_prompt_forbids_the_whole_suite_and_allows_named_test_ids() -> None:
    section = _section()
    assert "Run no whole-suite check" in section
    assert "just check" in section
    assert "named test id" in section


def test_the_review_prompt_requires_the_verdict_label_within_the_allowance() -> None:
    section = _section()
    assert "within your turn allowance" in section
    assert "emit your verdict label" in section
