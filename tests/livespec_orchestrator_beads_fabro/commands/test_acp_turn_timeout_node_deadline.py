"""An ACP turn that reached its ceiling is a node deadline, not a provider limit.

`SPECIFICATION/contracts.md` section "Factory-configurable ACP fallback
priority" lists "node deadline or stall expiry" among the classes that are
"non-eligible before configured matching", and Scenario 127's sub-scenario
"Non-eligible failures outrank configured text overlap" names `node timeout`
in that list and requires that "the non-eligible class mints no hold and is
not released for re-dispatch".

WHY THIS IS A CONFORMANCE GAP RATHER THAN A NEW CLASS. The `node_deadline`
guard matched `node deadline exceeded`, `deadline exceeded` and `node
timeout` -- and the engine's own wording for a turn that reached its ceiling
is NONE of those. Measured 2026-10-17 on `bd-ib-6itdjz`, run
01M54W4YM2SWANMK515YNPFY7J on hp: the implement attempt's `causes[-1]` read
`ACP turn timed out after 345 tool call(s) and 3658 session update(s); last
update at 13344311ms`, and Fabro categorised it `transient_infra`. The agent
had been doing genuine work for the whole four hours -- 360 completed tool
calls, 14 git commits, a largest event gap of 13.5 minutes, and a final open
call that was a Red commit running the full pytest suite -- and `run.log`
carried no 429, overloaded, rate-limit, stream-reset or headroom text.

THE OUTCOME WAS ALREADY CORRECT AND IT WAS CORRECT BY ACCIDENT, which is the
whole reason these cases exist. Today's classifier keys on signature matches
rather than on the engine's category, so that cause reached `unmatched` and
was non-eligible on those grounds. Nothing named the class, and nothing
pinned it: a configured literal broad enough to catch a provider timeout
would silently reclassify a WORK timeout as a provider-limit release, which
returns a four-hour genuine-progress run to `ready` as though an allowance
had been spent.

THE CONTROL IS THE `transient_infra` CASE. `AcpFailureSignal` carries no
category field and its docstring forbids adding one, so the engine's
category reaches the classifier only inside `original_identity` --
`implement|transient_infra|acp turn failed`. A build that had started
reading provider eligibility off that segment would turn every
`transient_infra` terminal into an availability failure, and the positive
cases below cannot catch it: they assert what a turn timeout does, and that
segment is present in them too.

Everything is HERMETIC: no adapter is launched, no provider is reached, and
no journal is written.
"""

from __future__ import annotations

from livespec_orchestrator_beads_fabro.commands._acp_candidate_schema import (
    AcpCandidate,
    AcpCandidateIdentity,
)
from livespec_orchestrator_beads_fabro.commands._acp_candidate_signatures import (
    AcpAvailabilitySignature,
)
from livespec_orchestrator_beads_fabro.commands._acp_failure_classifier import (
    AcpAvailabilityFailure,
    AcpNonEligibleFailure,
    classify_acp_failure,
)
from livespec_orchestrator_beads_fabro.commands._acp_failure_signals import (
    AcpFailureSignal,
    non_eligible_reason,
)
from livespec_orchestrator_beads_fabro.commands._acp_node_adapters import AcpAdapter

# The engine's verbatim wording, from the measurement above.
_TURN_TIMEOUT = (
    "ACP turn timed out after 345 tool call(s) and 3658 session update(s); "
    "last update at 13344311ms"
)
# The failure's own name, which a non-eligible verdict terminates WITH. Its
# middle segment is the engine's category, and it is the control's subject.
_IDENTITY_WITH_TRANSIENT_INFRA = "implement|transient_infra|acp turn failed"

_IDENTITY = AcpCandidateIdentity(
    display_name="Claude ACP primary",
    candidate_key="claude-primary",
    availability_key="anthropic-team",
)


def _candidate(*, signatures: tuple[AcpAvailabilitySignature, ...]) -> AcpCandidate:
    return AcpCandidate(
        adapter=AcpAdapter(command="claude-code-acp", args=(), env={}),
        identity=_IDENTITY,
        signatures=signatures,
    )


