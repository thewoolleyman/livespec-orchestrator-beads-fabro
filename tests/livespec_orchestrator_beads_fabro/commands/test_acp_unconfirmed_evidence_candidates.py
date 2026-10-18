"""An unobserved candidate is never treated as confirmed unheld.

Binds `SPECIFICATION/contracts.md` section "Factory-configurable ACP fallback
priority": "An unreadable or incomplete evidence source is unavailable, not an
empty hold set. ... It MAY continue with candidates whose availability evidence
is independently complete; it MUST NOT treat an unobserved candidate as
confirmed unheld." Scenario 127's "An unreadable availability source never
becomes an empty hold set" grades it.

THE TWO HALVES OF THE CLAUSE ARE ASSERTED AGAINST EACH OTHER, because each half
alone is satisfiable by an implementation that ignores the other. One that
skipped EVERY candidate whenever any source was unreadable satisfies the
not-confirmed-unheld half and wedges every dispatch in the fleet the moment a
factory is unreachable; one that skipped NONE satisfies the
independently-complete half and is the behaviour the clause forbids. So the
positive case and the control sit on ONE chain whose two candidates name
different entitlements, and only the one the unread source could have held is
skipped.

THE SKIP CARRIES NO TYPED CAUSE, and that is asserted rather than assumed. The
clause's neighbouring sentence forbids a refusal with no governing hold from
inventing "a hold identity or expiry", and an evidence source that could not be
read supplies neither -- so a skip filling `cause`, `scope` or `hold_key` from
anywhere would read, at the journal, exactly like an observed provider outage.

THE ORDER AGAINST THE OTHER FILTERS IS ASSERTED IN BOTH DIRECTIONS. A live typed
hold outranks it, because a record that was READ says more than one that could
not be; and it outranks the credential probe, because a candidate whose
availability is unknown must not cost a provider round trip to find out
something else. The probe case counts the keys the probe was ASKED about, which
is the only way to tell "assessed and overridden" from "never assessed".
"""

from __future__ import annotations

import importlib
from typing import Any

_PACKAGE = "livespec_orchestrator_beads_fabro.commands"

_DOMAIN = "availability-domain"

# The pool a candidate routes through, declared as a domain-signature
# `hold_key` override. It is deliberately NOT either candidate's own
# `availability_key`, so a reader that consulted only the availability key
# cannot pass the override case.
_SHARED_POOL = "shared-pool"


def _module(*, name: str) -> Any:
    return importlib.import_module(f"{_PACKAGE}.{name}")


def _candidate(*, availability_key: str | None, candidate_key: str, pool: bool = False) -> Any:
    """One candidate, optionally routing through the shared pool above."""
    schema = _module(name="_acp_candidate_schema")
    signatures = _module(name="_acp_candidate_signatures")
    adapters = _module(name="_acp_node_adapters")
    identity = (
        None
        if availability_key is None
        else schema.AcpCandidateIdentity(
            display_name=candidate_key,
            candidate_key=candidate_key,
            availability_key=availability_key,
        )
    )
    declared = (
        (
            signatures.AcpAvailabilitySignature(
                source="process.terminal_diagnostic",
                cause="quota",
                scope=_DOMAIN,
                all_literals=("usage limit",),
                hold_key=_SHARED_POOL,
            ),
        )
        if pool
        else ()
    )
    return schema.AcpCandidate(
        adapter=adapters.AcpAdapter(command=f"adapter-{candidate_key}", env={}, args=()),
        identity=identity,
        signatures=declared,
    )


def _chain(*, primary: Any, fallbacks: tuple[Any, ...] = ()) -> Any:
    """One resolved `implement` chain in configured order."""
    return _module(name="_acp_chain_resolution").ResolvedAcpChain(
        node="implement",
        primary=primary,
        fallbacks=fallbacks,
        enabled=True,
        primary_generation="gen-1",
        full_chain="chain-1",
        redacted={},
    )


def _hold(*, hold_key: str) -> Any:
    """One live typed domain record, as the ledger fold yields it."""
    return _module(name="_acp_hold_records").AcpAvailabilityHold(
        schema_version=1,
        observation_id="acpobs-observed",
        scope=_DOMAIN,
        hold_key=hold_key,
        candidate_key=None,
        cause="quota",
        occurred_at="2026-10-16T11:50:00Z",
        expires_at="2026-10-16T12:05:00Z",
    )


def _filtered(*, chain: Any, inputs: Any) -> Any:
    """This node's surviving candidates and the skips that removed the rest."""
    return _module(name="_acp_candidate_preflight").filter_node_candidates(
        chain=chain, inputs=inputs, assessed={}
    )


def _keys(*, node: Any) -> list[str | None]:
    """The surviving candidates' keys, in configured order."""
    return [
        None if candidate.identity is None else candidate.identity.candidate_key
        for candidate in node.candidates
    ]


def _two_candidate_chain() -> Any:
    """A primary on `codex` and a fallback on `anthropic`, in that order."""
    return _chain(
        primary=_candidate(availability_key="codex", candidate_key="primary"),
        fallbacks=(_candidate(availability_key="anthropic", candidate_key="fallback"),),
    )


