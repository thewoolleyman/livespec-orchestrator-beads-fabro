"""Whether one terminated run's failing attempt releases, and what it observed.

`SPECIFICATION/contracts.md` section "Factory-configurable ACP fallback
priority" → "Provider-limit release and re-dispatch" (`bd-ib-6itdjz`,
Scenario 127): when a run terminates "through any terminal, the workflow's
`needs_human` terminal included" and the failing node's recorded failure
"classifies under this section's signatures as an eligible cause", the
Dispatcher records the hold, journals the release, returns the item to `ready`
and leaves it to the ordinary admission valve.

PURE, AND THE DECISION ONLY. It mints no hold, writes no journal, reads no
configuration and touches no ledger: it returns the release a terminal owes, or
`None` for a route this clause does not change. `_dispatcher_provider_limit_
records` turns a release into its two appendable records and
`_dispatcher_provider_limit_release` performs it, which is the same
decision/record/perform split `_acp_failure_classifier` /
`_acp_hold_records` / `_acp_hold_ledger` take one level down.

THE RECORDED CAUSE IS READ AS THE ACP PROTOCOL MESSAGE, and that single
mapping is what makes the whole clause reachable. `_acp_failure_matching`
chooses the observed field BY the signature's `source` and states the
invariant outright -- "there is no path on which a literal declared for
`protocol.message` can be satisfied by a terminal diagnostic" -- so the field
this reading picks decides whether anything can ever match. Two independent
facts put the cause on the message:

- The ENGINE names the channel. `causes[0]` of a failed ACP stage is the
  literal `ACP protocol error` and `causes[-1]` carries the provider's own
  sentence (`AGENTS.md`, measured over all 17 failure blocks of the 53 failed
  hp runs), so the chain this reads is a protocol error by the engine's own
  account.
- The SIGNATURE TABLE agrees. `_acp_builtin_signatures._quota_message`
  records that the message form is "the one that survives an engine keeping
  only the failure message text ... and what a run routed through
  `needs_human` can be left with" -- which is precisely the terminal this
  clause releases.

SO THE TERMINAL-DIAGNOSTIC FIELD IS LEFT EMPTY, DELIBERATELY. Populating both
from the one recorded text would widen every terminal-sourced signature onto a
channel it was not measured on, which is the structural half of the contract's
"never an arbitrary exec-output tail" rule turned off. The consequence is
worth stating plainly rather than discovering later: a signature declared for
`process.terminal_diagnostic` -- the built-in `model_unsupported` and
`model_not_found` mappings among them -- cannot match through THIS reading,
and keeps its existing route. That is the conservative direction, and a
repository needing those causes released from a terminal declares them for
`protocol.message`, which is the channel the record actually carries.

RELEASE IS A DISJUNCTION OF TWO ARMS, NOT ONE LADDER. An eligible
classification releases AND mints a typed hold. A failure carrying the typed
provider-usage-limit flag releases on that alone and mints NO typed hold,
because the clause keeps "a typed provider-limit failure from an identity-less
legacy adapter" releasing "without inventing a candidate identity" -- there is
no entitlement a typed record could be scoped by, and the existing legacy
provider observation is what covers it. Only a failure that is neither keeps
its existing route, including the `blocked / needs-human` rest
`SPECIFICATION/contracts.md` gives a run that never awaits a human.

The legacy arm is reached for an identity-FUL candidate too, whenever its
declared signatures did not match. That is deliberate: a typed flag is a
provider ceiling the cause-text classification already recognised, so the item
must not sit on a human for want of a signature somebody had not declared
yet -- and taking the legacy arm there mints no hold, so nothing is asserted
about an entitlement that was not measured.
"""

from __future__ import annotations

from dataclasses import dataclass

from livespec_orchestrator_beads_fabro.commands._acp_dispatch_coverage import RenderedCandidate
from livespec_orchestrator_beads_fabro.commands._acp_failure_classifier import (
    AcpAvailabilityFailure,
    classify_acp_failure,
)
from livespec_orchestrator_beads_fabro.commands._acp_failure_signals import AcpFailureSignal
from livespec_orchestrator_beads_fabro.commands._fabro_port_records import FabroFailureDetail

__all__: list[str] = [
    "UNNAMED_FAILURE_IDENTITY",
    "ProviderLimitRelease",
    "classified_release",
    "provider_limit_signal",
]

# What a non-eligible verdict terminates WITH when the engine recorded no
# signature for the failure. The contract's "MUST terminate with their original
# identity" needs a name to carry, and inventing a provider cause nobody
# measured is the one thing that arm exists to prevent.
UNNAMED_FAILURE_IDENTITY = "unnamed-acp-failure"


