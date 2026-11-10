"""Controls for refresh-repair cause attribution at the needs-human terminal."""

from __future__ import annotations

import pytest
from livespec_orchestrator_beads_fabro.commands import _dispatcher_needs_human_terminal
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandResult
from livespec_orchestrator_beads_fabro.commands._fabro_causal_stage import (
    STAGE_FAILURE,
    CausalStageFailure,
)
from livespec_orchestrator_beads_fabro.commands._fabro_port import FabroInspectResult
from livespec_orchestrator_beads_fabro.commands._fabro_port_records import FabroFailureDetail

_ABSENT = "LIVESPEC_REFRESH_REPAIR_ABSENT: refresh repair brief was absent"


def _causal(*, stages: tuple[str, ...]) -> CausalStageFailure:
    return CausalStageFailure(kind=STAGE_FAILURE, stages=stages, signatures=(), history=())


def _inspect() -> FabroInspectResult:
    return FabroInspectResult(
        command=CommandResult(exit_code=0, stdout="", stderr=""),
        payload=[],
        status_kind="failed",
        failure=None,
        events_payload=[],
    )


@pytest.mark.parametrize(
    ("stages", "repair_cause"),
    [
        (("janitor@1", "refresh_repair@1"), _ABSENT),
        (("pr_refresh@1", "refresh_repair@1"), "refresh_repair timed out after 300 seconds"),
    ],
)
def test_only_an_absent_repair_after_a_refresh_is_reattributed(
    monkeypatch: pytest.MonkeyPatch, *, stages: tuple[str, ...], repair_cause: str
) -> None:
    """A repair's own fault, or an unrelated predecessor, remains the cause."""
    causal = _causal(stages=stages)

    def repair_failure(**_: object) -> FabroFailureDetail:
        return FabroFailureDetail(cause=repair_cause, category=None, signature=None)

    monkeypatch.setattr(
        _dispatcher_needs_human_terminal,
        "routing_stage_failure",
        repair_failure,
    )

    assert (
        _dispatcher_needs_human_terminal._refresh_source_causal(  # noqa: SLF001 - exact attribution seam.
            causal=causal, inspect=_inspect()
        )
        == causal
    )
