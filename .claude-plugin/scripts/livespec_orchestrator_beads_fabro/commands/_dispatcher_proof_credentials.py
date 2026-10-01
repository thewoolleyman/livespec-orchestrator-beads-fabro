"""Repository-declared proof credentials: the declaration, and what refuses it.

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

from collections.abc import Mapping
from dataclasses import dataclass
from typing import cast

from livespec_orchestrator_beads_fabro.commands._acp_candidate_secrets import secret_marker

__all__: list[str] = [
    "PROOF_CREDENTIALS_KEY",
    "PROOF_CREDENTIAL_CAPABILITIES",
    "READ_ONLY_CAPABILITY",
    "ProofCredential",
    "parse_proof_credentials",
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
    """The capability and value-shape grades over one well-shaped entry."""
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
    """
    for position, text in (("name", credential.name), ("purpose", credential.purpose)):
        marker = secret_marker(text=text)
        if marker is not None:
            return (
                f"{_DECLARED_KEY} declaration {credential.name} reads as a literal "
                f"credential at `{position}` (matched {marker!r}); the declaration "
                "carries names only, and the value arrives from the Dispatcher's "
                "own environment through the target's credential wrapper"
            )
    return None