def test_a_candidate_whose_evidence_source_is_unavailable_is_not_confirmed_unheld() -> None:
    """Both halves of the clause, on one chain, from one unread source.

    The unread source could have held `codex`, so the primary is NOT selectable
    this evaluation; it says nothing about `anthropic`, whose evidence is
    independently complete, so the fallback still is.
    """
    preflight = _module(name="_acp_candidate_preflight")
    assert hasattr(
        preflight.PreflightInputs, "unconfirmed_keys"
    ), "the candidate filter receives no unobservable-evidence input yet"
    assert hasattr(
        preflight, "UNAVAILABLE_EVIDENCE_SKIP"
    ), "there is no skip reason for an unavailable evidence source yet"

    node = _filtered(
        chain=_two_candidate_chain(),
        inputs=preflight.PreflightInputs(unconfirmed_keys=frozenset({"codex"})),
    )

    assert _keys(node=node) == ["fallback"]
    assert [skip.candidate_key for skip in node.skipped] == ["primary"]
    skip = node.skipped[0]
    assert skip.reason == preflight.UNAVAILABLE_EVIDENCE_SKIP
    # "It MUST NOT invent a hold identity or expiry": a source that could not be
    # read supplies no typed availability cause to record.
    assert (skip.cause, skip.scope, skip.hold_key) == (None, None, None)
    assert skip.condition is None
    assert skip.headroom is None


def test_no_unavailable_source_leaves_every_candidate_selectable() -> None:
    """The control: a complete read must change nothing about any candidate.

    Without it, a filter that skipped every identified candidate outright would
    satisfy the case above while refusing every dispatch this repository makes.
    """
    preflight = _module(name="_acp_candidate_preflight")

    node = _filtered(chain=_two_candidate_chain(), inputs=preflight.PreflightInputs())

    assert _keys(node=node) == ["primary", "fallback"]
    assert node.skipped == ()


def test_an_unavailable_source_reaches_a_declared_domain_override_too() -> None:
    """A candidate belongs to its availability key PLUS its declared hold keys.

    The primary's own `availability_key` is `codex` and the unread source could
    only have held the `shared-pool` its domain signature declares, so a filter
    comparing the availability key alone reports this candidate selectable --
    which is the "confirmed unheld" the clause forbids.
    """
    preflight = _module(name="_acp_candidate_preflight")
    chain = _chain(
        primary=_candidate(availability_key="codex", candidate_key="primary", pool=True),
        fallbacks=(_candidate(availability_key="anthropic", candidate_key="fallback"),),
    )

    node = _filtered(
        chain=chain, inputs=preflight.PreflightInputs(unconfirmed_keys=frozenset({_SHARED_POOL}))
    )

    assert _keys(node=node) == ["fallback"]
    assert node.skipped[0].reason == preflight.UNAVAILABLE_EVIDENCE_SKIP


def test_an_identity_less_candidate_is_never_skipped_for_unconfirmed_evidence() -> None:
    """An adapter carrying no identity keeps the conservative legacy posture.

    It belongs to no typed availability domain at all, so no unread typed
    source can be about it -- and skipping it would strand the one adapter
    shape the contract allows to carry no identity.
    """
    preflight = _module(name="_acp_candidate_preflight")
    chain = _chain(primary=_candidate(availability_key=None, candidate_key="legacy"))

    node = _filtered(
        chain=chain, inputs=preflight.PreflightInputs(unconfirmed_keys=frozenset({"codex"}))
    )

    assert node.candidates != ()
    assert node.skipped == ()


def test_a_live_typed_hold_outranks_an_unavailable_source_on_the_same_candidate() -> None:
    """A record that WAS read says more than one that could not be.

    Both conditions cover the primary here. Reporting the unavailable source
    would discard the one fact carrying a bounded expiry and an operator-
    clearable identity, which is what the scheduled reevaluation reads.
    """
    preflight = _module(name="_acp_candidate_preflight")

    node = _filtered(
        chain=_two_candidate_chain(),
        inputs=preflight.PreflightInputs(
            holds=(_hold(hold_key="codex"),), unconfirmed_keys=frozenset({"codex"})
        ),
    )

    assert node.skipped[0].reason == preflight.TYPED_HOLD_SKIP
    assert node.skipped[0].hold_key == "codex"


def test_an_unavailable_source_is_settled_before_any_credential_round_trip() -> None:
    """A candidate whose availability is unknown costs no provider request.

    The probe is asked about `anthropic` alone, so the primary left the
    selectable set WITHOUT one -- which is the claim a reason-only assertion
    cannot make, since a filter that probed first and then overrode its own
    answer reports the identical reason.
    """
    preflight = _module(name="_acp_candidate_preflight")
    asked: list[str] = []

    def probe(key: str) -> str:
        asked.append(key)
        return "exhausted"

    node = _filtered(
        chain=_two_candidate_chain(),
        inputs=preflight.PreflightInputs(probe=probe, unconfirmed_keys=frozenset({"codex"})),
    )

    assert asked == ["anthropic"]
    assert [skip.reason for skip in node.skipped] == [
        preflight.UNAVAILABLE_EVIDENCE_SKIP,
        preflight.PROBE_SKIP,
    ]
    assert node.candidates == ()
