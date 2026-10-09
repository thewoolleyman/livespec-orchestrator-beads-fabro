"""The two adopted per-cycle runtime ceilings, and what counts as a breach.

Scenario 165 makes `dispatcher.adopted_cycle_product_lloc_ceiling` and
`dispatcher.adopted_cycle_duration_seconds_ceiling` committed-only settings,
absent by default, each a positive integer excluding booleans, with invalid
policy refusing before any claim or lifecycle mutation. Only an ADOPTED ceiling
can contribute a breach, the breach is STRICT so equality is not one, and an
unobserved measurement can neither manufacture nor waive one.
"""

from __future__ import annotations

import importlib
from pathlib import Path
from types import ModuleType

from livespec_orchestrator_beads_fabro.commands._dispatcher_completed_cycles import (
    CycleSource,
    Unobserved,
    completed_cycle,
    observed_series,
    unreadable_series,
)

_MODULE_NAME = "livespec_orchestrator_beads_fabro.commands._dispatcher_cycle_ceilings"
_MODULE_PATH = (
    Path(__file__).resolve().parents[3]
    / ".claude-plugin"
    / "scripts"
    / "livespec_orchestrator_beads_fabro"
    / "commands"
    / "_dispatcher_cycle_ceilings.py"
)


def _module() -> ModuleType:
    """Import the module under test, asserting it exists first.

    The existence assertion is the genuine failing assertion this slice's Red
    commit stands on, rather than a collection-time `ModuleNotFoundError`.
    """
    assert _MODULE_PATH.is_file(), f"{_MODULE_PATH} does not exist yet"
    return importlib.import_module(_MODULE_NAME)


def _source() -> CycleSource:
    return CycleSource(
        commit="aaaa111",
        pair_id="sha256:one@2026-10-01T10:00:00Z",
        red_captured_at="2026-10-01T10:00:00Z",
        green_verified_at="2026-10-01T10:00:10Z",
    )


def test_both_ceilings_are_absent_by_default_and_adopt_a_positive_integer() -> None:
    module = _module()

    absent = module.adopted_cycle_ceilings(block={})
    adopted = module.adopted_cycle_ceilings(
        block={
            module.ADOPTED_CYCLE_PRODUCT_LLOC_CEILING_KEY: 10,
            module.ADOPTED_CYCLE_DURATION_SECONDS_CEILING_KEY: 10,
        }
    )

    assert absent == module.NO_ADOPTED_CYCLE_CEILINGS
    assert not absent.adopted
    assert adopted.product_lloc == 10
    assert adopted.duration_seconds == 10
    assert adopted.adopted


def test_zero_negative_boolean_and_non_integer_policy_refuses_naming_the_setting() -> None:
    module = _module()

    for key in module.COMMITTED_ONLY_RUNTIME_CEILING_KEYS:
        for value in (0, -1, True, "10", 10.5, None):
            refusal = module.adopted_cycle_ceilings(block={key: value})

            assert isinstance(refusal, str), f"{key}={value!r} must refuse"
            assert key in refusal
            assert "positive integer" in refusal


def test_a_cycle_strictly_exceeding_an_adopted_ceiling_breaches_naming_everything() -> None:
    module = _module()
    series = observed_series(
        cycles=(completed_cycle(ordinal=1, source=_source(), product_lloc=11),),
        assertion_count=1,
    )

    breaches = module.cycle_ceiling_breaches(
        series=series,
        ceilings=module.AdoptedCycleCeilings(product_lloc=10, duration_seconds=None),
    )

    assert len(breaches) == 1
    breach = breaches[0]
    assert breach.setting == module.ADOPTED_CYCLE_PRODUCT_LLOC_CEILING_KEY
    assert breach.limit == 10
    assert breach.observed == 11
    assert breach.cycle_ordinal == 1
    assert breach.pair_id == _source().pair_id
    reason = breach.as_reason()
    assert module.ADOPTED_CYCLE_PRODUCT_LLOC_CEILING_KEY in reason
    assert "10" in reason
    assert "11" in reason
    assert _source().pair_id in reason


def test_the_duration_ceiling_breaches_on_its_own_measurement() -> None:
    module = _module()
    source = CycleSource(
        commit="bbbb222",
        pair_id="sha256:two@2026-10-01T10:00:00Z",
        red_captured_at="2026-10-01T10:00:00Z",
        green_verified_at="2026-10-01T10:00:11Z",
    )
    series = observed_series(
        cycles=(completed_cycle(ordinal=1, source=source, product_lloc=1),), assertion_count=1
    )

    breaches = module.cycle_ceiling_breaches(
        series=series,
        ceilings=module.AdoptedCycleCeilings(product_lloc=None, duration_seconds=10),
    )

    assert [breach.setting for breach in breaches] == [
        module.ADOPTED_CYCLE_DURATION_SECONDS_CEILING_KEY
    ]
    assert breaches[0].observed == 11


def test_equality_is_not_a_breach() -> None:
    module = _module()
    series = observed_series(
        cycles=(completed_cycle(ordinal=1, source=_source(), product_lloc=10),),
        assertion_count=1,
    )

    breaches = module.cycle_ceiling_breaches(
        series=series,
        ceilings=module.AdoptedCycleCeilings(product_lloc=10, duration_seconds=10),
    )

    assert breaches == ()


def test_absent_adoption_and_unobserved_measurements_manufacture_no_breach() -> None:
    module = _module()
    unobserved = observed_series(
        cycles=(
            completed_cycle(
                ordinal=1,
                source=_source(),
                product_lloc=Unobserved(reason="source-tree-unavailable"),
            ),
        ),
        assertion_count=1,
    )
    enormous = observed_series(
        cycles=(completed_cycle(ordinal=1, source=_source(), product_lloc=10_000),),
        assertion_count=1,
    )

    assert (
        module.cycle_ceiling_breaches(series=enormous, ceilings=module.NO_ADOPTED_CYCLE_CEILINGS)
        == ()
    )
    assert (
        module.cycle_ceiling_breaches(
            series=unobserved,
            ceilings=module.AdoptedCycleCeilings(product_lloc=1, duration_seconds=None),
        )
        == ()
    )
    assert (
        module.cycle_ceiling_breaches(
            series=unreadable_series(reason="provenance-unreadable", assertion_count=1),
            ceilings=module.AdoptedCycleCeilings(product_lloc=1, duration_seconds=1),
        )
        == ()
    )
