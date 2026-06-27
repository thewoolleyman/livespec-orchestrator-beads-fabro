"""Tests for the fail-closed cost-observability seam (work-item 5v9).

Covers `_dispatcher_cost` — the per-run cost-signal extractor and the
fail-closed gate decision that the y0m spend-cap will build on. The
load-bearing facts under test, established by the 5v9 investigation
(fabro v0.254.0, ACP backend): `total_usd_micros` is carried by `fabro
ps -a --json` (never `fabro inspect`) and is `null` on every run, and no
per-node `usage` or token count is populated anywhere — so per-run cost
is FUNDAMENTALLY UNOBSERVABLE at dispatch time in this fabro version.

The warranted path is therefore the fail-closed gate (preconditions.md
leg (b)): in `autonomous` (unattended) mode an
unobservable cost is itself a cap-accounting failure and the loop must
REFUSE to keep picking; in `shadow` mode (a human is present) a warn
suffices. The extractor is the observable-cost seam; when fabro starts
populating the field, the same extractor surfaces a real value with no
gate change.
"""

from __future__ import annotations

import json

from livespec_orchestrator_beads_fabro.commands._dispatcher_cost import (
    CostGateDecision,
    CostObservation,
    cost_gate_decision,
    observe_run_cost,
    resolve_per_run_cap_usd,
    resolve_per_session_cap_usd,
)

# A `fabro ps -a --json` array shaped exactly like fabro v0.254.0 emits
# it: the per-run record carries `total_usd_micros` and it is null on
# every run (the 5v9 finding). Only the fields the extractor reads are
# kept; credential-bearing fields are deliberately absent.
_PS_JSON_NULL_COST = json.dumps(
    [
        {"run_id": "01RUNAAA", "status": {"kind": "succeeded"}, "total_usd_micros": None},
        {"run_id": "01RUNBBB", "status": {"kind": "succeeded"}, "total_usd_micros": None},
    ]
)

# A forward-compat array where fabro HAS populated the cost field (a
# future fabro version / the field going live): $1.250000 == 1_250_000
# micros. The extractor must surface it unchanged so y0m's cap reads a
# real number with no gate change.
_PS_JSON_REAL_COST = json.dumps(
    [
        {"run_id": "01RUNAAA", "status": {"kind": "succeeded"}, "total_usd_micros": 1_250_000},
    ]
)


def test_observe_run_cost_returns_unobservable_when_field_is_null() -> None:
    """The canonical 5v9 case: total_usd_micros is null → unobservable."""
    observation = observe_run_cost(ps_json=_PS_JSON_NULL_COST, run_id="01RUNAAA")
    assert observation == CostObservation(
        run_id="01RUNAAA",
        usd_micros=None,
        observable=False,
    )


def test_observe_run_cost_surfaces_a_real_populated_cost() -> None:
    """Forward-compat: a populated field is surfaced as an observable cost."""
    observation = observe_run_cost(ps_json=_PS_JSON_REAL_COST, run_id="01RUNAAA")
    assert observation == CostObservation(
        run_id="01RUNAAA",
        usd_micros=1_250_000,
        observable=True,
    )


def test_observe_run_cost_unobservable_when_run_absent_from_ps() -> None:
    """A run id not present in `fabro ps` output is unobservable, not a crash."""
    observation = observe_run_cost(ps_json=_PS_JSON_NULL_COST, run_id="01MISSING")
    assert observation == CostObservation(
        run_id="01MISSING",
        usd_micros=None,
        observable=False,
    )


def test_observe_run_cost_unobservable_on_malformed_ps_json() -> None:
    """Malformed `fabro ps` output yields an unobservable result, never raises."""
    observation = observe_run_cost(ps_json="not json {", run_id="01RUNAAA")
    assert observation.observable is False
    assert observation.usd_micros is None


def test_observe_run_cost_unobservable_on_non_array_payload() -> None:
    """A JSON object (not the expected array) yields an unobservable result."""
    observation = observe_run_cost(ps_json='{"runs": []}', run_id="01RUNAAA")
    assert observation.observable is False
    assert observation.usd_micros is None


