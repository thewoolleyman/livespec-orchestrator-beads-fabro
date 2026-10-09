"""The two agreeing projections of one dispatch's runtime cycle observations.

Scenario 165 requires the terminal calibration journal and span to expose the
per-cycle observations, the effective assertion count, the completed-cycle count
and the bounce contributors, and requires the two projections to AGREE: an absent
numeric observation stays null in the journal and is OMITTED from the span, with
the accompanying reason surviving on both.

So the discriminating assertions here are the ones a single-shape projection
would pass anyway: that the journal keeps a key the span drops, that the reason
beside it survives the drop, and that an observed EMPTY series does not read the
same as an UNREADABLE one on either surface.
"""

from __future__ import annotations

import importlib
import json
from pathlib import Path
from types import ModuleType

from livespec_orchestrator_beads_fabro.commands._dispatcher_completed_cycles import (
    UNOBSERVED_SOURCE_TREE,
    UNREADABLE_PROVENANCE,
    CycleSource,
    Unobserved,
    completed_cycle,
    observed_series,
    unreadable_series,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_cycle_ceilings import (
    NO_ADOPTED_CYCLE_CEILINGS,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_cycle_convergence import (
    PROGRESS_DEFICIT_CONTRIBUTOR,
    RuntimeConvergenceVerdict,
    runtime_convergence_verdict,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_cycle_measure import (
    PRODUCT_LLOC_MEASUREMENT_METHOD,
)

_MODULE_NAME = "livespec_orchestrator_beads_fabro.commands._dispatcher_cycle_projection"
_MODULE_PATH = (
    Path(__file__).resolve().parents[3]
    / ".claude-plugin"
    / "scripts"
    / "livespec_orchestrator_beads_fabro"
    / "commands"
    / "_dispatcher_cycle_projection.py"
)

_EXPECTED_KEYS = (
    "cycle_observations",
    "completed_cycle_count",
    "effective_assertion_count",
    "bounce_contributors",
    "cycle_series_unobserved_reason",
    "cycle_progress_unobserved_reason",
    "cycle_measurement_method",
)


def _module() -> ModuleType:
    """Import the module under test, asserting it exists first."""
    assert _MODULE_PATH.is_file(), f"{_MODULE_PATH} does not exist yet"
    return importlib.import_module(_MODULE_NAME)


def _source(*, index: int) -> CycleSource:
    return CycleSource(
        commit=f"commit{index}",
        pair_id=f"sha256:{index}@2026-10-01T1{index}:00:00Z",
        red_captured_at=f"2026-10-01T1{index}:00:00Z",
        green_verified_at=f"2026-10-01T1{index}:00:07Z",
    )


def _verdict(*, series, at_cap: bool = False) -> RuntimeConvergenceVerdict:
    return runtime_convergence_verdict(
        series=series,
        ceilings=NO_ADOPTED_CYCLE_CEILINGS,
        at_fix_loop_cap=at_cap,
        cap="workflow.janitor_fix_loop_visit_cap",
        cap_value=3,
    )


def test_the_projected_key_set_is_declared_once_in_projection_order() -> None:
    module = _module()

    assert module.CYCLE_PROJECTED_KEYS == _EXPECTED_KEYS


def test_an_observed_cycle_projects_its_ordinal_identity_and_both_measurements() -> None:
    module = _module()

    observations = module.cycle_observations(
        cycles=(completed_cycle(ordinal=1, source=_source(index=1), product_lloc=12),)
    )

    assert observations == [
        {
            "ordinal": 1,
            "pair_id": "sha256:1@2026-10-01T11:00:00Z",
            "commit": "commit1",
            "product_lloc_changed": 12,
            "product_lloc_unobserved_reason": None,
            "elapsed_seconds": 7,
            "elapsed_unobserved_reason": None,
        }
    ]


def test_the_journal_keeps_an_unmeasured_size_as_null_beside_its_reason() -> None:
    module = _module()
    series = observed_series(
        cycles=(
            completed_cycle(
                ordinal=1,
                source=_source(index=1),
                product_lloc=Unobserved(reason=UNOBSERVED_SOURCE_TREE),
            ),
        ),
        assertion_count=2,
    )

    fields = module.cycle_journal_fields(series=series, verdict=_verdict(series=series))

    assert tuple(fields) == _EXPECTED_KEYS
    assert fields["completed_cycle_count"] == 1
    assert fields["effective_assertion_count"] == 2
    assert fields["cycle_measurement_method"] == PRODUCT_LLOC_MEASUREMENT_METHOD
    observation = fields["cycle_observations"]
    assert isinstance(observation, list)
    assert observation[0]["product_lloc_changed"] is None
    assert observation[0]["product_lloc_unobserved_reason"] == UNOBSERVED_SOURCE_TREE


def test_the_span_omits_the_absent_numbers_and_serializes_the_cycles_once() -> None:
    module = _module()
    series = observed_series(
        cycles=(completed_cycle(ordinal=1, source=_source(index=1), product_lloc=4),),
        assertion_count=None,
    )
    verdict = _verdict(series=series)

    journal = module.cycle_journal_fields(series=series, verdict=verdict)
    span = module.cycle_span_fields(series=series, verdict=verdict)

    # The journal records the unestablished assertion count as an explicit null;
    # the span drops the attribute rather than shipping the string "None".
    assert journal["effective_assertion_count"] is None
    assert "effective_assertion_count" not in span
    # Every key the span DOES carry holds the journal's own value, except the
    # cycles, which ride as one JSON string because OTLP attributes are scalars.
    assert json.loads(span["cycle_observations"]) == journal["cycle_observations"]
    assert span["completed_cycle_count"] == journal["completed_cycle_count"]
    assert span["bounce_contributors"] == journal["bounce_contributors"]
    assert span["cycle_measurement_method"] == PRODUCT_LLOC_MEASUREMENT_METHOD


def test_a_reason_survives_on_the_span_that_omitted_its_numeric_sibling() -> None:
    module = _module()
    series = unreadable_series(reason=UNREADABLE_PROVENANCE, assertion_count=2)
    verdict = _verdict(series=series, at_cap=True)

    journal = module.cycle_journal_fields(series=series, verdict=verdict)
    span = module.cycle_span_fields(series=series, verdict=verdict)

    # An UNREADABLE series has no cycles and no count on either surface...
    assert journal["cycle_observations"] is None
    assert journal["completed_cycle_count"] is None
    assert "cycle_observations" not in span
    assert "completed_cycle_count" not in span
    # ...and the omission is readable only because both reasons are still there.
    assert span["cycle_series_unobserved_reason"] == UNREADABLE_PROVENANCE
    assert span["cycle_progress_unobserved_reason"] == UNREADABLE_PROVENANCE
    assert span["bounce_contributors"] == []


def test_an_observed_empty_series_does_not_read_as_an_unreadable_one() -> None:
    module = _module()
    empty = observed_series(cycles=(), assertion_count=2)
    verdict = _verdict(series=empty, at_cap=True)

    journal = module.cycle_journal_fields(series=empty, verdict=verdict)
    span = module.cycle_span_fields(series=empty, verdict=verdict)

    # A run that authored no cycle is a FINDING: the count is zero, not absent,
    # and the deficit contributes, where an unreadable series contributes nothing.
    assert journal["cycle_observations"] == []
    assert journal["completed_cycle_count"] == 0
    assert journal["cycle_series_unobserved_reason"] is None
    assert journal["bounce_contributors"] == [PROGRESS_DEFICIT_CONTRIBUTOR]
    assert span["completed_cycle_count"] == 0
    assert "cycle_series_unobserved_reason" not in span
    assert span["bounce_contributors"] == [PROGRESS_DEFICIT_CONTRIBUTOR]