def test_the_measured_turn_timeout_names_the_node_deadline_guard_class() -> None:
    """The guard reads the engine's own wording on either readable field."""
    assert (
        non_eligible_reason(
            signal=AcpFailureSignal(
                original_identity=_IDENTITY_WITH_TRANSIENT_INFRA,
                protocol_message=_TURN_TIMEOUT,
            )
        )
        == "node_deadline"
    )
    # The same sentence on the separately captured adapter diagnostic names
    # the same class: the guard markers are read from both readable fields,
    # unlike a configured signature, which is bound to the one its `source`
    # names.
    assert (
        non_eligible_reason(
            signal=AcpFailureSignal(
                original_identity=_IDENTITY_WITH_TRANSIENT_INFRA,
                terminal_diagnostic=_TURN_TIMEOUT,
            )
        )
        == "node_deadline"
    )


def test_a_turn_timeout_outranks_a_configured_literal_that_matches_its_text() -> None:
    """Scenario 127: the guard wins even where the declared literal IS present.

    The literal is drawn from the timeout sentence itself, so a build with no
    guard for this wording returns a domain-scoped quota release here -- the
    exact silent reclassification the guard exists to prevent.
    """
    greedy = AcpAvailabilitySignature(
        source="protocol.message",
        cause="quota",
        scope="availability-domain",
        all_literals=("timed out",),
    )

    verdict = classify_acp_failure(
        signal=AcpFailureSignal(
            original_identity=_IDENTITY_WITH_TRANSIENT_INFRA,
            protocol_message=_TURN_TIMEOUT,
            turn_started=True,
        ),
        candidate=_candidate(signatures=(greedy,)),
        builtin=True,
    )

    assert isinstance(verdict, AcpNonEligibleFailure)
    assert verdict.reason == "node_deadline"
    # Non-eligible means it terminates with the identity it already had,
    # rather than with a provider cause nobody measured.
    assert verdict.original_identity == _IDENTITY_WITH_TRANSIENT_INFRA


def test_the_transient_infra_identity_segment_alone_yields_no_availability_failure() -> None:
    """The CONTROL: the engine's category is not provider evidence.

    A quiet failure carrying no guard marker and no declared literal is
    `unmatched` -- non-eligible, minting nothing -- even though its identity
    names `transient_infra`, the category Fabro put on the measured turn
    timeout. Without this case a build reading eligibility off that segment
    would satisfy every other case in this module.
    """
    verdict = classify_acp_failure(
        signal=AcpFailureSignal(
            original_identity=_IDENTITY_WITH_TRANSIENT_INFRA,
            protocol_message="the worker reported an unremarkable hiccup",
            turn_started=True,
        ),
        candidate=_candidate(
            signatures=(
                AcpAvailabilitySignature(
                    source="protocol.message",
                    cause="quota",
                    scope="availability-domain",
                    all_literals=("hit your session limit",),
                ),
            )
        ),
        builtin=True,
    )

    assert not isinstance(verdict, AcpAvailabilityFailure)
    assert isinstance(verdict, AcpNonEligibleFailure)
    assert verdict.reason == "unmatched"
    assert verdict.original_identity == _IDENTITY_WITH_TRANSIENT_INFRA


def test_a_turn_timeout_carrying_a_usage_limit_machine_code_is_still_a_node_deadline() -> None:
    """A structured code takes precedence over TEXT, never over a guard class.

    The contract orders the two rules: "Structured machine codes take
    precedence" governs which configured signature wins among those that
    matched, while the non-eligible classes sit "before configured matching"
    altogether. So a cause chain carrying both the timeout sentence and a
    provider's structured usage-limit token is a node deadline.
    """
    coded = AcpAvailabilitySignature(
        source="protocol.machine_code",
        cause="quota",
        scope="availability-domain",
        machine_code="provider.usage_limit",
    )

    verdict = classify_acp_failure(
        signal=AcpFailureSignal(
            original_identity=_IDENTITY_WITH_TRANSIENT_INFRA,
            machine_code="provider.usage_limit",
            protocol_message=_TURN_TIMEOUT,
            turn_started=True,
        ),
        candidate=_candidate(signatures=(coded,)),
        builtin=True,
    )

    assert isinstance(verdict, AcpNonEligibleFailure)
    assert verdict.reason == "node_deadline"
    assert verdict.original_identity == _IDENTITY_WITH_TRANSIENT_INFRA
