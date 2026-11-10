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
    HeadRefusal,
    SharedTree,
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


def _compare(
    *, proved: CommandResult, current: CommandResult, tmp_path: Path
) -> SharedTree | HeadRefusal:
    forge = _Forge(answers={_PROVED: proved, _CURRENT: current})
    return compare_heads(repo=tmp_path, proved=_PROVED, current=_CURRENT, runner=forge)


def _refusal(*, proved: CommandResult, current: CommandResult, tmp_path: Path) -> str:
    refused = _compare(proved=proved, current=current, tmp_path=tmp_path)
    assert isinstance(refused, HeadRefusal)
    return refused.measurement


def test_two_commits_on_one_parent_with_one_tree_share_that_tree(tmp_path: Path) -> None:
    shared = _compare(proved=_commit(), current=_commit(), tmp_path=tmp_path)

    assert shared == SharedTree(tree=_TREE)


def test_each_commit_is_read_through_the_forge_by_its_full_sha(tmp_path: Path) -> None:
    forge = _Forge(answers={_PROVED: _commit(), _CURRENT: _commit()})

    _ = compare_heads(repo=tmp_path, proved=_PROVED, current=_CURRENT, runner=forge)

    assert forge.argvs == [
        ["gh", "api", f"/repos/{{owner}}/{{repo}}/git/commits/{_PROVED}"],
        ["gh", "api", f"/repos/{{owner}}/{{repo}}/git/commits/{_CURRENT}"],
    ]


def test_a_different_tree_names_the_tree_comparison_and_both_trees(tmp_path: Path) -> None:
    named = _refusal(proved=_commit(), current=_commit(tree="3" * 40), tmp_path=tmp_path)

    assert "tree comparison" in named
    assert _TREE in named
    assert "3" * 40 in named


def test_a_different_tree_is_named_before_a_different_parent(tmp_path: Path) -> None:
    """When both moved, the tree is the measurement named: it is the one the proof graded."""
    other = _commit(tree="3" * 40, parents=("4" * 40,))

    named = _refusal(proved=_commit(), current=other, tmp_path=tmp_path)

    assert "tree comparison" in named
    assert "parent comparison" not in named


def test_a_different_parent_names_the_parent_comparison_and_both_parents(
    tmp_path: Path,
) -> None:
    named = _refusal(proved=_commit(), current=_commit(parents=("4" * 40,)), tmp_path=tmp_path)

    assert "parent comparison" in named
    assert "tree comparison" not in named
    assert _PARENT in named
    assert "4" * 40 in named


@pytest.mark.parametrize("parents", [(), (_PARENT, "4" * 40)])
def test_a_commit_without_exactly_one_parent_names_the_parent_comparison(
    tmp_path: Path, parents: tuple[str, ...]
) -> None:
    """Identical commits still refuse: a root or a merge commit is not a reworded commit."""
    same = _commit(parents=parents)

    assert "parent comparison" in _refusal(proved=same, current=same, tmp_path=tmp_path)


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
def test_an_unreadable_commit_names_the_read_that_failed(
    tmp_path: Path, unreadable: CommandResult
) -> None:
    """The refusal names WHICH commit's read failed, for either side."""
    proved_side = _refusal(proved=unreadable, current=_commit(), tmp_path=tmp_path)
    current_side = _refusal(proved=_commit(), current=unreadable, tmp_path=tmp_path)

    assert f"the read of commit {_PROVED}" in proved_side
    assert f"the read of commit {_CURRENT}" in current_side
