"""Resolve needs-human refs to their publishing runs."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandRunner

__all__: list[str] = [
    "NeedsHumanRef",
    "NeedsHumanRefsUnobservable",
    "newest_needs_human_ref",
]

_LS_REMOTE_FIELDS = 2


@dataclass(frozen=True, kw_only=True)
class NeedsHumanRef:
    """A needs-human ref, the run it carries, and the carrying refs the choice passed over."""

    commit_sha: str
    ref: str
    run_id: str
    passed_over: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True, kw_only=True)
class NeedsHumanRefsUnobservable:
    """The remote listing or an inspected tip could not be read."""

    detail: str


def newest_needs_human_ref(
    *,
    runner: CommandRunner,
    repo: Path,
    run_ids: tuple[str, ...],
    ref_prefix: str,
    remote: str,
    timeout_seconds: float,
) -> NeedsHumanRef | NeedsHumanRefsUnobservable | None:
    """Return the tree to seed from: the descendant, else newest, tip among every carrying ref."""
    result = runner.run(
        argv=["git", "ls-remote", remote, f"{ref_prefix}/*"],
        cwd=repo,
        timeout_seconds=timeout_seconds,
    )
    if result.exit_code != 0:
        return NeedsHumanRefsUnobservable(
            detail=(
                f"git ls-remote {remote} {ref_prefix}/* exited {result.exit_code}; whether"
                " the failed run preserved its terminal tree could not be established"
            )
        )
    found = _refs_by_name(stdout=result.stdout)
    carrying: list[NeedsHumanRef] = []
    for ref, commit in sorted(found.items()):
        run_id = _suffix_run_id(ref=ref, ref_prefix=ref_prefix, run_ids=run_ids)
        if run_id is None:
            run_id = _tip_run_id(
                runner=runner,
                repo=repo,
                commit=commit,
                run_ids=run_ids,
                timeout_seconds=timeout_seconds,
            )
            if isinstance(run_id, NeedsHumanRefsUnobservable):
                return run_id
        if run_id is not None:
            carrying.append(NeedsHumanRef(commit_sha=commit, ref=ref, run_id=run_id))
    if not carrying:
        return None
    return _select(
        runner=runner,
        repo=repo,
        carrying=carrying,
        ref_prefix=ref_prefix,
        run_ids=run_ids,
        timeout_seconds=timeout_seconds,
    )


def _select(
    *,
    runner: CommandRunner,
    repo: Path,
    carrying: list[NeedsHumanRef],
    ref_prefix: str,
    run_ids: tuple[str, ...],
    timeout_seconds: float,
) -> NeedsHumanRef | NeedsHumanRefsUnobservable:
    """Take the descendant tip, else the newest tip, then let a name break a same-commit tie.

    The choice never reads the order `run_ids` arrives in, and a name never
    outranks history: two refs at different commits are ordered by ancestry and
    committer time alone, so the newer tree of a run beats the older one whatever
    either ref is called.
    """
    commits = sorted({one.commit_sha for one in carrying})
    chosen_commit = commits[0]
    if len(commits) > 1:
        times = _committer_times(
            runner=runner, repo=repo, commits=commits, timeout_seconds=timeout_seconds
        )
        if isinstance(times, NeedsHumanRefsUnobservable):
            return times
        maximal = _maximal_commits(
            runner=runner,
            repo=repo,
            commits=commits,
            timeout_seconds=timeout_seconds,
        )
        if isinstance(maximal, NeedsHumanRefsUnobservable):
            return maximal
        first_name = {
            commit: min(one.ref for one in carrying if one.commit_sha == commit)
            for commit in maximal
        }
        chosen_commit = min(maximal, key=lambda commit: (-times[commit], first_name[commit]))
    at_tip = [one for one in carrying if one.commit_sha == chosen_commit]
    taken = min(
        at_tip,
        key=lambda one: (
            _suffix_run_id(ref=one.ref, ref_prefix=ref_prefix, run_ids=run_ids) is None,
            one.ref,
        ),
    )
    passed_over = tuple((one.ref, one.commit_sha) for one in carrying if one.ref != taken.ref)
    return NeedsHumanRef(
        commit_sha=taken.commit_sha, ref=taken.ref, run_id=taken.run_id, passed_over=passed_over
    )


def _committer_times(
    *, runner: CommandRunner, repo: Path, commits: list[str], timeout_seconds: float
) -> dict[str, int] | NeedsHumanRefsUnobservable:
    """Each commit's committer time, from one `git show`."""
    result = runner.run(
        argv=["git", "show", "-s", "--format=%H %ct", *commits],
        cwd=repo,
        timeout_seconds=timeout_seconds,
    )
    times = {
        fields[0]: int(fields[1])
        for line in result.stdout.splitlines()
        if len(fields := line.split()) == _LS_REMOTE_FIELDS and fields[1].isdigit()
    }
    if result.exit_code != 0 or set(times) != set(commits):
        return NeedsHumanRefsUnobservable(
            detail=(
                f"git show of {len(commits)} needs-human tips could not read every committer"
                " time, so which tree is newest could not be established"
            )
        )
    return times


