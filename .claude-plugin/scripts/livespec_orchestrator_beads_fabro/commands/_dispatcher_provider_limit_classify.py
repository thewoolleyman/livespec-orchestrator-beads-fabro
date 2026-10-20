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

BUT A NON-ELIGIBLE GUARD CLASS OUTRANKS BOTH ARMS, THE LEGACY ONE INCLUDED.
`SPECIFICATION/contracts.md` keeps those classes "non-eligible before
configured matching" and says in as many words that they "mint no hold, are
not released for re-dispatch, and keep their original identity and their
existing route". The eligible arm already honours that, because
`classify_acp_failure` checks the guard first; the legacy arm did not, and the
gap is not theoretical: `provider_usage_limit` is derived from the cause TEXT,
so a failure whose sentence happens to carry a provider's limit vocabulary
sets the flag whatever the real fault was. A node deadline released that way
returns a run that spent its whole node timeout making genuine progress to
`ready` as though an allowance had been spent, and then re-dispatches it from
scratch -- the one outcome the class exists to prevent.

The guard is read from the failure's OWN sentence rather than from a verdict,
so it applies with no resolved candidate at all. That matters, because the
no-candidate reading is precisely the one that otherwise reaches the legacy
route without any classification being attempted.
"""

from __future__ import annotations

from dataclasses import dataclass

from livespec_orchestrator_beads_fabro.commands._acp_candidate_schema import AcpCandidateIdentity
from livespec_orchestrator_beads_fabro.commands._acp_dispatch_coverage import RenderedCandidate
from livespec_orchestrator_beads_fabro.commands._acp_failure_classifier import (
    AcpAvailabilityFailure,
    classify_acp_failure,
)
from livespec_orchestrator_beads_fabro.commands._acp_failure_signals import (
    AcpFailureSignal,
    non_eligible_reason,
)
from livespec_orchestrator_beads_fabro.commands._fabro_port_records import FabroFailureDetail

__all__: list[str] = [
    "UNNAMED_FAILURE_IDENTITY",
    "ProviderLimitAttempt",
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
class ProviderLimitAttempt:
    """The one failed record or reclassified succeeded turn a terminal grades."""

    signal: AcpFailureSignal
    failure: FabroFailureDetail | None = None


@dataclass(frozen=True, kw_only=True)
class ProviderLimitRelease:
    """One terminal's release: the attempt it is keyed by, and what it observed.

    `matched` is the typed verdict on the eligible arm and `None` on the legacy
    posture, and the two are NOT interchangeable: a release carrying a verdict
    mints a scoped hold, while one carrying none mints no typed record at all.
    `legacy_provider` is the mirror -- the vendor the cause-text classification
    attributed -- and is `None` on the eligible arm, where the hold key is the
    entitlement the run actually recorded.

    `executed` is the entitlement the failing node ACTUALLY ran, and it is kept
    apart from `matched` because the clause asks for both and they disagree by
    design: a quota signature is domain-scoped, so its verdict carries no
    `candidate_key` at all -- the hold parser refuses a domain record that
    names one -- while the release record must still name "the candidate
    identity that failed". Reading that identity off the verdict would report
    every domain release as having run no candidate.

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
    executed: AcpCandidateIdentity | None
    legacy_provider: str | None
    recovery_source: str
    recorded_cause: str | None = None

    @property
    def release_key(self) -> str:
        """The `factory:run:node attempt` triple replay is keyed on.

        The clause makes each release "idempotent and replayable by
        reconciliation, keyed by resolved factory, run, and failing node
        attempt", so the key is built once here rather than re-joined by each
        surface that has to compare two releases.
        """
        return f"{self.factory}:{self.run_id}:{self.node_attempt}"

    @property
    def source(self) -> str | None:
        """The signature source that classified this release, if one did."""
        return None if self.matched is None else self.matched.source


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
    attempt: ProviderLimitAttempt,
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
    failure = attempt.failure
    classified_signal = attempt.signal
    # BEFORE either arm, because the guard classes sit before configured
    # matching and are "not released for re-dispatch" -- see the module
    # docstring for why the legacy arm needs this and the eligible one does not.
    if non_eligible_reason(signal=classified_signal) is not None:
        return None
    matched = _eligible(signal=classified_signal, rendered=rendered)
    legacy_provider: str | None = None
    if matched is None:
        if failure is None or not failure.provider_usage_limit:
            return None
        legacy_provider = failure.provider_usage_limit_provider
    return ProviderLimitRelease(
        factory=factory,
        run_id=run_id,
        node_attempt=node_attempt,
        matched=matched,
        executed=None if rendered is None else rendered.candidate.identity,
        # The two arms are mutually exclusive by construction rather than by a
        # rule: a matched verdict already names the entitlement whose allowance
        # was spent, so reporting a cause-text provider beside it would be two
        # answers about one attempt.
        legacy_provider=legacy_provider,
        recovery_source=recovery_source,
        recorded_cause=(
            classified_signal.turn_final_output
            if classified_signal.turn_final_output is not None
            else None
            if failure is None
            else failure.cause
        ),
    )


def _eligible(
    *, signal: AcpFailureSignal, rendered: RenderedCandidate | None
) -> AcpAvailabilityFailure | None:
    """This attempt's eligible availability verdict, or `None` for every other.

    Every non-eligible verdict collapses to `None` because this decision owes
    them all the same treatment -- the failure keeps its existing route -- and
    `AcpNonEligibleFailure` already carries the reason for a surface that needs
    to report it.

    The signal is handed DOWN rather than rebuilt here, so the guard the caller
    consulted and the classification taken afterwards are two readings of one
    signal rather than of two that happen to agree.
    """
    if rendered is None:
        return None
    verdict = classify_acp_failure(
        signal=signal,
        candidate=rendered.candidate,
        builtin=rendered.builtin,
    )
    if isinstance(verdict, AcpAvailabilityFailure):
        return verdict
    return None
