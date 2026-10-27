"""The mixed review-fix verdict leaves record defects for proof capture.

`bd-ib-usu57d`: a review verdict can carry both a repairable tree finding and
an immutable Proof of Done record finding. The existing all-record fallback
correctly returns directly to recapture, but its following ``Otherwise`` arm
made the stage treat the record finding as an unfixable accepted finding after
repairing the tree. That ended the run at needs-human before the ordinary
``review_fix -> janitor -> publish_draft -> proof_capture`` path could replace
the record.

This is a prompt contract because the review-fix agent, not host code, decides
which accepted finding remains for the later proof-capture visit. The prompt
must therefore say both that a mixed round succeeds once its tree work is done
and that an actually unfixable tree finding remains a needs-human outcome.
"""

from __future__ import annotations

import re
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_WORKFLOW = _REPO_ROOT / ".claude-plugin" / ".fabro" / "workflows" / "implement-work-item"
_GRAPH = _WORKFLOW / "workflow.fabro"
_PROMPTS = _WORKFLOW / "prompts"
_REVIEW_FIX_NODE = "review_fix"

_NODE_BLOCK = re.compile(
    r"^[ \t]*(?P<name>\w+)[ \t]*\[$(?P<body>.*?)^[ \t]*\]$",
    re.DOTALL | re.MULTILINE,
)
_PROMPT_ATTR = re.compile(r'prompt="@prompts/(?P<file>[\w.-]+\.md)"')
_MIXED_FIX_STEP = re.compile(r"^3\. Otherwise,.*?(?=^4\. |\Z)", re.DOTALL | re.MULTILINE)
_NEEDS_HUMAN_STEP = re.compile(r"^4\. If an ACCEPTED.*?(?=^5\. |\Z)", re.DOTALL | re.MULTILINE)

_MIXED_RECORD_HANDOFF = "Leave every ACCEPTED `(proof-record)` finding to the `proof_capture` visit this fix round reaches"
_MIXED_TREE_SUCCESS = "Once every ACCEPTED `(tree)` finding is fixed, end succeeded"
_RECORD_IS_NOT_NEEDS_HUMAN = "do not end needs-human solely over the proof-record finding"
_UNFIXABLE_TREE_NEEDS_HUMAN = "If an ACCEPTED `(tree)` finding cannot be implemented honestly within scope, that is a needs-human `failed` outcome"


def _review_fix_prompt_file() -> Path:
    """The prompt file the committed graph assigns to its review-fix node."""
    files: list[str] = []
    for block in _NODE_BLOCK.finditer(_GRAPH.read_text(encoding="utf-8")):
        if block.group("name") != _REVIEW_FIX_NODE:
            continue
        prompt = _PROMPT_ATTR.search(block.group("body"))
        assert prompt is not None, "the review-fix node declares no prompt"
        files.append(prompt.group("file"))
    assert len(files) == 1, f"expected one review-fix prompt, found {files}"
    path = _PROMPTS / files[0]
    assert path.is_file(), f"the graph names missing prompt {path}"
    return path


def _step(*, pattern: re.Pattern[str]) -> str:
    """The one numbered prompt step a contract applies to, whitespace-collapsed."""
    matches = pattern.findall(_review_fix_prompt_file().read_text(encoding="utf-8"))
    assert len(matches) == 1, f"expected one matching review-fix step, found {len(matches)}"
    return re.sub(r"\s+", " ", matches[0])


def test_a_mixed_accepted_verdict_leaves_the_record_for_proof_capture_after_tree_fixes() -> None:
    """A record defect does not turn a completed in-scope tree repair into failure."""
    step = _step(pattern=_MIXED_FIX_STEP)

    for phrase in (
        _MIXED_RECORD_HANDOFF,
        _MIXED_TREE_SUCCESS,
        _RECORD_IS_NOT_NEEDS_HUMAN,
    ):
        assert phrase in step, (
            f"the mixed-findings review-fix step omits {phrase!r}; a repaired tree can "
            "then be stranded at needs-human by the immutable record finding instead of "
            "reaching its ordinary proof-capture visit"
        )


def test_an_unfixable_accepted_tree_finding_still_ends_needs_human() -> None:
    """The record handoff does not retire the failure outcome for tree work."""
    step = _step(pattern=_NEEDS_HUMAN_STEP)

    assert _UNFIXABLE_TREE_NEEDS_HUMAN in step, (
        "the review-fix prompt no longer explicitly preserves needs-human for an accepted "
        "tree finding that cannot honestly be implemented within scope"
    )
