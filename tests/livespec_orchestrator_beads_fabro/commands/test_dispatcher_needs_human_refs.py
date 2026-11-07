"""The unreadable-tip boundary for trailer-based needs-human attribution."""

from __future__ import annotations

from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandResult
from livespec_orchestrator_beads_fabro.commands._dispatcher_needs_human_refs import (
    NeedsHumanRefsUnobservable,
    newest_needs_human_ref,
)


class _Runner:
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
        if argv[1] == "ls-remote":
            return CommandResult(
                exit_code=0,
                stdout=("e" * 40) + "\trefs/heads/needs-human/opaque\n",
                stderr="",
            )
        return CommandResult(exit_code=128, stdout="", stderr="missing commit")


def test_an_unreadable_trailer_only_tip_is_unobservable() -> None:
    found = newest_needs_human_ref(
        runner=_Runner(),
        repo=Path("/repo"),
        run_ids=("run",),
        ref_prefix="refs/heads/needs-human",
        remote="origin",
        timeout_seconds=1.0,
    )

    assert isinstance(found, NeedsHumanRefsUnobservable)
    assert "git show" in found.detail


class _FabroTrailerRunner:
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
        if argv[1] == "ls-remote":
            return CommandResult(
                exit_code=0,
                stdout=("f" * 40) + "\trefs/heads/needs-human/opaque\n",
                stderr="",
            )
        return CommandResult(exit_code=0, stdout="Fabro-Run: run\n", stderr="")


def test_a_fabro_run_tip_trailer_attributes_an_opaque_ref() -> None:
    found = newest_needs_human_ref(
        runner=_FabroTrailerRunner(),
        repo=Path("/repo"),
        run_ids=("run",),
        ref_prefix="refs/heads/needs-human",
        remote="origin",
        timeout_seconds=1.0,
    )

    assert found is not None and not isinstance(found, NeedsHumanRefsUnobservable)
    assert found.run_id == "run"


class _UnattributedTipRunner(_FabroTrailerRunner):
    def run(
        self,
        *,
        argv: list[str],
        cwd: Path,
        timeout_seconds: float,
        env: dict[str, str] | None = None,
        stdin: int | None = None,
    ) -> CommandResult:
        result = super().run(
            argv=argv,
            cwd=cwd,
            timeout_seconds=timeout_seconds,
            env=env,
            stdin=stdin,
        )
        if argv[1] == "show":
            return CommandResult(exit_code=0, stdout="Other-Run: run\n", stderr="")
        return result


def test_an_opaque_tip_without_an_accepted_run_trailer_is_not_a_seed() -> None:
    found = newest_needs_human_ref(
        runner=_UnattributedTipRunner(),
        repo=Path("/repo"),
        run_ids=("run",),
        ref_prefix="refs/heads/needs-human",
        remote="origin",
        timeout_seconds=1.0,
    )

    assert found is None
