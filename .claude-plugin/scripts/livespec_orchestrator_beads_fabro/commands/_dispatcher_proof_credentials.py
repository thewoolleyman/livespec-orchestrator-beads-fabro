"""Repository-declared proof credentials: the declaration, and what refuses it.

The PROJECTION this declaration earns — the overlay env lines an admitted
declaration renders — lives in `_dispatcher_proof_credential_projection`, which
reads this module's parse rather than re-deriving one.

`SPECIFICATION/contracts.md`'s proof-credential-projection clause (ratified
v114) lets a governed repository declare the credentials its proof stages need
to exercise the deliverable's backing services from inside the sandbox. The
declaration is committed configuration — `dispatcher.proof_credentials`, a list
of `{name, purpose, capability}` objects — and it carries NAMES ONLY: the values
arrive from the Dispatcher's own environment, as supplied by the target's
configured credential wrapper, and are projected through the existing
run-configuration overlay.

WHY THE PARSE IS A REFUSAL LADDER RATHER THAN A FILTER. Every fault this module
names is a fault in COMMITTED configuration, so there is no "mostly usable"
declaration to salvage: a declaration the Dispatcher silently narrowed would
project a different credential set than the repository wrote, and the operator
would learn that only from a proof stage failing inside a sandbox. So the first
fault refuses the whole declaration, before any run exists.

NO REFUSAL THIS MODULE PRODUCES ECHOES A CREDENTIAL VALUE. A refusal is
journaled, and the same contract requires journals and records to carry names
and never values, so a credential-shaped hit names its POSITION and the marker
that matched — never the text around it. That is the discipline
`_acp_candidate_secrets` already keeps for committed adapter configuration, and
this module reuses that scan rather than growing a second vocabulary.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from livespec_orchestrator_beads_fabro.commands._acp_candidate_secrets import secret_marker
from livespec_orchestrator_beads_fabro.commands._config import dispatcher_block

__all__: list[str] = [
    "COPIED_PROVISIONING",
    "MINTED_PER_RUN_CREDENTIALS",
    "MINTED_PROVISIONING",
    "PROOF_CREDENTIALS_KEY",
    "PROOF_CREDENTIAL_CAPABILITIES",
    "PROOF_CREDENTIAL_JOURNAL_STAGE",
    "READ_ONLY_CAPABILITY",
    "WITHHELD_DISPATCH_CREDENTIALS",
    "ProofCredential",
    "parse_proof_credentials",
    "proof_credential_journal_record",
    "proof_credential_provisioning",
    "proof_credentials_refusal",
    "proof_credentials_refusal_for_items",
]

PROOF_CREDENTIALS_KEY = "proof_credentials"
# The committed key as an operator reads it in `.livespec.jsonc`, so every
# refusal names the thing they have to edit rather than this module's own view.
_DECLARED_KEY = f"dispatcher.{PROOF_CREDENTIALS_KEY}"

# The closed capability enumeration. `read_only` is its only member today and
# means the credential can observe the named service and cannot create, modify,
# delete, or spend. The enumeration MAY gain values by ratification, and its
# values are SELF-DESCRIBING names — never tiers or levels — so a dispatch-time
# refusal tells an adopter what they declared rather than a number.
READ_ONLY_CAPABILITY = "read_only"
PROOF_CREDENTIAL_CAPABILITIES: tuple[str, ...] = (READ_ONLY_CAPABILITY,)

# Every field is required, and the scan below reads two of them. `capability` is
# graded against the enumeration; `name` and `purpose` are scanned for a pasted
# value, because a declaration carrying one has already committed a secret.
_DECLARATION_FIELDS: tuple[str, ...] = ("name", "purpose", "capability")

# The withheld dispatch credentials, each mapped to the class the contract names
# it under. A proof credential may never be one of these: the sandbox is a
# read-only consumer of what the host projects, and these two are precisely what
# the host keeps.
#
# TWO ENTRIES, NOT FOUR, AND THE ABSENCES ARE DELIBERATE. The contract names four
# classes; only two of them carry an environment-variable NAME in this build, and
# a predicate must key on the narrowest surface that actually requires the
# withheld capability rather than approximate it. There is no long-lived
# personal access token to name — the fleet-PAT fallback is retired and
# `mint-app-token` resolves fail-closed with no second route — and the host
# provider refresh credential lives in the host's own agent credential file, not
# in the environment, so no declared `name` can reach it. A future name for
# either belongs HERE, as a named entry; it does not belong in a substring
# heuristic over `name`, which would refuse dispatchable declarations.
WITHHELD_DISPATCH_CREDENTIALS: Mapping[str, str] = {
    "BEADS_DOLT_PASSWORD": "the work-items store credential",
    "GITHUB_PRIVATE_KEY": "the durable GitHub App private key",
}

# How a projected proof credential was provisioned, which the dispatch journal
# records per declaration. `minted` is the preferred form wherever the provider
# offers a management interface that can mint a scoped, expiring credential,
# because a minted credential expires on its own rather than handing the sandbox
# a copy of the host's.
MINTED_PROVISIONING = "minted"
COPIED_PROVISIONING = "copied"

# The names this build MINTS per run rather than copying from its own
# environment. `GITHUB_TOKEN` is the GitHub App installation token the Dispatcher
# mints fresh for every dispatch and the overlay already projects: scoped,
# expiring, and never the durable App key. A declaration naming it is therefore
# minted, needs no host value, and must NOT be projected a second time — a
# duplicate key would make the whole overlay unparseable, turning one
# repository's declaration into a dispatch-wide failure.
MINTED_PER_RUN_CREDENTIALS: tuple[str, ...] = ("GITHUB_TOKEN",)

# The dispatch-journal stage the per-declaration record is written under.
PROOF_CREDENTIAL_JOURNAL_STAGE = "proof-credential"


@dataclass(frozen=True, kw_only=True)
class ProofCredential:
    """One declared proof credential: a NAME, why it is needed, and its capability.

    Frozen and carrying no value field by construction: the declaration is
    committed data, and this type is what the Dispatcher passes around, so there
    is no shape in which a secret can ride alongside the name it was declared
    under.
    """

    name: str
    purpose: str
    capability: str


def parse_proof_credentials(*, block: Mapping[str, object]) -> tuple[ProofCredential, ...] | str:
    """The declared proof credentials, or the FIRST refusal the declaration earns.

    An ABSENT key parses to the empty tuple rather than to a refusal: declaring
    no proof credential is the normal posture for a repository whose proof stages
    need nothing beyond what every dispatch already projects.

    The return is `tuple | str` rather than a raised error because every caller
    on this path routes an expected failure as data — the dispatch reports it as
    a pre-dispatch precondition and never as a traceback.
    """
    if PROOF_CREDENTIALS_KEY not in block:
        return ()
    declared = block[PROOF_CREDENTIALS_KEY]
    if not isinstance(declared, list):
        return (
            f"{_DECLARED_KEY} must be a list of "
            "{name, purpose, capability} objects naming the credentials this "
            f"repository's proof stages need; got {type(declared).__name__}"
        )
    parsed: list[ProofCredential] = []
    for index, entry in enumerate(cast("list[object]", declared)):
        resolved = _parse_entry(entry=entry, index=index)
        if isinstance(resolved, str):
            return resolved
        parsed.append(resolved)
    return tuple(parsed)


def _parse_entry(*, entry: object, index: int) -> ProofCredential | str:
    """One declaration entry, graded shape-first then capability then value-shape.

    The ORDER is load-bearing and is asserted by this module's tests. Shape comes
    first because the later grades read fields that a malformed entry does not
    carry; the capability grade comes before the credential-shaped scan because a
    capability value is not a credential, so reporting the generic fault for a
    specific one would send an operator looking in the wrong place.
    """
    if not isinstance(entry, dict):
        return (
            f"{_DECLARED_KEY}[{index}] must be an object carrying "
            f"{', '.join(_DECLARATION_FIELDS)}; got {type(entry).__name__}"
        )
    fields = cast("dict[str, object]", entry)
    values: dict[str, str] = {}
    for field_name in _DECLARATION_FIELDS:
        value = fields.get(field_name)
        if not isinstance(value, str) or not value.strip():
            return (
                f"{_DECLARED_KEY}[{index}] must carry a non-empty string "
                f"`{field_name}`; a proof-credential declaration carries a name, "
                "the one-sentence purpose it serves, and its capability"
            )
        values[field_name] = value.strip()
    credential = ProofCredential(
        name=values["name"], purpose=values["purpose"], capability=values["capability"]
    )
    return _declaration_refusal(credential=credential) or credential


def _declaration_refusal(*, credential: ProofCredential) -> str | None:
    """The withheld, capability and value-shape grades over one well-shaped entry.

    WITHHELD IS GRADED FIRST, and that ordering is load-bearing rather than
    stylistic. Every withheld name is ITSELF credential-shaped —
    `BEADS_DOLT_PASSWORD` case-folds to text carrying `password`,
    `GITHUB_PRIVATE_KEY` to text carrying `private_key` — so a ladder that ran the
    marker scan first would report the generic "reads as a literal credential"
    fault for the two declarations this module most needs to refuse by name, and
    the withheld refusal would be unreachable in practice while looking perfectly
    well tested.
    """
    if credential.name in WITHHELD_DISPATCH_CREDENTIALS:
        return (
            f"{_DECLARED_KEY} declaration {credential.name} names a withheld "
            f"dispatch credential ({WITHHELD_DISPATCH_CREDENTIALS[credential.name]}); "
            "the factory sandbox is a read-only consumer of what the host projects "
            "and never holds this one, so work needing it must be host-routed "
            "rather than declared as a proof credential"
        )
    if credential.capability not in PROOF_CREDENTIAL_CAPABILITIES:
        return (
            f"{_DECLARED_KEY} declaration {credential.name} declares capability "
            f"{credential.capability!r}, which is outside the closed enumeration "
            f"({', '.join(PROOF_CREDENTIAL_CAPABILITIES)}); a proof credential may "
            "only observe the named service, so a capability that would let the "
            "sandbox execute code on the host substrate or modify a gate that "
            "validates the factory's own output is refused before any run exists"
        )
    return _credential_shaped_refusal(credential=credential)


def _credential_shaped_refusal(*, credential: ProofCredential) -> str | None:
    """The first credential-shaped field of one declaration, naming its position.

    Scanned in declaration order — `name` then `purpose` — so a declaration that
    pasted a value into both is reported at the field an operator reads first.

    A name the Dispatcher ITSELF provisions is exempt from the `name` arm, and the
    exemption is narrow by construction: those names are credential-NAMED
    (`GITHUB_TOKEN` carries the `token` marker), and what this scan exists to catch
    is a pasted VALUE, not a well-known key the Dispatcher already projects under
    that spelling. `purpose` is scanned either way, because free prose is where a
    pasted value actually lands. The withheld names are refused above and never
    reach here, so the exempt set is exactly the minted one.
    """
    scanned = (
        (("purpose", credential.purpose),)
        if credential.name in MINTED_PER_RUN_CREDENTIALS
        else (("name", credential.name), ("purpose", credential.purpose))
    )
    for position, text in scanned:
        marker = secret_marker(text=text)
        if marker is not None:
            return (
                f"{_DECLARED_KEY} declaration {credential.name} reads as a literal "
                f"credential at `{position}` (matched {marker!r}); the declaration "
                "carries names only, and the value arrives from the Dispatcher's "
                "own environment through the target's credential wrapper"
            )
    return None


def proof_credential_provisioning(*, credential: ProofCredential) -> str:
    """Whether this declaration's credential is MINTED per run or COPIED from the host."""
    if credential.name in MINTED_PER_RUN_CREDENTIALS:
        return MINTED_PROVISIONING
    return COPIED_PROVISIONING


