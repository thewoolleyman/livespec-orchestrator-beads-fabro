"""The remote WIP-capture reading used by recovery routing."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandResult
from livespec_orchestrator_beads_fabro.commands._dispatcher_recovery_release import (
    released_for_recovery,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_recovery_routes import RecoverySeed
from livespec_orchestrator_beads_fabro.commands._dispatcher_recovery_wip import (
    WIP_REF_PREFIX,
    WipRefUnobservable,
    verified_latest_wip_seed,
)

_ITEM = "bd-ib-v6br5b"
_RUN = "01M6XG3X8VT5SMWHS7BE65RG5H"
_PREFIX = f"{WIP_REF_PREFIX}/{_ITEM}/{_RUN}"


@dataclass(kw_only=True)
class _Runner:
    result: CommandResult
    calls: list[str] = field(default_factory=list)

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
        self.calls.append(" ".join(argv))
        return self.result


def test_no_run_id_spends_no_remote_read() -> None:
    runner = _Runner(result=CommandResult(exit_code=0, stdout="", stderr=""))

    assert (
        verified_latest_wip_seed(runner=runner, repo=Path("/repo"), work_item_id=_ITEM, run_id=None)
        is None
    )
    assert runner.calls == []


def test_an_unreadable_latest_capture_listing_is_not_absence() -> None:
    runner = _Runner(result=CommandResult(exit_code=128, stdout="", stderr="refused"))

    found = verified_latest_wip_seed(
        runner=runner, repo=Path("/repo"), work_item_id=_ITEM, run_id=_RUN
    )

    assert isinstance(found, WipRefUnobservable)
    assert _PREFIX in found.detail


def test_an_empty_latest_capture_listing_has_no_seed() -> None:
    runner = _Runner(result=CommandResult(exit_code=0, stdout="", stderr=""))

    assert (
        verified_latest_wip_seed(runner=runner, repo=Path("/repo"), work_item_id=_ITEM, run_id=_RUN)
        is None
    )


def test_only_numbered_refs_of_the_latest_run_compete_for_the_capture() -> None:
    runner = _Runner(
        result=CommandResult(
            exit_code=0,
            stdout=(
                f"a{'0' * 39}\t{_PREFIX}/2\n"
                f"b{'0' * 39}\t{_PREFIX}/19\n"
                f"c{'0' * 39}\t{_PREFIX}/latest\n"
                f"d{'0' * 39}\t{WIP_REF_PREFIX}/{_ITEM}/other/99\n"
                "not a remote ref\n"
            ),
            stderr="",
        )
    )

    assert verified_latest_wip_seed(
        runner=runner, repo=Path("/repo"), work_item_id=_ITEM, run_id=_RUN
    ) == RecoverySeed(
        source_run_id=_RUN,
        remote="origin",
        commit_sha=f"b{'0' * 39}",
        preservation_ref=f"{_PREFIX}/19",
    )


def test_a_ready_item_returned_after_a_cancel_is_released_for_wip_recovery() -> None:
    """Restart, outside, and budget cancellations use the same released route."""
    for status in ("cancelled", "run-wall-budget-exceeded"):
        assert released_for_recovery(
            records=(
                {"stage": "dispatch-id", "work_item_id": _ITEM},
                {
                    "stage": "outcome",
                    "outcome": {"work_item_id": _ITEM, "status": status, "detail": ""},
                },
            ),
            work_item_id=_ITEM,
        )
