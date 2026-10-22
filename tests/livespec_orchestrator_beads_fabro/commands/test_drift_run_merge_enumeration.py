"""The drift run enumerates every merge after the frontier and judges each diff.

Assertion 1 of `bd-ib-yvjxo4`, the first of the five the per-merge drift run
carries: "Each reconcile pass enumerates every default-branch merge after the
recorded frontier and runs the drift pass over each merge's diff through the
spec-stated judgement, in merge order."

Three things are pinned here and each is a separate way the assertion fails.
ORDER, because a pass that judged newest-first would file the newest merge's
proposal while the frontier still cannot advance past an earlier one.
COMPLETENESS, because "merge counting excludes nothing silently" is the
detection coverage-record contract's own wording and a `--merges`-style filter
would silently skip every rebased series this repository lands. And that each
judgement carries THAT merge's own diff, because one statement judged against
the wrong diff returns a verdict about a behaviour the merge does not add.
"""

from __future__ import annotations

import importlib
from dataclasses import dataclass, field
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandResult

_COMMANDS = (
    Path(__file__).resolve().parents[3]
    / ".claude-plugin"
    / "scripts"
    / "livespec_orchestrator_beads_fabro"
    / "commands"
)
_FRONTIER = "0" * 40
_MERGES = ("aaaaaaa1", "bbbbbbb2", "ccccccc3")


@dataclass(kw_only=True)
class _GitRunner:
    """A `CommandRunner` answering the three git reads the enumeration makes."""

    argvs: list[list[str]] = field(default_factory=list)

    def run(
        self,
        *,
        argv: list[str],
        cwd: Path,
        timeout_seconds: float,
        env: dict[str, str] | None = None,
        stdin: int | None = None,
    ) -> CommandResult:
        _ = (cwd, timeout_seconds, env, stdin)
        self.argvs.append(argv)
        if argv[1] == "symbolic-ref":
            return CommandResult(exit_code=0, stdout="origin/master\n", stderr="")
        if argv[1] == "rev-list":
            return CommandResult(exit_code=0, stdout="\n".join(_MERGES) + "\n", stderr="")
        return CommandResult(exit_code=0, stdout=f"subject for {argv[-1]}\n", stderr="")


@dataclass(kw_only=True)
class _Judge:
    """One `ModelRunner` recording every prompt it was handed, in order."""

    prompts: list[str] = field(default_factory=list)

    def __call__(self, prompt: str) -> str:
        self.prompts.append(prompt)
        return (
            '{"kind": "stated", "stated_by": [], '
            '"generalization_target": null, "rationale": "r"}'
        )


def _spec_tree(*, root: Path) -> None:
    (root / "SPECIFICATION").mkdir(parents=True, exist_ok=True)
    _ = (root / "SPECIFICATION" / "contracts.md").write_text(
        "## A governing heading\n\nSome ratified text.\n", encoding="utf-8"
    )


def test_the_pass_judges_every_merge_after_the_frontier_in_merge_order(tmp_path: Path) -> None:
    assert (_COMMANDS / "_drift_run.py").is_file()
    assert (_COMMANDS / "_drift_run_merges.py").is_file()
    assert (_COMMANDS / "_drift_run_findings.py").is_file()
    drift_run = importlib.import_module(
        "livespec_orchestrator_beads_fabro.commands._drift_run",
    )
    _spec_tree(root=tmp_path)
    runner = _GitRunner()
    judge = _Judge()

    outcome = drift_run.run_drift_pass(
        project_root=tmp_path,
        frontier=_FRONTIER,
        seams=drift_run.DriftRunSeams(runner=runner, judge=judge),
    )

    assert outcome.merges == _MERGES
    assert tuple(judged.merge for judged in outcome.judged) == _MERGES
    assert len(judge.prompts) == len(_MERGES)


def test_the_enumeration_excludes_no_class_of_commit(tmp_path: Path) -> None:
    assert (_COMMANDS / "_drift_run_merges.py").is_file()
    merges = importlib.import_module(
        "livespec_orchestrator_beads_fabro.commands._drift_run_merges",
    )
    runner = _GitRunner()

    enumerated = merges.merges_after(project_root=tmp_path, runner=runner, since=_FRONTIER)

    assert enumerated == _MERGES
    rev_list = next(argv for argv in runner.argvs if argv[1] == "rev-list")
    assert rev_list[-1] == f"{_FRONTIER}..origin/master"
    # No `--merges`, no `--first-parent`, no path filter: under this
    # repository's rebase-merge discipline a landed pull request appears as its
    # rebased series rather than as one merge commit, so any such filter would
    # skip the merges the run exists to judge.
    assert [token for token in rev_list if token.startswith("--")] == ["--reverse"]


def test_each_judgement_carries_that_merges_own_diff(tmp_path: Path) -> None:
    assert (_COMMANDS / "_drift_run.py").is_file()
    drift_run = importlib.import_module(
        "livespec_orchestrator_beads_fabro.commands._drift_run",
    )
    _spec_tree(root=tmp_path)
    judge = _Judge()

    outcome = drift_run.run_drift_pass(
        project_root=tmp_path,
        frontier=_FRONTIER,
        seams=drift_run.DriftRunSeams(runner=_GitRunner(), judge=judge),
    )

    for merge, prompt in zip(_MERGES, judge.prompts, strict=True):
        assert f"subject for {merge}" in prompt
    for judged, merge in zip(outcome.judged, _MERGES, strict=True):
        assert merge in judged.statement
