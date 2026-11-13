"""Coverage for malformed needs-human write-side tree-guard records."""

from __future__ import annotations

from livespec_orchestrator_beads_fabro.commands._dispatcher_needs_human_detail import (
    needs_human_terminal_detail,
)
from livespec_orchestrator_beads_fabro.commands._fabro_causal_stage import (
    UNESTABLISHED,
    CausalStageFailure,
)


def test_an_incomplete_tree_guard_record_is_not_treated_as_a_ref() -> None:
    """The guard needs every field before the Dispatcher can report a refusal."""
    detail = needs_human_terminal_detail(
        work_item_id="bd-ib-mezwux",
        run_id="01M7ACAZFQJ8AQ2M5K98D0AYB4",
        text=("LIVESPEC_NEEDS_HUMAN_NOT_PRESERVED: " "ref=refs/heads/needs-human/dispatch-id\n"),
        causal=CausalStageFailure(kind=UNESTABLISHED, stages=(), signatures=(), history=()),
        failure=None,
    )

    assert "whether the tree reached a run-scoped ref is UNKNOWN" in detail