def _maximal_commits(
    *, runner: CommandRunner, repo: Path, commits: list[str], timeout_seconds: float
) -> list[str] | NeedsHumanRefsUnobservable:
    """The commits no other listed commit descends from.

    An ancestry that cannot be read is unobservable and never the absence of a
    descendant, because that reading would pick an older tree over its successor.
    """
    maximal: list[str] = []
    for older in commits:
        superseded = False
        for newer in commits:
            if newer == older:
                continue
            result = runner.run(
                argv=["git", "merge-base", "--is-ancestor", older, newer],
                cwd=repo,
                timeout_seconds=timeout_seconds,
            )
            if result.exit_code not in {0, 1}:
                return NeedsHumanRefsUnobservable(
                    detail=(
                        f"git merge-base --is-ancestor {older} {newer} exited"
                        f" {result.exit_code}; whether one needs-human tree descends from"
                        " the other could not be established"
                    )
                )
            superseded = superseded or result.exit_code == 0
        if not superseded:
            maximal.append(older)
    return maximal


def _suffix_run_id(*, ref: str, ref_prefix: str, run_ids: tuple[str, ...]) -> str | None:
    """The run encoded in the conventional ref suffix, when it names one."""
    suffix = ref.removeprefix(f"{ref_prefix}/")
    return suffix if suffix in run_ids else None


def _tip_run_id(
    *,
    runner: CommandRunner,
    repo: Path,
    commit: str,
    run_ids: tuple[str, ...],
    timeout_seconds: float,
) -> str | NeedsHumanRefsUnobservable | None:
    """The accepted run trailer on a ref tip, if it has one."""
    result = runner.run(
        argv=["git", "show", "-s", "--format=%B", commit],
        cwd=repo,
        timeout_seconds=timeout_seconds,
    )
    if result.exit_code != 0:
        return NeedsHumanRefsUnobservable(
            detail=(
                f"git show {commit} exited {result.exit_code}; whether the needs-human"
                " ref's publishing run can be established could not be established"
            )
        )
    trailers = _trailers(message=result.stdout)
    for key in ("Fabro-Run", "Factory-Run-Id"):
        candidate = trailers.get(key)
        if candidate in run_ids:
            return candidate
    return None


def _refs_by_name(*, stdout: str) -> dict[str, str]:
    """Map each well-formed `ls-remote` line by the ref it named."""
    return {
        fields[1]: fields[0]
        for line in stdout.splitlines()
        if len(fields := line.split()) == _LS_REMOTE_FIELDS
    }


def _trailers(*, message: str) -> dict[str, str]:
    """Read simple git trailers without accepting prose that merely contains a colon."""
    found: dict[str, str] = {}
    for line in message.splitlines():
        key, separator, value = line.partition(":")
        if separator and key in {"Fabro-Run", "Factory-Run-Id"}:
            found[key] = value.strip()
    return found
