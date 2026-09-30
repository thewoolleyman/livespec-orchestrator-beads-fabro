"""WHICH of the two ratified forms a candidate object is written in.

`SPECIFICATION/contracts.md` section "ACP node adapter configuration": "A
node's adapter configuration, and every entry of its `fallbacks` array ..., is
EXACTLY ONE of two forms." The discriminator is the presence of `agent`, and it
is safe as a discriminator because the closed grammar of section
"Factory-configurable ACP fallback priority" refuses "any object that carries
`agent` together with `command`, `args` or `env`" -- so the two key sets cannot
overlap in an admissible object.

THE DISCRIMINATION AND THE REFUSAL ARE THE SAME DECISION READ TWICE, which is
why they live in one module. Asking "is this structured" without also owning
"is this a legal object of that form" is how a mixed object gets read as
structured, its manual fields silently dropped, and a node launched against an
adapter the operator never wrote.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from livespec_orchestrator_beads_fabro.commands._acp_structured_render import AcpStructuredEntry

__all__: list[str] = [
    "STRUCTURED_FIELDS",
    "is_structured_entry",
    "parse_structured_entry",
]

# The three fields that make an entry structured. `agent` alone decides the
# FORM; `model` and `effort` are what it carries.
STRUCTURED_FIELDS: tuple[str, ...] = ("agent", "model", "effort")

_AGENT_FIELD = "agent"


def is_structured_entry(*, entry: Mapping[str, Any]) -> bool:
    """Whether this entry is written in the structured form.

    Keyed on the PRESENCE of `agent` rather than on its value, for the same
    reason `_acp_node_adapters` keys its primary-field detection on presence: an
    entry naming `agent: ""` has made a statement about the form it is written
    in, and reading it as manual would answer a malformed structured entry with
    a refusal about a missing `command`.
    """
    return _AGENT_FIELD in entry


def parse_structured_entry(*, entry: Mapping[str, Any], key: str) -> AcpStructuredEntry | str:
    """Read the three structured fields off one entry, or refuse naming the key.

    `effort` is optional and resolves to the empty string when absent, which the
    renderer reads as "take the adapter's own default". Neither `agent` nor
    `model` has such a resolution: an entry with no model is not a candidate.
    """
    resolved: list[str] = []
    for name in (_AGENT_FIELD, "model"):
        value = entry.get(name)
        if not isinstance(value, str) or value.strip() == "":
            return f"{key}.{name} must be non-empty text in the structured form; got {value!r}"
        resolved.append(value)
    effort = entry.get("effort")
    if effort is None:
        return AcpStructuredEntry(agent=resolved[0], model=resolved[1])
    if not isinstance(effort, str) or effort.strip() == "":
        return f"{key}.effort must be non-empty text when declared; got {effort!r}"
    return AcpStructuredEntry(agent=resolved[0], model=resolved[1], effort=effort)
