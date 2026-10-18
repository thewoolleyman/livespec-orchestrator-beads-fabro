"""The terminal-side classification a provider-limit release rests on.

`SPECIFICATION/contracts.md` section "Factory-configurable ACP fallback
priority" → "Provider-limit release and re-dispatch" (work-item
`bd-ib-6itdjz`, Scenario 127). The clause releases a terminated run whose
failing node's recorded failure "classifies under this section's signatures as
an eligible cause", so the Dispatcher needs a reading that turns ONE run
record's failing attempt into the classifier's two inputs.

THE RECORDED CAUSE IS THE ACP PROTOCOL MESSAGE, AND THAT MAPPING IS THE WHOLE
TEST. `_acp_failure_matching` chooses the observed field BY the signature's
`source` and says so in as many words -- "there is no path on which a literal
declared for `protocol.message` can be satisfied by a terminal diagnostic" --
so a reading that put the recorded cause on the wrong field would classify
NOTHING while returning a perfectly well-formed verdict. Measured on this
repository 2026-10-17: the built-in Anthropic session-limit signature matched
the measured sentence on `protocol_message` and returned `unmatched` for the
identical sentence on `terminal_diagnostic`. The negative control below pins
that, because it is the arm a refactor is most likely to "simplify" by
populating both.

The cause text is placed there rather than on the terminal diagnostic because
that is what the engine records: `causes[0]` of a failed ACP stage is the
literal `ACP protocol error` and `causes[-1]` carries the provider's own
sentence (`AGENTS.md`, measured over 17 failure blocks), so the chain names
itself a protocol error. `_acp_builtin_signatures._quota_message` reaches the
same conclusion from the other direction: the message form is "the one that
survives an engine keeping only the failure message text ... and what a run
routed through `needs_human` can be left with", which is exactly this path.

THE TYPED FLAG IS A SECOND, INDEPENDENT ROUTE TO RELEASE. The clause keeps "a
typed provider-limit failure from an identity-less legacy adapter" releasing
"without inventing a candidate identity", and the item's Definition of Done
keeps the existing route only for a failure that classifies as no eligible
cause AND carries no typed flag. So the two arms are a disjunction, and the
legacy arm mints no typed hold -- there is no entitlement for one to be scoped
by.
"""

from __future__ import annotations

import importlib
from pathlib import Path
from typing import Any

from livespec_orchestrator_beads_fabro.commands._acp_candidate_schema import (
    AcpCandidate,
    AcpCandidateIdentity,
)
from livespec_orchestrator_beads_fabro.commands._acp_dispatch_coverage import RenderedCandidate
from livespec_orchestrator_beads_fabro.commands._acp_node_adapters import AcpAdapter
from livespec_orchestrator_beads_fabro.commands._fabro_port_records import FabroFailureDetail

_MODULE = "livespec_orchestrator_beads_fabro.commands._dispatcher_provider_limit_classify"
_SOURCE = (
    Path(__file__).resolve().parents[3]
    / ".claude-plugin"
    / "scripts"
    / "livespec_orchestrator_beads_fabro"
    / "commands"
    / "_dispatcher_provider_limit_classify.py"
)

# MEASURED 2026-10-16 on hp, run 01M52R2WND7Y of `bd-ib-26deyw`: the implement
# node's recorded `causes[-1]`, with `errorKind` `rate_limit`. Four runs ended
# this way in one day and every one rested at `blocked / needs-human`
# (ledger rider on `bd-ib-6itdjz`).
_SESSION_LIMIT = "You have hit your session limit, resets 7:20pm (UTC)"
# MEASURED 2026-10-17 on hp, run 01M54W4YM2SWANMK515YNPFY7J of `bd-ib-6itdjz`:
# the implement attempt's recorded `causes[-1]` after four hours of genuine
# progress -- 360 completed tool calls, 14 git commits, and no 429, overloaded,
# rate-limit, stream-reset or headroom text anywhere in `run.log`. Fabro
# categorised it `transient_infra`, which is the SAME category the session-limit
# cause above carries, so the category cannot tell the two apart.
_TURN_TIMEOUT = (
    "ACP turn timed out after 345 tool call(s) and 3658 session update(s); "
    "last update at 13344311ms"
)
_SIGNATURE = "implement|transient_infra|acp turn failed"

_DECLARED_QUOTA = {
    "source": "protocol.message",
    "cause": "quota",
    "scope": "availability-domain",
    "all_literals": ["hit your session limit"],
}


