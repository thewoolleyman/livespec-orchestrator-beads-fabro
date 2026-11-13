"""Coverage for the contaminated-item supersession command."""

from __future__ import annotations

import importlib


def test_copied_comment_preserves_stage_scope_and_records_safe_provenance() -> None:
    """A successor carries a rider without carrying its goal-template opener."""
    module = importlib.import_module(
        "livespec_orchestrator_beads_fabro.commands._dispatcher_supersede_contaminated"
    )
    opener = "{" + "{"

    copied = module.copied_comment_body(
        original_id="bd-ib-old",
        comment_id="comment-7",
        created_at="2026-11-13T00:00:00Z",
        text=f"FOR implement ONLY:\nretain {opener} evidence",
    )

    assert copied.splitlines()[:2] == [
        "FOR implement ONLY:",
        "Superseded from bd-ib-old comment comment-7 created 2026-11-13T00:00:00Z.",
    ]
    assert opener not in copied
    assert "⟦⟦" in copied
