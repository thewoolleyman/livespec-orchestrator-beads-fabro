"""`SPECIFICATION/scenarios.md` Scenario 199 — a fix turn grades each tree once, through its commit hook.

WHAT THIS BINDS. `SPECIFICATION/contracts.md` section "Self-contained plugin
dispatch", paragraph "A fix turn grades each tree once, through its commit
hook": a successful fix turn leaves a head whose last commit passed the gate its
commit hook ran, the `fix` prompt MUST NOT direct a run of the full check suite
beyond what that hook runs (the `janitor` visit that follows runs the full
aggregate), a hook run that did not grade the committed tree — a Red commit on
the hook's fast path — does not satisfy the obligation, and a change to the tree
after the last passing hook run is committed through the hook again.

WHY THE MEASUREMENT MATTERS. On 2026-11-07 run 01M6V7SGBQXFK2V8JHDMTKK0Z2 of
livespec-dev-tooling-js3cum reached its fix turn with the tree unchanged from
the one the janitor had just failed on. The prompt then OWED a full suite, so
the turn started the aggregate on the master worktree and on its own tree, read
two tool calls that had returned without an exit status as passing verdicts,
started a third full suite beside them, and polled `ps` for about 120 calls
until the 3600-second turn limit cut it. Three named tests that fail in 16
seconds were never run on their own.

A PROMPT TEST because the obligation is discharged by the AGENT out of this
prose and is rendered by no Python caller: nothing host-side can observe whether
a turn chose to start a suite. The deliverable here is the prompt.

THE PROMPT IS DERIVED from the committed graph's `fix` node rather than spelled,
so these cases assert about the file that node actually dispatches; a literal
path would keep passing after the node was re-pointed.

POLARITY IS PINNED POSITIVELY throughout. Each obligation is asserted as the
sentence that GRANTS it rather than by probing for the absence of a phrase: an
absence probe over a prompt that said nothing at all would read clean. The one
structural absence asserted — no LIST ITEM names the check-suite workflow input —
is paired with a control that the enumeration reaches the known steps, so a
splitter that matched nothing fails rather than reporting clean.
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

# The per-repository DECLARATION the prompt names the suite through. A fleet
# recipe literal in any prompt is already refused repository-wide by
# `dev-tooling/checks/no_fleet_toolchain_literals.py`.
_SUITE_INPUT = "{{ inputs.sandbox_check_suite }}"

_HEADING = "## A fix turn grades each tree once, through its commit hook"
# One regex rather than a find-the-next-heading walk: the lookahead ends the
# section at the next H2 or at end of file without a branch either way.
_SECTION = re.compile(
    rf"^{re.escape(_HEADING)}\n.*?(?=\n## |\Z)",
    re.DOTALL | re.MULTILINE,
)

_LIST_MARKER = re.compile(r"^\s*(?:\d+\.|[-*])\s")

# Each needle sits WITHIN one physical line of the hard-wrapped prose: a needle
# straddling a line break fails while the prose says exactly the thing.

# The hook is the grading; the full suite is not directed beyond it.
_HOOK_IS_THE_GRADING = (
    "That hook run IS this turn's grading of the tree it committed.",
    "This turn directs no run of the full check suite beyond what its commit hook runs.",
)

# Unchanged head and working tree: no full suite at all.
_UNCHANGED_TREE = (
    "Do NOT start a full run of the check suite while `HEAD` and the working tree",
    "are unchanged from the tree the preceding `janitor` visit failed on.",
)

# Reproduce through the named tests, never through the aggregate.
_REPRODUCE_BY_NAMED_TESTS = (
    "failing tests that target's own output names",
    "never by re-running the aggregate target that contains them.",
)

# A return without an exit status is not a verdict.
_NO_STATUS_IS_NO_VERDICT = (
    "A command whose tool call returned WITHOUT an exit status is STILL RUNNING",
    "and has produced NO verdict.",
)

# One live full suite at a time.
_NO_SECOND_LIVE_SUITE = (
    "Do NOT start a full run of the check suite while another full run you started is still live.",
)

# Changed tree or Red fast path: commit through the hook to a passing result.
_COMMIT_THROUGH_THE_HOOK = (
    "A tree that CHANGED after your last passing commit-hook run, or whose only",
    "commit took the hook's Red fast path, which grades only part of the suite, is",
    "not yet graded: commit that tree through the commit hook to a passing result before the turn ends.",
    "Do not run the full check suite beyond what that hook runs.",
)

# The refresh-repair half — Scenario 199's third gherkin scenario.
_INTEGRATED_TREE = (
    "The same rule governs the refresh-repair steps above, on the tree the repair",
    "produced: a commit whose hook passed on the INTEGRATED tree grades that tree,",
)

# What the rule must NOT be read as relaxing.
_RELAXES_NOTHING = (
    "This relaxes NOTHING. The `janitor` visit the graph re-enters after a successful",
    "turn runs the whole suite as a hard gate on the tree you leave, so a full run",
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
    refresh-repair steps are adjacent lines with no blank line between them.
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


def _the_one_section() -> str:
    sections = _SECTION.findall(_fix_prompt_text())
    assert (
        len(sections) == 1
    ), f"the fix prompt carries {len(sections)} sections headed {_HEADING!r}; expected exactly one"
    section: str = sections[0]
    return section


def _assert_section_carries(*, needles: tuple[str, ...]) -> None:
    section = _the_one_section()
    for needle in needles:
        assert needle in section, f"the {_HEADING!r} section omits {needle!r}"


def test_the_graph_scan_names_one_fix_prompt_that_is_on_disk() -> None:
    """Control: the derivation can return a hit, and the file it names exists."""
    assert (
        len(_FIX_PROMPT_FILES) == 1
    ), f"graph declares {len(_FIX_PROMPT_FILES)} `{_FIX_NODE}` nodes with a prompt; expected one"
    named = _PROMPTS_DIR / _FIX_PROMPT_FILES[0]
    assert named.is_file(), f"{named} is declared by the graph but absent on disk"


def test_no_step_of_the_fix_prompt_directs_a_run_of_the_check_suite() -> None:
    """No list item names the suite input, so no numbered step can direct a suite run.

    The control is the count: the enumeration must reach the fix step and the
    refresh-repair step, each of which formerly carried the input, so a splitter
    that matched nothing fails rather than reporting a clean scan over no items.
    """
    items = _list_items(text=_fix_prompt_text())
    graded = tuple(item for item in items if "grades each tree once" in item)

    assert len(graded) == 2, (
        f"found {len(graded)} list items pointing at the grading rule; expected the fix "
        f"step and the refresh-repair step: {graded}"
    )
    directing = tuple(item for item in items if _SUITE_INPUT in item)
    assert (
        not directing
    ), f"list items still name {_SUITE_INPUT}, so they direct a suite run: {directing}"


def test_the_commit_hook_run_is_the_turn_s_only_grading_of_a_tree() -> None:
    """Scenario 199's first gherkin scenario: the hook grades the tree, no suite run is directed."""
    _assert_section_carries(needles=_HOOK_IS_THE_GRADING)