def _signatures(*, declared: dict[str, object]) -> Any:
    """The declared signature tuple, parsed through the committed grammar.

    Parsed rather than constructed, so the fixture cannot drift from the
    configuration an operator actually writes.
    """
    module = importlib.import_module(
        "livespec_orchestrator_beads_fabro.commands._acp_candidate_signatures"
    )
    parsed = module.parse_availability_signatures(value=[declared], key="probe")
    assert not isinstance(parsed, str), parsed
    return parsed


def _rendered(*, identity: AcpCandidateIdentity | None, declared: dict[str, object] | None) -> Any:
    return RenderedCandidate(
        candidate=AcpCandidate(
            adapter=AcpAdapter(command="claude-code-acp", args=(), env={}),
            identity=identity,
            signatures=() if declared is None else _signatures(declared=declared),
        ),
        builtin=False,
    )


_IDENTITY = AcpCandidateIdentity(
    display_name="Claude ACP primary",
    candidate_key="claude-primary",
    availability_key="anthropic-team",
)


def _failure(*, cause: str | None, usage_limit: bool = False) -> FabroFailureDetail:
    return FabroFailureDetail(
        cause=cause,
        category="transient_infra",
        signature=_SIGNATURE,
        provider_usage_limit=usage_limit,
        provider_usage_limit_provider="anthropic" if usage_limit else None,
    )


def _release(*, failure: FabroFailureDetail, rendered: Any) -> Any:
    module = importlib.import_module(_MODULE)
    return module.classified_release(
        failure=failure,
        rendered=rendered,
        node_attempt="implement",
        factory="hp",
        run_id="01M52R2WND7Y",
        recovery_source="refs/heads/needs-human/01M52R2WND7Y",
    )


def test_the_recorded_cause_is_read_as_the_acp_protocol_message() -> None:
    """The signal puts the engine's cause chain on the field quota signatures name."""
    assert _SOURCE.is_file()
    module = importlib.import_module(_MODULE)

    signal = module.provider_limit_signal(failure=_failure(cause=_SESSION_LIMIT))

    assert signal.protocol_message == _SESSION_LIMIT
    # The negative half, and the one a refactor is most likely to undo: the
    # terminal-diagnostic field stays EMPTY, because duplicating the one
    # recorded text onto both fields would defeat the source-selection
    # invariant `_acp_failure_matching` exists to hold.
    assert signal.terminal_diagnostic is None
    assert signal.machine_code is None
    # The failure terminates with its OWN identity on every non-eligible arm,
    # so the engine's recorded signature is carried rather than replaced.
    assert signal.original_identity == _SIGNATURE


def test_a_declared_quota_signature_releases_on_its_own_scope_and_key() -> None:
    """The measured session-limit sentence classifies eligible and is domain-scoped."""
    assert _SOURCE.is_file()

    release = _release(
        failure=_failure(cause=_SESSION_LIMIT),
        rendered=_rendered(identity=_IDENTITY, declared=_DECLARED_QUOTA),
    )

    assert release is not None
    assert release.matched is not None
    assert release.matched.cause == "quota"
    assert release.matched.scope == "availability-domain"
    # Keyed as the SIGNATURE declares: this one names no `hold_key` override,
    # so the candidate's own availability key is the hold key.
    assert release.matched.hold_key == "anthropic-team"
    assert release.matched.candidate_key is None
    assert release.legacy_provider is None
    # The release is addressed by the factory, run and failing node attempt --
    # the triple the clause keys replay on.
    assert release.release_key == "hp:01M52R2WND7Y:implement"
    assert release.recovery_source == "refs/heads/needs-human/01M52R2WND7Y"


def test_the_same_sentence_without_a_declared_signature_is_not_eligible() -> None:
    """The POSITIVE control's counterpart: nothing matches, so nothing releases.

    Without this the test above proves only that a release can be produced, not
    that the declared signature is what produced it. Measured on this
    repository 2026-10-17: its own structured `acp_nodes` candidates resolve
    `builtin=False` and declare no signatures, so this is the live arm for
    every node it dispatches today.
    """
    assert _SOURCE.is_file()

    assert (
        _release(
            failure=_failure(cause=_SESSION_LIMIT),
            rendered=_rendered(identity=_IDENTITY, declared=None),
        )
        is None
    )


def test_an_identity_less_adapter_releases_on_the_typed_flag_alone() -> None:
    """The conservative legacy posture: released, but minting no typed hold."""
    assert _SOURCE.is_file()

    release = _release(
        failure=_failure(cause=_SESSION_LIMIT, usage_limit=True),
        rendered=_rendered(identity=None, declared=None),
    )

    assert release is not None
    # No entitlement was recorded, so there is none a typed hold could be
    # scoped by -- the clause's "without inventing a candidate identity".
    assert release.matched is None
    assert release.legacy_provider == "anthropic"


