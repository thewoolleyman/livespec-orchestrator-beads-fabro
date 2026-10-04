"""The provider management interface a declared proof credential is minted through.

`SPECIFICATION/contracts.md`'s proof-credential-projection clause (ratified
v114) says that WHERE THE PROVIDER OFFERS A MANAGEMENT INTERFACE that can mint a
scoped, expiring credential, the Dispatcher SHOULD mint one per run and revoke it
afterwards rather than copy the host's credential — and that the dispatch journal
MUST record per declaration whether the projected credential was minted or
copied. This module is the seam that makes the minted side of that possible: what
a management interface is, which declared names have one, what a mint yields, and
what revoking it afterwards does.

THE DECLARATION SHAPE DOES NOT CHANGE, which is what forces the resolution to be
BY NAME. A declaration is `{name, purpose, capability}` and nothing else, so a
repository cannot nominate its own provider adapter, and the Dispatcher cannot
discover one from committed configuration. So the registry below is keyed by the
declared environment-variable name, exactly as the self-provisioned
`MINTED_PER_RUN_CREDENTIALS` table beside it already is: a shipped adapter
declares the names it manages, and every other declared name stays copied.

THE REGISTRY IS EMPTY IN THIS BUILD, and that is a recorded fact rather than an
omission. No provider adapter ships here — the clause names Honeycomb and
Supabase as the kind of provider it has in mind, and an adapter for either needs
a management credential and a network round trip at dispatch time that this
repository does not hold. What ships is the MECHANISM plus its proof against a
hermetic double, so that registering a real adapter is a one-entry change rather
than a design. Do NOT read the empty mapping as "minting is unreachable": the
journal already records `minted` for the installation token the Dispatcher
provisions itself, and this path is what a provider-backed declaration would take
the moment an adapter lands.

NOTHING HERE JOURNALS FREE TEXT. The same clause requires journals and records to
carry names and never values, and a provider's own failure prose is text this
repository does not control. So a revoke record carries the declared name and a
boolean, the reasons are RETURNED to the caller instead, and no record ever
carries a minted value or a revocation handle.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Protocol

__all__: list[str] = [
    "PROOF_CREDENTIAL_PROVIDERS",
    "PROOF_CREDENTIAL_REVOKE_STAGE",
    "MintedProofCredential",
    "ProofCredentialLease",
    "ProofCredentialProvider",
    "mint_from_provider",
    "provider_for",
    "revoke_proof_credential_lease",
]

# The dispatch-journal stage the per-credential revoke record is written under.
# Distinct from the projection stage so a reader can ask "was this run's minted
# credential revoked" without re-deriving it from the projection record.
PROOF_CREDENTIAL_REVOKE_STAGE = "proof-credential-revoke"


@dataclass(frozen=True, kw_only=True)
class MintedProofCredential:
    """One run-scoped credential a provider's management interface issued.

    THIS TYPE CARRIES A VALUE, and the asymmetry with the `ProofCredential`
    DECLARATION it is minted for is deliberate rather than an oversight. A
    declaration is committed data, so it carries names only and there is no shape
    in which a secret can ride alongside it. A mint is the opposite: the value
    exists only for the life of one run, arrives from the provider rather than
    from a file, and has to reach the run-configuration overlay somehow.

    What keeps the discipline is everything around it. Nothing journals this type
    — the journal record is built from the declaration — and `revocation_handle`
    is what a revoke needs, so no caller has a reason to hold the value past the
    overlay write. `capability` is carried because it is the OBSERVED grant,
    which the mint grade below checks against what the repository declared.
    """

    name: str
    capability: str
    value: str
    revocation_handle: str


class ProofCredentialProvider(Protocol):
    """A provider's management interface: mint a scoped expiring credential, revoke it.

    Both verbs route an expected failure as DATA rather than raising. A provider
    is a network service, so "it said no" is an ordinary outcome on both sides,
    and the two callers need it as a value: a failed mint becomes a pre-dispatch
    precondition the dispatch reports before any run exists, and a failed revoke
    becomes a journaled fact about a run that has already finished.

    The declaration's `purpose` prose is deliberately NOT passed. It exists for
    the operator reading the committed configuration; a management interface has
    no use for it, and handing it over would make free-text the repository wrote
    part of what reaches a third-party service.
    """

    def mint(self, *, name: str, capability: str, dispatch_id: str) -> MintedProofCredential | str:
        """This run's credential for `name`, or the reason none could be minted."""
        ...

    def revoke(self, *, minted: MintedProofCredential) -> str | None:
        """None once the credential is revoked, else the reason it was not."""
        ...


# The declared names whose provider exposes a management interface, mapped to the
# adapter that drives it. EMPTY in this build — see the module docstring for why,
# and do not treat that emptiness as a reason to drop the path.
PROOF_CREDENTIAL_PROVIDERS: Mapping[str, ProofCredentialProvider] = {}


@dataclass(frozen=True, kw_only=True)
class ProofCredentialLease:
    """Everything one dispatch minted, and therefore everything it must revoke.

    Run-scoped by construction: the lease is created before the overlay is
    written and discharged when the run returns, so it is the only thing that
    knows both which values to project and which credentials are still live at
    the provider. It deliberately holds no provider references — the revoke
    re-resolves each one through the registry — so that a lease is a plain value
    that cannot outlive a registry change silently.
    """

    minted: tuple[MintedProofCredential, ...]

    def overlay_values(self) -> dict[str, str]:
        """Each minted value, keyed by the name its declaration projects it under."""
        return {credential.name: credential.value for credential in self.minted}


