"""The commit-hook waiting directions the implement and fix stage prompts must carry.

bd-ib-aaxsta. Measured from the implement-stage events of hp runs 01M5BGXNTG2T and
01M5BH5FEY5X: a Codex execute tool returned while the commit's hook aggregate was
still running — the first `git commit` came back reporting failure at 40.6 seconds
with the hook's own children still alive — so the agent polled, killed live hook
processes by hand, made a duplicate commit attempt, finally killed its own Green
amend and ended the turn. Three of four runs ended that way with the Red committed
and the Green amend abandoned. NO timeout fired: the turns ran 32.6 and 27.6
minutes against a 14400-second node limit and both ACP turns ended `end_turn`, so
the only available mitigation is the prompt. The one success polled the same way
but waited the full check out twice over a 79.5-minute turn and finished green.

THE DIRECTIONS ARE ADAPTER-AGNOSTIC, which is why they are asserted as prose
rather than inferred from a Codex-specific symptom. Claude's tool tolerates the
long hook today, so Claude implement turns do not show this; an adapter change or
a slower host reproduces it anywhere.

THE PROMPTS UNDER TEST ARE DERIVED from the committed graph's `implement` and
`fix` node blocks rather than named by path: a literal path keeps passing after a
node is re-pointed at a different prompt, which is an instrument that cannot
return the hit it exists to find. The sibling control asserts the derivation named
exactly one prompt per node and that both are on disk.

ONE WORDING ACROSS BOTH PROMPTS, asserted by comparing the two sections' bytes.
The item's Definition of Done requires the fix prompt to carry "the same four
commit-hook directions as the implement stage prompt", and two paraphrases drift
apart while each still satisfies a per-prompt needle list.

POLARITY IS PINNED POSITIVELY throughout. Every needle is a sentence that must be
PRESENT; none probes for the absence of a phrase, because an absence probe reads
clean over a prompt that says nothing at all — the exact state this item exists to
end. The needles sit WITHIN one physical line of the hard-wrapped prose, since a
needle straddling a line break can only fail silently.

This item is the prompt-level guidance for the commit leg AS IT RUNS TODAY. The
detached sandbox commit runner that `SPECIFICATION/contracts.md` requires for the
commit leg is bd-ib-sufca7, which also owns Scenario 179's registry binding; the
waiting direction is therefore worded to hold for that runner's BOUNDED WAITS as
well as for a foreground block, and that clause-compatibility is asserted here so
a later re-wording cannot quietly contradict it.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

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
_COMMITTING_STAGE_NODES = ("implement", "fix")

_HEADING = "## A commit hook outlasts a tool call — a return is not a verdict"
# One regex rather than a find-the-next-heading walk: the lookahead ends the
# section at the next H2 or at end of file without a branch either way.
_SECTION = re.compile(
    rf"^{re.escape(_HEADING)}\n.*?(?=\n## |\Z)",
    re.DOTALL | re.MULTILINE,
)

# Direction 1 — how long the hook aggregate actually runs on a factory host.
_HOOK_DURATION = (
    "that aggregate runs for MINUTES",
    "measured at 142 and 553",
    "up to about ten minutes",
)

# Direction 2 — a tool call that returns mid-hook has not failed the commit.
_RETURN_IS_NOT_A_FAILURE = (
    "A RETURN WHILE THE HOOK IS STILL RUNNING IS NOT A FAILED COMMIT.",
    "never the tool call's return",
)

# Direction 3 — wait for the hook's own exit, kill nothing, start nothing else.
_WAIT_WITHOUT_KILLING = (
    "WAIT FOR A RUNNING COMMIT HOOK'S OWN EXIT BEFORE ANY FURTHER COMMIT.",
    "DO NOT KILL THE HOOK'S PROCESSES.",
    "DO NOT START ANOTHER `git commit` WHILE ONE IS STILL LIVE.",
)

# Direction 4 — the turn does not end while a hook it started is still running.
_NO_TURN_END_MID_HOOK = ("DO NOT END YOUR TURN WHILE A COMMIT HOOK YOU STARTED IS STILL RUNNING.",)

# The waiting direction must hold for the detached commit runner's bounded waits
# too, so bd-ib-sufca7 can ship that runner without contradicting this prose.
_RUNNER_COMPATIBILITY = (
    "where this stage prompt names a commit runner, repeat that runner's bounded",
    "Reaping a hook run that outlived a limit belongs to the run itself, never",
)


def _committing_stage_prompts() -> dict[str, Path]:
    """The committed graph's prompt file for each stage whose agent commits here."""
    found: dict[str, Path] = {}
    for block in _NODE_BLOCK.finditer(_GRAPH.read_text(encoding="utf-8")):
        name = block.group("name")
        if name not in _COMMITTING_STAGE_NODES:
            continue
        attr = _PROMPT_ATTR.search(block.group("body"))
        assert attr is not None, f"node {name} declares no prompt"
        assert name not in found, f"graph declares more than one {name} node prompt"
        found[name] = _PROMPTS_DIR / attr.group("file")
    return found


