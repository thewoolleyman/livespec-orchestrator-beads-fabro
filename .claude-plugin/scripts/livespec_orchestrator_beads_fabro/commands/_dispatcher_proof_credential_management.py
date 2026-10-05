"""The provider management interface a repository declares per proof credential.

`SPECIFICATION/contracts.md`'s proof-credential-projection clause (ratified
v114) says that WHERE THE PROVIDER OFFERS A MANAGEMENT INTERFACE able to mint a
scoped, expiring credential, the Dispatcher SHOULD mint one per run and revoke
it afterwards rather than copy the host's. Nothing in the
`{name, purpose, capability}` declaration can answer whether such an interface
exists — that is a fact about the PROVIDER, not about the credential — so the
repository declares it under its own committed key,
`dispatcher.proof_credential_management`: a mapping from one declared
proof-credential NAME to the argv pair that drives that provider.

    "proof_credential_management": {
      "ACME_STATUS_READER": {
        "mint":   ["/usr/local/bin/acme-admin", "proof-key", "mint"],
        "revoke": ["/usr/local/bin/acme-admin", "proof-key", "revoke"]
      }
    }

WHY A COMMAND PAIR RATHER THAN A PROVIDER TABLE COMPILED INTO THIS BUILD. A
table can mint only for the providers someone has already written a client for,
so every adopter whose provider is absent from it is told a ratified SHOULD does
not apply to them — and the table's own emptiness looks identical to "no
repository declared one". The argv pair inverts that: the Dispatcher owns the
LIFECYCLE (one credential per run, revoked when the run ends) and the repository
owns the PROVIDER CALL, which is the half only the adopter can know. It is the
shape `credential_wrapper` already takes for the same reason.

HOW THE TWO COMMANDS ARE ADDRESSED, AND WHY NEITHER TAKES AN ARGUMENT. Both run
with the declaration's facts in the ENVIRONMENT — the name, the capability it was
declared under, and the per-run SCOPE — rather than as appended argv, so there is
no template grammar to get wrong and nothing run-specific in a command line that
`/proc` publishes to every local user. `mint` prints the minted value on stdout
and nothing else; `revoke` revokes whatever was minted under the scope it is
handed. That scope is the dispatch id: unique per run, already a non-secret
identifier the dispatch carries, and derivable by BOTH legs — which is what lets
revoke run with no state threaded from mint, including after a mint whose
process is long gone.

NO CREDENTIAL-MARKER SCAN RUNS OVER THESE ARGVS, AND THE ABSENCE IS DELIBERATE.
The sibling scan over a declaration's `name` and `purpose` refuses text carrying
`token`, `credential`, `secret` and the rest of that vocabulary. That vocabulary
is this key's DOMAIN: a provider's credential-management CLI is spelled with
exactly those words, so here the scan has no discriminating power and would
refuse the ordinary case — and `_acp_candidate_secrets` names that trade-off
itself ("a scan that refuses ordinary configuration gets switched off"). What
keeps a value out of this key is that no field in it holds one: the mint command
PRINTS the credential, on a channel nothing commits.
"""

from __future__ import annotations

from collections.abc import Collection, Mapping
from dataclasses import dataclass
from typing import cast

__all__: list[str] = [
    "MINT_OPERATION",
    "PROOF_CREDENTIAL_CAPABILITY_ENV",
    "PROOF_CREDENTIAL_MANAGEMENT_KEY",
    "PROOF_CREDENTIAL_NAME_ENV",
    "PROOF_CREDENTIAL_SCOPE_ENV",
    "REVOKE_OPERATION",
    "ProviderManagementInterface",
    "management_environment",
    "parse_provider_management_interfaces",
    "undeclared_management_refusal",
]

PROOF_CREDENTIAL_MANAGEMENT_KEY = "proof_credential_management"
# The committed keys as an operator reads them in `.livespec.jsonc`, so every
# refusal names the thing they have to edit rather than this module's own view.
_DECLARED_KEY = f"dispatcher.{PROOF_CREDENTIAL_MANAGEMENT_KEY}"
_CREDENTIALS_KEY = "dispatcher.proof_credentials"

# The two operations one interface declares. Both are REQUIRED: an interface
# that can mint and not revoke is not a lifecycle, and the missing half's only
# symptom is a credential outliving the run that needed it — which no run
# reports, because every run it affects succeeds.
MINT_OPERATION = "mint"
REVOKE_OPERATION = "revoke"
_OPERATIONS: tuple[str, ...] = (MINT_OPERATION, REVOKE_OPERATION)

# The environment the two commands are addressed through, rather than argv. The
# SCOPE is what makes the pair addressable without shared state: revoke is
# handed the same per-run value mint was, so it can ask the provider to drop
# whatever that run holds.
PROOF_CREDENTIAL_NAME_ENV = "LIVESPEC_PROOF_CREDENTIAL_NAME"
PROOF_CREDENTIAL_CAPABILITY_ENV = "LIVESPEC_PROOF_CREDENTIAL_CAPABILITY"
PROOF_CREDENTIAL_SCOPE_ENV = "LIVESPEC_PROOF_CREDENTIAL_SCOPE"


