"""A structured entry written as TEXT, rendered into adapter bytes.

TWO LAYERS SPELL A STRUCTURED ENTRY AS A STRING, and this is what they share.
`SPECIFICATION/contracts.md` section "Built-in ACP node defaults" makes the
WORKFLOW layer's declared inputs structured entries, and section "ACP node
adapter configuration" lets the PER-DISPATCH `--acp-node` value "be either
form -- a legacy adapter string (the manual form) or a JSON object in the
structured form". Both arrive as text because both ride a channel that carries
only strings: a TOML scalar and a command-line argument.

The repository layer does NOT use this. Its entries arrive from JSONC already
decoded into objects, so it hands `_acp_structured_render` a mapping directly;
routing it through a JSON round trip here would be inventing a serialization
step between two things that already agree.

A VALUE IS STRUCTURED IFF IT OPENS WITH `{`. That is a complete discriminator
rather than a heuristic: a manual adapter is a command line, whose first token
is an environment assignment or an executable, and neither can begin with a
brace. A value that opens with one and does NOT parse as a JSON object is a
MALFORMED structured entry and refuses, rather than being passed through as a
command named `{`.

WHY THE MALFORMED CASE MUST REFUSE RATHER THAN FALL BACK. The rendered string
is shell-tokenized before execution, and POSIX tokenization CONSUMES quote
characters -- so a JSON object that slipped through as a command line arrives
as `{agent: claude-acp, model: ...}`, which is a plausible-looking argv whose
first token is not an executable. The failure then surfaces inside a sandbox,
as a launch error, with nothing pointing back at the configuration that caused
it.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any, cast

from livespec_orchestrator_beads_fabro.commands._acp_candidate_forms import (
    candidate_form_refusal,
    parse_structured_entry,
)
from livespec_orchestrator_beads_fabro.commands._acp_catalogs import AcpCatalogs
from livespec_orchestrator_beads_fabro.commands._acp_node_adapters import render_adapter
from livespec_orchestrator_beads_fabro.commands._acp_structured_render import (
    render_structured_entry,
)

__all__: list[str] = [
    "STRUCTURED_OPENER",
    "is_structured_text",
    "rendered_structured_text",
]

STRUCTURED_OPENER = "{"


def is_structured_text(*, value: str) -> bool:
    """Whether this text is a structured entry rather than a command line."""
    return value.lstrip().startswith(STRUCTURED_OPENER)


def rendered_structured_text(
    *, value: str, key: str, catalogs: AcpCatalogs, read_only: bool
) -> tuple[str, str | None]:
    """One structured entry's adapter bytes, and any refusal naming `key`.

    The PAIR is returned rather than a union because a rendered adapter and a
    refusal are both strings, and a caller that had to tell them apart by
    inspecting the text is one plausible refusal away from launching a node
    whose `acp.command` is an error message.

    The CLOSED grammar is applied before the catalog lookup, so a mixed entry,
    an unknown key, or a committed `config_options` refuses on what it says
    rather than on whichever catalog miss it happens to produce.
    """
    decoded, refusal = _decoded_object(value=value, key=key)
    if refusal is not None:
        return ("", refusal)
    form = candidate_form_refusal(entry=decoded, key=key)
    if form is not None:
        return ("", form)
    entry = parse_structured_entry(entry=decoded, key=key)
    if isinstance(entry, str):
        return ("", entry)
    resolved = render_structured_entry(entry=entry, catalogs=catalogs, key=key, read_only=read_only)
    if isinstance(resolved, str):
        return ("", resolved)
    return (render_adapter(adapter=resolved.adapter), None)


def _decoded_object(*, value: str, key: str) -> tuple[Mapping[str, Any], str | None]:
    """The text's JSON object, and any refusal naming the key.

    There is NO non-object arm, and its absence is deliberate rather than an
    omission: a caller only reaches here for text opening with `{`, and such
    text either decodes to an object or raises. A guard for "parsed, but not a
    dict" would be unreachable, and an unreachable guard is worse than none --
    it reads as a handled case and can never be exercised.
    """
    try:
        decoded = json.loads(value)
    except json.JSONDecodeError as error:
        malformed = (
            f"{key} opens with '{{' and so is a structured adapter entry, but it does not "
            f"parse as JSON: {error}"
        )
        return ({}, malformed)
    return (cast("dict[str, Any]", decoded), None)