def _section(*, node: str) -> str:
    prompt = _committing_stage_prompts()[node]
    sections = _SECTION.findall(prompt.read_text(encoding="utf-8"))
    assert (
        len(sections) == 1
    ), f"the {node} prompt carries {len(sections)} sections headed {_HEADING!r}; expected one"
    return str(sections[0])


def test_the_graph_names_one_prompt_per_committing_stage_and_both_are_on_disk() -> None:
    """Control: the derivation can return a hit, and the files it names exist."""
    prompts = _committing_stage_prompts()

    assert tuple(prompts) == _COMMITTING_STAGE_NODES, (
        f"graph scan found {tuple(prompts)} committing stage prompts; "
        f"expected {_COMMITTING_STAGE_NODES}"
    )
    for node, prompt in prompts.items():
        assert prompt.is_file(), f"node {node} names missing prompt {prompt}"


@pytest.mark.parametrize("node", _COMMITTING_STAGE_NODES)
def test_the_prompt_states_how_long_the_commit_hook_aggregate_runs(node: str) -> None:
    section = _section(node=node)

    for phrase in _HOOK_DURATION:
        assert phrase in section, f"the {node} prompt's commit-hook section omits {phrase!r}"


@pytest.mark.parametrize("node", _COMMITTING_STAGE_NODES)
def test_the_prompt_says_a_return_mid_hook_is_not_a_failed_commit(node: str) -> None:
    section = _section(node=node)

    for phrase in _RETURN_IS_NOT_A_FAILURE:
        assert phrase in section, f"the {node} prompt's commit-hook section omits {phrase!r}"


@pytest.mark.parametrize("node", _COMMITTING_STAGE_NODES)
def test_the_prompt_directs_waiting_without_killing_or_a_second_commit(node: str) -> None:
    section = _section(node=node)

    for phrase in _WAIT_WITHOUT_KILLING:
        assert phrase in section, f"the {node} prompt's commit-hook section omits {phrase!r}"


@pytest.mark.parametrize("node", _COMMITTING_STAGE_NODES)
def test_the_prompt_forbids_ending_the_turn_while_a_commit_hook_runs(node: str) -> None:
    section = _section(node=node)

    for phrase in _NO_TURN_END_MID_HOOK:
        assert phrase in section, f"the {node} prompt's commit-hook section omits {phrase!r}"


@pytest.mark.parametrize("node", _COMMITTING_STAGE_NODES)
def test_the_waiting_direction_holds_for_a_commit_runner_s_bounded_waits(node: str) -> None:
    """The prose must not contradict the clause bd-ib-sufca7 implements."""
    section = _section(node=node)

    for phrase in _RUNNER_COMPATIBILITY:
        assert phrase in section, f"the {node} prompt's commit-hook section omits {phrase!r}"


def test_the_fix_prompt_carries_the_same_directions_as_the_implement_prompt() -> None:
    """One wording, not two: a per-prompt paraphrase drifts and cannot be audited."""
    distinct = {_section(node=node) for node in _COMMITTING_STAGE_NODES}

    assert len(distinct) == 1, (
        f"{len(distinct)} distinct commit-hook wordings across "
        f"{len(_COMMITTING_STAGE_NODES)} prompts; expected one"
    )


@pytest.mark.parametrize("node", _COMMITTING_STAGE_NODES)
def test_the_commit_hook_section_precedes_the_turn_end_guidance(node: str) -> None:
    """The directions are read while the commits are still ahead of the agent."""
    text = _committing_stage_prompts()[node].read_text(encoding="utf-8")
    turn_end = "## Ending the turn — leave nothing running in the background"

    assert _HEADING in text, f"the {node} prompt carries no section headed {_HEADING!r}"
    assert text.index(_HEADING) < text.index(turn_end)
