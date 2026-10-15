"""Every committing ACP stage prompt routes its commits through the sandbox runner.

bd-ib-sufca7, and with it `SPECIFICATION/scenarios.md` Scenario 179 and the
commit-leg-completion paragraph of `SPECIFICATION/contracts.md`: an
implement-stage commit whose repository hook outlasts one of the agent's tool
calls has to reach the hook's OWN verdict. The runner is the mechanism and the
prompt is what makes a stage use it, so the prompt text is a deliverable in its
own right — a runner nothing is told to call changes nothing.

THE COMMITTING STAGE SET IS DERIVED, NOT SPELLED. It is read off the committed
graph's own ACP nodes, narrowed to those whose prompt names the Red-Green-Replay
ritual — the vocabulary a stage that commits has to carry. A hand-written list
is blind to a committing stage added later, and would report a clean pass for a
prompt nothing ever checked. The sibling control asserts the derivation found
exactly the three stages the ratified paragraph names today, so a derivation
that silently matched a subset — or nothing — fails here instead of certifying
what it never read.

THE NEEDLES SIT WITHIN ONE PHYSICAL LINE, because prompt prose is hard-wrapped
and a needle straddling a line break fails while the prose says exactly the
thing. That is a probe which can only fail silently, which is the one shape of
check this repository treats as worse than no check at all.

THE RUNNER PATH IS IMPORTED rather than transcribed. The prompt names a path the
Dispatcher's prepare step writes; if the two ever disagree the stage reaches for
a program that is not there, and a transcribed literal here would keep agreeing
with itself while they diverged.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro.commands._dispatcher_sandbox_commit_runner import (
    sandbox_commit_runner_path_expansion,
)

_REPO_ROOT = Path(__file__).resolve().parents[2]
_WORKFLOW_DIR = _REPO_ROOT / ".claude-plugin" / ".fabro" / "workflows" / "implement-work-item"
_PROMPTS_DIR = _WORKFLOW_DIR / "prompts"
_GRAPH = _WORKFLOW_DIR / "workflow.fabro"

# Same node-block shape the turn-end discipline module derives from: `<name> [`
# on its own line through a closing `]` on its own line. Edge declarations carry
# their attributes inline on ONE line, so this cannot match an edge.
_NODE_BLOCK = re.compile(
    r"^[ \t]*(?P<name>\w+)[ \t]*\[$(?P<body>.*?)^[ \t]*\]$",
    re.DOTALL | re.MULTILINE,
)
_PROMPT_ATTR = re.compile(r'prompt="@prompts/(?P<file>[\w.-]+\.md)"')

_RUNNER_HEADING = "## Every commit goes through the sandbox commit runner"
# One regex rather than a find-the-next-heading walk: the lookahead ends the
# section at the next H2 or at end of file without a branch either way.
_RUNNER_SECTION = re.compile(
    rf"^{re.escape(_RUNNER_HEADING)}\n.*?(?=\n## |\Z)",
    re.DOTALL | re.MULTILINE,
)

# The three stages the ratified paragraph names. Asserted by the control below
# rather than used to SELECT the prompts under test.
_COMMITTING_PROMPTS = ("implement.md", "fix.md", "review-fix.md")

_ROUTING_PHRASES = (
    "So EVERY git commit you make — the Red commit, the Green amend, and any",
    "later commit — goes through the sandbox commit runner at",
    "It runs the argv you give it UNCHANGED, with this repository's hooks",
    "1. START it, in the FOREGROUND. It prints a commit run id and returns in",
    "2. WAIT on it, with a bound in whole seconds, in as many later tool calls",
    "3. READ the `state:` line of that report. It is the verdict:",
    "- `running` — the commit has not finished. Wait again.",
    "- `passed` — the commit happened. The report carries `exit_status: 0`",
    "- `failed` — a hook refused it. The report carries the commit",
    "HEAD is unchanged. A failed commit run IS NOT A COMMIT: fix the",
    "- `no-verdict` — the commit was ended by a signal, or its process is",
    "either, and it is NOT a refusal: nothing is known about the gate.",
    "- Only ONE commit run may be in flight in this sandbox. A start while",
    "another is `running` is refused and names the running commit run.",
    "- NEVER pass `--no-verify` and never set a variable that skips or",
)

_TURN_END_PHRASES = (
    "THE COMMIT RUN AND ITS BOUNDED WAITS ARE THE ONE EXCEPTION to the rule",
    "below against backgrounding a tool call, and the turn-end obligation is",
    "UNCHANGED: before your final message every commit run you started must",
    "be terminal — `passed`, `failed` or `no-verdict` — or stopped. Confirm",
    "that with a last `wait` or `status` on each commit run id you hold.",
)


def _acp_prompt_files() -> tuple[str, ...]:
    """Prompt filenames of every `backend="acp"` node in the committed graph."""
    graph = _GRAPH.read_text(encoding="utf-8")
    names: list[str] = []
    for block in _NODE_BLOCK.finditer(graph):
        body = block.group("body")
        if 'backend="acp"' not in body:
            continue
        attr = _PROMPT_ATTR.search(body)
        assert attr is not None, f"acp node {block.group('name')} declares no prompt"
        names.append(attr.group("file"))
    return tuple(names)


def _prompt_text(*, name: str) -> str:
    return (_PROMPTS_DIR / name).read_text(encoding="utf-8")


def _committing_prompt_files() -> tuple[str, ...]:
    """Prompt files that direct the agent to make a git commit.

    Derived by CONTENT — a prompt naming the `Red-Green-Replay` ritual is a
    prompt whose stage commits — rather than from a list written here. The
    discriminator is measured rather than assumed: across the eight committed
    ACP prompts the token appears in exactly `implement.md`, `fix.md` and
    `review-fix.md` and in none of the other five, and it is vocabulary those
    three carried BEFORE the runner section existed, so the selection cannot be
    circular with what the cases then assert about them.
    """
    return tuple(
        name for name in _acp_prompt_files() if "Red-Green-Replay" in _prompt_text(name=name)
    )


_COMMITTING_UNDER_TEST = _committing_prompt_files()


def test_the_derivation_found_exactly_the_stages_that_commit() -> None:
    """Control: the content scan can return a hit, and returns the three it owes.

    Without this, a scan whose vocabulary had drifted would select NO prompts and
    every parametrized case below would vanish — a suite reporting clean over a
    question it stopped asking.
    """
    assert sorted(_COMMITTING_UNDER_TEST) == sorted(_COMMITTING_PROMPTS)
    assert len(set(_COMMITTING_UNDER_TEST)) == len(_COMMITTING_UNDER_TEST)


@pytest.mark.parametrize("prompt_name", _COMMITTING_UNDER_TEST)
def test_every_committing_prompt_routes_each_commit_through_the_runner(
    prompt_name: str,
) -> None:
    """Assertion 9: every commit the agent makes goes through the runner and its waits."""
    sections = _RUNNER_SECTION.findall(_prompt_text(name=prompt_name))

    assert len(sections) == 1, (
        f"{prompt_name} carries {len(sections)} sections headed {_RUNNER_HEADING!r}; "
        "expected exactly one"
    )
    assert (
        sandbox_commit_runner_path_expansion() in sections[0]
    ), f"{prompt_name} does not name the path the prepare step materializes"
    for phrase in _ROUTING_PHRASES:
        assert phrase in sections[0], f"{prompt_name}'s runner section omits {phrase!r}"


@pytest.mark.parametrize("prompt_name", _COMMITTING_UNDER_TEST)
def test_every_committing_prompt_owes_a_terminal_or_stopped_run_at_turn_end(
    prompt_name: str,
) -> None:
    """Assertion 10: nothing the stage started is still running at its final message."""
    [section] = _RUNNER_SECTION.findall(_prompt_text(name=prompt_name))

    for phrase in _TURN_END_PHRASES:
        assert phrase in section, f"{prompt_name}'s runner section omits {phrase!r}"


def test_the_runner_instruction_is_one_wording_across_every_committing_prompt() -> None:
    """One wording, not three: a per-prompt paraphrase drifts and cannot be audited."""
    per_prompt = {
        name: _RUNNER_SECTION.findall(_prompt_text(name=name)) for name in _COMMITTING_UNDER_TEST
    }
    without = sorted(name for name, found in per_prompt.items() if len(found) != 1)

    assert not without, f"committing prompts without exactly one runner section: {without}"
    distinct = {found[0] for found in per_prompt.values()}
    assert (
        len(distinct) == 1
    ), f"{len(distinct)} distinct runner wordings across {len(per_prompt)} prompts; expected one"


def test_no_non_committing_acp_prompt_carries_the_runner_section() -> None:
    """The exception is scoped: a stage that does not commit is not given the carveout.

    The runner is the ONE exception a committing stage's prompt makes to its rule
    against backgrounding a tool call, so a prompt that never commits must not
    carry it — otherwise the carveout widens by copy-paste rather than by ruling.
    """
    others = [name for name in _acp_prompt_files() if name not in _COMMITTING_UNDER_TEST]
    carrying = sorted(name for name in others if _RUNNER_SECTION.findall(_prompt_text(name=name)))

    assert others, "the control found no non-committing ACP prompt to check"
    assert not carrying, f"non-committing prompts carrying the runner carveout: {carrying}"
