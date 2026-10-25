"""The Claude WEEKLY ceiling is a measured provider-limit form, not a mystery.

`SPECIFICATION/contracts.md` section "Factory-configurable ACP fallback
priority": "A newly measured provider-limit form is added to this set by a
committed change to the built-in signatures or the model catalog, never by
loosening a literal into a broader match." This file is the committed change's
test; work-item `bd-ib-ht7v4q`, finding F-bi.

WHAT WAS MEASURED. On gmktec, run `01M580PF02S0` of `bd-ib-fubkcv` ran for six
hours and then failed at `proof_verify@3`. The Petri-era engine kept no
`node_outcomes` on the checkpoint, so the refusal survives ONLY in that stage's
own output, as the adapter's JSON-RPC error carrying
`message: "Internal error: You've hit your weekly limit · resets Oct 23, 3pm
(UTC)"` and `data: { errorKind: 'rate_limit' }`. The run routed to
`needs_human`, no provider-limit release fired, the item rested for a human and
its pull request stayed unmerged.

WHY NO EXISTING SIGNATURE CAUGHT IT, which is the whole of the defect and is a
one-word difference. The Anthropic table carried `hit your session limit`, the
conjunction `hit your limit` + `resets`, `hit your usage limit`, and `org` +
`spend limit`. "hit your weekly limit" contains NONE of them: `hit your limit`
is not a substring of `hit your weekly limit`, because the vendor put a word in
the middle. So the attempt classified `unmatched`, `classified_release`
returned `None`, and a six-hour run's whole output was spent reaching a rest
state a release would have turned into a re-dispatch on the next candidate.

THE LITERAL IS THE MEASURED SENTENCE AND NOTHING WIDER. `resets` rides beside
`hit your weekly limit` for the same reason it rides beside the generic form:
the ceiling wording is a prefix of sentences that are not ceilings, and the
reset clause is what the vendor prints when an allowance is actually spent.

THE STRUCTURED KIND IS NOT THE DISCRIMINATOR, and the control below is what
keeps it from becoming one. The same contract section says "A Claude
`rate_limit` kind alone does not establish quota exhaustion; its measured
message discriminator is required", and Scenario 65's sub-scenario "A Claude
rate_limit kind without the measured sentence is not a quota exhaustion" grades
it. So the kind is carried on the positive case exactly as the engine recorded
it, and asserted NOT to classify on its own -- a mapping keyed on `rate_limit`
would satisfy every positive here while holding the whole Anthropic domain over
an ordinary throttle.
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
    DOMAIN_SCOPE,
    AcpAvailabilityFailure,
    AcpNonEligibleFailure,
    classify_acp_failure,
)
from livespec_orchestrator_beads_fabro.commands._acp_failure_signals import AcpFailureSignal
from livespec_orchestrator_beads_fabro.commands._acp_node_adapters import AcpAdapter
from livespec_orchestrator_beads_fabro.commands._dispatcher_provider_limit_classify import (
    classified_release,
)
from livespec_orchestrator_beads_fabro.commands._fabro_port_records import FabroFailureDetail

_MESSAGE_SOURCE = "protocol.message"
_QUOTA = "quota"

# The form the table must carry, transcribed from the measured sentence rather
# than chosen for breadth.
_WEEKLY_LITERALS: tuple[str, ...] = ("hit your weekly limit", "resets")

# The provider's own sentence, as the adapter's JSON-RPC error carried it.
_WEEKLY_SENTENCE = "Internal error: You've hit your weekly limit · resets Oct 23, 3pm (UTC)"
# The structured kind that arrived WITH it, and that must never decide alone.
_RATE_LIMIT_KIND = "rate_limit"
# An ordinary refusal carrying that same kind: the control's whole input.
_THROTTLED_SENTENCE = "Internal error: the request was throttled, please retry"

# The failing `proof_verify@3` stage output of run 01M580PF02S0, verbatim.
_STAGE_OUTPUT = (
    "Error handling request { jsonrpc: '2.0', id: 3, method: 'session/prompt', "
    "params: { sessionId: '167c78c9-f173-44dc-888f-445c8c2828bc', "
    "prompt: [ [Object] ] } } { code: -32603, "
    'message: "Internal error: You\'ve hit your weekly limit · resets Oct 23, 3pm (UTC)", '
    "data: { errorKind: 'rate_limit' } }"
)
_RUN = "01M580PF02S0"
_NODE_ATTEMPT = "proof_verify@3"
_PRESERVED_REF = "refs/heads/needs-human/01M580PF02S0"
# The engine's own name for the failure, which a non-eligible verdict would
# have to terminate with.
_SIGNATURE = "proof_verify|transient_infra|acp turn failed"

_IDENTITY = AcpCandidateIdentity(
    display_name="built-in anthropic ACP adapter",
    candidate_key="builtin-anthropic-0000000000000000",
    availability_key=ANTHROPIC_DOMAIN,
)


def _candidate() -> AcpCandidate:
    """The built-in `claude-acp` candidate, declaring no signatures of its own.

    Declaring none is the point: every signature that classifies it comes from
    the shipped table, so a passing assertion below can only be the committed
    mapping and never a fixture's own literal.
    """
    return AcpCandidate(
        adapter=AcpAdapter(command="claude-code-acp", args=(), env={}),
        identity=_IDENTITY,
        signatures=(),
    )


def _verdict(
    *, message: str, machine_code: str | None
) -> AcpAvailabilityFailure | AcpNonEligibleFailure:
    """One built-in `claude-acp` attempt graded as the terminal recorded it."""
    return classify_acp_failure(
        signal=AcpFailureSignal(
            original_identity=_SIGNATURE,
            protocol_message=message,
            machine_code=machine_code,
            turn_started=True,
        ),
        candidate=_candidate(),
        builtin=True,
    )


def test_the_measured_weekly_form_is_a_builtin_anthropic_quota_signature() -> None:
    """Assertion 1: the table carries the weekly conjunction, once, as domain quota."""
    matches = [
        signature
        for signature in builtin_availability_signatures(availability_key=ANTHROPIC_DOMAIN)
        if signature.source == _MESSAGE_SOURCE
        and frozenset(signature.all_literals) == frozenset(_WEEKLY_LITERALS)
    ]

    assert len(matches) == 1, matches
    assert matches[0].cause == _QUOTA
    assert matches[0].scope == DOMAIN_SCOPE
    # No `hold_key` override: a spent weekly allowance belongs to the account,
    # so the candidate's own availability key is the right hold key.
    assert matches[0].hold_key is None


def test_the_weekly_sentence_with_its_structured_kind_classifies_as_quota() -> None:
    """Assertion 2: the measured payload, both halves, reaches a typed quota verdict."""
    verdict = _verdict(message=_WEEKLY_SENTENCE, machine_code=_RATE_LIMIT_KIND)

    assert isinstance(verdict, AcpAvailabilityFailure), verdict
    assert verdict.cause == _QUOTA
    assert verdict.scope == DOMAIN_SCOPE
    assert verdict.hold_key == ANTHROPIC_DOMAIN
    assert verdict.candidate_key is None
    # The SENTENCE is what matched, not the structured kind beside it.
    assert verdict.source == _MESSAGE_SOURCE


def test_the_weekly_sentence_alone_classifies_as_quota() -> None:
    """Assertion 3: the engine that kept only the message text still releases.

    This is the arm the measured run actually took: the Petri-era checkpoint
    carried no structured payload at all, so a mapping that needed one would
    have classified nothing on the very ending it was written for.
    """
    verdict = _verdict(
        message="You've hit your weekly limit · resets Oct 23, 3pm (UTC)", machine_code=None
    )

    assert isinstance(verdict, AcpAvailabilityFailure), verdict
    assert verdict.cause == _QUOTA
    assert verdict.scope == DOMAIN_SCOPE
    assert verdict.hold_key == ANTHROPIC_DOMAIN


def test_the_measured_needs_human_stage_output_releases_for_re_dispatch() -> None:
    """Assertion 4: the verbatim `proof_verify@3` output owes a provider-limit release.

    `provider_usage_limit` is False on purpose. The typed flag is a SECOND,
    independent route to release, so leaving it set would let this pass with no
    signature mapped at all -- the legacy arm would carry it. False makes the
    committed mapping the only thing that can produce a release here.
    """
    release = classified_release(
        failure=FabroFailureDetail(
            cause=_STAGE_OUTPUT,
            category="deterministic",
            signature=_SIGNATURE,
            provider_usage_limit=False,
        ),
        rendered=RenderedCandidate(candidate=_candidate(), builtin=True),
        node_attempt=_NODE_ATTEMPT,
        factory="gmktec",
        run_id=_RUN,
        recovery_source=_PRESERVED_REF,
    )

    assert release is not None
    # The ELIGIBLE arm produced it, so a typed hold is minted and no cause-text
    # provider is reported beside it.
    assert release.matched is not None
    assert release.matched.cause == _QUOTA
    assert release.matched.hold_key == ANTHROPIC_DOMAIN
    assert release.legacy_provider is None
    assert release.executed == _IDENTITY
    assert release.release_key == f"gmktec:{_RUN}:{_NODE_ATTEMPT}"
    assert release.recovery_source == _PRESERVED_REF


def test_the_structured_kind_without_the_measured_sentence_is_not_a_quota() -> None:
    """CONTROL: Scenario 65's sub-scenario, which this mapping must not weaken.

    A `rate_limit` kind is an ordinary throttle until the vendor's own ceiling
    sentence says otherwise. Without this, a table keyed on the kind would
    satisfy every positive above while holding the whole Anthropic domain --
    and every candidate drawing on it -- over a retryable refusal.
    """
    verdict = _verdict(message=_THROTTLED_SENTENCE, machine_code=_RATE_LIMIT_KIND)

    assert isinstance(verdict, AcpNonEligibleFailure), verdict
    assert verdict.reason == "unmatched"
    assert verdict.original_identity == _SIGNATURE
