"""The gate prompt's check 6 reads the verdict, and still steers the proof.

Two of work-item `bd-ib-m76p2n`'s assertions meet in one paragraph of
`dod-gate.md`, and they pull in opposite directions — which is why they are
bound together rather than in two modules that could each pass while the
paragraph as a whole was wrong.

The FIRST is the node's leg of assertion 1: the node must take the
governing-heading verdict from the spec-stated judgement rather than from its
own recollection, and name the heading it returns as the remedy. The Dispatcher
writes that verdict into the brief as a block, so the prompt has to name that
block in the words the renderer uses — which is why every needle here is
IMPORTED from `_dod_governing_heading` rather than retyped. A prompt naming a
block the renderer does not write is a prompt pointed at nothing, and it reads
exactly like a correct one.

The SECOND is assertion 3, which is a REGRESSION guarantee: the node must steer
the proof stage to the referenced scenario's steps "exactly as before". The
rewrite replaced the paragraph that carried that steering, so the steering is
the thing most easily lost to it — and losing it is silent, because a capture
stage that was never told to walk the scenario still produces a record.

THE FALLBACK IS ASSERTED TOO, and it is the arm a reader is most likely to
delete as redundant. A verdict the Dispatcher could not take renders an explicit
ABSENCE rather than no block at all, and the node's answer to that absence is
its own search — so a prompt that dropped the search would leave the node with
nothing to do on exactly the dispatches where the component was unavailable.

PROMPT PROSE IS HARD-WRAPPED, so every needle is chosen to sit WITHIN one
physical line. A needle straddling a line break can only fail silently while the
prose says exactly the thing.
"""

from __future__ import annotations

import re
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dod_governing_heading import (
    GOVERNING_HEADING_BLOCK_HEADING,
)

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


def _dod_gate_prompt() -> str:
    """The prompt the committed graph assigns to the gate, read off the graph.

    Resolved through the node's own attribute rather than by filename, so a
    rewiring that pointed the gate at a different prompt fails here instead of
    leaving this module grading a file nothing runs.
    """
    graph = _WORKFLOW_GRAPH.read_text(encoding="utf-8")
    filenames = [
        match.group("filename")
        for node in _NODE_BLOCK.finditer(graph)
        if node.group("name") == _DOD_GATE_NODE
        for match in [_PROMPT_ATTRIBUTE.search(node.group("body"))]
        if match is not None
    ]

    assert filenames == ["dod-gate.md"]
    return (_PROMPTS_DIRECTORY / filenames[0]).read_text(encoding="utf-8")


def test_the_gate_reads_the_governing_heading_verdict_the_dispatcher_writes() -> None:
    """The block is named in the renderer's own words, not in a retyped copy."""
    prompt = _dod_gate_prompt()

    assert GOVERNING_HEADING_BLOCK_HEADING in prompt
    assert "governing heading:" in prompt


def test_the_gate_names_the_returned_heading_as_the_remedy() -> None:
    """One remedy across four surfaces: add the heading to the reference line."""
    prompt = _dod_gate_prompt()

    assert "the reference line does not name verbatim is a" in prompt
    assert "name that heading and give the remedy, which is to add it to" in prompt


def test_an_unstated_verdict_raises_no_reference_line_finding() -> None:
    """Behaviour the tree does not state is the spec-change tier's business.

    Telling a filer to cite a clause that does not exist is a remedy they
    cannot carry out, so the prompt has to say this arm produces no finding.
    """
    prompt = _dod_gate_prompt()

    assert "A `kind: unstated` verdict names no governing heading, so there is no" in prompt


def test_the_gate_keeps_its_own_search_for_a_verdict_that_was_not_taken() -> None:
    """The absence arm: without the search, an unavailable component mutes check 6."""
    prompt = _dod_gate_prompt()

    assert "no judgement was taken" in prompt
    assert "Search `scenarios.md`" in prompt
    assert "before concluding none does" in prompt


def test_the_gate_still_steers_the_proof_stage_to_the_referenced_scenario() -> None:
    """Assertion 3, and the thing the rewrite could most easily have dropped.

    A capture stage that was never told to walk the scenario still produces a
    record, so the loss is invisible at every surface downstream of it.
    """
    prompt = _dod_gate_prompt()

    assert "referenced scenario governs the proof, and the capture stage is told to" in prompt
    assert "follow that scenario's own steps." in prompt


def test_a_surplus_citation_is_still_not_a_finding_of_its_own() -> None:
    """A non-scenario H2 remains valid for an assertion no scenario states.

    The judgement answers which clauses GOVERN, not which citations are
    surplus, so a mirror rule refusing an unreturned reference would refuse
    conforming items — and it is the rule a reader is most likely to add.
    """
    prompt = _dod_gate_prompt()

    assert "valid reference for an assertion no" in prompt
    assert "a reference the verdict did not return is not a" in prompt
