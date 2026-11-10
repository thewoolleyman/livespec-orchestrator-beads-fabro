"""The edges of telling a needs-human ref that carries work from one that carries none.

`test_dispatcher_recovery_no_change_refs.py` drives the rule through recovery
routing. This module drives `split_unchanged_needs_human_refs` itself, because its
other arms are the ones that decide whether work is lost: a comparison that cannot
be taken is unobservable and never an answer in either direction, and a tip that
shares no history with the default branch carries work, since it has nothing to be
identical to.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandResult
from livespec_orchestrator_beads_fabro.commands._dispatcher_needs_human_refs import (
    NeedsHumanRef,
    NeedsHumanRefsUnobservable,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_needs_human_unchanged import (
    UnchangedSplit,
    split_unchanged_needs_human_refs,
)

_TIP = "a1" * 20
_REF = NeedsHumanRef(commit_sha=_TIP, ref="refs/heads/needs-human/run", run_id="run")
_BASE = "b2" * 20
_TREE = "c3" * 20
_OTHER_TREE = "d4" * 20
_OK = CommandResult(exit_code=0, stdout="", stderr="")


@dataclass(kw_only=True)
class _Runner:
    """Answers each git subcommand from `answers`, defaulting the unscripted ones to success."""

    answers: dict[str, CommandResult] = field(default_factory=dict[str, CommandResult])
    calls: list[list[str]] = field(default_factory=list[list[str]])

    def run(
        self,
        *,
        argv: list[str],
        cwd: Path,
        timeout_seconds: float,
        env: dict[str, str] | None = None,
        stdin: int | None = None,
    ) -> CommandResult:
        _ = cwd, timeout_seconds, env, stdin
        self.calls.append(argv)
        return self.answers.get(argv[1], _OK)


def _healthy(*, tip_tree: str = _TREE, base_tree: str = _TREE) -> dict[str, CommandResult]:
    return {
        "symbolic-ref": CommandResult(exit_code=0, stdout="origin/main\n", stderr=""),
        "merge-base": CommandResult(exit_code=0, stdout=f"{_BASE}\n", stderr=""),
        "rev-parse": CommandResult(exit_code=0, stdout=f"{tip_tree}\n{base_tree}\n", stderr=""),
    }


def _split(*, runner: _Runner, carrying: list[NeedsHumanRef] | None = None):
    return split_unchanged_needs_human_refs(
        runner=runner,
        repo=Path("/repo"),
        carrying=[_REF] if carrying is None else carrying,
        remote="origin",
        timeout_seconds=1.0,
    )


def test_no_carrying_ref_reads_nothing() -> None:
    runner = _Runner()

    assert _split(runner=runner, carrying=[]) == UnchangedSplit(with_work=[], unchanged=[])
    assert runner.calls == []


def test_a_tip_whose_tree_is_its_merge_bases_tree_carries_no_work() -> None:
    runner = _Runner(answers=_healthy())

    assert _split(runner=runner) == UnchangedSplit(with_work=[], unchanged=[_REF])


def test_the_default_branch_and_the_tips_are_fetched_before_any_comparison() -> None:
    runner = _Runner(answers=_healthy())

    _ = _split(runner=runner)

    assert runner.calls[1] == [
        "git",
        "fetch",
        "--quiet",
        "--no-tags",
        "origin",
        "+refs/heads/main:refs/remotes/origin/main",
        _REF.ref,
    ]
    assert ["git", "merge-base", _TIP, "refs/remotes/origin/main"] in runner.calls
    assert ["git", "rev-parse", f"{_TIP}^{{tree}}", f"{_BASE}^{{tree}}"] in runner.calls


def test_a_tip_whose_tree_differs_from_its_merge_bases_tree_carries_work() -> None:
    runner = _Runner(answers=_healthy(tip_tree=_OTHER_TREE))

    assert _split(runner=runner) == UnchangedSplit(with_work=[_REF], unchanged=[])


def test_a_tip_sharing_no_history_with_the_default_branch_carries_work() -> None:
    answers = _healthy() | {"merge-base": CommandResult(exit_code=1, stdout="", stderr="")}

    assert _split(runner=_Runner(answers=answers)) == UnchangedSplit(with_work=[_REF], unchanged=[])


def test_an_unresolvable_default_branch_is_unobservable() -> None:
    runner = _Runner(
        answers={
            "symbolic-ref": CommandResult(exit_code=128, stdout="", stderr="no head"),
            "repo": CommandResult(exit_code=1, stdout="", stderr="no gh"),
        }
    )

    found = _split(runner=runner)

    assert isinstance(found, NeedsHumanRefsUnobservable)
    assert "default branch could not be resolved" in found.detail


def test_a_failed_fetch_is_unobservable() -> None:
    answers = _healthy() | {"fetch": CommandResult(exit_code=128, stdout="", stderr="gone")}

    found = _split(runner=_Runner(answers=answers))

    assert isinstance(found, NeedsHumanRefsUnobservable)
    assert "exited 128" in found.detail


def test_a_merge_base_that_cannot_be_read_is_unobservable() -> None:
    for broken in (
        CommandResult(exit_code=128, stdout="", stderr="bad object"),
        CommandResult(exit_code=0, stdout="\n", stderr=""),
    ):
        answers = _healthy() | {"merge-base": broken}

        found = _split(runner=_Runner(answers=answers))

        assert isinstance(found, NeedsHumanRefsUnobservable)
        assert "merge base" in found.detail


def test_trees_that_cannot_be_read_are_unobservable() -> None:
    for broken in (
        CommandResult(exit_code=128, stdout="", stderr="bad object"),
        CommandResult(exit_code=0, stdout=f"{_TREE}\n", stderr=""),
    ):
        answers = _healthy() | {"rev-parse": broken}

        found = _split(runner=_Runner(answers=answers))

        assert isinstance(found, NeedsHumanRefsUnobservable)
        assert "tree of needs-human tip" in found.detail
