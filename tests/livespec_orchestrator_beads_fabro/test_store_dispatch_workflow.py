"""The `dispatch_workflow` metadata pin: where it lands and what it preserves.

The load-bearing test here is the sibling-key one. `bd update --metadata`
MERGES top-level keys but REPLACES a nested object wholesale, so a pin written
under an existing object would destroy every sub-key the payload did not
happen to resend -- silently, and only for callers that read those sub-keys
later. Asserting the key is at the TOP LEVEL and that a nested neighbour
survives is what pins the write away from that shape.
"""

from __future__ import annotations

from typing import Any

from livespec_orchestrator_beads_fabro._beads_client import (
    FakeBeadsClient,
    IssueDraft,
    make_beads_client,
)
from livespec_orchestrator_beads_fabro._store_dispatch_workflow import (
    dispatch_workflow_for,
    dispatch_workflow_from_record,
    dispatch_workflow_metadata,
    record_dispatch_workflow,
)
from livespec_orchestrator_beads_fabro.types import StoreConfig


def _config() -> StoreConfig:
    return StoreConfig(
        tenant="livespec-impl-beads",
        prefix="livespec-impl-beads",
        server_user="livespec-impl-beads",
        database="livespec-impl-beads",
        bd_path="bd",
        fake=True,
    )


def _fake() -> FakeBeadsClient:
    client = make_beads_client(config=_config())
    assert isinstance(client, FakeBeadsClient)
    return client


def _issue(*, issue_id: str) -> None:
    _ = _fake().create_issue(
        draft=IssueDraft(
            issue_id=issue_id,
            issue_type="task",
            title="title",
            description="description",
            assignee=None,
            created_at="2026-05-19T00:00:00Z",
        )
    )


def _metadata_of(*, issue_id: str) -> dict[str, Any]:
    raw = _fake().show_issue(issue_id=issue_id).get("metadata")
    assert isinstance(raw, dict)
    return dict(raw)


def test_an_unpinned_item_reports_no_recorded_workflow() -> None:
    """The unconfigured case: nothing recorded reads back as nothing."""
    _issue(issue_id="li-wf-none")

    assert dispatch_workflow_for(path=_config(), work_item_id="li-wf-none") is None


def test_the_pin_is_written_and_read_back_as_a_top_level_key() -> None:
    """The pin lands at `metadata.dispatch_workflow`, not nested under anything."""
    _issue(issue_id="li-wf-pin")

    record_dispatch_workflow(path=_config(), work_item_id="li-wf-pin", workflow="codex-first")

    assert _metadata_of(issue_id="li-wf-pin")["dispatch_workflow"] == "codex-first"
    assert dispatch_workflow_for(path=_config(), work_item_id="li-wf-pin") == "codex-first"


def test_the_pin_preserves_every_other_metadata_key_including_nested_ones() -> None:
    """A nested neighbour survives the write, sub-key by sub-key."""
    _issue(issue_id="li-wf-sib")
    _fake().update_issue(
        issue_id="li-wf-sib",
        metadata={"rank": "a1", "audit": {"actor": "operator", "note": "kept"}},
    )

    record_dispatch_workflow(path=_config(), work_item_id="li-wf-sib", workflow="codex-first")

    metadata = _metadata_of(issue_id="li-wf-sib")
    assert metadata["rank"] == "a1"
    assert metadata["audit"] == {"actor": "operator", "note": "kept"}
    assert metadata["dispatch_workflow"] == "codex-first"


def test_rewriting_the_same_pin_leaves_the_record_untouched() -> None:
    """The no-op arm: an unchanged pin does not re-enter the store."""
    _issue(issue_id="li-wf-same")
    record_dispatch_workflow(path=_config(), work_item_id="li-wf-same", workflow="codex-first")
    before = _fake().show_issue(issue_id="li-wf-same")

    record_dispatch_workflow(path=_config(), work_item_id="li-wf-same", workflow="codex-first")

    assert _fake().show_issue(issue_id="li-wf-same") == before


def test_a_replacement_pin_overwrites_the_previous_one() -> None:
    """The newest resolution wins, so a re-selection is not shadowed."""
    _issue(issue_id="li-wf-new")
    record_dispatch_workflow(path=_config(), work_item_id="li-wf-new", workflow="codex-first")

    record_dispatch_workflow(path=_config(), work_item_id="li-wf-new", workflow="claude-first")

    assert dispatch_workflow_for(path=_config(), work_item_id="li-wf-new") == "claude-first"


def test_a_malformed_metadata_column_reads_back_as_no_pin() -> None:
    """A record whose metadata is not an object carries no pin, and does not raise."""
    assert dispatch_workflow_from_record(record={"metadata": "not-json-object"}) is None


def test_a_blank_pin_reads_back_as_no_pin() -> None:
    """An empty or whitespace-only value is absence, not a variant named ''."""
    assert dispatch_workflow_from_record(record={"metadata": {"dispatch_workflow": "   "}}) is None


def test_the_pin_overlay_is_the_one_top_level_key_a_reader_finds_the_pin_under() -> None:
    """The overlay a token-guarded write merges reads back as the pin it carries."""
    overlay = dispatch_workflow_metadata(workflow="groom-cut")

    assert overlay == {"dispatch_workflow": "groom-cut"}
    assert dispatch_workflow_from_record(record={"metadata": overlay}) == "groom-cut"
