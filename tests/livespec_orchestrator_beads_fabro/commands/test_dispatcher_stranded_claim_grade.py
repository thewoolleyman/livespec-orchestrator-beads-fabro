"""The grading ladder: the fourteen hold reasons and the one release route.

Every case here is a PURE call, which is the only way the ladder's whole point
can be asserted: each hold exists because some measurement could not be taken,
and a test that needed a real factory, forge or lock to reach one could only
reach it by breaking the thing it was measuring.

TWO CASES CARRY THE WHOLE SAFETY ARGUMENT and are worth naming. The
earliest-failing-condition case asserts that a claim stamped by ANOTHER host
whose factory is also unreachable grades `owner-elsewhere` — both conditions
hold, and the two have different remedies, so a ladder returning whichever it
noticed first would send an operator to the wrong place. And the
unobservable-is-not-negative cases assert that an unreachable factory and an
unreadable lock are HOLDS: read as "the run is gone" and "no owner is alive",
each would release a live dispatch's claim.
"""

from __future__ import annotations

import importlib
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro._store_dispatch_claim import ClaimStamp

_MODULE_PATH = (
    Path(".claude-plugin/scripts/livespec_orchestrator_beads_fabro/commands")
    / "_dispatcher_stranded_claim_grade.py"
)
_MODULE_NAME = "livespec_orchestrator_beads_fabro.commands._dispatcher_stranded_claim_grade"

_HOST = "owning-host"
_RUN = "01RUN"


def _module() -> object:
    return importlib.import_module(_MODULE_NAME)


def _stamp(**overrides: object) -> ClaimStamp:
    base = ClaimStamp(
        dispatch_id="01DISPATCH",
        dispatching_host=_HOST,
        run_id=_RUN,
        factory_name="hp",
        factory_server="https://hp.example:32276",
    )
    return ClaimStamp(
        dispatch_id=overrides.get("dispatch_id", base.dispatch_id),  # pyright: ignore[reportArgumentType]
        dispatching_host=overrides.get("dispatching_host", base.dispatching_host),  # pyright: ignore[reportArgumentType]
        run_id=overrides.get("run_id", base.run_id),  # pyright: ignore[reportArgumentType]
        factory_name=overrides.get("factory_name", base.factory_name),  # pyright: ignore[reportArgumentType]
        factory_server=overrides.get("factory_server", base.factory_server),  # pyright: ignore[reportArgumentType]
    )


def test_the_hold_reason_set_is_complete_and_ordered() -> None:
    assert _MODULE_PATH.is_file()
    module = _module()

    assert module.HOLD_REASON_ORDER == (
        "claim-unattributable",
        "attribution-pending",
        "owner-elsewhere",
        "factory-unobservable",
        "run-live",
        "liveness-unobservable",
        "dispatch-live",
        "run-succeeded",
        "forge-unobservable",
        "merged-pr",
        "history-unavailable",
        "terminal-evidence-unavailable",
        "claim-changed",
        "effect-unobservable",
    )
    assert len(set(module.HOLD_REASON_ORDER)) == 14


@pytest.mark.parametrize(
    ("stamp", "declared", "host", "reason"),
    [
        (None, True, _HOST, "claim-unattributable"),
        (_stamp(factory_name=None), True, _HOST, "claim-unattributable"),
        (_stamp(), False, _HOST, "claim-unattributable"),
        (_stamp(run_id=None), True, _HOST, "attribution-pending"),
        (_stamp(dispatching_host=None), True, _HOST, "owner-elsewhere"),
        (_stamp(dispatching_host="other-host"), True, _HOST, "owner-elsewhere"),
        (
            _stamp(dispatching_host="unknown-dispatching-host"),
            True,
            "unknown-dispatching-host",
            "owner-elsewhere",
        ),
    ],
)
def test_the_attribution_ladder_grades_reasons_one_to_three(
    *,
    stamp: ClaimStamp | None,
    declared: bool,
    host: str,
    reason: str,
) -> None:
    module = _module()

    graded = module.attribute_claim(stamp=stamp, declared_factory=declared, this_host=host)

    assert isinstance(graded, module.ClaimHold)
    assert graded.reason == reason


def test_an_attributed_claim_carries_its_narrowed_run_and_factory() -> None:
    module = _module()

    graded = module.attribute_claim(stamp=_stamp(), declared_factory=True, this_host=_HOST)

    assert isinstance(graded, module.AttributedClaim)
    assert (graded.run_id, graded.factory_name) == (_RUN, "hp")


