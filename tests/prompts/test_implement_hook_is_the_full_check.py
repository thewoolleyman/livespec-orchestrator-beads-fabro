"""The hook-is-the-full-check instruction the factory implement stage must carry.

History. bd-ib-z6fmp first answered a measured coverage cost: four Green amends
each drove the ~11.5-minute aggregate to completion only to be refused for an
uncovered line, about 46 minutes of a 2h10m stage. Its remedy told the
implementer to run the per-file coverage check over the full suite itself before
every Green. Measured on three implement runs of 2026-10-31 that ended in partial
progress (overseer-e6bvmt, overseer-uzvcbn.9, bd-ib-37wvsk; recorded on epic
livespec-dev-tooling-dfixhe, root-cause finding 2), that remedy became the cost:
the implementer pre-ran the whole aggregate and the coverage check, then the
commit hook ran the same aggregate again, and its own runs plus the sleep and
`ps` loops polling them took 57 of overseer-e6bvmt's 95 implement minutes.

The instruction is now the inverse, and keeps the original lesson. The commit
hook runs the declared suite, coverage gate included, so its run IS the one full
check: the implementer runs only targeted tests, never a whole-suite command, and
when the hook refuses it closes EVERY gap the refusal names before committing
again, which is what the 46 minutes were actually spent failing to do.

The prompt under test is DERIVED from the committed graph's `implement` node
rather than spelled here, so this asserts about the file that node actually
dispatches: a literal path would keep passing after the node was re-pointed at a
different prompt. The sibling control asserts the derivation named exactly one
such node and that the file it named is on disk.

POLARITY IS PINNED POSITIVELY. The prohibition on self-started whole-suite runs,
and the whole-suite reason coverage belongs to the hook, are each required as
their physical lines, which fails if a sentence is deleted, truncated or
inverted; asserting that some paraphrase of "run the suite first" is absent
would be a probe that can never return a hit.

REPO-AGNOSTICISM: the instruction names the suite through the workflow input
rather than a fleet recipe name; that NO fleet-toolchain literal reaches any
prompt file at all is already a repository-wide gate
(`dev-tooling/checks/no_fleet_toolchain_literals.py`), so it is deliberately not
restated as a second, weaker copy.
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

_HEADING = "## The commit hook is the full check — run only targeted tests yourself"
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
    "This repository's commit hook runs its whole declared check suite,",
    "{{ inputs.sandbox_check_suite }}",
    "that suite contains the per-file coverage gate. That hook run IS this stage's",
    "one full check. Before a commit, run only the targeted tests: every test file",
    "read EVERY failed target and EVERY uncovered",
    "them before the next commit. One refusal names every gap at once.",
    "This relaxes NOTHING.",
)

# The prohibition on self-started whole-suite runs, as its physical lines.
_NO_SELF_STARTED_SUITE = (
    "of a file you edited. Never run the full suite, the per-file coverage check or",
    "any other whole-suite command yourself, neither before a commit nor after one",
)

# Why coverage belongs to the hook, as its physical lines.
_WHOLE_SUITE_COVERAGE = (
    "- Coverage is measured over the WHOLE suite, which is why it belongs to the",
    "hook: a logic change drops coverage in files it never edits, so a reading",
)


def _implement_prompt_files() -> tuple[str, ...]:
    """Prompt filenames of every node named `implement` in the committed graph."""
    graph = _GRAPH.read_text(encoding="utf-8")
    names: list[str] = []
    for block in _NODE_BLOCK.finditer(graph):
        if block.group("name") != _IMPLEMENT_NODE:
            continue
        attr = _PROMPT_ATTR.search(block.group("body"))
        assert attr is not None, f"node {_IMPLEMENT_NODE} declares no prompt"
        names.append(attr.group("file"))
    return tuple(names)


_IMPLEMENT_PROMPT_FILES = _implement_prompt_files()


def _implement_prompt_text() -> str:
    assert len(_IMPLEMENT_PROMPT_FILES) == 1
    return (_PROMPTS_DIR / _IMPLEMENT_PROMPT_FILES[0]).read_text(encoding="utf-8")


def test_the_graph_scan_names_one_implement_prompt_that_is_on_disk() -> None:
    """Control: the derivation can return a hit, and the file it names exists."""
    assert len(_IMPLEMENT_PROMPT_FILES) == 1, (
        f"graph declares {len(_IMPLEMENT_PROMPT_FILES)} `{_IMPLEMENT_NODE}` nodes "
        f"with a prompt; expected one"
    )
    named = _PROMPTS_DIR / _IMPLEMENT_PROMPT_FILES[0]
    assert named.is_file(), f"{named} is declared by the graph but absent on disk"


def _the_section() -> str:
    sections = _SECTION.findall(_implement_prompt_text())
    assert len(sections) == 1, (
        f"the implement prompt carries {len(sections)} sections headed "
        f"{_HEADING!r}; expected exactly one"
    )
    return sections[0]


def test_the_implement_prompt_makes_the_commit_hook_the_one_full_check() -> None:
    section = _the_section()

    for phrase in _REQUIRED_PHRASES:
        assert phrase in section, f"the hook-is-the-full-check section omits {phrase!r}"


def test_the_instruction_forbids_a_self_started_whole_suite_run() -> None:
    section = _the_section()

    for phrase in _NO_SELF_STARTED_SUITE:
        assert (
            phrase in section
        ), f"the hook-is-the-full-check section omits the self-run prohibition line {phrase!r}"


def test_the_instruction_keeps_coverage_measured_over_the_whole_suite() -> None:
    section = _the_section()

    for phrase in _WHOLE_SUITE_COVERAGE:
        assert (
            phrase in section
        ), f"the hook-is-the-full-check section omits the whole-suite coverage line {phrase!r}"


def test_the_implement_prompt_no_longer_directs_a_coverage_run_before_green() -> None:
    """The superseded section is gone, so the two instructions cannot both stand."""
    prompt = _implement_prompt_text()

    assert "## Coverage before Green" not in prompt
    assert "per-file coverage check over the FULL test suite" not in prompt


def test_the_instruction_precedes_the_run_finishing_guidance() -> None:
    """The instruction is read while the Green amends are still ahead of the agent."""
    prompt = _implement_prompt_text()

    assert _HEADING in prompt, f"the implement prompt carries no section headed {_HEADING!r}"
    assert prompt.index(_HEADING) < prompt.index("## Finish the run")
