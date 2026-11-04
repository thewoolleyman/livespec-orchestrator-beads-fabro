"""The Claude WEEKLY limit is a measured, built-in provider-limit form.

`SPECIFICATION/contracts.md` section "Factory-configurable ACP fallback
priority": "A newly measured provider-limit form is added to this set by a
committed change to the built-in signatures or the model catalog, never by
loosening a literal into a broader match." Measured 2026-10-18 on gmktec, run
01M580PF02S0 of bd-ib-fubkcv: after six hours `proof_verify@3` failed with
`Internal error: You've hit your weekly limit · resets Oct 23, 3pm (UTC)` and
`errorKind: 'rate_limit'`. No built-in form matched, the attempt classified as
unmatched, and the run rested at `needs_human` instead of being released.

THE CONTROL IS THE `rate_limit` KIND WITHOUT THE SENTENCE. The same section says
"A Claude `rate_limit` kind alone does not establish quota exhaustion; its
measured message discriminator is required", so the weekly literal must be
specific to the weekly sentence and the kind must never classify on its own.
"""

from __future__ import annotations

from livespec_orchestrator_beads_fabro.commands._acp_builtin_candidates import ANTHROPIC_DOMAIN
from livespec_orchestrator_beads_fabro.commands._acp_builtin_signatures import (
    builtin_availability_signatures,
)
from livespec_orchestrator_beads_fabro.commands._acp_candidate_schema import (
    AcpCandidate,
    AcpCandidateIdentity,
)
from livespec_orchestrator_beads_fabro.commands._acp_dispatch_coverage import RenderedCandidate
from livespec_orchestrator_beads_fabro.commands._acp_failure_classifier import (
    AcpAvailabilityFailure,
    AcpNonEligibleFailure,
    classify_acp_failure,
)
from livespec_orchestrator_beads_fabro.commands._acp_failure_signals import AcpFailureSignal
from livespec_orchestrator_beads_fabro.commands._acp_node_adapters import AcpAdapter
from livespec_orchestrator_beads_fabro.commands._dispatcher_provider_limit_classify import (
    ProviderLimitRelease,
    classified_release,
)
from livespec_orchestrator_beads_fabro.commands._fabro_port_records import FabroFailureDetail

_WEEKLY_SENTENCE = "You've hit your weekly limit · resets Oct 23, 3pm (UTC)"
_WEEKLY_MESSAGE = f"Internal error: {_WEEKLY_SENTENCE}"
# Verbatim from the recorded `proof_verify@3` stage output of run 01M580PF02S0.
_WEEKLY_STAGE_OUTPUT = (
    "Error handling request { jsonrpc: '2.0', id: 3, method: 'session/prompt', "
    "params: { sessionId: '167c78c9-f173-44dc-888f-445c8c2828bc', prompt: [ [Object] ] } } "
    f"{{ code: -32603, message: \"{_WEEKLY_MESSAGE}\", data: {{ errorKind: 'rate_limit' }} }}"
)
_RATE_LIMIT_ONLY_OUTPUT = (
    "Error handling request { jsonrpc: '2.0', id: 3, method: 'session/prompt', "
    "params: { sessionId: '167c78c9-f173-44dc-888f-445c8c2828bc', prompt: [ [Object] ] } } "
    '{ code: -32603, message: "Internal error: Overloaded, please retry shortly.", '
    "data: { errorKind: 'rate_limit' } }"
)
_SIGNATURE = "proof_verify|transient_infra|acp turn failed"


def _rendered() -> RenderedCandidate:
    """A built-in `claude-acp` candidate declaring no signatures of its own."""
    return RenderedCandidate(
        candidate=AcpCandidate(
            adapter=AcpAdapter(command="claude-code-acp", args=(), env={}),
            identity=AcpCandidateIdentity(
                display_name="built-in anthropic ACP adapter",
                candidate_key="builtin-anthropic-0000000000000000",
                availability_key=ANTHROPIC_DOMAIN,
            ),
            signatures=(),
        ),
        builtin=True,
    )


def _classify(*, signal: AcpFailureSignal) -> object:
    rendered = _rendered()
    return classify_acp_failure(
        signal=signal, candidate=rendered.candidate, builtin=rendered.builtin
    )


def test_the_weekly_limit_form_is_a_builtin_domain_scoped_quota_signature() -> None:
    matches = [
        signature
        for signature in builtin_availability_signatures(availability_key=ANTHROPIC_DOMAIN)
        if signature.source == "protocol.message"
        and frozenset(signature.all_literals) == frozenset({"hit your weekly limit", "resets"})
    ]
    assert len(matches) == 1
    assert matches[0].cause == "quota"
    assert matches[0].scope == "availability-domain"


def test_the_weekly_limit_with_its_structured_rate_limit_kind_is_an_availability_failure() -> None:
    verdict = _classify(
        signal=AcpFailureSignal(
            original_identity="acp-protocol-error",
            protocol_message=f"{_WEEKLY_MESSAGE} {{ errorKind: 'rate_limit' }}",
            turn_started=True,
        )
    )
    assert isinstance(verdict, AcpAvailabilityFailure)
    assert verdict.cause == "quota"
    assert verdict.hold_key == ANTHROPIC_DOMAIN


def test_the_weekly_sentence_alone_is_an_availability_failure() -> None:
    verdict = _classify(
        signal=AcpFailureSignal(
            original_identity="acp-protocol-error",
            protocol_message=_WEEKLY_SENTENCE,
            turn_started=True,
        )
    )
    assert isinstance(verdict, AcpAvailabilityFailure)
    assert verdict.cause == "quota"
    assert verdict.scope == "availability-domain"


def test_a_rate_limit_kind_without_the_weekly_sentence_is_not_a_quota() -> None:
    """CONTROL: the structured kind alone never establishes quota exhaustion."""
    verdict = _classify(
        signal=AcpFailureSignal(
            original_identity="acp-protocol-error",
            protocol_message="Internal error: Overloaded, please retry shortly. "
            "{ errorKind: 'rate_limit' }",
            turn_started=True,
        )
    )
    assert isinstance(verdict, AcpNonEligibleFailure)
    assert verdict.reason == "unmatched"


def test_a_needs_human_run_whose_proof_verify_recorded_the_weekly_limit_is_released() -> None:
    release = classified_release(
        failure=FabroFailureDetail(
            cause=_WEEKLY_STAGE_OUTPUT, category="transient_infra", signature=_SIGNATURE
        ),
        rendered=_rendered(),
        node_attempt="proof_verify",
        factory="petri",
        run_id="01M580PF02S0",
        recovery_source="refs/heads/needs-human/01M580PF02S0",
    )
    assert isinstance(release, ProviderLimitRelease)
    assert release.matched is not None
    assert release.matched.cause == "quota"
    assert release.matched.hold_key == ANTHROPIC_DOMAIN
    assert release.release_key == "petri:01M580PF02S0:proof_verify"


def test_a_needs_human_run_whose_proof_verify_recorded_only_a_rate_limit_is_not_released() -> None:
    """CONTROL: the same stage output without the weekly sentence keeps the human route."""
    release = classified_release(
        failure=FabroFailureDetail(
            cause=_RATE_LIMIT_ONLY_OUTPUT, category="transient_infra", signature=_SIGNATURE
        ),
        rendered=_rendered(),
        node_attempt="proof_verify",
        factory="petri",
        run_id="01M580PF02S0",
        recovery_source="refs/heads/needs-human/01M580PF02S0",
    )
    assert release is None
