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
    """A needs-human ref and the run its suffix or tip trailer establishes."""

    commit_sha: str
    ref: str
    run_id: str


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
    """Return the newest matching ref, including one attributable only by trailer."""
    result = runner.run(
        argv=["git", "ls-remote", remote, f"{ref_prefix}/"],
        cwd=repo,
        timeout_seconds=timeout_seconds,
    )
    if result.exit_code != 0:
        return NeedsHumanRefsUnobservable(
            detail=(
                f"git ls-remote {remote} {ref_prefix}/ exited {result.exit_code}; whether"
                " the failed run preserved its terminal tree could not be established"
            )
        )
    found = _refs_by_name(stdout=result.stdout)
    matched: dict[str, NeedsHumanRef] = {}
    for ref, commit in found.items():
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
            matched[run_id] = NeedsHumanRef(commit_sha=commit, ref=ref, run_id=run_id)
    return next((matched[run_id] for run_id in run_ids if run_id in matched), None)


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
