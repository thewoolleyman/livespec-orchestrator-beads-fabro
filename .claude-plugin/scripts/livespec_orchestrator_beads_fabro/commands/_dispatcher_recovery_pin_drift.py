"""Detect preserved work whose base predates a dev-tooling pin bump on master."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandRunner
from livespec_orchestrator_beads_fabro.commands._dispatcher_recovery_routes import RecoverySeed

__all__: list[str] = [
    "PreservedBasePinDrift",
    "preserved_base_pin_drift",
]

_DEFAULT_BRANCH_REF = "origin/master"
_DEV_TOOLING_KEY = "livespec-dev-tooling"
_GIT_TIMEOUT_SECONDS = 120.0


@dataclass(frozen=True, kw_only=True)
class PreservedBasePinDrift:
    """The default-branch commit whose pin makes a preserved base unsafe to seed."""

    base_commit: str
    default_branch_commit: str


def preserved_base_pin_drift(
    *, runner: CommandRunner, repo: Path, seed: RecoverySeed
) -> PreservedBasePinDrift | None:
    """Return the audit facts when a preserved base has an older tooling pin.

    A failed measurement deliberately leaves the established seeded route intact.
    Recovery already verified the preserved ref itself; this extra protection only
    changes that route once the repository can prove that the default branch's
    tooling pin differs and can name the intervening default-branch commit.
    """
    base = _git_stdout(
        runner=runner, repo=repo, argv=["git", "rev-parse", f"{seed.commit_sha}^"]
    )
    default_branch = _git_stdout(
        runner=runner, repo=repo, argv=["git", "rev-parse", _DEFAULT_BRANCH_REF]
    )
    if base is None or default_branch is None:
        return None
    base_pin = _dev_tooling_pin(
        _git_stdout(runner=runner, repo=repo, argv=["git", "show", f"{base}:pyproject.toml"])
    )
    default_pin = _dev_tooling_pin(
        _git_stdout(
            runner=runner, repo=repo, argv=["git", "show", f"{_DEFAULT_BRANCH_REF}:pyproject.toml"]
        )
    )
    if base_pin is None or default_pin is None or base_pin == default_pin:
        return None
    changed = _git_stdout(
        runner=runner,
        repo=repo,
        argv=[
            "git",
            "log",
            "--format=%H",
            f"{base}..{_DEFAULT_BRANCH_REF}",
            "--",
            "pyproject.toml",
        ],
    )
    if changed is None:
        return None
    bump_commit = next((line for line in changed.splitlines() if line), None)
    if bump_commit is None:
        return None
    return PreservedBasePinDrift(base_commit=base, default_branch_commit=bump_commit)


def _git_stdout(*, runner: CommandRunner, repo: Path, argv: list[str]) -> str | None:
    """Read one git fact, returning no fact when its command is not readable."""
    result = runner.run(argv=argv, cwd=repo, timeout_seconds=_GIT_TIMEOUT_SECONDS)
    if result.exit_code != 0:
        return None
    value = result.stdout.strip()
    return value or None


def _dev_tooling_pin(pyproject: str | None) -> str | None:
    """Extract the source declaration without depending on the rest of the TOML."""
    if pyproject is None:
        return None
    for line in pyproject.splitlines():
        key, separator, value = line.partition("=")
        if separator and key.strip() == _DEV_TOOLING_KEY:
            return value.strip()
    return None
