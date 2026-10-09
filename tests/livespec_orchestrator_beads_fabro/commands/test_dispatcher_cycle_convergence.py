"""What the per-cycle observations contribute to the non-convergence bounce.

Scenario 165 makes the progress comparison an ADDITIONAL convergence condition
at the existing fix-loop cap: a deficit there returns the item to backlog
surfacing both counts and the cap, while the SAME count difference before the
cap triggers nothing. A sufficient count proves nothing about acceptance, an
unestablished count is reported unobserved rather than as a zero-count deficit,
and an adopted-ceiling breach contributes at the pre-merge boundary whether or
not the cap was reached.
"""

from __future__ import annotations

import importlib
from pathlib import Path
from types import ModuleType

from livespec_orchestrator_beads_fabro.commands._dispatcher_completed_cycles import (
    UNREADABLE_PROVENANCE,
    CycleSource,
    completed_cycle,
    observed_series,
    unreadable_series,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_cycle_ceilings import (
    NO_ADOPTED_CYCLE_CEILINGS,
    AdoptedCycleCeilings,
)

_MODULE_NAME = "livespec_orchestrator_beads_fabro.commands._dispatcher_cycle_convergence"
_MODULE_PATH = (
    Path(__file__).resolve().parents[3]
    / ".claude-plugin"
    / "scripts"
    / "livespec_orchestrator_beads_fabro"
    / "commands"
    / "_dispatcher_cycle_convergence.py"
)

_CAP = "workflow.janitor_fix_loop_visit_cap"


def _module() -> ModuleType:
    """Import the module under test, asserting it exists first."""
    assert _MODULE_PATH.is_file(), f"{_MODULE_PATH} does not exist yet"
    return importlib.import_module(_MODULE_NAME)


def _series(*, cycles: int, assertions: int, lloc: int = 1):
    sources = tuple(
        CycleSource(
            commit=f"commit{index}",
            pair_id=f"sha256:{index}@2026-10-01T1{index}:00:00Z",
            red_captured_at=f"2026-10-01T1{index}:00:00Z",
            green_verified_at=f"2026-10-01T1{index}:00:05Z",
        )
        for index in range(cycles)
    )
    return observed_series(
        cycles=tuple(
            completed_cycle(ordinal=index + 1, source=source, product_lloc=lloc)
            for index, source in enumerate(sources)
        ),
        assertion_count=assertions,
    )


def test_a_deficit_at_the_cap_bounces_surfacing_both_counts_and_the_cap() -> None:
    module = _module()

    verdict = module.runtime_convergence_verdict(
        series=_series(cycles=1, assertions=3),
        ceilings=NO_ADOPTED_CYCLE_CEILINGS,
        at_fix_loop_cap=True,
        cap=_CAP,
        cap_value=3,
    )

    assert verdict.bounces
    assert verdict.progress_deficit
    assert verdict.contributors == (module.PROGRESS_DEFICIT_CONTRIBUTOR,)
    reason = verdict.as_reason()
    assert reason is not None
    assert "1" in reason
    assert "3" in reason
    assert _CAP in reason


def test_the_same_deficit_before_the_cap_triggers_no_bounce() -> None:
    module = _module()

    verdict = module.runtime_convergence_verdict(
        series=_series(cycles=1, assertions=3),
        ceilings=NO_ADOPTED_CYCLE_CEILINGS,
        at_fix_loop_cap=False,
        cap=_CAP,
        cap_value=3,
    )

    assert not verdict.bounces
    assert not verdict.progress_deficit
    assert verdict.contributors == ()
    assert verdict.as_reason() is None


def test_a_sufficient_count_at_the_cap_contributes_no_deficit() -> None:
    module = _module()

    verdict = module.runtime_convergence_verdict(
        series=_series(cycles=3, assertions=3),
        ceilings=NO_ADOPTED_CYCLE_CEILINGS,
        at_fix_loop_cap=True,
        cap=_CAP,
        cap_value=3,
    )

    assert not verdict.bounces
    assert not verdict.progress_deficit
    assert verdict.completed_count == 3
    assert verdict.assertion_count == 3


def test_an_unreadable_series_at_the_cap_is_unobserved_not_a_zero_deficit() -> None:
    module = _module()

    unreadable = module.runtime_convergence_verdict(
        series=unreadable_series(reason=UNREADABLE_PROVENANCE, assertion_count=3),
        ceilings=NO_ADOPTED_CYCLE_CEILINGS,
        at_fix_loop_cap=True,
        cap=_CAP,
        cap_value=3,
    )
    countless = module.runtime_convergence_verdict(
        series=observed_series(cycles=_series(cycles=1, assertions=1).cycles, assertion_count=None),
        ceilings=NO_ADOPTED_CYCLE_CEILINGS,
        at_fix_loop_cap=True,
        cap=_CAP,
        cap_value=3,
    )

    assert not unreadable.bounces
    assert not unreadable.progress_deficit
    assert unreadable.progress_unobserved_reason == UNREADABLE_PROVENANCE
    assert not countless.bounces
    assert countless.progress_unobserved_reason == module.UNOBSERVED_ASSERTION_COUNT


def test_an_adopted_ceiling_breach_contributes_before_the_cap_is_reached() -> None:
    module = _module()

    verdict = module.runtime_convergence_verdict(
        series=_series(cycles=1, assertions=1, lloc=11),
        ceilings=AdoptedCycleCeilings(product_lloc=10, duration_seconds=None),
        at_fix_loop_cap=False,
        cap=None,
        cap_value=None,
    )

    assert verdict.bounces
    assert not verdict.progress_deficit
    assert verdict.contributors == (module.CYCLE_CEILING_CONTRIBUTOR,)
    reason = verdict.as_reason()
    assert reason is not None
    assert "adopted_cycle_product_lloc_ceiling" in reason
    assert "11" in reason


def test_both_contributors_are_reported_when_both_conditions_hold() -> None:
    module = _module()

    verdict = module.runtime_convergence_verdict(
        series=_series(cycles=1, assertions=3, lloc=11),
        ceilings=AdoptedCycleCeilings(product_lloc=10, duration_seconds=None),
        at_fix_loop_cap=True,
        cap=_CAP,
        cap_value=3,
    )

    assert verdict.contributors == (
        module.PROGRESS_DEFICIT_CONTRIBUTOR,
        module.CYCLE_CEILING_CONTRIBUTOR,
    )