def proof_credentials_refusal(
    *, block: Mapping[str, object], environ: Mapping[str, str], wrapper_text: str
) -> str | None:
    """The pre-dispatch gate over one repository's declaration: None to proceed.

    Two grades, in this order. The DECLARATION grades come first, through the
    parse, because they are faults in committed configuration and hold regardless
    of what any environment carries. The ENVIRONMENT grade follows: a declared
    name whose value the Dispatcher does not hold cannot be projected, and the
    refusal names the target's credential wrapper because injecting it is that
    wrapper's job and the Dispatcher has no other route to the value.

    A MINTED name is exempt from the environment grade. Its value is provisioned
    by the Dispatcher itself, later on the same dispatch, so refusing it for an
    absent host value would refuse a credential that is about to exist.
    """
    parsed = parse_proof_credentials(block=block)
    if isinstance(parsed, str):
        return parsed
    return _environment_refusal(parsed=parsed, environ=environ, wrapper_text=wrapper_text)


def _environment_refusal(
    *,
    parsed: tuple[ProofCredential, ...],
    environ: Mapping[str, str],
    wrapper_text: str,
) -> str | None:
    """The first declared name whose value the Dispatcher's environment lacks."""
    for credential in parsed:
        if proof_credential_provisioning(credential=credential) == MINTED_PROVISIONING:
            continue
        if not environ.get(credential.name, ""):
            return (
                f"{_DECLARED_KEY} declaration {credential.name} is declared but its "
                "value is absent from the Dispatcher's own environment; the target's "
                f"credential_wrapper ({wrapper_text}) must inject it before a proof "
                "stage can exercise the service it observes"
            )
    return None


