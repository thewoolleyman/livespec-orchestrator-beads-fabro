"""Tree identity decides whether an unattributable preservation ref competes."""

from __future__ import annotations

from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandResult
from livespec_orchestrator_beads_fabro.commands._dispatcher_recovery_published_head import (
    PublishedHeadEquivalent,
    PublishedHeadUnobservable,
    RecoveryPublicationHistory,
    newer_published_head_seed,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_recovery_routes import RecoverySeed

_ITEM = "bd-ib-6szexa"
_TERMINAL = "a" * 40
_HEAD = "b" * 40
_TERMINAL_REF = "refs/livespec/preserved-publish/bd-ib-6szexa/a"
_HEAD_REF = "refs/heads/feat/bd-ib-6szexa"


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
        _ = cwd, timeout_seconds, env, stdin
        joined = " ".join(argv)
        if _HEAD_REF in joined:
            return CommandResult(exit_code=0, stdout=f"{_HEAD}\t{_HEAD_REF}\n", stderr="")
        if f"{_TERMINAL}^{{tree}}" in joined:
            return CommandResult(exit_code=0, stdout=f"{'1' * 40}\n", stderr="")
        if f"{_HEAD}^{{tree}}" in joined:
            return CommandResult(exit_code=0, stdout=f"{'2' * 40}\n", stderr="")
        return CommandResult(exit_code=128, stdout="", stderr="unexpected command")


class _SameTreeRunner(_Runner):
    """The published head and terminal preservation resolve to one whole tree."""

    def run(
        self,
        *,
        argv: list[str],
        cwd: Path,
        timeout_seconds: float,
        env: dict[str, str] | None = None,
        stdin: int | None = None,
    ) -> CommandResult:
        joined = " ".join(argv)
        if f"{_TERMINAL}^{{tree}}" in joined or f"{_HEAD}^{{tree}}" in joined:
            return CommandResult(exit_code=0, stdout=f"{'1' * 40}\n", stderr="")
        return super().run(
            argv=argv,
            cwd=cwd,
            timeout_seconds=timeout_seconds,
            env=env,
            stdin=stdin,
        )


class _UnavailableTreeRunner(_Runner):
    """A preservation tip whose tree cannot be fetched remains unobservable."""

    def run(
        self,
        *,
        argv: list[str],
        cwd: Path,
        timeout_seconds: float,
        env: dict[str, str] | None = None,
        stdin: int | None = None,
    ) -> CommandResult:
        if f"{_TERMINAL}^{{tree}}" in " ".join(argv):
            return CommandResult(exit_code=128, stdout="", stderr="object missing")
        return super().run(
            argv=argv,
            cwd=cwd,
            timeout_seconds=timeout_seconds,
            env=env,
            stdin=stdin,
        )


def test_a_different_preservation_tree_remains_a_competitor_when_neither_run_is_attributable() -> (
    None
):
    outcome = newer_published_head_seed(
        runner=_Runner(),
        repo=Path("/repo"),
        work_item_id=_ITEM,
        terminal=RecoverySeed(
            source_run_id="older",
            remote="origin",
            commit_sha="base",
            preservation_ref=_TERMINAL_REF,
            preservation_tip_sha=_TERMINAL,
        ),
        history=RecoveryPublicationHistory(
            records=({"work_item_id": _ITEM, "published_head": _HEAD},),
            publications=(),
            earlier_run_ids=("older",),
        ),
    )
    assert isinstance(outcome, PublishedHeadUnobservable)
    assert outcome.measurement == "publishing-run-unobservable"


def test_an_identical_preservation_tree_is_not_a_competitor_when_neither_run_is_attributable() -> (
    None
):
    outcome = newer_published_head_seed(
        runner=_SameTreeRunner(),
        repo=Path("/repo"),
        work_item_id=_ITEM,
        terminal=RecoverySeed(
            source_run_id="older",
            remote="origin",
            commit_sha="base",
            preservation_ref=_TERMINAL_REF,
            preservation_tip_sha=_TERMINAL,
        ),
        history=RecoveryPublicationHistory(
            records=({"work_item_id": _ITEM, "published_head": _HEAD},),
            publications=(),
            earlier_run_ids=("older",),
        ),
    )
    assert isinstance(outcome, PublishedHeadEquivalent)
    assert outcome.seed.commit_sha == _HEAD
    assert outcome.competing_ref == _TERMINAL_REF


def test_an_unreadable_preservation_tree_remains_unobservable() -> None:
    outcome = newer_published_head_seed(
        runner=_UnavailableTreeRunner(),
        repo=Path("/repo"),
        work_item_id=_ITEM,
        terminal=RecoverySeed(
            source_run_id="older",
            remote="origin",
            commit_sha="base",
            preservation_ref=_TERMINAL_REF,
            preservation_tip_sha=_TERMINAL,
        ),
        history=RecoveryPublicationHistory(
            records=({"work_item_id": _ITEM, "published_head": _HEAD},),
            publications=(),
            earlier_run_ids=("older",),
        ),
    )
    assert isinstance(outcome, PublishedHeadUnobservable)
    assert outcome.measurement == "publishing-run-unobservable"


def test_a_preservation_without_a_tip_sha_remains_unobservable() -> None:
    outcome = newer_published_head_seed(
        runner=_Runner(),
        repo=Path("/repo"),
        work_item_id=_ITEM,
        terminal=RecoverySeed(
            source_run_id="older",
            remote="origin",
            commit_sha="base",
            preservation_ref=_TERMINAL_REF,
        ),
        history=RecoveryPublicationHistory(
            records=({"work_item_id": _ITEM, "published_head": _HEAD},),
            publications=(),
            earlier_run_ids=("older",),
        ),
    )
    assert isinstance(outcome, PublishedHeadUnobservable)
    assert outcome.measurement == "publishing-run-unobservable"
