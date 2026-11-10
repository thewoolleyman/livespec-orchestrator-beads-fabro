"""The commit readings behind the release's message-only head comparison.

`test_drive_merge_hold_valve.py` drives the comparison END TO END through the real
`set-merge-hold:<id>:off` action. What is left for this module is the shapes of a
forge answer that action never needs to spell out one at a time: every one of
them must read as "not shown to be message-only", and none may read as a shared
tree.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import cast

import pytest
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine_types import CommandResult
from livespec_orchestrator_beads_fabro.commands._drive_merge_hold_head_lineage import (
    compare_heads,
)

_PROVED = "a" * 40
_CURRENT = "b" * 40
_TREE = "1" * 40
_PARENT = "2" * 40


class _Forge:
    """A `CommandRunner` answering each commit lookup from a table keyed by sha."""

    def __init__(self, *, answers: Mapping[str, CommandResult]) -> None:
        self.answers = answers
        self.argvs: list[list[str]] = []

    def run(
        self,
        *,
        argv: list[str],
        cwd: Path,
        timeout_seconds: float,
        env: Mapping[str, str | None] | None = None,
        stdin: int | None = None,
    ) -> CommandResult:
        _ = (cwd, timeout_seconds, env, stdin)
        self.argvs.append(argv)
        return self.answers[argv[-1].rsplit("/", 1)[-1]]


def _commit(*, tree: str = _TREE, parents: object = (_PARENT,)) -> CommandResult:
    """A commit answer; a tuple of shas is shaped like the forge's, anything else rides raw."""
    shaped = (
        [{"sha": one} for one in cast("tuple[str, ...]", parents)]
        if isinstance(parents, tuple)
        else parents
    )
    return CommandResult(
        exit_code=0, stdout=json.dumps({"tree": {"sha": tree}, "parents": shaped}), stderr=""
    )


def _shared(*, proved: CommandResult, current: CommandResult, tmp_path: Path) -> str | None:
    forge = _Forge(answers={_PROVED: proved, _CURRENT: current})
    return compare_heads(repo=tmp_path, proved=_PROVED, current=_CURRENT, runner=forge).tree


def test_two_commits_on_one_parent_with_one_tree_share_that_tree(tmp_path: Path) -> None:
    assert _shared(proved=_commit(), current=_commit(), tmp_path=tmp_path) == _TREE


def test_each_commit_is_read_through_the_forge_by_its_full_sha(tmp_path: Path) -> None:
    forge = _Forge(answers={_PROVED: _commit(), _CURRENT: _commit()})

    _ = compare_heads(repo=tmp_path, proved=_PROVED, current=_CURRENT, runner=forge)

    assert forge.argvs == [
        ["gh", "api", f"/repos/{{owner}}/{{repo}}/git/commits/{_PROVED}"],
        ["gh", "api", f"/repos/{{owner}}/{{repo}}/git/commits/{_CURRENT}"],
    ]


def test_a_different_tree_is_not_a_message_only_move(tmp_path: Path) -> None:
    assert _shared(proved=_commit(), current=_commit(tree="3" * 40), tmp_path=tmp_path) is None


def test_a_different_tree_names_the_tree_comparison_and_both_trees(tmp_path: Path) -> None:
    forge = _Forge(answers={_PROVED: _commit(), _CURRENT: _commit(tree="3" * 40)})

    comparison = compare_heads(repo=tmp_path, proved=_PROVED, current=_CURRENT, runner=forge)

    assert comparison.tree is None
    assert comparison.failed is not None
    assert "tree comparison" in comparison.failed
    assert _TREE in comparison.failed
    assert "3" * 40 in comparison.failed


def test_a_different_parent_is_not_a_message_only_move(tmp_path: Path) -> None:
    other = _commit(parents=("4" * 40,))
    assert _shared(proved=_commit(), current=other, tmp_path=tmp_path) is None


@pytest.mark.parametrize("parents", [(), (_PARENT, "4" * 40)])
def test_a_commit_without_exactly_one_parent_is_not_a_message_only_move(
    tmp_path: Path, parents: tuple[str, ...]
) -> None:
    same = _commit(parents=parents)
    assert _shared(proved=same, current=same, tmp_path=tmp_path) is None


@pytest.mark.parametrize(
    "unreadable",
    [
        CommandResult(exit_code=1, stdout="", stderr="HTTP 404"),
        CommandResult(exit_code=0, stdout="not json", stderr=""),
        CommandResult(exit_code=0, stdout="[]", stderr=""),
        CommandResult(exit_code=0, stdout=json.dumps({"parents": []}), stderr=""),
        CommandResult(exit_code=0, stdout=json.dumps({"tree": {"sha": ""}}), stderr=""),
        CommandResult(exit_code=0, stdout=json.dumps({"tree": "x", "parents": []}), stderr=""),
        _commit(parents={"sha": _PARENT}),
        _commit(parents=[{"sha": _PARENT}, "not an object"]),
        _commit(parents=[{"sha": 7}]),
    ],
)
def test_an_unreadable_commit_on_either_side_is_not_a_message_only_move(
    tmp_path: Path, unreadable: CommandResult
) -> None:
    assert _shared(proved=unreadable, current=_commit(), tmp_path=tmp_path) is None
    assert _shared(proved=_commit(), current=unreadable, tmp_path=tmp_path) is None
