"""`SPECIFICATION/scenarios.md` Scenario 199 — a fix turn runs the suite once per tree.

WHAT THIS BINDS. `SPECIFICATION/contracts.md` section "Self-contained plugin
dispatch" gained the paragraph "A fix turn runs the check suite once per tree"
at v159: a commit whose repository pre-commit hook ran the full check suite to a
passing result on the exact tree it committed satisfies that turn's suite
obligation for that tree, and the `fix` prompt MUST NOT direct a second run of
the suite on that same tree in the same turn — while a partial hook run, such as
a Red commit on the hook's fast path, and any change to the tree after the last
passing full run both still owe a full run before a successful turn ends. The
refresh-repair steps are governed identically, on the tree the repair produced.

WHY THE MEASUREMENT MATTERS. On 2026-10-18 run 01M56YAEWMS8 of bd-ib-spc6xr
reached its fix turn, committed its fix as 7b909571 with the pre-commit hook
running the full aggregate green in 1364 seconds, and then launched a second
aggregate on the identical tree. The 3600-second turn limit killed that second
run and the run exited through needs_human with the work preserved. With six or
more runs live one aggregate takes about 22 minutes, so two inside one turn
exhaust the limit BY CONSTRUCTION — the prompt's two unqualified "Re-run the
repository's check suite" directives were the whole mechanism.

A PROMPT TEST because the obligation is discharged by the AGENT out of this
prose and is rendered by no Python caller: nothing host-side can observe whether
a turn chose to run the suite twice, and the engine reports the resulting
timeout as an ordinary node failure. The deliverable here is the prompt.

THE PROMPT IS DERIVED from the committed graph's `fix` node rather than spelled,
so these cases assert about the file that node actually dispatches; a literal
path would keep passing after the node was re-pointed, which is an instrument
that cannot return the hit it exists to find. The sibling control asserts the
derivation named exactly one such node and that the file it named is on disk.

THE DIRECTIVE SITES ARE ENUMERATED, not needled. The defect was not a missing
paragraph — it was that each site which DIRECTS a run of the suite said "re-run
it until it is green" with no exemption, and a rule stated in a section the
directive never references leaves the directive saying the thing that cost the
run. So `test_every_directive_to_run_the_suite_carries_the_once_per_tree_rule`
collects every list item carrying the check-suite workflow input and requires the
rule AT each of them, which fails for a third directive added later without it;
a whole-file needle would pass over exactly the shape this scenario forbids.
Its control is the count: the enumeration must reach BOTH known sites, so a
splitter that matched nothing fails rather than reporting clean.

POLARITY IS PINNED POSITIVELY throughout. The owed-run arms are asserted as the
sentences that GRANT them rather than by probing for the absence of a phrase:
an absence probe over a prompt that said nothing at all would read clean, which
is the one reading that would re-open the defect from the other side.
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
# shape cannot match an edge. Same reader as the sibling implement-prompt module.
_NODE_BLOCK = re.compile(
    r"^[ \t]*(?P<name>\w+)[ \t]*\[$(?P<body>.*?)^[ \t]*\]$",
    re.DOTALL | re.MULTILINE,
)
_PROMPT_ATTR = re.compile(r'prompt="@prompts/(?P<file>[\w.-]+\.md)"')
_FIX_NODE = "fix"

# The per-repository DECLARATION the prompt names the suite through. Asserting
# the rule sits beside THIS token rather than beside a recipe name is what keeps
# the instruction repo-agnostic; a fleet recipe literal in any prompt is already
# refused repository-wide by `dev-tooling/checks/no_fleet_toolchain_literals.py`,
# so that half is deliberately not restated here as a weaker second copy.
_SUITE_INPUT = "{{ inputs.sandbox_check_suite }}"

_HEADING = "## The check suite runs ONCE per tree — a commit hook's green run counts"
# One regex rather than a find-the-next-heading walk: the lookahead ends the
# section at the next H2 or at end of file without a branch either way.
_SECTION = re.compile(
    rf"^{re.escape(_HEADING)}\n.*?(?=\n## |\Z)",
    re.DOTALL | re.MULTILINE,
)

_LIST_MARKER = re.compile(r"^\s*(?:\d+\.|[-*])\s")

# The two needles every suite directive owes, each sitting WITHIN one physical
# line of the hard-wrapped prose: a needle straddling a line break fails while
# the prose says exactly the thing, which is a probe that can only fail silently.
_DIRECTIVE_NEEDLES = ("ONCE per tree", "once-per-tree rule")

# The counting rule and the prohibition it licenses — Scenario 199's first
# gherkin scenario.
_COUNTS_THE_HOOK_RUN = (
    "commit the hook admitted has ALREADY run that suite in full on the exact tree",
    "That hook run IS this turn's run of the suite for that tree.",
    "Do NOT launch a second run of the suite on a tree a hook already passed it on",
    "exact tree it committed: that tree is COVERED. Leave the branch at that",
)

# The arms that still OWE a full run — Scenario 199's second gherkin scenario.
_STILL_OWES_A_FULL_RUN = (
    "The tree CHANGED after that run",
    "sitting in the working tree: the suite is OWED on the new tree. Run it in",
    "No commit in this turn ran the full suite: the suite is OWED. A Red commit",
    "takes the hook's fast path, which runs only part of the suite, and a hook run",
    "You cannot tell which of these holds: run it in full. This rule removes a",
)

# The refresh-repair half — Scenario 199's third gherkin scenario.
_INTEGRATED_TREE = (
    "The same rule governs the refresh-repair steps above, on the tree the repair",
    "produced: a commit whose hook ran the full suite green on the INTEGRATED tree",
    "is that tree's run, and no second run of the suite on that integrated tree is",
)

# What the rule must NOT be read as relaxing. The janitor re-run is the reason
# the duplicate is safe to drop at all, so a section omitting it argues for
# dropping the obligation rather than the duplicate.
_RELAXES_NOTHING = (
    "This relaxes NOTHING. The suite must still have passed IN FULL on the tree you",
    "successful turn runs the whole suite again as a hard gate. What changes is only",
)


def _fix_prompt_files() -> tuple[str, ...]:
    """Prompt filenames of every node named `fix` in the committed graph."""
    graph = _GRAPH.read_text(encoding="utf-8")
    names: list[str] = []
    for block in _NODE_BLOCK.finditer(graph):
        if block.group("name") != _FIX_NODE:
            continue
        attr = _PROMPT_ATTR.search(block.group("body"))
        assert attr is not None, f"node {_FIX_NODE} declares no prompt"
        names.append(attr.group("file"))
    return tuple(names)


_FIX_PROMPT_FILES = _fix_prompt_files()


def _fix_prompt_text() -> str:
    assert len(_FIX_PROMPT_FILES) == 1
    return (_PROMPTS_DIR / _FIX_PROMPT_FILES[0]).read_text(encoding="utf-8")


def _list_items(*, text: str) -> tuple[str, ...]:
    """Every markdown list item in `text`, each as its own joined continuation block.

    Items are split at the MARKER rather than at blank lines, because the
    refresh-repair steps are adjacent lines with no blank line between them: a
    blank-line split would lump all three into one block, and a qualifier on
    step 1 would then satisfy an assertion about step 2.
    """
    items: list[list[str]] = []
    current: list[str] | None = None
    for line in text.splitlines():
        if _LIST_MARKER.match(line) is not None:
            current = [line]
            items.append(current)
            continue
        if not line.strip():
            current = None
            continue
        if current is not None:
            current.append(line)
    return tuple("\n".join(lines) for lines in items)


def _suite_directives() -> tuple[str, ...]:
    return tuple(item for item in _list_items(text=_fix_prompt_text()) if _SUITE_INPUT in item)


def _the_one_section() -> str:
    sections = _SECTION.findall(_fix_prompt_text())
    assert (
        len(sections) == 1
    ), f"the fix prompt carries {len(sections)} sections headed {_HEADING!r}; expected exactly one"
    section: str = sections[0]
    return section


def test_the_graph_scan_names_one_fix_prompt_that_is_on_disk() -> None:
    """Control: the derivation can return a hit, and the file it names exists."""
    assert (
        len(_FIX_PROMPT_FILES) == 1
    ), f"graph declares {len(_FIX_PROMPT_FILES)} `{_FIX_NODE}` nodes with a prompt; expected one"
    named = _PROMPTS_DIR / _FIX_PROMPT_FILES[0]
    assert named.is_file(), f"{named} is declared by the graph but absent on disk"


def test_every_directive_to_run_the_suite_carries_the_once_per_tree_rule() -> None:
    """Each site that DIRECTS a run of the suite carries the exemption, not just the prompt.

    The count is the control: the enumeration must reach both known directive
    sites — the fix step and the refresh-repair step — so a splitter that
    matched nothing fails rather than reporting a clean scan over no items.
    """
    directives = _suite_directives()

    assert len(directives) == 2, (
        f"found {len(directives)} list items directing a run of {_SUITE_INPUT}; "
        f"expected the fix step and the refresh-repair step: {directives}"
    )
    for directive in directives:
        for needle in _DIRECTIVE_NEEDLES:
            assert needle in directive, (
                f"a suite directive omits {needle!r}, so it directs an unqualified "
                f"run: {directive}"
            )


def test_a_hook_green_full_suite_run_is_counted_as_the_turn_s_run_for_that_tree() -> None:
    """Scenario 199's first gherkin scenario: the hook run counts, no second run is directed."""
    section = _the_one_section()

    for needle in _COUNTS_THE_HOOK_RUN:
        assert needle in section, f"the once-per-tree section omits {needle!r}"


