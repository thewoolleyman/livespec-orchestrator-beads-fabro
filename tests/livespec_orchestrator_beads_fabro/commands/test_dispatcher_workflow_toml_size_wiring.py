"""Wiring for the materialized workflow.toml size guards."""

from __future__ import annotations

import importlib
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[3]


def test_dispatch_refusal_names_the_measured_size_and_engine_limit() -> None:
    """An over-limit materialization is a pre-claim refusal."""
    module = importlib.import_module(
        "livespec_orchestrator_beads_fabro.commands._dispatcher_workflow_toml_size"
    )
    assert hasattr(module, "dispatch_size_refusal")
    assert module.dispatch_size_refusal(measured_bytes=526_975) == (
        "REFUSED: materialized workflow.toml is 526975 bytes; Fabro limit is 524288 bytes; "
        "no claim was taken and no Fabro run was created"
    )


def test_check_aggregate_runs_the_materialized_workflow_toml_size_target() -> None:
    """The release aggregate cannot omit the representative-size guard."""
    justfile = (_ROOT / "justfile").read_text(encoding="utf-8")
    assert "check-materialized-workflow-toml-size" in justfile
