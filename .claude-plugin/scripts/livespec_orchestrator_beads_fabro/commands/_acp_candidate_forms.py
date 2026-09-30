"""WHICH of the two ratified forms a candidate object is, and whether it is legal.

`SPECIFICATION/contracts.md` section "ACP node adapter configuration": "A node's
adapter configuration, and every entry of its `fallbacks` array ..., is EXACTLY
ONE of two forms. The Dispatcher MUST refuse before claim an entry that mixes the
two or matches neither, naming the entry and the offending field." Section
"Factory-configurable ACP fallback priority" closes each form's key set: the
structured form admits `agent`, `model`, `effort` and the five override keys; the
manual form admits `command`, `args`, `env` and the same five.

THE DISCRIMINATION AND THE REFUSAL ARE ONE DECISION, which is why they live in
one module. Asking "is this structured" without also owning "is this a legal
object of that form" is how a MIXED object gets read as structured, its manual
fields silently dropped, and a node launched against an adapter the operator
never wrote -- with the rendered bytes looking perfectly well-formed.

`config_options` IS REFUSED AS CONFIGURATION, NOT AS AN UNKNOWN KEY OF ONE FORM.
The contract is explicit that it "is NOT a configuration key: it is a field of
the rendered chain the Dispatcher emits to Fabro ... and MUST refuse if it
appears in committed configuration". Checking it before the form is discriminated
is what makes the refusal say the right thing in BOTH forms: an unknown-key
message would name the key without saying why an operator cannot have it, and
would not fire at all for a form whose set happened to be checked later.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from livespec_orchestrator_beads_fabro.commands._acp_candidate_schema import (
    IDENTITY_FIELDS,
    AcpCandidateIdentity,
)
from livespec_orchestrator_beads_fabro.commands._acp_candidate_secrets import secret_marker
from livespec_orchestrator_beads_fabro.commands._acp_schema_fields import (
    non_empty_text,
    unknown_keys_refusal,
)
from livespec_orchestrator_beads_fabro.commands._acp_structured_render import AcpStructuredEntry

__all__: list[str] = [
    "CONFIG_OPTIONS_KEY",
    "MANUAL_FIELDS",
    "STRUCTURED_CANDIDATE_KEYS",
    "STRUCTURED_FIELDS",
    "candidate_form_refusal",
    "is_structured_entry",
    "parse_partial_identity",
    "parse_structured_entry",
]

# The three fields that make an entry structured. `agent` alone decides the
# FORM; `model` and `effort` are what it carries.
STRUCTURED_FIELDS: tuple[str, ...] = ("agent", "model", "effort")

# The three fields of the manual form. Any one of them beside `agent` is the
# mixed-form fault.
MANUAL_FIELDS: tuple[str, ...] = ("command", "args", "env")

# The key the rendered CHAIN carries and committed configuration may not.
CONFIG_OPTIONS_KEY = "config_options"

# The five override keys both forms admit: the identity triple plus the two
# metadata objects a candidate may declare for itself.
_OVERRIDE_KEYS: frozenset[str] = frozenset({"availability_signatures", "pricing", *IDENTITY_FIELDS})

STRUCTURED_CANDIDATE_KEYS: frozenset[str] = frozenset(STRUCTURED_FIELDS) | _OVERRIDE_KEYS

_AGENT_FIELD = "agent"


def is_structured_entry(*, entry: Mapping[str, Any]) -> bool:
    """Whether this entry is written in the structured form.

    Keyed on the PRESENCE of `agent` rather than on its value, for the same
    reason `_acp_node_adapters` keys its primary-field detection on presence: an
    entry naming `agent: ""` has made a statement about the form it is written
    in, and reading it as manual would answer a malformed structured entry with a
    refusal about a missing `command`.
    """
    return _AGENT_FIELD in entry


def candidate_form_refusal(
    *, entry: Mapping[str, Any], key: str, extra_allowed: frozenset[str] = frozenset()
) -> str | None:
    """Refuse a mixed object, a committed `config_options`, or an unknown key.

    `extra_allowed` is what a NODE entry adds to the candidate key set -- today
    exactly `fallbacks`, which a node may carry and a fallback may not. It is a
    parameter rather than a member of the closed set because a nested fallback
    declaring its own `fallbacks` is a chain of chains the contract does not
    define, and admitting the key everywhere would accept one silently.

    Order is load-bearing. `config_options` first, because it is illegal in BOTH
    forms and its message is about what the key IS rather than about a key set.
    Then the mixed-form check, because a mixed object belongs to neither key set
    and an unknown-key message about it would name a key that is perfectly legal
    in the other form. Only then is the closed set of the STRUCTURED form
    applied -- the manual form's set is enforced where its legacy tolerance is
    decided (`_acp_node_chains`), which this module must not quietly widen.
    """
    if CONFIG_OPTIONS_KEY in entry:
        return (
            f"{key} carries {CONFIG_OPTIONS_KEY!r}, which is not a configuration key: it is a "
            "field of the rendered chain the Dispatcher emits to Fabro, derived from the "
            "agent catalog's declared mechanism"
        )
    if not is_structured_entry(entry=entry):
        return None
    mixed = [name for name in MANUAL_FIELDS if name in entry]
    if mixed:
        return (
            f"{key} carries {_AGENT_FIELD!r} together with {mixed[0]!r}; a candidate is "
            f"EXACTLY ONE of the structured form ({', '.join(STRUCTURED_FIELDS)}) or the "
            f"manual form ({', '.join(MANUAL_FIELDS)}), never both"
        )
    return unknown_keys_refusal(
        entry=entry, allowed=STRUCTURED_CANDIDATE_KEYS | extra_allowed, key=key
    )


def parse_structured_entry(*, entry: Mapping[str, Any], key: str) -> AcpStructuredEntry | str:
    """Read the three structured fields off one entry, or refuse naming the key.

    `effort` is optional and resolves to the empty string when absent, which the
    renderer reads as "take the adapter's own default". Neither `agent` nor
    `model` has such a resolution: an entry with no model is not a candidate.
    """
    resolved: list[str] = []
    for name in (_AGENT_FIELD, "model"):
        text = non_empty_text(value=entry.get(name))
        if text is None:
            return (
                f"{key}.{name} must be non-empty text in the structured form; "
                f"got {entry.get(name)!r}"
            )
        resolved.append(text)
    if "effort" not in entry:
        return AcpStructuredEntry(agent=resolved[0], model=resolved[1])
    effort = non_empty_text(value=entry["effort"])
    if effort is None:
        return f"{key}.effort must be non-empty text when declared; got {entry['effort']!r}"
    return AcpStructuredEntry(agent=resolved[0], model=resolved[1], effort=effort)


def parse_partial_identity(
    *, entry: Mapping[str, Any], key: str
) -> AcpCandidateIdentity | None | str:
    """The identity fields a STRUCTURED entry overrides, each independently.

    This is where the structured form departs from the manual one, and the
    departure is the contract's own: a manual candidate's identity is all-or-none
    because nothing can supply a missing field, while a structured candidate
    DERIVES every field it does not override. So a partial override is legal here
    and refused there, and `parse_candidate_identity` -- which owns the
    all-or-none rule -- cannot be reused.

    The two PER-FIELD rules are applied directly instead, and they are the same
    two that function applies: an identity value must be non-blank text, and it
    must not read as a credential reference, because candidate identity is
    committed public data. Reusing that function by padding a whole triple with
    one value was tried and is WRONG -- the refusal then names whichever field
    the loop reached first rather than the one the operator wrote, which is
    exactly the mis-attribution the fully-qualified messages exist to prevent.
    `test_acp_candidate_two_forms_paths` binds both rules on both spellings so
    they cannot drift apart.

    An UNDECLARED field comes back as the empty string, which
    `_acp_structured_identity` reads as "derive this one". That is why the return
    is a complete identity object carrying blanks rather than a mapping: every
    consumer downstream takes the finished triple, so the blank-means-derive
    convention stays contained to the one function that resolves it.
    """
    declared = [name for name in IDENTITY_FIELDS if name in entry]
    if not declared:
        return None
    resolved: dict[str, str] = {}
    for name in declared:
        text = non_empty_text(value=entry[name])
        if text is None:
            return f"{key}.{name} must be non-empty text; got {entry[name]!r}"
        marker = secret_marker(text=text)
        if marker is not None:
            return (
                f"{key}.{name} reads as a credential reference (matched {marker!r}); "
                "candidate identity is committed public data"
            )
        resolved[name] = text
    return AcpCandidateIdentity(
        display_name=resolved.get("display_name", ""),
        candidate_key=resolved.get("candidate_key", ""),
        availability_key=resolved.get("availability_key", ""),
    )