def test_the_earliest_failing_condition_names_the_hold() -> None:
    """Both conditions hold; the EARLIER one has to win."""
    module = _module()

    graded = module.attribute_claim(
        stamp=_stamp(dispatching_host="host-a"), declared_factory=True, this_host="host-b"
    )

    assert isinstance(graded, module.ClaimHold)
    # `factory-unobservable` would also have been true had the ladder reached
    # it, and it names a different remedy.
    assert graded.reason == "owner-elsewhere"


def _measurements(*, module: object, **overrides: object) -> object:
    attributed = module.AttributedClaim(stamp=_stamp(), run_id=_RUN, factory_name="hp")
    fields: dict[str, object] = {
        "attributed": attributed,
        "run_state": module.RUN_ABSENT,
        "owner_liveness": module.OWNER_NONE,
        "forge": module.FORGE_NO_MERGED_PR,
        "predecessor": module.HISTORY_NO_PREDECESSOR,
        "terminal_evidence_readable": True,
    }
    fields.update(overrides)
    return module.ClaimMeasurements(**fields)


@pytest.mark.parametrize(
    ("overrides", "reason"),
    [
        ({"run_state": "unobservable"}, "factory-unobservable"),
        ({"run_state": "live"}, "run-live"),
        ({"owner_liveness": "unobservable"}, "liveness-unobservable"),
        ({"owner_liveness": "live"}, "dispatch-live"),
        ({"run_state": "succeeded"}, "run-succeeded"),
        ({"forge": "unobservable"}, "forge-unobservable"),
        ({"forge": "merged-pr"}, "merged-pr"),
        ({"predecessor": "unavailable"}, "history-unavailable"),
        (
            {"run_state": "failed", "terminal_evidence_readable": False},
            "terminal-evidence-unavailable",
        ),
    ],
)
def test_each_observation_that_cannot_prove_the_claim_stranded_holds(
    *,
    overrides: dict[str, object],
    reason: str,
) -> None:
    module = _module()

    graded = module.grade_claim(measurements=_measurements(module=module, **overrides))

    assert isinstance(graded, module.ClaimHold)
    assert graded.reason == reason


def test_a_proven_absent_run_earns_the_release_route() -> None:
    module = _module()

    graded = module.grade_claim(measurements=_measurements(module=module))

    assert isinstance(graded, module.ClaimRoute)
    assert graded.action == module.ACTION_ABSENT_RUN_RELEASE


@pytest.mark.parametrize("predecessor", ["no-predecessor", "other-outcome"])
def test_a_predecessor_that_did_not_release_still_earns_the_release(*, predecessor: str) -> None:
    module = _module()

    graded = module.grade_claim(measurements=_measurements(module=module, predecessor=predecessor))

    assert isinstance(graded, module.ClaimRoute)
    assert graded.action == module.ACTION_ABSENT_RUN_RELEASE


def test_a_predecessor_that_ended_in_an_absent_run_release_earns_the_repeat() -> None:
    """The release is bounded to ONE per consecutive sequence of absent runs."""
    module = _module()

    graded = module.grade_claim(
        measurements=_measurements(module=module, predecessor="absent-run-release")
    )

    assert isinstance(graded, module.ClaimRoute)
    assert graded.action == module.ACTION_ABSENT_RUN_REPEATED


@pytest.mark.parametrize(
    ("surveyed", "status_kinds", "expected"),
    [
        (False, {}, "unobservable"),
        (False, {_RUN: "running"}, "unobservable"),
        (True, {}, "absent"),
        (True, {_RUN: None}, "unobservable"),
        (True, {_RUN: "running"}, "live"),
        (True, {_RUN: "blocked"}, "live"),
        (True, {_RUN: "queued"}, "live"),
        (True, {_RUN: "succeeded"}, "succeeded"),
        (True, {_RUN: "failed"}, "failed"),
        (True, {_RUN: "cancelled"}, "failed"),
    ],
)
def test_the_run_state_is_read_off_the_listing_this_pass_already_took(
    *,
    surveyed: bool,
    status_kinds: dict[str, str | None],
    expected: str,
) -> None:
    module = _module()

    assert (
        module.run_state_from_inventory(surveyed=surveyed, status_kinds=status_kinds, run_id=_RUN)
        == expected
    )


def test_a_readable_terminal_failure_earns_the_completion_route() -> None:
    """The route that adds no disposition of its own, only the Dispatcher's."""
    module = _module()

    graded = module.grade_claim(
        measurements=_measurements(
            module=module, run_state="failed", terminal_evidence_readable=True
        )
    )

    assert isinstance(graded, module.ClaimRoute)
    assert graded.action == module.ACTION_TERMINAL_COMPLETION
