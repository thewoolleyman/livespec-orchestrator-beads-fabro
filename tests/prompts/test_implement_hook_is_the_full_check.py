"""Command nodes own implement commits; Red and Green run targeted tests and the gate preview.

Before bd-ib-vy75ws the single `implement` prompt carried a "commit hook is the
full check" section: never self-run the whole suite, and coverage belongs to the
hook, because the agent's own Green amend ran the whole declared suite. The
red/green split retires that premise and two ratified clauses of
SPECIFICATION/contracts.md replace those instructions:

- "The implement stage runs Red and Green as separate nodes": no agent turn of
  the implement stage commits or waits on a commit hook, the `red` prompt runs
  ONLY its test, and the `green` prompt runs ONLY "the tests its change touches".
  That is the targeted-tests half of the retired section, now pinned below as the
  two prompts' own positive wording.
- "An implement turn sees its commit gate's verdict before it ends": the `red`
  and `green` prompts MUST run the gate preview, which runs "the same checks the
  repository's commit hooks would run" (the per-file coverage gate included) over
  exactly the paths the commit node stages. That replaces both "never run the
  whole suite yourself" and "coverage belongs to the hook": the agent now SEES the
  hook's coverage verdict before it ends, instead of leaving it to a commit it no
  longer makes. Pinned below.
"""

from __future__ import annotations

from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_dot_graph import parse_dot_graph

_GRAPH = (
    Path(__file__).resolve().parents[2]
    / ".claude-plugin/.fabro/workflows/implement-work-item/workflow.fabro"
)


def test_implement_commits_are_owned_by_command_nodes() -> None:
    """Red and Green do not start the detached commit runner themselves."""
    graph = parse_dot_graph(text=_GRAPH.read_text(encoding="utf-8"))
    assert not isinstance(graph, str), graph

    assert "implement" not in graph.nodes
    assert graph.nodes["commit_red"]["script"] == "bash dev-tooling/commit-red.sh"
    assert graph.nodes["commit_green"]["script"] == "bash dev-tooling/commit-green.sh"


def test_fix_and_review_fix_keep_their_commit_runner_settle_nodes() -> None:
    """The graph rewrite does not alter either existing repair loop."""
    graph = parse_dot_graph(text=_GRAPH.read_text(encoding="utf-8"))
    assert not isinstance(graph, str), graph

    for node in ("fix_commit_settle", "review_fix_commit_settle"):
        assert "livespec-commit-runner.py" in graph.nodes[node]["script"]


_PROMPTS = (
    Path(__file__).resolve().parents[2]
    / ".claude-plugin/.fabro/workflows/implement-work-item/prompts"
)
_PREVIEW = '"${LIVESPEC_SANDBOX_CLAUDE_PLUGINS_ROOT:-$HOME/.claude/plugins}/livespec-implement-gate-preview.py"'


def test_red_runs_only_its_test_and_green_only_the_tests_its_change_touches() -> None:
    """The targeted-tests half of the retired section, as each prompt words it."""
    red = (_PROMPTS / "red.md").read_text(encoding="utf-8")
    green = (_PROMPTS / "green.md").read_text(encoding="utf-8")

    assert "3. Run only that test and capture its failure output. Do not make a commit." in red
    assert "2. Run only the tests your change touches. Do not make a commit." in green


def test_red_and_green_run_the_gate_preview_of_their_own_commit_node_before_ending() -> None:
    """The commit hook's checks, coverage included, are previewed before the turn ends."""
    for node in ("red", "green"):
        text = (_PROMPTS / f"{node}.md").read_text(encoding="utf-8")
        assert (
            f"{_PREVIEW} {node}" in text
        ), f"the {node} prompt runs no gate preview of its own node"
        assert "run the preview again after each fix" in text.replace("\n", " ").replace(
            "   ", " "
        ), f"the {node} prompt does not direct a re-run of the preview after each fix"
