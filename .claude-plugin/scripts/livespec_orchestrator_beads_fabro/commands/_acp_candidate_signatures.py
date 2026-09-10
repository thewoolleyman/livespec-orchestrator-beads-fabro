"""The CLOSED availability-signature grammar one candidate declares.

A signature says which observed adapter diagnostic counts as that
candidate's own availability failure. `SPECIFICATION/contracts.md` section
"Factory-configurable ACP fallback priority" fixes its shape exactly, and
this module is the parse half of it: the enumerations, the
discriminator rule, and the STATIC conflict refusal.

THE DISCRIMINATOR RULE IS THE POINT OF THE SHAPE. A machine-code source
requires one non-empty exact `machine_code` and FORBIDS `all_literals`;
every other source requires a non-empty array of non-empty `all_literals`
and forbids `machine_code`. `exit_code` only REFINES whichever
discriminator is required and is never sufficient alone -- an exit status
is shared by every failure a process can have, so a signature keyed on one
would claim unrelated failures as its provider's.

WHAT IS NOT HERE. Runtime MATCHING -- case folding, whitespace
normalization, conjunction, machine-code precedence, the non-eligible
pre-checks and the runtime multi-match ambiguity rule -- belongs to the
classifier slice, and none of it is implemented in this repository yet.
This module refuses configuration that could not be classified honestly;
it never classifies. The one runtime-adjacent thing it does own is the
STATIC conflict: two signatures whose matchers are identical but whose
dispositions differ can only ever produce the ambiguity the contract says
must never be resolved by first match, so the configuration is refused
before it can be claimed rather than at the moment a run trips over it.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, cast

from livespec_orchestrator_beads_fabro.commands._acp_schema_fields import (
    bounded_int,
    missing_keys_refusal,
    non_empty_text,
    string_tuple,
    unknown_keys_refusal,
)

__all__: list[str] = [
    "SIGNATURE_CAUSES",
    "SIGNATURE_SCOPES",
    "SIGNATURE_SOURCES",
    "AcpAvailabilitySignature",
    "conflicting_signature_refusal",
    "parse_availability_signatures",
]

SIGNATURE_SOURCES: tuple[str, ...] = (
    "process.terminal_diagnostic",
    "protocol.machine_code",
    "protocol.message",
)

SIGNATURE_CAUSES: tuple[str, ...] = (
    "model_not_entitled",
    "model_not_found",
    "model_unavailable",
    "model_unsupported",
    "provider_capacity",
    "provider_server_unavailable",
    "quota",
    "rate_limit",
)

SIGNATURE_SCOPES: tuple[str, ...] = ("availability-domain", "candidate")

_MACHINE_CODE_SOURCE = "protocol.machine_code"
_DOMAIN_SCOPE = "availability-domain"

_SIGNATURE_KEYS: frozenset[str] = frozenset(
    {
        "all_literals",
        "cause",
        "exit_code",
        "hold_key",
        "machine_code",
        "scope",
        "source",
    }
)
_REQUIRED_KEYS: frozenset[str] = frozenset({"cause", "scope", "source"})

# The contract's own bounds. 0 is excluded because a zero exit is success,
# and 126 upward are the shell's own command-not-found / signal encodings,
# which the same section lists as non-eligible before matching runs.
_EXIT_CODE_LOW = 1
_EXIT_CODE_HIGH = 125


@dataclass(frozen=True, kw_only=True)
class AcpAvailabilitySignature:
    """One declared mapping from an observed diagnostic to a typed cause."""

    source: str
    cause: str
    scope: str
    machine_code: str | None = None
    all_literals: tuple[str, ...] = ()
    exit_code: int | None = None
    hold_key: str | None = None

    @property
    def matcher(self) -> tuple[str, str, frozenset[str], int | None]:
        """What this signature MATCHES, independent of what it then decides.

        `all_literals` collapses to a frozenset because the contract makes
        it a CONJUNCTION: two signatures listing the same literals in a
        different order match exactly the same diagnostics, so ordering
        them would hide a conflict behind a cosmetic difference.
        """
        return (self.source, self.machine_code or "", frozenset(self.all_literals), self.exit_code)

    @property
    def disposition(self) -> tuple[str, str, str]:
        """What this signature DECIDES once it has matched."""
        return (self.cause, self.scope, self.hold_key or "")


def parse_availability_signatures(
    *, value: object, key: str
) -> tuple[AcpAvailabilitySignature, ...] | str:
    """Parse one candidate's whole `availability_signatures` array, or refuse."""
    if not isinstance(value, list):
        return f"{key} must be an array of availability signatures; got {value!r}"
    entries = cast("list[object]", value)
    signatures: list[AcpAvailabilitySignature] = []
    for index, entry in enumerate(entries):
        parsed = _parse_one(entry=entry, key=f"{key}[{index}]")
        if isinstance(parsed, str):
            return parsed
        signatures.append(parsed)
    conflict = conflicting_signature_refusal(signatures=tuple(signatures), key=key)
    if conflict is not None:
        return conflict
    return tuple(signatures)


