"""The Codex overlay leg hands the dispatch's `--node-timeout` layer to the allowance."""

from __future__ import annotations

import importlib
from pathlib import Path
from typing import Any

import pytest

_PACKAGE = "livespec_orchestrator_beads_fabro.commands"


def test_the_leg_forwards_node_timeout_arguments_to_the_requirement(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A Codex-routed leg sizes its requirement with the dispatch's arguments."""
    leg = importlib.import_module(f"{_PACKAGE}._dispatcher_codex_overlay_leg")
    routing = importlib.import_module(f"{_PACKAGE}._dispatcher_codex_routing")
    seen: dict[str, Any] = {}

    def _requirement(**kwargs: Any) -> str:
        seen.update(kwargs)
        return "stop here"

    monkeypatch.setattr(leg, "credential_lifetime_requirement_for", _requirement)

    resolved = leg.project_codex_overlay_leg(
        committed=tmp_path / "workflow.toml",
        block={},
        review_fix_visit_cap=2,
        graph_override=None,
        adapter_inputs=frozenset(),
        clock=lambda: 1_000_000,
        codex_routing=routing.CodexRouting(routes_codex=True, detail="codex"),
        sandbox_otel_endpoint="http://127.0.0.1:44318",
        work_item_id="bd-ib-meejjz",
        dispatch_id="01M50FM0207FG8V82VBE1TTDT8",
        node_timeout_arguments=("fix_commit_settle=7200",),
    )

    assert isinstance(resolved, str), resolved
    assert seen["node_timeout_arguments"] == ("fix_commit_settle=7200",)
