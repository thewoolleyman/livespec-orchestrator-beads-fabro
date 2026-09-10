"""One CANDIDATE: its explicit identity, its complete adapter, its metadata.

`SPECIFICATION/contracts.md` section "Factory-configurable ACP fallback
priority" gives every explicitly identified candidate, and every candidate
in a fallback-enabled chain, a non-empty non-secret `display_name`,
`candidate_key` and opaque `availability_key`. The pair
`(availability_key, candidate_key)` identifies ONE candidate entitlement
and may be repeated ACROSS nodes when the entitlement is truly shared;
different accounts or routers must use different keys.

DISPLAY TEXT IS NEVER A MACHINE KEY, which is why identity is a triple
rather than a name plus a slug. `display_name` is what an operator reads
in a warning; the two keys are what a hold is scoped by. Collapsing them
would make renaming the operator-facing text silently retarget every live
hold.

NOTHING IS INHERITED FROM A NEIGHBOUR, and that is enforced structurally
rather than by a rule: `parse_fallback_candidate` reads ONE table and
never sees another, so a fallback's command, args, env, model, identity,
signatures and pricing can only come from its own entry. An omitted
`args` resolves to the empty tuple and an omitted `env` to the empty
table -- NOT to whatever the primary had. A fallback additionally REQUIRES
a complete `command`, because the alternative to requiring it is
inheriting one.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, cast

from livespec_orchestrator_beads_fabro.commands._acp_candidate_pricing import (
    AcpCandidatePricing,
    parse_candidate_pricing,
)
from livespec_orchestrator_beads_fabro.commands._acp_candidate_secrets import (
    adapter_secret_refusal,
    secret_marker,
)
from livespec_orchestrator_beads_fabro.commands._acp_candidate_signatures import (
    AcpAvailabilitySignature,
    parse_availability_signatures,
)
from livespec_orchestrator_beads_fabro.commands._acp_node_adapters import AcpAdapter
from livespec_orchestrator_beads_fabro.commands._acp_schema_fields import (
    missing_keys_refusal,
    non_empty_text,
    string_map,
    string_tuple,
    unknown_keys_refusal,
)

__all__: list[str] = [
    "CANDIDATE_KEYS",
    "IDENTITY_FIELDS",
    "AcpCandidate",
    "AcpCandidateIdentity",
    "AcpCandidateMetadata",
    "parse_candidate_identity",
    "parse_candidate_metadata",
    "parse_fallback_candidate",
]

# The three identity fields, all-or-none: declaring one declares all.
IDENTITY_FIELDS: tuple[str, ...] = ("display_name", "candidate_key", "availability_key")

# Every key a FALLBACK entry may carry. The node's own primary entry adds
# `command` / `env` / `args`'s legacy overlay meanings on top of these; see
# `_acp_node_chains`.
CANDIDATE_KEYS: frozenset[str] = frozenset(
    {
        "args",
        "availability_signatures",
        "command",
        "env",
        "pricing",
        *IDENTITY_FIELDS,
    }
)


@dataclass(frozen=True, kw_only=True)
class AcpCandidateIdentity:
    """The operator text and the two machine keys one candidate is known by."""

    display_name: str
    candidate_key: str
    availability_key: str

    @property
    def pair(self) -> tuple[str, str]:
        """The `(availability_key, candidate_key)` entitlement pair."""
        return (self.availability_key, self.candidate_key)


@dataclass(frozen=True, kw_only=True)
class AcpCandidate:
    """One position in a node's ordered chain: identity, adapter, metadata.

    `identity` is `None` only for the conservative legacy posture -- an
    identity-less arbitrary adapter with no fallback metadata, which the
    contract keeps covered by every live legacy provider record. Every
    candidate in a fallback-enabled chain carries one.
    """

    adapter: AcpAdapter
    identity: AcpCandidateIdentity | None = None
    signatures: tuple[AcpAvailabilitySignature, ...] = ()
    pricing: AcpCandidatePricing | None = None


@dataclass(frozen=True, kw_only=True)
class AcpCandidateMetadata:
    """The signature and pricing objects a candidate table declares."""

    signatures: tuple[AcpAvailabilitySignature, ...] = ()
    pricing: AcpCandidatePricing | None = None


def parse_candidate_identity(
    *, entry: Mapping[str, Any], key: str
) -> AcpCandidateIdentity | None | str:
    """Parse the identity triple, or `None` when the table declares none.

    A PARTIAL identity is refused rather than completed: guessing the
    missing key would mint an entitlement identity nobody wrote, and a
    hold scoped to it would skip a candidate the operator never named.
    """
    if not any(name in entry for name in IDENTITY_FIELDS):
        return None
    missing = missing_keys_refusal(entry=entry, required=frozenset(IDENTITY_FIELDS), key=key)
    if missing is not None:
        return missing
    resolved: list[str] = []
    for name in IDENTITY_FIELDS:
        text = non_empty_text(value=entry[name])
        if text is None:
            return f"{key}.{name} must be non-empty text; got {entry[name]!r}"
        marker = secret_marker(text=text)
        if marker is not None:
            return (
                f"{key}.{name} reads as a credential reference (matched {marker!r}); "
                "candidate identity is committed public data"
            )
        resolved.append(text)
    return AcpCandidateIdentity(
        display_name=resolved[0], candidate_key=resolved[1], availability_key=resolved[2]
    )


def parse_candidate_metadata(*, entry: Mapping[str, Any], key: str) -> AcpCandidateMetadata | str:
    """Parse the optional `availability_signatures` and `pricing` objects."""
    signatures: tuple[AcpAvailabilitySignature, ...] = ()
    if "availability_signatures" in entry:
        parsed = parse_availability_signatures(
            value=entry["availability_signatures"], key=f"{key}.availability_signatures"
        )
        if isinstance(parsed, str):
            return parsed
        signatures = parsed
    pricing: AcpCandidatePricing | None = None
    if "pricing" in entry:
        priced = parse_candidate_pricing(value=entry["pricing"], key=f"{key}.pricing")
        if isinstance(priced, str):
            return priced
        pricing = priced
    return AcpCandidateMetadata(signatures=signatures, pricing=pricing)


def parse_fallback_candidate(*, entry: object, key: str) -> AcpCandidate | str:
    """Parse one COMPLETE fallback entry from its own table alone, or refuse."""
    if not isinstance(entry, dict):
        return f"{key} must be a fallback candidate table; got {entry!r}"
    table = cast("dict[str, Any]", entry)
    unknown = unknown_keys_refusal(entry=table, allowed=CANDIDATE_KEYS, key=key)
    if unknown is not None:
        return unknown
    identity = _fallback_identity(table=table, key=key)
    if isinstance(identity, str):
        return identity
    adapter = _fallback_adapter(table=table, key=key)
    if isinstance(adapter, str):
        return adapter
    metadata = parse_candidate_metadata(entry=table, key=key)
    if isinstance(metadata, str):
        return metadata
    return AcpCandidate(
        adapter=adapter,
        identity=identity,
        signatures=metadata.signatures,
        pricing=metadata.pricing,
    )


def _fallback_identity(*, table: Mapping[str, Any], key: str) -> AcpCandidateIdentity | str:
    """The fallback's REQUIRED identity, or a refusal naming what is missing."""
    identity = parse_candidate_identity(entry=table, key=key)
    if identity is None:
        return (
            f"{key} must declare {', '.join(IDENTITY_FIELDS)}; a fallback candidate "
            "carries explicit identity and inherits none from another candidate"
        )
    return identity


def _fallback_adapter(*, table: Mapping[str, Any], key: str) -> AcpAdapter | str:
    """The fallback's own complete `(command, env, args)`, or a refusal.

    An omitted `args` resolves to the EMPTY tuple and an omitted `env` to
    the EMPTY table, which is the contract's wording and the opposite of
    inheritance. `command` has no such empty resolution: a candidate with
    no command is not a candidate.

    The committed-credential scan lives here rather than beside the other
    candidate refusals because this is the one place holding all three of
    the fields it reads, already normalized.
    """
    command = non_empty_text(value=table.get("command"))
    if command is None:
        return (
            f"{key}.command must be a non-empty complete adapter command; "
            f"got {table.get('command')!r}"
        )
    args = () if table.get("args") is None else string_tuple(value=table["args"])
    if args is None:
        return f"{key}.args must be an array of strings; got {table['args']!r}"
    empty: Mapping[str, str] = {}
    env = empty if table.get("env") is None else string_map(value=table["env"])
    if env is None:
        return f"{key}.env must be a table of string to string; got {table['env']!r}"
    secret = adapter_secret_refusal(command=command, args=args, env=env, key=key)
    if secret is not None:
        return secret
    return AcpAdapter(command=command, env=env, args=args)