def conflicting_signature_refusal(
    *, signatures: tuple[AcpAvailabilitySignature, ...], key: str
) -> str | None:
    """Refuse two STATICALLY identical matchers that disagree on disposition.

    Identical matcher AND identical disposition is merely redundant, so it
    passes: the second signature can never change an outcome. A
    disposition difference cannot be reconciled at runtime without the
    first-match choice the contract forbids, so it is refused here, before
    any claim, rather than surfaced as an ambiguous failure mid-run.
    """
    seen: dict[tuple[str, str, frozenset[str], int | None], tuple[str, str, str]] = {}
    for signature in signatures:
        previous = seen.get(signature.matcher)
        if previous is not None and previous != signature.disposition:
            return (
                f"{key} declares two signatures matching identically on "
                f"source {signature.source!r} but disposing differently "
                f"({previous[0]}/{previous[1]} versus {signature.cause}/{signature.scope}); "
                "a runtime multi-match may never be resolved by first match"
            )
        seen[signature.matcher] = signature.disposition
    return None


def _parse_one(*, entry: object, key: str) -> AcpAvailabilitySignature | str:
    """Parse and validate one signature table."""
    if not isinstance(entry, dict):
        return f"{key} must be an availability-signature table; got {entry!r}"
    table = cast("dict[str, Any]", entry)
    for check in (_shape_refusal, _exit_code_refusal, _hold_key_refusal):
        refusal = check(table=table, key=key)
        if refusal is not None:
            return refusal
    discriminator = _discriminator(table=table, key=key)
    if isinstance(discriminator, str):
        return discriminator
    machine_code, all_literals = discriminator
    return AcpAvailabilitySignature(
        source=str(table["source"]),
        cause=str(table["cause"]),
        scope=str(table["scope"]),
        machine_code=machine_code,
        all_literals=all_literals,
        exit_code=table.get("exit_code"),
        hold_key=table.get("hold_key"),
    )


def _shape_refusal(*, table: Mapping[str, Any], key: str) -> str | None:
    """Refuse an unknown key, a missing required key, or an unknown enum value."""
    unknown = unknown_keys_refusal(entry=table, allowed=_SIGNATURE_KEYS, key=key)
    if unknown is not None:
        return unknown
    missing = missing_keys_refusal(entry=table, required=_REQUIRED_KEYS, key=key)
    if missing is not None:
        return missing
    for field_name, allowed in (
        ("source", SIGNATURE_SOURCES),
        ("cause", SIGNATURE_CAUSES),
        ("scope", SIGNATURE_SCOPES),
    ):
        if table[field_name] not in allowed:
            return (
                f"{key}.{field_name} must be one of {', '.join(allowed)}; "
                f"got {table[field_name]!r}"
            )
    return None


def _exit_code_refusal(*, table: Mapping[str, Any], key: str) -> str | None:
    """Refuse an optional refining exit code outside the contract's bounds."""
    if "exit_code" not in table:
        return None
    if bounded_int(value=table["exit_code"], low=_EXIT_CODE_LOW, high=_EXIT_CODE_HIGH) is None:
        return (
            f"{key}.exit_code must be an integer from {_EXIT_CODE_LOW} through "
            f"{_EXIT_CODE_HIGH}; got {table['exit_code']!r}"
        )
    return None


def _hold_key_refusal(*, table: Mapping[str, Any], key: str) -> str | None:
    """Refuse a hold-key override at candidate scope, or a blank one at domain scope."""
    if "hold_key" not in table:
        return None
    if table["scope"] != _DOMAIN_SCOPE:
        return (
            f"{key}.hold_key is only valid at scope {_DOMAIN_SCOPE!r}; a candidate-scoped "
            "signature keys on its own (availability_key, candidate_key) pair"
        )
    if non_empty_text(value=table["hold_key"]) is None:
        return f"{key}.hold_key must be non-empty text; got {table['hold_key']!r}"
    return None


def _discriminator(
    *, table: Mapping[str, Any], key: str
) -> tuple[str | None, tuple[str, ...]] | str:
    """The required discriminator for this source, or a refusal naming it."""
    if table["source"] == _MACHINE_CODE_SOURCE:
        if "all_literals" in table:
            return f"{key}.all_literals is forbidden for source {_MACHINE_CODE_SOURCE!r}"
        code = non_empty_text(value=table.get("machine_code"))
        if code is None:
            return (
                f"{key}.machine_code must be one exact non-empty code for source "
                f"{_MACHINE_CODE_SOURCE!r}; got {table.get('machine_code')!r}"
            )
        return (code, ())
    if "machine_code" in table:
        return f"{key}.machine_code is forbidden for source {table['source']!r}"
    literals = string_tuple(value=table.get("all_literals"))
    if literals is None or not literals or any(literal.strip() == "" for literal in literals):
        return (
            f"{key}.all_literals must be a non-empty array of non-empty strings for source "
            f"{table['source']!r}; got {table.get('all_literals')!r}"
        )
    return (None, literals)
