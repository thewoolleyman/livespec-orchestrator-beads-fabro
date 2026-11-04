"""A refusal booked as a successful turn is not a success that retires a hold.

`SPECIFICATION/contracts.md` section "Factory-configurable ACP fallback
priority": "A node attempt that starts after a domain observation and completes
successfully (an attempt reclassified as failed under 'A provider refusal booked
as a successful turn is a failed attempt' is not a successful completion) ...
retires only the older domain record", and such an attempt "MUST NOT count as a
successful completion under 'A record is falsifiable only by later matching
execution'". The factory-derived success reading is where that has to hold, or a
`codex-acp` candidate that just refused for capacity would clear its own hold by
being recorded as having succeeded.

EACH RETIREMENT CASE SITS BESIDE A POSITIVE CONTROL on the same hold: a success
that is not a refusal still retires it, so an implementation that stopped
deriving successes altogether cannot satisfy the refusal case.
"""

from __future__ import annotations

from livespec_orchestrator_beads_fabro.commands._acp_builtin_candidates import (
    ANTHROPIC_DOMAIN,
    CODEX_DOMAIN,
)
from livespec_orchestrator_beads_fabro.commands._acp_factory_run_attempts import (
    succeeded_confirmations,
)
from livespec_orchestrator_beads_fabro.commands._acp_hold_records import AcpAvailabilityHold
from livespec_orchestrator_beads_fabro.commands._acp_hold_retirement import retained_holds
from livespec_orchestrator_beads_fabro.commands._fabro_port_records import FabroRunSummary

_RUN = "01M5C0FBAE8FVZK15XN9WHVM6H"
_CANDIDATE = "builtin-codex-0000000000000000"
_REFUSAL = "Selected model is at capacity. Please try a different model."
_INCIDENT_OUTPUT = (
    "I'm reviewing the branch. I'll make no changes.Selected model is at capacity. "
    "Please try a different model."
)
_HOLD_OCCURRED = "2026-10-20T06:00:00Z"
_RUN_STARTED = "2026-10-20T06:30:00Z"


def _hold(*, availability_key: str = CODEX_DOMAIN) -> AcpAvailabilityHold:
    return AcpAvailabilityHold(
        schema_version=1,
        observation_id="acpobs-capacity",
        scope="candidate",
        hold_key=availability_key,
        candidate_key=_CANDIDATE,
        cause="provider_capacity",
        occurred_at=_HOLD_OCCURRED,
        expires_at="2026-10-20T06:15:00Z",
    )


def _row(*, availability_key: str) -> FabroRunSummary:
    return FabroRunSummary(
        run_id=_RUN,
        status_kind="failed",
        goal=None,
        total_usd_micros=None,
        labels={
            "livespec.acp.review.availability": availability_key,
            "livespec.acp.review.candidate": _CANDIDATE,
        },
    )


def _payload(*, output: str) -> list[dict[str, object]]:
    return [
        {
            "run_id": _RUN,
            "stages": {
                "review@1": {
                    "handler": "agent",
                    "state": "succeeded",
                    "response": "",
                    "output": output,
                },
                "needs_human@1": {"handler": "command", "state": "failed", "output": "parked"},
            },
            "checkpoint": {"current_node": "needs_human"},
        }
    ]


def _retained(*, output: str, availability_key: str = CODEX_DOMAIN) -> tuple[object, ...]:
    successes = succeeded_confirmations(
        factory="gmktec",
        row=_row(availability_key=availability_key),
        payload=_payload(output=output),
        started_at=_RUN_STARTED,
    )
    return retained_holds(
        holds=(_hold(availability_key=availability_key),),
        successes=successes,
        retired_observation_ids=frozenset(),
    )


def test_a_succeeded_review_that_is_not_a_refusal_retires_the_candidate_hold() -> None:
    """CONTROL: the same run, the same hold, an ordinary verdict -- the hold is retired."""
    assert _retained(output="Looks good.\npreferred_label: approve") == ()


def test_a_succeeded_codex_attempt_ending_with_the_capacity_refusal_leaves_the_hold() -> None:
    retained = _retained(output=_INCIDENT_OUTPUT)
    assert len(retained) == 1


def test_a_refusal_alone_as_the_output_leaves_the_hold() -> None:
    assert len(_retained(output=_REFUSAL)) == 1


def test_refusal_words_that_are_not_the_tail_are_still_a_success_that_retires() -> None:
    output = f"{_REFUSAL} The review verdict follows.\npreferred_label: approve"
    assert _retained(output=output) == ()


def test_a_claude_attempt_ending_with_the_same_words_is_still_a_success_that_retires() -> None:
    """The capacity form belongs to the codex table alone, so a Claude success stands."""
    assert _retained(output=_INCIDENT_OUTPUT, availability_key=ANTHROPIC_DOMAIN) == ()
