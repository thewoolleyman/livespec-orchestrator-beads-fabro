"""A CANDIDATE-scoped record is matched on its exact identity pair.

Separate from `test_acp_availability_wait.py` because this shape was found by a
coverage measurement taken after that module's Red was authored, and a Red's
test bytes are fixed across its Red-to-Green pair -- the same reason
`test_plan_result_proof_subject.py` sits beside its own siblings.

THE TWO CASES ARE A MATCHED PAIR AND NEITHER WORKS ALONE. `SPECIFICATION/
contracts.md` section "Factory-configurable ACP fallback priority": "A domain
record skips every candidate covered by its selected hold key; a candidate
record skips only the exact identity pair." So a matcher that ignored the
candidate key would satisfy the positive case while attributing one
entitlement's outage to a sibling model under the same account, and a matcher
that demanded it everywhere would satisfy the negative case while matching no
DOMAIN hold at all -- which is the common case, since a provider allowance
outage is what mints one.

BOTH CASES ASSERT THE INSTANT, not merely the hold list, because the expiry is
what the matching decides: a record that fails to match contributes no expiry,
so the wait falls back to the cadence. Reading the fallback instant is
therefore the observation that tells a missed match from a made one.
"""

from __future__ import annotations

import importlib
from typing import Any

_PACKAGE = "livespec_orchestrator_beads_fabro.commands"

_NOW = "2026-10-15T12:00:00Z"
_INTERVAL = 300
_NOW_PLUS_INTERVAL = "2026-10-15T12:05:00Z"
_HOLD_EXPIRY = "2026-10-15T12:40:00Z"

_CANDIDATE_SCOPE = "candidate"


def _module(*, name: str) -> Any:
    return importlib.import_module(f"{_PACKAGE}.{name}")


def _candidate_hold(*, candidate_key: str) -> Any:
    records = _module(name="_acp_hold_records")
    return records.AcpAvailabilityHold(
        schema_version=1,
        observation_id="obs-candidate",
        scope=_CANDIDATE_SCOPE,
        hold_key="codex",
        candidate_key=candidate_key,
        cause="model_not_entitled",
        occurred_at=_NOW,
        expires_at=_HOLD_EXPIRY,
    )


def _candidate_skip(*, candidate_key: str) -> Any:
    preflight = _module(name="_acp_candidate_preflight")
    return preflight.SkippedCandidate(
        availability_key="codex",
        candidate_key=candidate_key,
        reason=preflight.TYPED_HOLD_SKIP,
        cause="model_not_entitled",
        scope=_CANDIDATE_SCOPE,
        hold_key="codex",
    )


def _verdict_for(*, skip: Any) -> Any:
    preflight = _module(name="_acp_candidate_preflight")
    return _module(name="_acp_preflight_verdict").AcpPreflightVerdict(
        fallback_enabled=True,
        nodes=(
            preflight.NodePreflight(
                node="disposition", enabled=True, candidates=(), skipped=(skip,)
            ),
        ),
        success_critical=("implement",),
        admission_required=("disposition",),
        exhausted=("disposition",),
    )


def _wait(*, skip: Any, hold: Any) -> Any:
    return _module(name="_acp_availability_wait").availability_wait(
        verdict=_verdict_for(skip=skip),
        holds=(hold,),
        now_iso=_NOW,
        reprobe_interval_seconds=_INTERVAL,
    )


def test_a_candidate_record_governs_its_own_exact_identity_pair() -> None:
    """The positive case: the pair agrees, so the record's expiry governs."""
    wait = _wait(
        skip=_candidate_skip(candidate_key="gpt-5.5-high"),
        hold=_candidate_hold(candidate_key="gpt-5.5-high"),
    )

    assert wait is not None
    assert [hold.observation_id for hold in wait.holds] == ["obs-candidate"]
    assert wait.reevaluate_at == _HOLD_EXPIRY


def test_a_candidate_record_does_not_govern_a_sibling_candidate_key() -> None:
    """The control: same scope, same account, DIFFERENT entitlement.

    "Explicitly identified candidates MUST NOT be broadened to unrelated
    identities." The record substantiates nothing about this skip, so no hold
    is named and the cadence governs instead of a borrowed expiry.
    """
    wait = _wait(
        skip=_candidate_skip(candidate_key="gpt-5.5-high"),
        hold=_candidate_hold(candidate_key="gpt-5.5-low"),
    )

    assert wait is not None
    assert wait.holds == ()
    assert wait.reevaluate_at == _NOW_PLUS_INTERVAL
