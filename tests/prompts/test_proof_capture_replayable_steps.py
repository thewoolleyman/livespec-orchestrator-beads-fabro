"""The two replayability properties the proof-capture prompt must demand.

bd-ib-mhqj3h: the `proof_verify` leg graded this item's own record
`not_reproduced` while the implementation under it was correct. Both defects
were in the PUBLISHED PROCEDURE, and both were properties the capture prompt's
Step 2 list did not ask for:

1. An expectation the capture's own publication made permanently unobservable.
   A step expected the pull request's timeline to carry the unique event set
   `committed`. Posting the record added a `commented` event to that same
   timeline, so the replay observed `commented,committed` and no replayer can
   ever see `committed` alone again.
2. Four of five published steps aborted before exercising anything. The
   harness called `Path.mkdir(parents=True)` with no `exist_ok=True`, and the
   capture leg's own scratch worlds persist in the sandbox the replay runs in,
   so each step raised `FileExistsError`.

Neither hazard had any coverage in the prompt before this change: scope
searched was both proof prompts in full, over twelve patterns including
`idempot`, `exist_ok`, `pre-existing`, `twice` and `timeline`, all zero, while
`scratch` and `posting` returned hits in the same files — so the instrument
reached the prose and the absences were real.

The prompt under test is DERIVED from the committed graph's `proof_capture`
node rather than spelled here, per this tier's convention: a literal path keeps
passing after the node is re-pointed at a different prompt, which is an
instrument that cannot return the hit it exists to find. The sibling control
asserts the derivation named exactly one such node and that its file is on
disk.

POLARITY IS PINNED POSITIVELY. Each property is asserted by requiring the
sentence that demands it, never by probing for the absence of a bad practice —
a probe for "no exact-total expectation" could never return a hit and would
read clean over a prompt that said nothing at all. Needles are chosen to sit
within ONE physical line of the hard-wrapped prose, because a needle
straddling a line break fails while the prose says exactly the thing.
"""

from __future__ import annotations

import re
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_WORKFLOW_DIR = _REPO_ROOT / ".claude-plugin" / ".fabro" / "workflows" / "implement-work-item"
_PROMPTS_DIR = _WORKFLOW_DIR / "prompts"
_GRAPH = _WORKFLOW_DIR / "workflow.fabro"

# A graph node block is `<name> [` on its own line through a closing `]` on its
# own line. Edge declarations carry their attributes inline on ONE line, so this
# shape cannot match an edge.
_NODE_BLOCK = re.compile(
    r"^[ \t]*(?P<name>\w+)[ \t]*\[$(?P<body>.*?)^[ \t]*\]$",
    re.DOTALL | re.MULTILINE,
)
_PROMPT_ATTR = re.compile(r'prompt="@prompts/(?P<file>[\w.-]+\.md)"')
_CAPTURE_NODE = "proof_capture"

_STEP_2_HEADING = "## Step 2 — author the reproduction steps for each factory_captured assertion"
_STEP_3_HEADING = "## Step 3 — execute the steps verbatim"

# One regex rather than a find-the-next-heading walk: the lookahead ends each
# section at the next H2 or at end of file without a branch either way.
_STEP_2_SECTION = re.compile(
    rf"^{re.escape(_STEP_2_HEADING)}\n.*?(?=\n## |\Z)",
    re.DOTALL | re.MULTILINE,
)
_STEP_3_SECTION = re.compile(
    rf"^{re.escape(_STEP_3_HEADING)}\n.*?(?=\n## |\Z)",
    re.DOTALL | re.MULTILINE,
)

# Property 1 — an expectation the record's own publication cannot falsify.
_UNFALSIFIABLE_BY_OWN_RECORD = (
    "**Unfalsifiable by your own record.**",
    "to the very pull request your steps observe, so an expectation stated as",
    "No replayer can ever meet it.",
    "never as an exact set, count or total of everything present.",
)

# Property 2 — a program that survives its own prior run.
_RERUNNABLE_OVER_OWN_LEAVINGS = (
    "**Re-runnable over your own leavings.**",
    "sandbox, AFTER you, so every scratch directory, repository and file your",
    "that builds its scratch state without tolerating a pre-existing copy",
    "or derive a per-invocation scratch root.",
)