def test_a_partial_hook_run_or_a_later_change_still_owes_a_full_run() -> None:
    """Scenario 199's second gherkin scenario, asserted as the sentences that grant it."""
    section = _the_one_section()

    for needle in _STILL_OWES_A_FULL_RUN:
        assert needle in section, f"the once-per-tree section omits the owed-run arm {needle!r}"


def test_the_rule_reaches_the_refresh_repair_steps_integrated_tree() -> None:
    """Scenario 199's third gherkin scenario: the repaired tree is governed identically."""
    section = _the_one_section()

    for needle in _INTEGRATED_TREE:
        assert needle in section, f"the once-per-tree section omits {needle!r}"


def test_the_rule_states_that_it_relaxes_no_check_and_no_gate() -> None:
    """The duplicate is dropped, never the obligation or the janitor re-run behind it."""
    section = _the_one_section()

    for needle in _RELAXES_NOTHING:
        assert needle in section, f"the once-per-tree section omits {needle!r}"


def test_the_rule_is_read_before_the_turn_finishing_guidance() -> None:
    """The section sits where an agent reads it while the suite run is still ahead."""
    prompt = _fix_prompt_text()

    assert _HEADING in prompt, f"the fix prompt carries no section headed {_HEADING!r}"
    assert prompt.index("## What to do") < prompt.index(_HEADING)
    assert prompt.index(_HEADING) < prompt.index("## Ending the turn")
