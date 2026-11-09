"""Read the latest settled capture of one run directly from origin."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandRunner
from livespec_orchestrator_beads_fabro.commands._dispatcher_recovery_routes import RecoverySeed

__all__: list[str] = [
    "WIP_REF_PREFIX",
    "WipRefUnobservable",
    "verified_latest_wip_seed",
]

WIP_REF_PREFIX = "refs/livespec/wip"
_SEED_REMOTE = "origin"
_GIT_TIMEOUT_SECONDS = 120.0
_LS_REMOTE_FIELDS = 2


@dataclass(frozen=True, kw_only=True)
class WipRefUnobservable:
    """Origin could not answer whether the latest run has a settled capture."""

    detail: str


def verified_latest_wip_seed(
    *,
    runner: CommandRunner,
    repo: Path,
    work_item_id: str,
    run_id: str | None,
) -> RecoverySeed | WipRefUnobservable | None:
    """Return the latest run's highest-numbered WIP ref, if origin verifies one."""
    if run_id is None or not run_id.strip():
        return None
    pattern = f"{WIP_REF_PREFIX}/{work_item_id}/{run_id}/*"
    result = runner.run(
        argv=["git", "ls-remote", _SEED_REMOTE, pattern],
        cwd=repo,
        timeout_seconds=_GIT_TIMEOUT_SECONDS,
    )
    if result.exit_code != 0:
        return WipRefUnobservable(
            detail=(
                f"git ls-remote {_SEED_REMOTE} {pattern} exited {result.exit_code}; whether the"
                " latest run preserved a settled capture could not be established, so no seed"
                " was taken and absence is not confirmed"
            )
        )
    captures = [
        capture
        for line in result.stdout.splitlines()
        if (capture := _capture(line=line, prefix=f"{WIP_REF_PREFIX}/{work_item_id}/{run_id}/"))
        is not None
    ]
    if not captures:
        return None
    _, ref, commit = max(captures)
    return RecoverySeed(
        source_run_id=run_id,
        remote=_SEED_REMOTE,
        commit_sha=commit,
        preservation_ref=ref,
    )


def _capture(*, line: str, prefix: str) -> tuple[int, str, str] | None:
    """Parse one numbered WIP capture from `git ls-remote` output."""
    fields = line.split()
    if len(fields) != _LS_REMOTE_FIELDS or not fields[1].startswith(prefix):
        return None
    sequence = fields[1].removeprefix(prefix)
    if not sequence.isdecimal():
        return None
    return int(sequence), fields[1], fields[0]