def provider_for(*, name: str) -> ProofCredentialProvider | None:
    """The management interface for one declared name, or None when it has none.

    A function rather than a direct mapping read, because every caller asks the
    same question and the answer governs three separate decisions — whether the
    journal says minted, whether the absent-value grade applies, and whether the
    overlay line comes from the lease or from the host environment. Resolving it
    one way keeps those three from drifting apart.
    """
    return PROOF_CREDENTIAL_PROVIDERS.get(name)


def mint_from_provider(
    *,
    provider: ProofCredentialProvider,
    name: str,
    capability: str,
    dispatch_id: str,
) -> MintedProofCredential | str:
    """One per-run mint, GRADED against what the repository declared.

    The grade is the point of this wrapper, and it exists because a management
    interface is a third party. `SPECIFICATION/constraints.md`'s
    factory-sandbox-credential rules judge the capability rule against the
    declared value AND the observed grant, and say a credential observed holding
    more than its declared capability is a violation regardless of run outcome.
    The mint is the one moment the Dispatcher can see the grant BEFORE the
    sandbox does, so refusing here is the only place that judgment can be cheap.

    Name and capability are graded TOGETHER because a re-keyed mint is the same
    class of fault as an over-granted one: it would reach the sandbox as a
    perfectly well-formed overlay line projecting a credential under a name the
    repository never declared. The refusal names both the observed pair and the
    declared one, since naming one side leaves an operator unable to tell which
    moved.

    The returned reason carries no `dispatcher.proof_credentials` prefix on
    purpose: the declaration-aware caller owns that prose, and this module
    deliberately does not know how the key is spelled.
    """
    minted = provider.mint(name=name, capability=capability, dispatch_id=dispatch_id)
    if isinstance(minted, str):
        return f"its provider's management interface minted nothing ({minted})"
    if (minted.name, minted.capability) != (name, capability):
        return (
            f"its provider minted {minted.name!r} holding capability "
            f"{minted.capability!r}, which is not the declared {name!r} at "
            f"{capability!r}; a proof credential may only observe the named "
            "service, and a grant wider than the declaration is a violation "
            "regardless of what the run goes on to do"
        )
    return minted


def revoke_proof_credential_lease(
    *,
    lease: ProofCredentialLease | None,
    journal: object = None,
    work_item_id: str | None = None,
) -> tuple[str, ...]:
    """Revoke everything this run minted, journal each by name, report the failures.

    NEVER RAISES, and that is the load-bearing property rather than defensive
    habit. This runs as the run's teardown, after the dispatch outcome is already
    decided, so an exception here would replace a completed dispatch's result
    with a traceback about a credential that expires on its own anyway. A failure
    is reported as data and recorded as `revoked: false`.

    `None` revokes nothing and is the shape the teardown really passes whenever
    the mint stage was never reached. The no-op lives HERE rather than at the call
    site deliberately: a teardown that had to test the lease first would be a
    teardown that could be skipped, and the paths most likely to skip it are the
    ones that failed partway through.

    `journal` is reached through its own `append`, matching the sibling
    projection gate, so the same function serves a hermetic caller holding no
    journal and the dispatch path holding one.
    """
    if lease is None:
        return ()
    failures: list[str] = []
    for credential in lease.minted:
        reason = _revoke_one(credential=credential)
        if reason is not None:
            failures.append(reason)
        _journal_revocation(
            journal=journal,
            credential=credential,
            work_item_id=work_item_id,
            revoked=reason is None,
        )
    return tuple(failures)


def _revoke_one(*, credential: MintedProofCredential) -> str | None:
    """Revoke one minted credential, or the reason it is still live at the provider.

    A credential whose provider is NO LONGER REGISTERED is reported as a failure
    rather than skipped. That arm is unreachable on the ordinary path, since the
    lease was minted from this same registry — but the opposite shape, treating
    an unresolvable provider as nothing to do, would report a clean revoke for a
    credential that is still live, which is the expensive direction to be wrong
    in.
    """
    provider = provider_for(name=credential.name)
    if provider is None:
        return (
            f"{credential.name} was minted for this run but no provider management "
            "interface is registered for it now, so it could not be revoked and "
            "will stay live until it expires on its own"
        )
    reason = provider.revoke(minted=credential)
    if reason is None:
        return None
    return (
        f"{credential.name} was not revoked by its provider's management interface " f"({reason})"
    )


def _journal_revocation(
    *,
    journal: object,
    credential: MintedProofCredential,
    work_item_id: str | None,
    revoked: bool,
) -> None:
    """Record that one minted credential was or was not revoked, by NAME ONLY.

    No value, no revocation handle, and no free-text detail: the clause requires
    records to carry names and never values, and a provider's own failure prose
    is text this repository does not control, so journaling it would make that
    guarantee depend on a third party's error strings.
    """
    append = getattr(journal, "append", None)
    if append is None:
        return
    append(
        record={
            "stage": PROOF_CREDENTIAL_REVOKE_STAGE,
            "work_item_id": work_item_id,
            "name": credential.name,
            "revoked": revoked,
        }
    )
