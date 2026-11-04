"""Every reading the drift pass can fail to take, and what it reports instead.

The companion to `test_drift_run_merge_enumeration`, which pins the happy
enumeration. What is pinned here is the SHAPE of each absence, because the
contract owes three of them different treatments and the pass is the only place
that can tell them apart:

- git declining to enumerate the range at all is not an empty scope, so the
  pass judges nothing and names the measurement rather than reporting a
  complete pass over no merges;
- a merge whose diff could not be read, and a judgement whose reply could not
  be parsed, are each one UNPROCESSED merge — which is what stops the frontier —
  and they carry different causes because they have different remedies;
- an empty tuple of merges IS an answer: a frontier that is already the branch
  head has nothing to judge, and that is a complete pass.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandResult
from livespec_orchestrator_beads_fabro.commands._drift_run import (
    CAUSE_JUDGEMENT_UNREADABLE,
    CAUSE_MERGE_UNREADABLE,
    CAUSE_MERGES_UNREADABLE,
    DriftRunSeams,
    run_drift_pass,
)
from livespec_orchestrator_beads_fabro.commands._drift_run_findings import (
    DIFF_EXCERPT_CHARACTERS,
    MergeUnderJudgement,
    behaviour_statement,
)
from livespec_orchestrator_beads_fabro.commands._drift_run_merges import (
    merge_range,
    merge_under_judgement,
    merges_after,
)


@dataclass(kw_only=True)
class _Runner:
    """A `CommandRunner` whose three git answers are each independently set."""

    symbolic_ref: CommandResult = field(
        default_factory=lambda: CommandResult(exit_code=0, stdout="origin/main\n", stderr="")
    )
    rev_list: CommandResult = field(
        default_factory=lambda: CommandResult(exit_code=0, stdout="aaaa1\n", stderr="")
    )
    show: CommandResult = field(
        default_factory=lambda: CommandResult(
            exit_code=0, stdout="a subject\n@@ a hunk\n", stderr=""
        )
    )
    argvs: list[list[str]] = field(default_factory=list)

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
        if argv[1] == "symbolic-ref":
            return self.symbolic_ref
        if argv[1] == "rev-list":
            return self.rev_list
        return self.show


def _spec_tree(*, root: Path) -> None:
    (root / "SPECIFICATION").mkdir(parents=True, exist_ok=True)
    _ = (root / "SPECIFICATION" / "contracts.md").write_text("## H\n\ntext\n", encoding="utf-8")


def _unparseable(prompt: str) -> str:
    """The one judge this module needs: every arm here either never reaches it,
    or reaches it to establish that an unparseable reply is an unprocessed
    merge. A judge that answered a well-formed verdict would make the
    unreadable-merge case weaker, not stronger — the merge cause has to win
    over the judgement cause, and it can only be seen to do so when the
    judgement would otherwise have failed too."""
    _ = prompt
    return "I think it is probably fine."


def test_a_truncated_diff_excerpt_says_so_in_the_statement() -> None:
    long_diff = "+" * (DIFF_EXCERPT_CHARACTERS + 1)

    statement = behaviour_statement(
        merge=MergeUnderJudgement(sha="aaaa1", subject="s", diff=long_diff)
    )

    assert "truncated" in statement
    assert len(statement) < len(long_diff) + len(statement) - DIFF_EXCERPT_CHARACTERS + 1


def test_a_short_diff_excerpt_carries_no_truncation_marker() -> None:
    statement = behaviour_statement(
        merge=MergeUnderJudgement(sha="aaaa1", subject="s", diff="@@ one hunk\n")
    )

    assert "truncated" not in statement
    assert "@@ one hunk" in statement


@pytest.mark.parametrize(
    ("since", "expected"),
    [(None, "origin/main"), ("deadbeef", "deadbeef..origin/main")],
)
def test_an_absent_frontier_ranges_over_the_whole_branch(since: str | None, expected: str) -> None:
    assert merge_range(since=since, ref="origin/main") == expected


@pytest.mark.parametrize(
    "runner",
    [
        _Runner(symbolic_ref=CommandResult(exit_code=1, stdout="", stderr="no HEAD")),
        _Runner(symbolic_ref=CommandResult(exit_code=0, stdout="\n", stderr="")),
        _Runner(rev_list=CommandResult(exit_code=128, stdout="", stderr="bad revision")),
    ],
)
def test_an_unreadable_enumeration_answers_none_and_never_an_empty_tuple(
    tmp_path: Path, runner: _Runner
) -> None:
    assert merges_after(project_root=tmp_path, runner=runner, since="deadbeef") is None


def test_an_unreadable_enumeration_judges_nothing_and_names_the_measurement(
    tmp_path: Path,
) -> None:
    _spec_tree(root=tmp_path)
    runner = _Runner(rev_list=CommandResult(exit_code=128, stdout="", stderr="bad revision"))

    outcome = run_drift_pass(
        project_root=tmp_path,
        frontier="deadbeef",
        seams=DriftRunSeams(runner=runner, judge=_unparseable),
    )

    assert outcome.unreadable == CAUSE_MERGES_UNREADABLE
    assert outcome.merges == ()
    assert outcome.judged == ()


def test_an_empty_scope_is_a_complete_pass_over_no_merges(tmp_path: Path) -> None:
    _spec_tree(root=tmp_path)
    runner = _Runner(rev_list=CommandResult(exit_code=0, stdout="\n", stderr=""))

    outcome = run_drift_pass(
        project_root=tmp_path,
        frontier="deadbeef",
        seams=DriftRunSeams(runner=runner, judge=_unparseable),
    )

    assert outcome.unreadable is None
    assert outcome.merges == ()


def test_an_unreadable_merge_is_one_unprocessed_merge(tmp_path: Path) -> None:
    _spec_tree(root=tmp_path)
    runner = _Runner(show=CommandResult(exit_code=128, stdout="", stderr="bad object"))

    outcome = run_drift_pass(
        project_root=tmp_path,
        frontier="deadbeef",
        seams=DriftRunSeams(runner=runner, judge=_unparseable),
    )

    assert merge_under_judgement(project_root=tmp_path, runner=runner, sha="aaaa1") is None
    assert [judged.failure for judged in outcome.judged] == [CAUSE_MERGE_UNREADABLE]
    assert [judged.verdict for judged in outcome.judged] == [None]


def test_an_unparseable_judgement_is_one_unprocessed_merge(tmp_path: Path) -> None:
    _spec_tree(root=tmp_path)

    outcome = run_drift_pass(
        project_root=tmp_path,
        frontier="deadbeef",
        seams=DriftRunSeams(runner=_Runner(), judge=_unparseable),
    )

    assert [judged.failure for judged in outcome.judged] == [CAUSE_JUDGEMENT_UNREADABLE]
    assert [judged.statement != "" for judged in outcome.judged] == [True]