# The mechanical control that catches property 2 before publication.
_SECOND_PASS_CONTROL = (
    "Then run the WHOLE sequence a SECOND time, in the same sandbox, without",
    "clearing anything by hand.",
    "hand-cleaned scratch root is a step to FIX here, not a note for the",
)


def _capture_prompt_files() -> tuple[str, ...]:
    """Prompt filenames of every node named `proof_capture` in the committed graph."""
    graph = _GRAPH.read_text(encoding="utf-8")
    names: list[str] = []
    for block in _NODE_BLOCK.finditer(graph):
        if block.group("name") != _CAPTURE_NODE:
            continue
        attr = _PROMPT_ATTR.search(block.group("body"))
        assert attr is not None, f"node {_CAPTURE_NODE} declares no prompt"
        names.append(attr.group("file"))
    return tuple(names)


_CAPTURE_PROMPT_FILES = _capture_prompt_files()


def _capture_prompt_text() -> str:
    assert len(_CAPTURE_PROMPT_FILES) == 1
    return (_PROMPTS_DIR / _CAPTURE_PROMPT_FILES[0]).read_text(encoding="utf-8")


def _one_section(*, pattern: re.Pattern[str], heading: str) -> str:
    sections = pattern.findall(_capture_prompt_text())
    assert len(sections) == 1, (
        f"the proof-capture prompt carries {len(sections)} sections headed "
        f"{heading!r}; expected exactly one"
    )
    return sections[0]


def test_the_graph_scan_names_one_proof_capture_prompt_that_is_on_disk() -> None:
    """Control: the derivation can return a hit, and the file it names exists."""
    assert len(_CAPTURE_PROMPT_FILES) == 1, (
        f"graph declares {len(_CAPTURE_PROMPT_FILES)} `{_CAPTURE_NODE}` nodes "
        f"with a prompt; expected one"
    )
    named = _PROMPTS_DIR / _CAPTURE_PROMPT_FILES[0]
    assert named.is_file(), f"{named} is declared by the graph but absent on disk"


def test_step_2_forbids_an_expectation_the_records_own_posting_falsifies() -> None:
    section = _one_section(pattern=_STEP_2_SECTION, heading=_STEP_2_HEADING)

    for phrase in _UNFALSIFIABLE_BY_OWN_RECORD:
        assert phrase in section, (
            f"the reproduction-step property list omits the "
            f"unfalsifiable-by-your-own-record line {phrase!r}"
        )


def test_step_2_requires_a_program_that_survives_its_own_prior_run() -> None:
    section = _one_section(pattern=_STEP_2_SECTION, heading=_STEP_2_HEADING)

    for phrase in _RERUNNABLE_OVER_OWN_LEAVINGS:
        assert phrase in section, (
            f"the reproduction-step property list omits the "
            f"re-runnable-over-your-own-leavings line {phrase!r}"
        )


def test_step_3_requires_a_second_pass_over_the_uncleaned_sandbox() -> None:
    section = _one_section(pattern=_STEP_3_SECTION, heading=_STEP_3_HEADING)

    for phrase in _SECOND_PASS_CONTROL:
        assert (
            phrase in section
        ), f"the execute-verbatim step omits the second-pass control line {phrase!r}"


def test_every_pinned_needle_sits_within_one_physical_line() -> None:
    """Control on this test's own instrument, per this tier's wrapping convention.

    A needle straddling a hard-wrap boundary can only fail silently: the prose
    could say exactly the required thing and the probe would still miss it. So
    every needle above must be findable in some single line of the prompt,
    which is what makes the three assertions capable of returning a hit.
    """
    lines = _capture_prompt_text().splitlines()

    for phrase in (
        *_UNFALSIFIABLE_BY_OWN_RECORD,
        *_RERUNNABLE_OVER_OWN_LEAVINGS,
        *_SECOND_PASS_CONTROL,
    ):
        assert any(phrase in line for line in lines), (
            f"needle {phrase!r} spans a line break, so the probe for it could "
            f"only ever fail silently"
        )
