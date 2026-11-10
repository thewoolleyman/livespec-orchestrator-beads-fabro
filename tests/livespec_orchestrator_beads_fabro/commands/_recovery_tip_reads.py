"""Scripted answers for the reads that tell a needs-human tip carrying work from one carrying none.

Recovery routing compares each carrying needs-human tip's tree with the tree of the
tip's merge base with the default branch. A test that stands a needs-human ref on a
scripted origin and is not about that comparison answers it here, with a tip that
DOES carry work, so the ref stays a candidate and the test keeps its own subject.
"""

from __future__ import annotations

from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandResult

__all__: list[str] = ["tip_read_answer"]

_BASE = "9" * 40
_TIP_TREE = "7" * 40
_BASE_TREE = "8" * 40


def tip_read_answer(*, argv: list[str]) -> CommandResult | None:
    """The scripted answer when `argv` is one of the work-carrying reads, else `None`."""
    joined = " ".join(argv)
    if joined == "git symbolic-ref --short refs/remotes/origin/HEAD":
        return CommandResult(exit_code=0, stdout="origin/master\n", stderr="")
    if argv[:4] == ["git", "fetch", "--quiet", "--no-tags"]:
        return CommandResult(exit_code=0, stdout="", stderr="")
    if argv[:2] == ["git", "merge-base"] and argv[-1] == "refs/remotes/origin/master":
        return CommandResult(exit_code=0, stdout=f"{_BASE}\n", stderr="")
    if argv[:2] == ["git", "rev-parse"] and argv[-1].endswith("^{tree}"):
        return CommandResult(exit_code=0, stdout=f"{_TIP_TREE}\n{_BASE_TREE}\n", stderr="")
    return None