def test_an_unchanged_head_and_tree_starts_no_full_suite_run() -> None:
    """The measured run's shape: nothing changed, so the janitor's verdict stands and no suite starts."""
    _assert_section_carries(needles=_UNCHANGED_TREE)


def test_a_failed_target_is_reproduced_through_the_tests_its_output_names() -> None:
    """A red janitor target is reproduced by its named failing tests, not by its aggregate."""
    _assert_section_carries(needles=_REPRODUCE_BY_NAMED_TESTS)


def test_a_tool_call_returning_without_an_exit_status_is_still_running() -> None:
    """A return carrying no exit status is no pass, no fail and no 'not reproducible'."""
    _assert_section_carries(needles=_NO_STATUS_IS_NO_VERDICT)


def test_no_full_suite_run_starts_while_another_the_turn_started_is_live() -> None:
    """One live suite at a time: three concurrent suites each ran at a third of the speed."""
    _assert_section_carries(needles=_NO_SECOND_LIVE_SUITE)


def test_a_changed_tree_or_a_red_fast_path_commit_is_committed_through_the_hook() -> None:
    """Scenario 199's second gherkin scenario: the remedy is a hook-graded commit, not a suite run."""
    _assert_section_carries(needles=_COMMIT_THROUGH_THE_HOOK)


def test_the_rule_reaches_the_refresh_repair_steps_integrated_tree() -> None:
    """Scenario 199's third gherkin scenario: the repaired tree is governed identically."""
    _assert_section_carries(needles=_INTEGRATED_TREE)


def test_the_rule_states_that_it_relaxes_no_check_and_no_gate() -> None:
    """The janitor's full run is the reason no suite is directed here, and it still runs."""
    _assert_section_carries(needles=_RELAXES_NOTHING)


def test_the_rule_is_read_before_the_turn_finishing_guidance() -> None:
    """The section sits where an agent reads it while the grading is still ahead."""
    prompt = _fix_prompt_text()

    assert _HEADING in prompt, f"the fix prompt carries no section headed {_HEADING!r}"
    assert prompt.index("## What to do") < prompt.index(_HEADING)
    assert prompt.index(_HEADING) < prompt.index("## Ending the turn")