def proof_credential_journal_record(*, credential: ProofCredential) -> dict[str, object]:
    """The journal body for one declaration: names and facts about it, never its value.

    `provisioning` is DERIVED rather than written, so the record reports what the
    Dispatcher actually did for this name rather than a constant that would stay
    accurate only by coincidence once a second minting route exists.
    """
    return {
        "name": credential.name,
        "capability": credential.capability,
        "provisioning": proof_credential_provisioning(credential=credential),
    }


def proof_credentials_refusal_for_items(
    *,
    repo: Path,
    environ: Mapping[str, str],
    wrapper_text: str,
    work_item_ids: Sequence[str],
    journal: object = None,
) -> str | None:
    """The pre-dispatch gate over a whole selection, journaling what it admits.

    The declaration is a REPOSITORY-level fact, so the refusal is computed once
    and returned once: enumerating it per candidate would read as N distinct
    faults when there is one. The journal records, by contrast, ARE per item,
    because each dispatched item gets its own run-configuration overlay and
    therefore its own projection — a reader asking what one item's dispatch
    projected must not be answered with a sibling's.

    A refusal writes NO projection record. Nothing was projected, and a journal
    asserting otherwise would describe a credential reaching a sandbox that was
    never launched; the refusal itself is journaled by the caller that reports it.

    `journal` is optional and is reached through its own `append`, so the gate is
    callable from a hermetic test and from a caller holding none, without a second
    serializer.
    """
    parsed = parse_proof_credentials(block=dispatcher_block(cwd=repo))
    if isinstance(parsed, str):
        return parsed
    environment_refusal = _environment_refusal(
        parsed=parsed, environ=environ, wrapper_text=wrapper_text
    )
    if environment_refusal is not None:
        return environment_refusal
    append = getattr(journal, "append", None)
    if append is None:
        return None
    for work_item_id in work_item_ids:
        for credential in parsed:
            append(
                record={
                    "stage": PROOF_CREDENTIAL_JOURNAL_STAGE,
                    "work_item_id": work_item_id,
                    **proof_credential_journal_record(credential=credential),
                }
            )
    return None
