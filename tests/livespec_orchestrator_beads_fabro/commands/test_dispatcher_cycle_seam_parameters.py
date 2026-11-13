"""The runtime-gate seams satisfy the parameter-count lint instead of suppressing it.

The repository caps a function at six parameters (`max-args` in `pyproject.toml`).
The first cut of the runtime-convergence gate cleared that detector with
`# noqa: PLR0913` on four seams. A suppression hides the condition the lint exists
to flag, so the repair is structural: the dispatch's fixed inputs travel as ONE
typed subject, and the gate rides the plan the engine already receives.
"""

from __future__ import annotations

import inspect
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands import _dispatcher_cycle_gate as gate_module
from livespec_orchestrator_beads_fabro.commands import _dispatcher_engine as engine_module
from livespec_orchestrator_beads_fabro.commands import _dispatcher_plan_build as plan_module

_MAX_PARAMETERS = 6
_COMMANDS = (
    Path(__file__).resolve().parents[3]
    / ".claude-plugin"
    / "scripts"
    / "livespec_orchestrator_beads_fabro"
    / "commands"
)


def _parameter_count(*, function: object) -> int:
    assert callable(function)
    return len(inspect.signature(function).parameters)


def test_the_runtime_gate_seams_stay_within_the_parameter_budget() -> None:
    counts = {
        "pre_merge_runtime_gate": _parameter_count(function=gate_module.pre_merge_runtime_gate),
        "record_terminal_runtime_convergence": _parameter_count(
            function=gate_module.record_terminal_runtime_convergence
        ),
        "run_dispatch": _parameter_count(function=engine_module.run_dispatch),
    }

    assert {name: count for name, count in counts.items() if count > _MAX_PARAMETERS} == {}


def test_the_dispatch_inputs_travel_as_one_typed_subject() -> None:
    subject_type = getattr(gate_module, "CycleGateSubject", None)

    assert subject_type is not None
    assert {"repo", "item", "dispatch_id", "fix_loop_cap", "journal", "runner"} <= set(
        inspect.signature(subject_type).parameters
    )


def test_the_pre_merge_gate_rides_the_plan_not_a_seventh_engine_parameter() -> None:
    assert "pre_merge_gate" in inspect.signature(plan_module.DispatchPlan).parameters
    assert "pre_merge_gate" not in inspect.signature(engine_module.run_dispatch).parameters


def test_no_runtime_gate_module_suppresses_the_parameter_count_lint() -> None:
    suppressed = [
        name
        for name in ("_dispatcher_cycle_gate.py", "_dispatcher_engine.py")
        if "noqa: PLR0913" in (_COMMANDS / name).read_text(encoding="utf-8")
    ]

    assert suppressed == []
