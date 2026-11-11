"""Terminal-preservation ref parsing, origin reads and merge-base diff accounting."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import (
    CommandResult,
    CommandRunner,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_preserved_tree_record import (
    PRESERVED_TREE_MARKER,
)

__all__: list[str] = [
    "PreservedRef",
    "checkpoint_ref",
    "diff_line",
    "named_terminal_refs",
    "needs_human_ref",
    "numstat",
    "remote_tip",
    "terminal_ref_lines",
    "terminal_refs",
]

_REMOTE = "origin"
_GIT_TIMEOUT_SECONDS = 5.0
_LS_REMOTE_FIELDS = 2
_NUMSTAT_FIELDS = 3


@dataclass(frozen=True, kw_only=True)
class PreservedRef:
    """A terminal preservation ref, its origin tip and its measured diff."""

    ref: str
    commit: str | None
    diff: tuple[int, int, int] | None


def terminal_refs(
    *, runner: CommandRunner, repo: Path, run_id: str, comments: tuple[object, ...]
) -> tuple[PreservedRef, ...]:
    """Measure every terminal ref that an earlier durable record names."""
    refs = named_terminal_refs(run_id=run_id, comments=comments)
    return tuple(_measure_ref(runner=runner, repo=repo, ref=ref) for ref in refs)


def named_terminal_refs(*, run_id: str, comments: tuple[object, ...]) -> tuple[str, ...]:
    """Read the needs-human and failed-checkpoint refs without inferring either."""
    refs: list[str] = []
    for comment in comments:
        text = getattr(comment, "text", "")
        if not isinstance(text, str) or f"run id: {run_id}" not in text:
            continue
        ref = needs_human_ref(text=text) or checkpoint_ref(text=text)
        if ref is not None and ref not in refs:
            refs.append(ref)
    return tuple(refs)


def needs_human_ref(*, text: str) -> str | None:
    """The exact ref carried by a needs-human cause, when it named one."""
    prefix = "preservation: the tree was preserved on "
    if not text.startswith("livespec-needs-human-cause"):
        return None
    for line in text.splitlines():
        if line.startswith(prefix):
            return line.removeprefix(prefix).partition(" (")[0] or None
    return None


def checkpoint_ref(*, text: str) -> str | None:
    """The ref a successful failed-checkpoint preservation comment names."""
    prefix = "preservation ref: "
    if not text.startswith(PRESERVED_TREE_MARKER):
        return None
    for line in text.splitlines():
        if line.startswith(prefix):
            ref = line.removeprefix(prefix)
            return None if ref.startswith("none") else ref
    return None


def _measure_ref(*, runner: CommandRunner, repo: Path, ref: str) -> PreservedRef:
    """Read a ref's origin tip and origin-merge-base diff, or state the gap."""
    tip = runner.run(
        argv=["git", "ls-remote", _REMOTE, ref], cwd=repo, timeout_seconds=_GIT_TIMEOUT_SECONDS
    )
    commit = remote_tip(ref=ref, result=tip)
    if commit is None:
        return PreservedRef(ref=ref, commit=None, diff=None)
    base = runner.run(
        argv=["git", "merge-base", "origin/HEAD", commit],
        cwd=repo,
        timeout_seconds=_GIT_TIMEOUT_SECONDS,
    )
    if base.exit_code != 0 or not base.stdout.strip():
        return PreservedRef(ref=ref, commit=commit, diff=None)
    diff = runner.run(
        argv=[
            "git",
            "diff",
            "--numstat",
            base.stdout.strip(),
            commit,
            "--",
            ".",
            ":(exclude).fabro",
        ],
        cwd=repo,
        timeout_seconds=_GIT_TIMEOUT_SECONDS,
    )
    measured = numstat(stdout=diff.stdout) if diff.exit_code == 0 else None
    return PreservedRef(ref=ref, commit=commit, diff=measured)


def remote_tip(*, ref: str, result: CommandResult) -> str | None:
    """The exact ref's SHA from one successful ls-remote response."""
    if result.exit_code != 0:
        return None
    for line in result.stdout.splitlines():
        fields = line.split()
        if len(fields) == _LS_REMOTE_FIELDS and fields[1] == ref:
            return fields[0]
    return None


def numstat(*, stdout: str) -> tuple[int, int, int] | None:
    """Sum git's tabular diff figures; binary or malformed output is unmeasurable."""
    additions = deletions = files = 0
    for line in stdout.splitlines():
        fields = line.split("\t", maxsplit=2)
        if len(fields) != _NUMSTAT_FIELDS or not fields[0].isdecimal() or not fields[1].isdecimal():
            return None
        additions += int(fields[0])
        deletions += int(fields[1])
        files += 1
    return files, additions, deletions


def terminal_ref_lines(*, refs: tuple[PreservedRef, ...]) -> list[str]:
    """Render every terminal ref's independently verifiable recovery account."""
    lines: list[str] = []
    for preserved in refs:
        lines.append(f"preserved ref: {preserved.ref}")
        if preserved.commit is None:
            lines.append("tip commit and merge-base diff could not be determined")
        else:
            lines.append(f"commit id: {preserved.commit}")
            lines.append(diff_line(diff=preserved.diff))
    return lines


def diff_line(*, diff: tuple[int, int, int] | None) -> str:
    """Render a measured diff or the distinct unreadability statement it needs."""
    if diff is None:
        return (
            "merge-base diff could not be determined (files changed, insertions and "
            "deletions could not be determined)"
        )
    files, additions, deletions = diff
    return (
        f"merge-base diff: {files} files changed, {additions} insertions(+), "
        f"{deletions} deletions(-)"
    )
