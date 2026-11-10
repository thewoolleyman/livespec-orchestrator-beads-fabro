"""A choice among one rank's needs-human refs that cannot be made is a hold, not a pick.

Two needs-human refs of the SAME run stand at different commits, so which of them
is the run's terminal tree is decided by committer time and ancestry. When origin's
objects cannot be read for that comparison the answer is unobservable: taking
either ref would be a guess, and the older one restores older work.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandResult
from livespec_orchestrator_beads_fabro.commands._dispatcher_recovery_preserved import (
    PreservedWorkUnobservable,
    verified_preserved_seed,
)

from tests.livespec_orchestrator_beads_fabro.commands._recovery_tip_reads import tip_read_answer

_ITEM = "bd-ib-choice"
_RUN = "01ONLYRUN000000000000000A"
_FIRST = "a1" * 20
_SECOND = "a2" * 20


class _Runner:
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
        if (tip := tip_read_answer(argv=argv)) is not None:
            return tip
        if argv[:3] == ["git", "ls-remote", "origin"]:
            listing = (
                f"{_FIRST}\trefs/heads/needs-human/{_RUN}\n"
                f"{_SECOND}\trefs/heads/needs-human/{_RUN}-again\n"
            )
            return CommandResult(exit_code=0, stdout=listing, stderr="")
        if argv[:3] == ["git", "show", "-s"] and argv[3] == "--format=%B":
            return CommandResult(exit_code=0, stdout=f"Factory-Run-Id: {_RUN}\n", stderr="")
        return CommandResult(exit_code=128, stdout="", stderr="object unreadable")


def test_an_unreadable_choice_among_the_latest_runs_refs_holds_recovery() -> None:
    seed = verified_preserved_seed(
        runner=_Runner(),
        repo=Path("/repo"),
        work_item_id=_ITEM,
        earlier_run_ids=(_RUN,),
        journal_records=({"work_item_id": _ITEM, "run_id": _RUN},),
    )
    assert isinstance(seed, PreservedWorkUnobservable)
    assert "committer time" in seed.detail