def test_observe_run_cost_skips_non_dict_array_entries() -> None:
    """Junk (non-dict) entries in the array are skipped, then the run is found."""
    ps_json = json.dumps(["junk-not-a-dict", {"run_id": "01RUNAAA", "total_usd_micros": 42}])
    observation = observe_run_cost(ps_json=ps_json, run_id="01RUNAAA")
    assert observation == CostObservation(run_id="01RUNAAA", usd_micros=42, observable=True)


def test_observe_run_cost_rejects_boolean_total_usd_micros() -> None:
    """A JSON `true` is an int in Python but is never a valid micro-USD count."""
    ps_json = json.dumps([{"run_id": "01RUNAAA", "total_usd_micros": True}])
    observation = observe_run_cost(ps_json=ps_json, run_id="01RUNAAA")
    assert observation.observable is False
    assert observation.usd_micros is None


def test_cost_gate_autonomous_refuses_on_unobservable_cost() -> None:
    """Fail-closed: autonomous mode + unobservable cost → REFUSE to continue."""
    decision = cost_gate_decision(
        mode="autonomous",
        observation=CostObservation(run_id="01RUNAAA", usd_micros=None, observable=False),
    )
    assert decision.refuse is True
    assert decision.severity == "critical"
    # The reason must name the actionable condition without any blob/secret.
    assert "unobservable" in decision.reason.lower()
    assert "01RUNAAA" in decision.reason


def test_cost_gate_shadow_warns_but_does_not_refuse_on_unobservable_cost() -> None:
    """Shadow mode (a human is present): unobservable cost warns, never refuses."""
    decision = cost_gate_decision(
        mode="shadow",
        observation=CostObservation(run_id="01RUNAAA", usd_micros=None, observable=False),
    )
    assert decision.refuse is False
    assert decision.severity == "warn"


def test_cost_gate_does_not_refuse_when_cost_is_observable() -> None:
    """An observable cost (even autonomous) does not trip the unobservable gate.

    Cap-VALUE enforcement (per-run/per-session ceilings) is y0m's job; the
    5v9 gate only fires on the unobservable condition. An observed cost is
    `info` and lets the loop proceed to y0m's cap check.
    """
    decision = cost_gate_decision(
        mode="autonomous",
        observation=CostObservation(run_id="01RUNAAA", usd_micros=1_250_000, observable=True),
    )
    assert decision.refuse is False
    assert decision.severity == "info"


def test_cost_gate_decision_is_a_frozen_value() -> None:
    """The decision is a leak-free value carrying only scalar fields."""
    decision = cost_gate_decision(
        mode="autonomous",
        observation=CostObservation(run_id="01RUNAAA", usd_micros=None, observable=False),
    )
    assert isinstance(decision, CostGateDecision)
    assert isinstance(decision.refuse, bool)
    assert isinstance(decision.severity, str)
    assert isinstance(decision.reason, str)


def test_resolve_caps_default_committed_values_when_env_absent() -> None:
    """Committed defaults so an unset env never means uncapped (preconditions.md)."""
    assert resolve_per_run_cap_usd(environ={}) == 25.0
    assert resolve_per_session_cap_usd(environ={}) == 100.0


def test_resolve_caps_honor_env_overrides() -> None:
    """The caps are env-overridable for y0m's cap enforcement."""
    environ = {"LIVESPEC_MAX_RUN_USD": "5", "LIVESPEC_MAX_SESSION_USD": "40"}
    assert resolve_per_run_cap_usd(environ=environ) == 5.0
    assert resolve_per_session_cap_usd(environ=environ) == 40.0


def test_resolve_caps_fall_back_to_default_on_unparseable_env() -> None:
    """A garbage env value falls back to the committed default, never crashes."""
    environ = {"LIVESPEC_MAX_RUN_USD": "not-a-number"}
    assert resolve_per_run_cap_usd(environ=environ) == 25.0