@dataclass(frozen=True, kw_only=True)
class ProviderLimitRelease:
    """One terminal's release: the attempt it is keyed by, and what it observed.

    `matched` is the typed verdict on the eligible arm and `None` on the legacy
    posture, and the two are NOT interchangeable: a release carrying a verdict
    mints a scoped hold, while one carrying none mints no typed record at all.
    `legacy_provider` is the mirror -- the vendor the cause-text classification
    attributed -- and is `None` on the eligible arm, where the hold key is the
    entitlement the run actually recorded.

    `recovery_source` is the clause's "preserved-work reference the release
    observed (the published head or preservation ref) or its confirmed
    absence". It is a REQUIRED field rather than a defaulted one for the reason
    every record in this tree states its own nulls: an omitted reference is
    what a record from a build predating the clause looks like, so a reader
    could not tell "no preserved work was found" from "nobody looked".
    """

    factory: str
    run_id: str | None
    node_attempt: str
    matched: AcpAvailabilityFailure | None
    legacy_provider: str | None
    recovery_source: str

    @property
    def release_key(self) -> str:
        """The `factory:run:node attempt` triple replay is keyed on.

        The clause makes each release "idempotent and replayable by
        reconciliation, keyed by resolved factory, run, and failing node
        attempt", so the key is built once here rather than re-joined by each
        surface that has to compare two releases.
        """
        return f"{self.factory}:{self.run_id}:{self.node_attempt}"


def provider_limit_signal(*, failure: FabroFailureDetail) -> AcpFailureSignal:
    """The classifier's reading of one recorded failure.

    THREE FIELDS ARE LEFT EMPTY BECAUSE THE RECORD CARRIES NO SUCH EVIDENCE,
    and each absence is honest rather than conservative padding.
    `FabroFailureDetail` holds one text channel, so there is no separately
    captured terminal diagnostic and no structured machine code to report; and
    `turn_started` keeps its `False` default because the record says nothing
    about whether a turn began. That last one costs nothing: the pre-turn guard
    fires only when NO readable field carries text, so a failure whose cause
    the engine recorded is still graded on its own sentence.

    The identity is the engine's recorded SIGNATURE and never its cause text.
    The signature is the failure's name (`implement|transient_infra|acp turn
    failed`); the cause is its message, and terminating a non-eligible failure
    with a provider's sentence in place of its identity is what the contract's
    original-identity rule forbids.
    """
    return AcpFailureSignal(
        original_identity=failure.signature or UNNAMED_FAILURE_IDENTITY,
        protocol_message=failure.cause,
    )


def classified_release(
    *,
    failure: FabroFailureDetail,
    rendered: RenderedCandidate | None,
    node_attempt: str,
    factory: str,
    run_id: str | None,
    recovery_source: str,
) -> ProviderLimitRelease | None:
    """The release this terminal owes, or `None` to leave its route unchanged.

    `rendered` is the candidate the failing node ACTUALLY ran, carrying both
    the signatures that classify it and the provenance flag `effective_
    signatures` reads. `None` means no entitlement was recorded for that node,
    which is the identity-less legacy posture rather than a failure to measure.
    """
    matched = _eligible(failure=failure, rendered=rendered)
    if matched is not None:
        return _release(
            matched=matched,
            legacy_provider=None,
            node_attempt=node_attempt,
            factory=factory,
            run_id=run_id,
            recovery_source=recovery_source,
        )
    if failure.provider_usage_limit:
        return _release(
            matched=None,
            legacy_provider=failure.provider_usage_limit_provider,
            node_attempt=node_attempt,
            factory=factory,
            run_id=run_id,
            recovery_source=recovery_source,
        )
    return None


def _release(
    *,
    matched: AcpAvailabilityFailure | None,
    legacy_provider: str | None,
    node_attempt: str,
    factory: str,
    run_id: str | None,
    recovery_source: str,
) -> ProviderLimitRelease:
    """One release value, assembled once for both arms."""
    return ProviderLimitRelease(
        factory=factory,
        run_id=run_id,
        node_attempt=node_attempt,
        matched=matched,
        legacy_provider=legacy_provider,
        recovery_source=recovery_source,
    )


def _eligible(
    *, failure: FabroFailureDetail, rendered: RenderedCandidate | None
) -> AcpAvailabilityFailure | None:
    """This attempt's eligible availability verdict, or `None` for every other.

    Every non-eligible verdict collapses to `None` because this decision owes
    them all the same treatment -- the failure keeps its existing route -- and
    `AcpNonEligibleFailure` already carries the reason for a surface that needs
    to report it.
    """
    if rendered is None:
        return None
    verdict = classify_acp_failure(
        signal=provider_limit_signal(failure=failure),
        candidate=rendered.candidate,
        builtin=rendered.builtin,
    )
    if isinstance(verdict, AcpAvailabilityFailure):
        return verdict
    return None
