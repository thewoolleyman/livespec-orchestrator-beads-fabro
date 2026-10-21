"""Contract tests for the scope check 4 of the Definition-of-Done gate reads.

bd-ib-uwhvdv. Check 2 admits an H2 and nothing deeper, so an item whose
governing text sits in an H3 under that H2 has no reference line its filer
could have written instead. Check 4 nonetheless told the gate to judge each
assertion against "the referenced heading" without saying that a heading's
text includes its nested sections, so a judge reading only the H2's lead text
raised "the reference resolves but does not govern the claim" against four
items in one week and prescribed an edit that does not exist.

A prompt test because the judgement is made by the `dod_gate` agent out of
this prose and is rendered by no Python caller: `_dispatcher_dod_judgement`'s
`_section_of` already carries the whole H2 section, nested headings included,
to both the in-run gate and the host preflight, so nothing mechanical can
observe that the judge was told to read less than it was handed.

The needles are scoped to check 4's own numbered item rather than to the whole
prompt: check 2 and check 6 both discuss headings and reference lines at
length, so a whole-file probe would read clean over a check 4 that still said
nothing about nesting. A control asserts the slice really isolated check 4.
"""

from __future__ import annotations

import re
from pathlib import Path

_REPOSITORY_ROOT = Path(__file__).parents[2]
_WORKFLOW_GRAPH = (
    _REPOSITORY_ROOT / ".claude-plugin/.fabro/workflows/implement-work-item/workflow.fabro"
)
_PROMPTS_DIRECTORY = _WORKFLOW_GRAPH.parent / "prompts"
_NODE_BLOCK = re.compile(
    r"^[ \t]*(?P<name>\w+)[ \t]*\[$(?P<body>.*?)^[ \t]*\]$",
    re.DOTALL | re.MULTILINE,
)
_PROMPT_ATTRIBUTE = re.compile(r'prompt="@prompts/(?P<filename>[\w.-]+\.md)"')
_DOD_GATE_NODE = "dod_gate"
_CHECK_FOUR = re.compile(
    r"^4\. \*\*The assertions are coherent\.\*\*.*?(?=^5\. \*\*)",
    re.DOTALL | re.MULTILINE,
)
_RECOGNISABILITY_SENTENCE = "recognise as satisfied or unsatisfied from the referenced heading is"
_CHECK_THREE_ONLY = "a closed triple"
_CHECK_FIVE_ONLY = "Check 3 catches a mode declared too WEAK"
_CHECK_SIX_ONLY = "A **test-existence assertion** is one whose subject is the existence,"
_WHOLE_SECTION_SCOPE = (
    "A referenced heading means its WHOLE SECTION, never its lead text",
    "the named H2 together with",
    "every nested heading beneath it",
    "up to the next H2 of that file",
)
_NESTED_TEXT_GOVERNS = (
    "Text you find in such a nested section GOVERNS THE ASSERTION exactly as",
    "is governed by it, is coherent",
    "from, the referenced heading's whole section, its nested headings",
)


def _dod_gate_prompt() -> Path:
    """Return the prompt file the workflow assigns to the Definition-of-Done gate."""
    graph = _WORKFLOW_GRAPH.read_text(encoding="utf-8")
    prompt_filenames = [
        match.group("filename")
        for node in _NODE_BLOCK.finditer(graph)
        if node.group("name") == _DOD_GATE_NODE
        for match in [_PROMPT_ATTRIBUTE.search(node.group("body"))]
        if match is not None
    ]

    assert prompt_filenames == ["dod-gate.md"]
    return _PROMPTS_DIRECTORY / prompt_filenames[0]


def _check_four() -> str:
    """Return check 4's own numbered item, sliced out of the gate prompt."""
    prompt = _dod_gate_prompt()
    assert prompt.is_file()
    slice_ = _CHECK_FOUR.search(prompt.read_text(encoding="utf-8"))
    assert slice_ is not None, "check 4 of the Definition-of-Done gate prompt did not parse"
    return slice_.group(0)


def test_the_check_four_slice_isolates_check_four() -> None:
    """The control: the slice is check 4 and carries no neighbouring check's text.

    Every assertion below reads this slice, so a slice that silently captured
    the whole prompt — or the wrong numbered item — would let those assertions
    pass on prose that says nothing about nesting. The positive half names a
    sentence only check 4 carries; the negative half names one sentence each
    from checks 3, 5 and 6, so an over-capturing slice fails here.
    """
    check_four = _check_four()

    assert _RECOGNISABILITY_SENTENCE in check_four
    assert _CHECK_THREE_ONLY not in check_four
    assert _CHECK_FIVE_ONLY not in check_four
    assert _CHECK_SIX_ONLY not in check_four


def test_check_four_reads_a_referenced_heading_as_its_whole_nested_section() -> None:
    """The referenced heading is the H2 plus every nested heading, to the next H2."""
    check_four = _check_four()

    for needle in _WHOLE_SECTION_SCOPE:
        assert needle in check_four, needle


def test_check_four_says_text_in_a_nested_section_governs_the_assertion() -> None:
    """Governing text found under a nested heading governs, so it is not a finding."""
    check_four = _check_four()

    for needle in _NESTED_TEXT_GOVERNS:
        assert needle in check_four, needle
