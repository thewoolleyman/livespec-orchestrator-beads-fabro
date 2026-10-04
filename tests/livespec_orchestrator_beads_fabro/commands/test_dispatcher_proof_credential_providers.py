"""The provider management interface a declared proof credential is minted through.

Covers the minting half of `SPECIFICATION/contracts.md`'s
proof-credential-projection clause (ratified v114): where the provider offers a
management interface that can mint a scoped, expiring credential, the Dispatcher
SHOULD mint one per run and revoke it afterwards rather than copy the host's
credential.

EVERY CASE HERE RUNS AGAINST A HERMETIC PROVIDER DOUBLE, registered into the
production registry exactly as a real adapter would be. That is deliberate and
it is also the only honest option: this build ships no provider adapter, so a
case that reached for a real provider would need a credential and a network, and
would measure the vendor rather than the Dispatcher. The empty production
registry is asserted directly below, so the double's registration is visible as
a substitution rather than as a coincidence.

The module under test is imported through `importlib` inside each test body
rather than at module top, so the first Red of a new-module slice fails on a
genuine assertion about the module's absence instead of dying at collection.
"""

from __future__ import annotations

import importlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from types import ModuleType
from typing import Any, cast

import livespec_orchestrator_beads_fabro.commands._acp_candidate_secrets as _commands_anchor
import pytest

_MODULE_NAME = "livespec_orchestrator_beads_fabro.commands._dispatcher_proof_credential_providers"
# Resolved off an existing sibling's own location, so the path is correct from
# any working directory the suite is invoked from.
_MODULE_PATH = Path(_commands_anchor.__file__).parent / (
    "_dispatcher_proof_credential_providers.py"
)

_NAME = "ACME_STATUS_READER"
_VALUE = "acme-minted-value"
_HANDLE = "acme-credential-7"
_DISPATCH_ID = "01DISPATCHMINT"
_READ_ONLY = "read_only"


def _module() -> ModuleType:
    """The module under test, asserting it exists before importing it."""
    assert _MODULE_PATH.is_file(), f"{_MODULE_PATH} does not exist yet"
    return importlib.import_module(_MODULE_NAME)


@dataclass(kw_only=True)
class _Journal:
    """A recording stand-in for `JournalFile`, offering only the `append` seam."""

    records: list[dict[str, object]] = field(default_factory=list)

    def append(self, *, record: dict[str, object]) -> None:
        self.records.append(record)


@dataclass(kw_only=True)
class _ProviderDouble:
    """A hermetic provider management interface: mints on demand, records every call.

    `mint_refusal`, `minted_capability`, `minted_name` and `revoke_refusal` are
    the four knobs the cases below turn. Each one models a way a REAL management
    interface can answer that the Dispatcher has to grade rather than trust: a
    refused mint, a credential granted wider than it was asked for, one issued
    under a different name, and a revoke the provider declines.
    """

    mint_refusal: str | None = None
    minted_capability: str | None = None
    minted_name: str | None = None
    revoke_refusal: str | None = None
    minted_type: Any = None
    mint_calls: list[tuple[str, str, str]] = field(default_factory=list)
    revoked_handles: list[str] = field(default_factory=list)

    def mint(self, *, name: str, capability: str, dispatch_id: str) -> Any:
        self.mint_calls.append((name, capability, dispatch_id))
        if self.mint_refusal is not None:
            return self.mint_refusal
        return self.minted_type(
            name=self.minted_name if self.minted_name is not None else name,
            capability=(
                self.minted_capability if self.minted_capability is not None else capability
            ),
            value=_VALUE,
            revocation_handle=_HANDLE,
        )

    def revoke(self, *, minted: Any) -> str | None:
        self.revoked_handles.append(cast("str", minted.revocation_handle))
        return self.revoke_refusal


def _double(
    *,
    module: ModuleType,
    mint_refusal: str | None = None,
    minted_capability: str | None = None,
    minted_name: str | None = None,
    revoke_refusal: str | None = None,
) -> _ProviderDouble:
    """A provider double already bound to the module's own minted-credential type."""
    return _ProviderDouble(
        minted_type=module.MintedProofCredential,
        mint_refusal=mint_refusal,
        minted_capability=minted_capability,
        minted_name=minted_name,
        revoke_refusal=revoke_refusal,
    )


def _register(
    *, module: ModuleType, monkeypatch: pytest.MonkeyPatch, provider: object, name: str = _NAME
) -> None:
    """Register one provider under `name`, exactly as a shipped adapter would be."""
    monkeypatch.setattr(module, "PROOF_CREDENTIAL_PROVIDERS", {name: provider})


