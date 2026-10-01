"""The WORKFLOW layer's own structured entries, rendered before anything reads them.

`SPECIFICATION/contracts.md` section "Built-in ACP node defaults": "The
workflow's own declared inputs ... MUST express the built-in defaults as
structured entries in the grammar of §'ACP node adapter configuration', never as
class-shaped tiers", and those entries "MUST render, literally" the v107 Claude
adapter strings -- byte for byte.

WHY THE RENDER HAPPENS HERE AND NOT INSIDE THE MERGE. Section "ACP node adapter
configuration" requires a structured entry rendered into the manual form "before
any layer merge, journal, digest or run input". The workflow layer is the LEAST
specific of the three, so rendering it at the merge would be rendering it in the
middle of one; rendering it as the inputs are read means every later stage --
the merge, the built-in identity table that keys on exact rendered bytes, the
journal, and the `--input` pairs a run receives -- sees manual-form strings and
needs to know nothing about the structured form at all.

THAT ALSO KEEPS THE BUILT-IN IDENTITY TABLE HONEST, which is the subtle half. The
table in `_acp_builtin_candidates` maps a workflow default's EXACT RENDERED BYTES
onto its identity. Handed raw structured JSON it would key on the JSON text,
which no resolved node can ever equal, and every built-in identity would silently
stop attaching -- a lookup miss that reads exactly like a deliberately overridden
adapter.

A VALUE IS STRUCTURED IFF IT OPENS WITH `{`. That is a complete discriminator
rather than a heuristic: a manual adapter is a command line, whose first token is
an environment assignment or an executable, and neither can begin with a brace. A
value that opens with one and does NOT parse as a JSON object is a MALFORMED
structured entry and refuses, rather than being passed through as a command named
`{` that would fail far later with nothing pointing back at the input.
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
from livespec_orchestrator_beads_fabro.commands._acp_node_adapters import (
    NODE_INPUT_CANDIDATES,
    render_adapter,
)
from livespec_orchestrator_beads_fabro.commands._acp_structured_render import (
    READ_ONLY_NODES,
    render_structured_entry,
)

__all__: list[str] = [
    "rendered_workflow_defaults",
]

_STRUCTURED_OPENER = "{"


def rendered_workflow_defaults(
    *, declared: Mapping[str, str], catalogs: AcpCatalogs
) -> Mapping[str, str] | str:
    """Every declared adapter input, with structured entries rendered, or a refusal.

    A MANUAL value passes through byte-for-byte rather than being parsed and
    re-rendered. That matters for a vendored workflow carrying an adapter the
    catalogs do not cover: a round trip through the parser would be a no-op for
    well-formed input and a silent rewrite for anything the parser normalizes,
    and neither is worth the risk when the value is already in its final form.
    """
    rendered: dict[str, str] = {}
    for name in sorted(declared):
        value = declared[name]
        if not value.lstrip().startswith(_STRUCTURED_OPENER):
            rendered[name] = value
            continue
        adapter, refusal = _rendered_entry(name=name, value=value, catalogs=catalogs)
        if refusal is not None:
            return refusal
        rendered[name] = adapter
    return rendered


def _rendered_entry(*, name: str, value: str, catalogs: AcpCatalogs) -> tuple[str, str | None]:
    """One structured input's adapter bytes, and any refusal.

    The PAIR is returned rather than a union because a rendered adapter and a
    refusal are both strings, and a caller that had to tell them apart by
    inspecting the text is one plausible refusal away from launching a node
    whose `acp.command` is an error message.
    """
    decoded, refusal = _decoded_object(name=name, value=value)
    if refusal is not None:
        return ("", refusal)
    key = f"workflow input {name}"
    # The CLOSED grammar binds at this layer too. Section "Built-in ACP node
    # defaults" requires the workflow's inputs to express their defaults "in the
    # grammar of" the adapter-configuration section, and that grammar is what
    # refuses a mixed entry, an unknown key, and a committed `config_options`.
    # Skipping it here would make the least specific layer the one place a typo
    # resolves silently -- and a workflow default is the hardest layer to notice
    # a typo in, because nothing in a repository mentions it.
    form = candidate_form_refusal(entry=decoded, key=key)
    if form is not None:
        return ("", form)
    entry = parse_structured_entry(entry=decoded, key=key)
    if isinstance(entry, str):
        return ("", entry)
    resolved = render_structured_entry(
        entry=entry, catalogs=catalogs, key=key, read_only=_read_only(name=name)
    )
    if isinstance(resolved, str):
        return ("", resolved)
    return (render_adapter(adapter=resolved.adapter), None)


def _decoded_object(*, name: str, value: str) -> tuple[Mapping[str, Any], str | None]:
    """The input's JSON object, and any refusal naming the input.

    There is NO non-object arm, and its absence is deliberate rather than an
    omission: the caller only reaches here for a value opening with `{`, and
    such a value either decodes to an object or raises. A guard for "parsed,
    but not a dict" would be unreachable, and an unreachable guard is worse
    than none -- it reads as a handled case and can never be exercised.
    """
    try:
        decoded = json.loads(value)
    except json.JSONDecodeError as error:
        malformed = (
            f"workflow input {name} opens with '{{' and so is a structured adapter entry, "
            f"but it does not parse as JSON: {error}"
        )
        return ({}, malformed)
    return (cast("dict[str, Any]", decoded), None)


def _read_only(*, name: str) -> bool:
    """Whether every node riding this input performs no writes.

    The posture is a property of the NODE, and one input can serve several --
    the shared `acp_adapter` rides all three implementer nodes. An input is
    treated as read-only only when EVERY node that could ride it is, so a shared
    input can never render a write-capable node read-only. An input no node
    rides at all is not read-only: there is no node asking for the weaker
    posture, and defaulting to it would be the unsafe direction for a node a
    later workflow adds.
    """
    riders = {node for node, names in NODE_INPUT_CANDIDATES.items() if name in names}
    return bool(riders) and riders <= READ_ONLY_NODES
