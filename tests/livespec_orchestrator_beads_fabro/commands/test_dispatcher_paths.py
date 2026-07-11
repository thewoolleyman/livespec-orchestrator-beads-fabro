"""Public path-helper surface extracted from the Dispatcher."""

from __future__ import annotations

from livespec_orchestrator_beads_fabro.commands import _dispatcher_paths


def test_dispatcher_paths_exports_promoted_public_helpers() -> None:
    assert _dispatcher_paths.__all__ == [
        "cost_report_spans_path",
        "cost_sink_path",
        "heartbeat_path",
        "is_writable_orchestrator_checkout",
        "journal_path",
        "plugin_root",
        "reflector_oob_spans_path",
        "resolve_merged_paths",
        "spans_path",
        "store_config",
        "workflow_toml",
    ]
