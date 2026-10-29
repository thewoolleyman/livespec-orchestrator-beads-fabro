"""A refusal booked as a successful turn is classified from the attempt's recorded output.

`SPECIFICATION/contracts.md` section "Factory-configurable ACP fallback
priority": a `turn.final_output` signature "applies only to an agent node
attempt that the engine recorded as succeeded". Both the recorded output and
the signature's `final_text` are normalized (case-folded, whitespace collapsed
and trimmed), and the signature "matches only when the normalized output ENDS
WITH the normalized `final_text` at a sentence boundary: the output either
equals that text, or the character immediately before the text is `.`, `!` or
`?`, or the text is preceded by exactly one space whose preceding character is
`.`, `!` or `?`." A refusal that is not the output's tail, or is marked as a
quotation, is not a refusal, and the capacity form is `codex-acp`-only.
"""

from __future__ import annotations

from livespec_orchestrator_beads_fabro.commands._acp_builtin_candidates import (
    ANTHROPIC_DOMAIN,
    CODEX_DOMAIN,
)
from livespec_orchestrator_beads_fabro.commands._acp_candidate_schema import (
    AcpCandidate,
    AcpCandidateIdentity,
)
from livespec_orchestrator_beads_fabro.commands._acp_failure_classifier import (
    AcpAvailabilityFailure,
    AcpNonEligibleFailure,
    classify_acp_failure,
)
from livespec_orchestrator_beads_fabro.commands._acp_failure_signals import AcpFailureSignal
from livespec_orchestrator_beads_fabro.commands._acp_node_adapters import AcpAdapter

_REFUSAL = "Selected model is at capacity. Please try a different model."
# MEASURED 2026-10-20, run 01M5C0FBAE8FVZK15XN9WHVM6H of bd-ib-davaxq, verbatim:
# the refusal follows the preceding sentence's period with no space.
_INCIDENT_OUTPUT = (
    "I'm reviewing the branch and its latest captured proof against the six stated "
    "acceptance assertions. I'll make no changes.Selected model is at capacity. "
    "Please try a different model."
)
_CODEX_CANDIDATE_KEY = "builtin-codex-0000000000000000"


def _candidate(*, availability_key: str) -> AcpCandidate:
    return AcpCandidate(
        adapter=AcpAdapter(command="codex-acp", args=(), env={}),
        identity=AcpCandidateIdentity(
            display_name="built-in ACP adapter",
            candidate_key=_CODEX_CANDIDATE_KEY,
            availability_key=availability_key,
        ),
        signatures=(),
    )


def _classify(
    *, output: str | None, availability_key: str = CODEX_DOMAIN, succeeded: bool = True
) -> object:
    return classify_acp_failure(
        signal=AcpFailureSignal(
            original_identity="review|succeeded",
            final_output=output,
            attempt_succeeded=succeeded,
            turn_started=True,
        ),
        candidate=_candidate(availability_key=availability_key),
        builtin=True,
    )


def _is_capacity(*, verdict: object) -> bool:
    return isinstance(verdict, AcpAvailabilityFailure) and verdict.cause == "provider_capacity"


def test_the_measured_incident_output_is_a_candidate_scoped_capacity_failure() -> None:
    verdict = _classify(output=_INCIDENT_OUTPUT)
    assert isinstance(verdict, AcpAvailabilityFailure)
    assert verdict.cause == "provider_capacity"
    assert verdict.scope == "candidate"
    assert verdict.source == "turn.final_output"
    assert verdict.availability_key == CODEX_DOMAIN
    assert verdict.hold_key == CODEX_DOMAIN
    assert verdict.candidate_key == _CODEX_CANDIDATE_KEY


def test_an_output_equal_to_the_refusal_matches() -> None:
    assert _is_capacity(verdict=_classify(output=_REFUSAL))


def test_a_refusal_after_each_sentence_terminator_with_one_space_matches() -> None:
    for terminator in (".", "!", "?"):
        assert _is_capacity(verdict=_classify(output=f"Done{terminator} {_REFUSAL}")), terminator
        assert _is_capacity(verdict=_classify(output=f"Done{terminator}{_REFUSAL}")), terminator


def test_case_and_whitespace_drift_in_the_output_still_matches() -> None:
    drifted = (
        "  Review done.\n\nSELECTED   model is at\tcapacity.\nPlease try a different MODEL.  \n"
    )
    assert _is_capacity(verdict=_classify(output=drifted))


def test_an_unmarked_reproduction_at_the_end_of_the_output_matches() -> None:
    lead = "Review passed. The adapter diagnostic is reproduced verbatim below."
    output = f"{lead} {_REFUSAL}"
    assert _is_capacity(verdict=_classify(output=output))


def test_refusal_words_that_are_not_the_tail_do_not_match() -> None:
    verdict = _classify(output=f"{_REFUSAL} The review verdict follows.\npreferred_label: approve")
    assert isinstance(verdict, AcpNonEligibleFailure)
    assert verdict.reason == "unmatched"


def test_a_refusal_mid_sentence_without_a_terminator_does_not_match() -> None:
    verdict = _classify(output=f"The adapter said {_REFUSAL}")
    assert isinstance(verdict, AcpNonEligibleFailure)


def test_a_refusal_followed_by_a_closing_quotation_mark_does_not_match() -> None:
    verdict = _classify(output=f'The adapter reported "{_REFUSAL}"')
    assert isinstance(verdict, AcpNonEligibleFailure)
    assert verdict.reason == "unmatched"


def test_a_refusal_preceded_by_a_colon_lead_in_does_not_match() -> None:
    for lead in ("The adapter reported: ", "The adapter reported:"):
        verdict = _classify(output=f"{lead}{_REFUSAL}")
        assert isinstance(verdict, AcpNonEligibleFailure), lead


def test_a_claude_acp_attempt_ending_with_the_same_words_does_not_match() -> None:
    verdict = _classify(output=_INCIDENT_OUTPUT, availability_key=ANTHROPIC_DOMAIN)
    assert isinstance(verdict, AcpNonEligibleFailure)
    assert verdict.reason == "unmatched"


def test_an_attempt_the_engine_did_not_record_as_succeeded_is_not_read_for_output() -> None:
    verdict = _classify(output=_INCIDENT_OUTPUT, succeeded=False)
    assert isinstance(verdict, AcpNonEligibleFailure)


def test_a_succeeded_attempt_with_no_recorded_output_does_not_match() -> None:
    verdict = _classify(output=None)
    assert isinstance(verdict, AcpNonEligibleFailure)
