"""The coverage-before-Green instruction the factory implement stage must carry.

bd-ib-z6fmp: measured on a production implement stage, the implementer ran lint,
types and the one test file before each Green amend and then committed. The
installed commit hook runs the repository's whole declared check suite and the
per-file coverage gate fails at its END, so four Green amends each drove the
~11.5-minute aggregate to completion only to be refused for an uncovered line —
about 46 minutes of a 2h10m stage spent discovering gaps a single up-front run
would have named. The prompt-side mitigation is one instruction: run the
repository's per-file coverage check over the FULL suite and close every gap
BEFORE attempting a Green commit or amend. No hook, gate or check is relaxed;
the failure is only moved to where it is cheap.

The prompt under test is DERIVED from the committed graph's `implement` node
rather than spelled here, so this asserts about the file that node actually
dispatches: a literal path would keep passing after the node was re-pointed at a
different prompt, which is an instrument that cannot return the hit it exists to
find. The sibling control asserts the derivation named exactly one such node and
that the file it named is on disk.

POLARITY IS PINNED POSITIVELY, not by probing for the absence of a narrowing
phrase. The instruction must forbid restricting coverage to the changed files;
asserting that some paraphrase of "only the changed files" is absent would be a
probe that can never return a hit, and would read clean over a prompt that said
nothing at all. Both physical lines of the prohibition are therefore required
instead, which fails if the sentence is deleted, truncated or inverted.

REPO-AGNOSTICISM has two halves and only one of them is asserted here. That the
instruction names the check through the workflow input rather than through a
fleet recipe name is asserted below; that NO fleet-toolchain literal reaches any
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

_HEADING = "## Coverage before Green — run the per-file coverage check FIRST"
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
    "Before you attempt ANY Green commit or amend",
    "per-file coverage check over the FULL test suite",
    "Run it BEFORE the commit",
    "Invoke the check the way THIS repository exposes it",
    "{{ inputs.sandbox_check_suite }}",
    "Measure coverage over the WHOLE suite.",
    "This relaxes NOTHING.",
)

# The prohibition on a changed-files-only reading, as its two physical lines.
_NO_CHANGED_FILES_NARROWING = (
    "Do NOT narrow it to the files",
    "this change touched: a logic change drops coverage in files it never",
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


def test_the_implement_prompt_requires_the_coverage_check_before_any_green() -> None:
    sections = _SECTION.findall(_implement_prompt_text())

    assert len(sections) == 1, (
        f"the implement prompt carries {len(sections)} sections headed "
        f"{_HEADING!r}; expected exactly one"
    )
    for phrase in _REQUIRED_PHRASES:
        assert phrase in sections[0], f"the coverage-before-Green section omits {phrase!r}"


def test_the_coverage_instruction_forbids_a_changed_files_only_reading() -> None:
    sections = _SECTION.findall(_implement_prompt_text())

    assert len(sections) == 1
    for phrase in _NO_CHANGED_FILES_NARROWING:
        assert phrase in sections[0], (
            f"the coverage-before-Green section omits the whole-suite "
            f"prohibition line {phrase!r}"
        )


def test_the_coverage_instruction_precedes_the_run_finishing_guidance() -> None:
    """The instruction is read while the Green amends are still ahead of the agent."""
    prompt = _implement_prompt_text()

    assert _HEADING in prompt, f"the implement prompt carries no section headed {_HEADING!r}"
    assert prompt.index(_HEADING) < prompt.index("## Finish the run")
