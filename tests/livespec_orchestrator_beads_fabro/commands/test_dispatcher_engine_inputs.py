"""Dispatcher engine-input rendering coverage."""

from types import SimpleNamespace

import pytest
from livespec_orchestrator_beads_fabro.commands import _dispatcher_engine_inputs as inputs_module
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine_inputs import (
    dispatch_fabro_run_inputs,
)


def test_engine_input_renderer_is_public() -> None:
    assert callable(dispatch_fabro_run_inputs)


def test_engine_input_renderer_guards_resolved_adapters_and_keeps_item_policy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Rendering preserves resolved values while applying the launch guard once."""
    monkeypatch.setattr(
        inputs_module,
        "guarded_adapter_string",
        lambda *, rendered: f"guarded {rendered}",
    )
    resolved = SimpleNamespace(
        acp_nodes=SimpleNamespace(run_inputs=("implement_adapter=codex exec",)),
        integration_inputs=("telemetry=on",),
        review_fix_visit_cap=3,
        merge_on_review_cap_outcome="backlog",
        merge_hold=True,
    )
    unresolved = SimpleNamespace(
        acp_nodes=None,
        integration_inputs=(),
        review_fix_visit_cap=0,
        merge_on_review_cap_outcome="succeeded",
        merge_hold=False,
    )

    assert inputs_module.dispatch_fabro_run_inputs(plan=resolved) == (
        "implement_adapter=guarded codex exec",
        "telemetry=on",
        "review_fix_visit_cap=3",
        "merge_on_review_cap_outcome=backlog",
        "merge_hold=true",
    )
    assert inputs_module.dispatch_fabro_run_inputs(plan=unresolved) == (
        "review_fix_visit_cap=0",
        "merge_on_review_cap_outcome=succeeded",
        "merge_hold=false",
    )