def test_a_node_whose_candidate_was_never_resolved_takes_the_same_legacy_arm() -> None:
    """A node with NO rendered candidate is the legacy posture, not an error.

    Distinct from the case above, and the distinction is the caller's: there a
    candidate ran and recorded no identity, here the reading found no candidate
    for the failing node at all -- an absent `acp_nodes` resolution, or a node
    the resolution does not carry. Both leave no entitlement a typed hold could
    be scoped by, so both release on the typed flag alone; passing a
    fabricated candidate to make the shapes match would invent the very
    identity the clause forbids inventing.
    """
    assert _SOURCE.is_file()

    release = _release(failure=_failure(cause=_SESSION_LIMIT, usage_limit=True), rendered=None)

    assert release is not None
    assert release.matched is None
    assert release.legacy_provider == "anthropic"
    # And with no typed flag either, an unresolvable candidate changes no route.
    assert _release(failure=_failure(cause=_SESSION_LIMIT), rendered=None) is None


def test_an_unclassified_failure_carrying_no_typed_flag_keeps_its_route() -> None:
    """Neither arm holds, so the terminal's existing route is left alone."""
    assert _SOURCE.is_file()

    assert (
        _release(
            failure=_failure(cause="the socket connection was closed unexpectedly"),
            rendered=_rendered(identity=_IDENTITY, declared=_DECLARED_QUOTA),
        )
        is None
    )


def test_a_failure_recording_no_cause_at_all_keeps_its_route() -> None:
    """An absent cause is no provider evidence, and names no identity either."""
    assert _SOURCE.is_file()
    module = importlib.import_module(_MODULE)

    signal = module.provider_limit_signal(failure=_failure(cause=None))

    assert signal.protocol_message is None
    assert (
        _release(
            failure=_failure(cause=None),
            rendered=_rendered(identity=_IDENTITY, declared=_DECLARED_QUOTA),
        )
        is None
    )


def test_a_turn_timeout_is_not_released_even_carrying_the_typed_flag() -> None:
    """A non-eligible GUARD verdict outranks the legacy provider-usage-limit arm.

    The two arms above are a disjunction, so the legacy arm releases a failure
    whose declared signatures did not match -- and `unmatched` is exactly where
    an unrecognised cause lands. A node deadline must NOT travel that route:
    `SPECIFICATION/contracts.md` section "Factory-configurable ACP fallback
    priority" puts "node deadline or stall expiry" among the classes that "mint
    no hold, are not released for re-dispatch, and keep their original identity
    and their existing route", and Scenario 127's "Non-eligible failures
    outrank configured text overlap" names `node timeout` in that list.

    The flag is derived from the cause TEXT, so a timeout sentence that happens
    to carry a provider's limit vocabulary sets it -- and releasing on it would
    return a run that spent four hours making genuine progress to `ready` as
    though an allowance had been spent, then re-dispatch it from scratch. The
    guard is read from the failure's own sentence, so it outranks the flag
    whether or not a candidate was resolved for the failing node: both arms are
    asserted, because the identity-less arm is the one that reaches the legacy
    route with no classification at all.

    The POSITIVE CONTROL is `test_an_identity_less_adapter_releases_on_the_
    typed_flag_alone` above, which carries the identical flag on a genuine
    provider sentence and DOES release. Without it this case would also pass
    against a build that had stopped honouring the typed flag entirely.
    """
    assert _SOURCE.is_file()
    timeout = _failure(cause=_TURN_TIMEOUT, usage_limit=True)

    assert _release(failure=timeout, rendered=_rendered(identity=None, declared=None)) is None
    assert _release(failure=timeout, rendered=None) is None
    # And with an identity plus a declared signature whose literal the timeout
    # sentence satisfies, the guard still wins: the class sits BEFORE configured
    # matching, so no declaration can claim it.
    assert (
        _release(
            failure=timeout,
            rendered=_rendered(
                identity=_IDENTITY,
                declared={
                    "source": "protocol.message",
                    "cause": "quota",
                    "scope": "availability-domain",
                    "all_literals": ["timed out"],
                },
            ),
        )
        is None
    )


def test_a_failure_recording_neither_signature_nor_cause_is_named_unnamed() -> None:
    """The identity fallback: a non-eligible verdict still has to name something."""
    assert _SOURCE.is_file()
    module = importlib.import_module(_MODULE)

    signal = module.provider_limit_signal(
        failure=FabroFailureDetail(cause=None, category=None, signature=None)
    )

    assert signal.original_identity == module.UNNAMED_FAILURE_IDENTITY