def _minted(*, module: ModuleType, name: str = _NAME) -> Any:
    """One already-minted credential, for the revoke cases."""
    return module.MintedProofCredential(
        name=name, capability=_READ_ONLY, value=_VALUE, revocation_handle=_HANDLE
    )


def test_the_production_registry_ships_no_provider_adapter() -> None:
    """The registry is EMPTY in this build, and saying so out loud is the point.

    The clause is a SHOULD conditioned on the provider offering a management
    interface, and no adapter ships here — so every other case in this module
    substitutes a double into this mapping. Without this assertion, a reader
    could take those cases as evidence that some declaration in some governed
    repository is minted today, which is exactly what is not yet true.
    """
    module = _module()

    assert module.PROOF_CREDENTIAL_PROVIDERS == {}


def test_a_name_no_provider_manages_resolves_no_management_interface() -> None:
    """The ordinary posture: a declared name whose provider offers nothing to call."""
    module = _module()

    assert module.provider_for(name=_NAME) is None


def test_a_registered_name_resolves_its_management_interface(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The control for the case above: resolution is by name, off the registry."""
    module = _module()
    provider = _double(module=module)
    _register(module=module, monkeypatch=monkeypatch, provider=provider)

    assert module.provider_for(name=_NAME) is provider
    assert module.provider_for(name="ACME_METRICS_READER") is None


def test_a_mint_issues_one_run_scoped_credential_carrying_the_declared_capability() -> None:
    """The positive path: the provider is asked for this run's credential by name.

    The DISPATCH ID is asserted to reach the provider, because "one per run" is
    the clause's own requirement and a mint that ignored it would be
    indistinguishable from a long-lived credential fetched once.
    """
    module = _module()
    provider = _double(module=module)

    issued = module.mint_from_provider(
        provider=provider, name=_NAME, capability=_READ_ONLY, dispatch_id=_DISPATCH_ID
    )

    assert provider.mint_calls == [(_NAME, _READ_ONLY, _DISPATCH_ID)]
    assert (issued.name, issued.capability, issued.value, issued.revocation_handle) == (
        _NAME,
        _READ_ONLY,
        _VALUE,
        _HANDLE,
    )


def test_a_provider_that_mints_nothing_is_reported_as_the_reason_it_gave() -> None:
    """A refused mint is data, not an exception: the dispatch reports it as a precondition."""
    module = _module()
    provider = _double(module=module, mint_refusal="the management API rejected the request")

    reason = module.mint_from_provider(
        provider=provider, name=_NAME, capability=_READ_ONLY, dispatch_id=_DISPATCH_ID
    )

    assert isinstance(reason, str)
    assert "the management API rejected the request" in reason


def test_a_credential_minted_wider_than_its_declaration_is_refused() -> None:
    """The OBSERVED grant is graded against the DECLARED capability, not trusted.

    `SPECIFICATION/constraints.md`'s factory-sandbox-credential rules say the
    capability rule is judged against the declared value AND the observed
    grant, and that a credential observed holding more than its declared
    capability is a violation regardless of run outcome. A mint is the
    one moment the Dispatcher can see the grant before the sandbox does, so
    this is where that judgment belongs — and the refusal names both values,
    since naming only one leaves an operator unable to tell which side moved.
    """
    module = _module()
    provider = _double(module=module, minted_capability="read_write")

    reason = module.mint_from_provider(
        provider=provider, name=_NAME, capability=_READ_ONLY, dispatch_id=_DISPATCH_ID
    )

    assert isinstance(reason, str)
    assert "read_write" in reason
    assert _READ_ONLY in reason


def test_a_credential_minted_under_another_name_is_refused() -> None:
    """The same grade's other half: a re-keyed mint would project under the wrong name.

    Paired with the capability case because one tuple comparison decides both,
    and a grade wired to only the capability would let a provider substitute a
    credential for a name the repository never declared — which reaches the
    sandbox as a perfectly well-formed overlay line.
    """
    module = _module()
    provider = _double(module=module, minted_name="ACME_DEPLOY_RUNNER")

    reason = module.mint_from_provider(
        provider=provider, name=_NAME, capability=_READ_ONLY, dispatch_id=_DISPATCH_ID
    )

    assert isinstance(reason, str)
    assert "ACME_DEPLOY_RUNNER" in reason
    assert _NAME in reason


def test_the_lease_projects_each_minted_value_under_its_declared_name() -> None:
    """The lease is what carries a minted value to the overlay, keyed by name."""
    module = _module()
    lease = module.ProofCredentialLease(
        minted=(
            _minted(module=module),
            module.MintedProofCredential(
                name="ACME_METRICS_READER",
                capability=_READ_ONLY,
                value="metrics-minted-value",
                revocation_handle="acme-credential-8",
            ),
        )
    )

    assert lease.overlay_values() == {
        _NAME: _VALUE,
        "ACME_METRICS_READER": "metrics-minted-value",
    }


def test_an_empty_lease_projects_nothing() -> None:
    """A repository with no provider-backed declaration leases nothing to project."""
    module = _module()

    assert module.ProofCredentialLease(minted=()).overlay_values() == {}


def test_revoking_a_lease_calls_the_provider_and_journals_the_credential_by_name(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The clause's second half: the run's credential is revoked once the run ends.

    Asserted on BOTH instruments, because each alone is satisfiable without the
    other. The provider's recorded handle says the revoke really reached the
    management interface; the journal record is what makes "revoked after the
    run ends" readable afterwards by an operator who was not watching.
    """
    module = _module()
    provider = _double(module=module)
    _register(module=module, monkeypatch=monkeypatch, provider=provider)
    journal = _Journal()

    failures = module.revoke_proof_credential_lease(
        lease=module.ProofCredentialLease(minted=(_minted(module=module),)),
        journal=journal,
        work_item_id="bd-ib-first",
    )

    assert failures == ()
    assert provider.revoked_handles == [_HANDLE]
    assert journal.records == [
        {
            "stage": module.PROOF_CREDENTIAL_REVOKE_STAGE,
            "work_item_id": "bd-ib-first",
            "name": _NAME,
            "revoked": True,
        }
    ]


def test_the_revoke_record_carries_the_name_and_never_the_minted_value(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A journal is durable, and the clause requires records to carry names, never values.

    The record deliberately carries NO free-text detail either. A provider's own
    failure prose is text this repository does not control, so journaling it
    would make the clause's guarantee depend on a third party's error strings;
    the reason is returned to the caller instead.
    """
    module = _module()
    provider = _double(module=module, revoke_refusal=f"token {_VALUE} already gone")
    _register(module=module, monkeypatch=monkeypatch, provider=provider)
    journal = _Journal()

    failures = module.revoke_proof_credential_lease(
        lease=module.ProofCredentialLease(minted=(_minted(module=module),)), journal=journal
    )

    assert _VALUE in failures[0]
    assert _VALUE not in json.dumps(journal.records)
    assert _HANDLE not in json.dumps(journal.records)


def test_a_revoke_the_provider_declines_is_reported_and_journaled_as_unrevoked(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A declined revoke is recorded as a FACT, not raised and not silently dropped.

    This runs as the run's teardown, so raising would replace a completed
    dispatch's outcome with a traceback about a credential that expires on its
    own anyway. `revoked: false` is the durable signal instead.
    """
    module = _module()
    provider = _double(module=module, revoke_refusal="the credential is already revoked")
    _register(module=module, monkeypatch=monkeypatch, provider=provider)
    journal = _Journal()

    failures = module.revoke_proof_credential_lease(
        lease=module.ProofCredentialLease(minted=(_minted(module=module),)), journal=journal
    )

    assert len(failures) == 1
    assert _NAME in failures[0]
    assert "the credential is already revoked" in failures[0]
    assert [record["revoked"] for record in journal.records] == [False]


def test_a_lease_whose_provider_is_no_longer_registered_reports_it_unrevoked() -> None:
    """A minted credential with nothing left to revoke it through is a recorded failure.

    Unreachable on the ordinary path, since the lease is minted from this same
    registry. Asserted anyway because the alternative shape — skip what cannot
    be resolved — would report a clean revoke for a credential that is still
    live at the provider, which is the expensive direction to be wrong in.
    """
    module = _module()
    journal = _Journal()

    failures = module.revoke_proof_credential_lease(
        lease=module.ProofCredentialLease(minted=(_minted(module=module),)), journal=journal
    )

    assert len(failures) == 1
    assert _NAME in failures[0]
    assert [record["revoked"] for record in journal.records] == [False]


def test_revoking_no_lease_revokes_nothing_and_journals_nothing() -> None:
    """The normal posture: a dispatch that minted nothing has nothing to revoke.

    `None` rather than an empty lease is the shape the teardown callback really
    passes when the mint stage was never reached, so the no-op has to live here
    rather than at the call site — a teardown that had to branch first would
    skip the revoke on exactly the paths that failed.
    """
    module = _module()
    journal = _Journal()

    assert module.revoke_proof_credential_lease(lease=None, journal=journal) == ()
    assert journal.records == []


def test_revoking_without_a_journal_still_reaches_the_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The journal is optional, so a caller holding none still revokes."""
    module = _module()
    provider = _double(module=module)
    _register(module=module, monkeypatch=monkeypatch, provider=provider)

    failures = module.revoke_proof_credential_lease(
        lease=module.ProofCredentialLease(minted=(_minted(module=module),))
    )

    assert failures == ()
    assert provider.revoked_handles == [_HANDLE]
