"""The completion field the factory implement stage must direct its turn to state.

`SPECIFICATION/contracts.md` section "Self-contained plugin dispatch" ->
"An implement turn that ends incomplete does not succeed" (v165) requires the
`implement` prompt to direct the turn to END ITS FINAL REPLY with a structured
completion field stating whether the work item's Definition of Done is complete
on the committed branch. That is a claim about PROSE: the field is authored by
the agent out of this instruction and is rendered by no Python caller, so nothing
host-side can observe whether a turn was ever asked for it.

THE MECHANISM IS NOT ASSERTED HERE AND THIS INSTRUCTION IS NOT ASSERTED THERE.
`tests/integration/test_implement_completion_field_scenario204.py` owns what the
stage's completion gate DOES with the field; a gate reading a record no prompt
ever asks for would fail every conforming run, and an instruction no gate reads
would be advice. The one join between the two halves is the record's PATH, and
this module derives it from the GATE'S OWN SCRIPT rather than spelling it, so a
rename on either side fails here instead of in production — where it would
surface as a run that recorded its completion somewhere nothing looks.

The prompt under test is DERIVED from the committed graph's `implement` node
rather than spelled, so this asserts about the file that node actually
dispatches: a literal path would keep passing after the node was re-pointed at a
different prompt, which is an instrument that cannot return the hit it exists to
find. The sibling control asserts the derivation named exactly one such node and
that the file it named is on disk.
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
_IMPLEMENT_NODE = "implement"
_GATE_NODE = "implement_completion"

# The record path, read off the gate's own `git rev-parse --git-path` argument.
_RECORD_PATH = re.compile(r"git rev-parse --git-path (?P<path>livespec-[\w-]+)\)")

_HEADING = "## The completion field — state whether the Definition of Done is done"
# One regex rather than a find-the-next-heading walk: the lookahead ends the
# section at the next H2 or at end of file without a branch either way.
_SECTION = re.compile(
    rf"^{re.escape(_HEADING)}\n.*?(?=\n## |\Z)",
    re.DOTALL | re.MULTILINE,
)

# Needles chosen to sit WITHIN one physical line of the hard-wrapped block: a
# needle straddling a line break fails while the prose says exactly the thing,
# which is a probe that can only fail silently.
_REQUIRED_PHRASES = (
    "This stage's outcome is decided from a structured COMPLETION FIELD you",
    "state, NOT from your turn merely ending. End your final reply with that",
    "field, stating whether the work-item's Definition of Done is complete on",
    "the committed branch, and record the SAME field — as the last thing you",
    '{"definition_of_done_complete": true}',
    '{"definition_of_done_complete": false}',
    "LIVESPEC_IMPLEMENT_PARTIAL_PROGRESS",
)

# The three verdicts the clause enumerates, pinned POSITIVELY — each as its own
# needle, because a section carrying two of them reads as complete prose and
# would leave the third arm unasked for.
_COMPLETE_VERDICT = "- COMPLETE. Every assertion of the Definition of Done is satisfied by"
_INCOMPLETE_VERDICT = "- INCOMPLETE. Anything of the Definition of Done is still owed — an"
_ABSENT_VERDICT = "- NO FIELD AT ALL is read as INCOMPLETE. A turn that states nothing is"


def _node_bodies() -> dict[str, str]:
    """Each declared node's attribute body, by node name."""
    graph = _GRAPH.read_text(encoding="utf-8")
    return {block.group("name"): block.group("body") for block in _NODE_BLOCK.finditer(graph)}


def _implement_prompt_files() -> tuple[str, ...]:
    """Prompt filenames of every node named `implement` in the committed graph."""
    names: list[str] = []
    for name, body in _node_bodies().items():
        if name != _IMPLEMENT_NODE:
            continue
        attr = _PROMPT_ATTR.search(body)
        assert attr is not None, f"node {_IMPLEMENT_NODE} declares no prompt"
        names.append(attr.group("file"))
    return tuple(names)


_IMPLEMENT_PROMPT_FILES = _implement_prompt_files()


def _implement_prompt_text() -> str:
    assert len(_IMPLEMENT_PROMPT_FILES) == 1
    return (_PROMPTS_DIR / _IMPLEMENT_PROMPT_FILES[0]).read_text(encoding="utf-8")


def _gate_record_path() -> str:
    """The record path the completion gate resolves, read off its own script."""
    body = _node_bodies()[_GATE_NODE]
    found = {match.group("path") for match in _RECORD_PATH.finditer(body)}
    assert len(found) == 2, found  # the record and the stage-cause file
    return sorted(found)[0]


def test_the_graph_scan_names_one_implement_prompt_that_is_on_disk() -> None:
    """Control: the derivation can return a hit, and the file it names exists."""
    assert len(_IMPLEMENT_PROMPT_FILES) == 1, (
        f"graph declares {len(_IMPLEMENT_PROMPT_FILES)} `{_IMPLEMENT_NODE}` nodes "
        f"with a prompt; expected one"
    )
    named = _PROMPTS_DIR / _IMPLEMENT_PROMPT_FILES[0]
    assert named.is_file(), f"{named} is declared by the graph but absent on disk"


def test_the_implement_prompt_directs_the_turn_to_state_a_completion_field() -> None:
    """The instruction exists, once, and says what the clause requires of it."""
    sections = _SECTION.findall(_implement_prompt_text())

    assert len(sections) == 1, (
        f"the implement prompt carries {len(sections)} sections headed "
        f"{_HEADING!r}; expected exactly one"
    )
    for phrase in _REQUIRED_PHRASES:
        assert phrase in sections[0], f"the completion-field section omits {phrase!r}"


def test_the_instruction_enumerates_all_three_completion_verdicts() -> None:
    """Complete, incomplete, and stated-nothing are each directed separately.

    The absent arm is the one a reader is most likely to think redundant and the
    one the clause is most explicit about: a turn that states nothing is treated
    as incomplete, so the prompt has to SAY so rather than leave the turn to
    discover it from a failed stage.
    """
    sections = _SECTION.findall(_implement_prompt_text())

    assert len(sections) == 1
    for verdict in (_COMPLETE_VERDICT, _INCOMPLETE_VERDICT, _ABSENT_VERDICT):
        assert verdict in sections[0], f"the completion-field section omits {verdict!r}"


def test_the_instruction_names_the_record_path_the_completion_gate_reads() -> None:
    """The prose and the gate agree on WHERE the field is recorded.

    Derived from the gate's script rather than spelled on both sides: the two
    halves are useless apart, and a rename of either one reads as a turn that
    recorded its completion correctly and a gate that found nothing — which the
    gate reports as partial progress, i.e. as the agent's fault.
    """
    sections = _SECTION.findall(_implement_prompt_text())

    assert len(sections) == 1
    assert _gate_record_path() in sections[0]


def test_the_instruction_is_read_before_the_turn_is_told_to_finish() -> None:
    """The field is directed where the turn is still deciding what it has done."""
    prompt = _implement_prompt_text()

    assert _HEADING in prompt, f"the implement prompt carries no section headed {_HEADING!r}"
    assert prompt.index(_HEADING) < prompt.index("## Finish the run")