@dataclass(frozen=True, kw_only=True)
class ProviderManagementInterface:
    """One provider's management interface: the name it manages, and its two argvs.

    Frozen and carrying no value field, for the same reason `ProofCredential`
    is: this is committed data, so there is no shape in which a secret can ride
    alongside the command that produces it.
    """

    name: str
    mint_argv: tuple[str, ...]
    revoke_argv: tuple[str, ...]


def parse_provider_management_interfaces(
    *, block: Mapping[str, object]
) -> dict[str, ProviderManagementInterface] | str:
    """The declared management interfaces by credential name, or the FIRST refusal.

    An ABSENT key parses to the empty mapping rather than to a refusal: every
    repository in this fleet declares none today, and the ratified clause is a
    SHOULD conditioned on the provider offering an interface at all.

    The return is `dict | str` rather than a raised error because every caller
    routes an expected failure as data — the dispatch reports it as a
    pre-dispatch precondition and never as a traceback.
    """
    if PROOF_CREDENTIAL_MANAGEMENT_KEY not in block:
        return {}
    declared = block[PROOF_CREDENTIAL_MANAGEMENT_KEY]
    if not isinstance(declared, dict):
        return (
            f"{_DECLARED_KEY} must be an object mapping one declared "
            f"{_CREDENTIALS_KEY} name to its provider's "
            "{mint, revoke} argv pair; got "
            f"{type(declared).__name__}"
        )
    parsed: dict[str, ProviderManagementInterface] = {}
    for name, entry in cast("dict[str, object]", declared).items():
        resolved = _parse_interface(name=name, entry=entry)
        if isinstance(resolved, str):
            return resolved
        parsed[name] = resolved
    return parsed


def _parse_interface(*, name: str, entry: object) -> ProviderManagementInterface | str:
    """One entry, graded shape-first then one argv per operation."""
    if not isinstance(entry, dict):
        return (
            f"{_DECLARED_KEY}[{name}] must be an object carrying "
            f"{', '.join(_OPERATIONS)} argv lists; got {type(entry).__name__}"
        )
    fields = cast("dict[str, object]", entry)
    argvs: dict[str, tuple[str, ...]] = {}
    for operation in _OPERATIONS:
        resolved = _parse_argv(name=name, operation=operation, value=fields.get(operation))
        if isinstance(resolved, str):
            return resolved
        argvs[operation] = resolved
    return ProviderManagementInterface(
        name=name,
        mint_argv=argvs[MINT_OPERATION],
        revoke_argv=argvs[REVOKE_OPERATION],
    )


def _parse_argv(*, name: str, operation: str, value: object) -> tuple[str, ...] | str:
    """One operation's argv: a non-empty list of non-blank strings, or a refusal.

    Every token reaches a subprocess argv verbatim, so a non-string token and a
    blank one are both unusable there — and a declaration carrying either is a
    fault in committed configuration rather than a value to coerce.
    """
    if not isinstance(value, list) or not value:
        return (
            f"{_DECLARED_KEY}[{name}].{operation} must be a non-empty argv list "
            f"naming the provider command that {operation}s this credential"
        )
    tokens = cast("list[object]", value)
    if any(not isinstance(token, str) or not token.strip() for token in tokens):
        return (
            f"{_DECLARED_KEY}[{name}].{operation} must carry non-blank string "
            "tokens only; every token reaches the provider command's argv verbatim"
        )
    return tuple(cast("list[str]", tokens))


def undeclared_management_refusal(
    *,
    management: Mapping[str, ProviderManagementInterface],
    declared: Collection[str],
) -> str | None:
    """A management entry naming no declared proof credential, or None to proceed.

    THIS IS THE SILENT-WRONG-ANSWER GRADE. An operator who commits a management
    interface believes the Dispatcher is minting per run. When its name matches
    no `dispatcher.proof_credentials` declaration nothing is minted, nothing is
    projected, and the dispatch is otherwise entirely healthy — so the belief is
    never contradicted by anything the run produces.
    """
    for name in management:
        if name not in declared:
            return (
                f"{_DECLARED_KEY}[{name}] declares a provider management "
                f"interface for a credential no {_CREDENTIALS_KEY} entry "
                "declares; nothing would be minted or projected under that "
                "name, so declare the credential or drop the interface"
            )
    return None


def management_environment(*, name: str, capability: str, scope: str) -> dict[str, str]:
    """The environment one mint or revoke command is addressed through.

    The CAPABILITY rides along because the clause asks for a READ-SCOPED
    credential: the provider command is what applies the scope, and it cannot
    apply one it was never told. The declaration's capability is already graded
    against the closed enumeration before this runs, so what arrives here is a
    ratified value rather than free text.
    """
    return {
        PROOF_CREDENTIAL_NAME_ENV: name,
        PROOF_CREDENTIAL_CAPABILITY_ENV: capability,
        PROOF_CREDENTIAL_SCOPE_ENV: scope,
    }
