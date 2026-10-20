"""A succeeded Codex turn can still be a typed provider-capacity failure.

Scenario 209 records the unusual engine shape precisely: the adapter writes its
capacity refusal into the final turn text and Fabro records the attempt as a
success.  The classifier must recognize only that final, unquoted refusal for
the Codex built-in candidate; an ordinary successful review that merely mentions
the words keeps its successful classification.
"""

from __future__ import annotations

from livespec_orchestrator_beads_fabro.commands._acp_builtin_candidates import (
    ANTHROPIC_DOMAIN,
    CODEX_DOMAIN,
)
from livespec_orchestrator_beads_fabro.commands._acp_builtin_signatures import (
    builtin_availability_signatures,
)
from livespec_orchestrator_beads_fabro.commands._acp_candidate_schema import (
    AcpCandidate,
    AcpCandidateIdentity,
)
from livespec_orchestrator_beads_fabro.commands._acp_candidate_signatures import (
    SIGNATURE_SOURCES,
)
from livespec_orchestrator_beads_fabro.commands._acp_failure_classifier import (
    AcpAvailabilityFailure,
    AcpNonEligibleFailure,
    classify_acp_failure,
)
from livespec_orchestrator_beads_fabro.commands._acp_failure_signals import AcpFailureSignal
from livespec_orchestrator_beads_fabro.commands._acp_node_adapters import AcpAdapter

_SOURCE = "turn.final_output"
_REFUSAL = "Selected model is at capacity. Please try a different model."
_MEASURED_OUTPUT = (
    "I'm reviewing the branch and its latest captured proof against the six stated "
    "acceptance assertions. I'll make no changes.Selected model is at capacity. "
    "Please try a different model."
)


def _candidate(*, availability_key: str) -> AcpCandidate:
    """One built-in candidate with the exact entitlement the attempt recorded."""
    return AcpCandidate(
        adapter=AcpAdapter(command="adapter", args=(), env={}),
        identity=AcpCandidateIdentity(
            display_name=f"{availability_key} ACP",
            candidate_key=f"{availability_key}-review",
            availability_key=availability_key,
        ),
        signatures=(),
    )


def _verdict(*, output: str, availability_key: str = CODEX_DOMAIN) -> object:
    """Classify one engine-recorded successful agent turn."""
    return classify_acp_failure(
        signal=AcpFailureSignal(
            original_identity="review|succeeded|unmatched",
            turn_final_output=output,
            turn_started=True,
            turn_succeeded=True,
        ),
        candidate=_candidate(availability_key=availability_key),
        builtin=True,
    )


def test_the_codex_capacity_form_is_a_candidate_scoped_final_output_signature() -> None:
    """The built-in table carries Scenario 209's measured, complete refusal."""
    assert _SOURCE in SIGNATURE_SOURCES

    matches = [
        signature
        for signature in builtin_availability_signatures(availability_key=CODEX_DOMAIN)
        if signature.source == _SOURCE
    ]

    assert len(matches) == 1
    signature = matches[0]
    assert signature.cause == "provider_capacity"
    assert signature.scope == "candidate"
    assert signature.final_text == _REFUSAL
    assert signature.all_literals == ()


def test_a_succeeded_codex_turn_ending_in_the_measured_refusal_is_reclassified() -> None:
    """The incident's no-space sentence boundary still names a candidate hold."""
    verdict = _verdict(output=_MEASURED_OUTPUT)

    assert isinstance(verdict, AcpAvailabilityFailure)
    assert verdict.cause == "provider_capacity"
    assert verdict.scope == "candidate"
    assert verdict.source == _SOURCE
    assert verdict.candidate_key == "codex-review"


def test_only_an_unquoted_sentence_boundary_tail_matches_the_capacity_form() -> None:
    """Mentioning, quoting, or colon-introducing the words leaves the turn successful."""
    non_matches = (
        _REFUSAL + " Review verdict: approved.",
        f'The adapter reported "{_REFUSAL}"',
        f"The adapter reported: {_REFUSAL}",
    )

    for output in non_matches:
        verdict = _verdict(output=output)
        assert isinstance(verdict, AcpNonEligibleFailure), output
        assert verdict.reason == "unmatched"


def test_the_codex_capacity_form_does_not_classify_a_claude_turn() -> None:
    """The same tail is a Codex-specific measurement, not provider-neutral text."""
    assert builtin_availability_signatures(availability_key=ANTHROPIC_DOMAIN)

    verdict = _verdict(output=_REFUSAL, availability_key=ANTHROPIC_DOMAIN)

    assert isinstance(verdict, AcpNonEligibleFailure)
    assert verdict.reason == "unmatched"
