"""Coverage for the shared shell-command shape read by both repo-local guards.

This module answers ONE question — which words of a Bash command would a shell
actually EXECUTE, and which are merely data it would carry — and two guards
depend on the answer: `livespec_tdd_order_targets` to find the paths a command
WRITES, and `livespec_sandbox_path_policy` to find the paths a command REMOVES.
Each guard is also covered end to end beside this file, so these cases exist to
pin the shape ITSELF, where a change silently moves both guards at once.

Every case is the same kind of case: a command whose dangerous-looking bytes
are DATA, read beside one where they are a command. That line is the whole
contract, and it is the one a reader cannot check by eye.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_HOOKS_DIR = _REPO_ROOT / ".claude" / "hooks"
_SHAPE_PATH = _HOOKS_DIR / "livespec_shell_shape.py"
_MODULE_NAME = "livespec_shell_shape_under_test"


def _load_shape() -> ModuleType:
    assert _SHAPE_PATH.is_file()
    if str(_HOOKS_DIR) not in sys.path:
        sys.path.insert(0, str(_HOOKS_DIR))
    spec = importlib.util.spec_from_file_location(_MODULE_NAME, _SHAPE_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[_MODULE_NAME] = module
    spec.loader.exec_module(module)
    return module


# ---------------------------------------------------------------------------
# shell_tokens — words and control operators, or None
# ---------------------------------------------------------------------------


def test_control_operators_are_their_own_tokens() -> None:
    shape = _load_shape()

    assert shape.shell_tokens(command="cd /tmp && rm -rf /workspace") == [
        "cd",
        "/tmp",
        "&&",
        "rm",
        "-rf",
        "/workspace",
    ]


def test_quotes_are_stripped_so_a_quoted_path_reads_as_one_word() -> None:
    shape = _load_shape()

    assert shape.shell_tokens(command='rm -rf "/a path"') == ["rm", "-rf", "/a path"]


def test_a_command_the_lexer_cannot_split_is_reported_as_unreadable() -> None:
    """`None` rather than an exception, because a lexer error must not refuse work."""
    shape = _load_shape()

    assert shape.shell_tokens(command='echo "unbalanced') is None


# ---------------------------------------------------------------------------
# without_heredoc_bodies — a body is file data, never a command
# ---------------------------------------------------------------------------


def test_a_heredoc_body_is_dropped_and_its_introducing_line_is_kept() -> None:
    command = "cat > sim.sh <<'EOF'\nrm -rf /workspace\nEOF\ngit status"

    shape = _load_shape()

    assert shape.without_heredoc_bodies(command=command) == "cat > sim.sh <<'EOF'\ngit status"


def test_an_indented_heredoc_terminator_still_closes_the_body() -> None:
    command = "cat <<-EOF\n\trm -rf /workspace\n\tEOF\ngit log"

    shape = _load_shape()

    assert shape.without_heredoc_bodies(command=command) == "cat <<-EOF\ngit log"


def test_a_heredoc_body_running_to_end_of_input_drops_everything_after_it() -> None:
    shape = _load_shape()

    assert shape.without_heredoc_bodies(command="cat <<EOF\nrm -rf /workspace") == "cat <<EOF"


def test_a_command_without_a_heredoc_keeps_every_line() -> None:
    command = "git status\ngit log --oneline"

    shape = _load_shape()

    assert shape.without_heredoc_bodies(command=command) == command


def test_an_unreadable_introducing_line_introduces_no_delimiter() -> None:
    """A line the lexer cannot split cannot be mined for a delimiter either."""
    shape = _load_shape()

    assert shape.without_heredoc_bodies(command='echo "unbalanced\nrm -rf /tmp/x') == (
        'echo "unbalanced\nrm -rf /tmp/x'
    )


# ---------------------------------------------------------------------------
# token_segments — one segment per command a shell would run
# ---------------------------------------------------------------------------


def test_each_control_operator_starts_a_new_segment_and_empties_are_dropped() -> None:
    shape = _load_shape()
    tokens = ["cd", "/tmp", "&&", "rm", "-rf", "/workspace", ";", ";", "echo", "done"]

    assert shape.token_segments(tokens=tokens) == [
        ["cd", "/tmp"],
        ["rm", "-rf", "/workspace"],
        ["echo", "done"],
    ]


def test_a_subshell_body_is_read_as_segments_of_its_own() -> None:
    """`(` and `)` are segment operators, so a subshell is not one opaque word."""
    shape = _load_shape()
    tokens = ["(", "cd", "/", "&&", "rm", "-rf", "workspace", ")"]

    assert shape.token_segments(tokens=tokens) == [["cd", "/"], ["rm", "-rf", "workspace"]]


# ---------------------------------------------------------------------------
# leading_command_index — the word that actually executes
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("tokens", "expected"),
    [
        (["rm", "-rf", "/tmp/x"], 0),
        (["sudo", "rm", "-rf", "/tmp/x"], 1),
        (["FOO=1", "rm", "-rf", "/tmp/x"], 1),
        (["mise", "exec", "--", "rm", "-rf", "/tmp/x"], 3),
        (["env", "FOO=1", "rm", "-rf", "/tmp/x"], 2),
        (["/usr/bin/rm", "-rf", "/tmp/x"], 0),
    ],
)
def test_wrappers_assignments_and_flags_are_peeled_off_the_command(
    tokens: list[str], expected: int
) -> None:
    shape = _load_shape()

    assert shape.leading_command_index(tokens=tokens) == expected


@pytest.mark.parametrize("tokens", [[], ["sudo"], ["FOO=1"], ["--"]])
def test_a_segment_that_executes_nothing_has_no_command_index(tokens: list[str]) -> None:
    """At or past the end means the segment is all flags, assignments and wrappers."""
    shape = _load_shape()

    assert shape.leading_command_index(tokens=tokens) >= len(tokens)


# ---------------------------------------------------------------------------
# operands — the non-flag words
# ---------------------------------------------------------------------------


def test_flags_and_the_argument_terminator_are_not_operands() -> None:
    shape = _load_shape()

    assert shape.operands(tokens=["-rf", "--", "/tmp/one", "/tmp/two"]) == [
        "/tmp/one",
        "/tmp/two",
    ]
