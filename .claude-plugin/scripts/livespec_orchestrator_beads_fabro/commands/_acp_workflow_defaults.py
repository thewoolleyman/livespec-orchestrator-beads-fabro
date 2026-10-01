"""The WORKFLOW layer's own structured entries, rendered before anything reads them.

`SPECIFICATION/contracts.md` section "Built-in ACP node defaults": "The
workflow's own declared inputs ... MUST express the built-in defaults as
structured entries in the grammar of section 'ACP node adapter configuration', never as
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

The TEXT-to-adapter rendering itself lives in `_acp_structured_text`, shared with
the per-dispatch layer, which spells a structured entry as a string for the same
reason this layer does: both ride a channel that carries only strings. What stays
here is the part that is the WORKFLOW layer\'s own -- which inputs there are, and
which node\'s posture each one renders under.
"""

from __future__ import annotations

from collections.abc import Mapping

from livespec_orchestrator_beads_fabro.commands._acp_catalogs import AcpCatalogs
from livespec_orchestrator_beads_fabro.commands._acp_node_adapters import NODE_INPUT_CANDIDATES
from livespec_orchestrator_beads_fabro.commands._acp_structured_render import READ_ONLY_NODES
from livespec_orchestrator_beads_fabro.commands._acp_structured_text import (
    is_structured_text,
    rendered_structured_text,
)

__all__: list[str] = [
    "rendered_workflow_defaults",
]


def rendered_workflow_defaults(
    *, declared: Mapping[str, str], catalogs: AcpCatalogs
) -> Mapping[str, str] | str:
    """Every declared adapter input, with structured entries rendered, or a refusal.

    A MANUAL value passes through byte-for-byte rather than being parsed and
    re-rendered. That matters for a vendored workflow carrying an adapter the
    catalogs do not cover: a round trip through the parser would be a no-op for
    well-formed input and a silent rewrite for anything the parser normalizes,
    and neither is worth the risk when the value is already in its final form.

    Inputs are visited in SORTED order, so a workflow with two broken defaults
    refuses on the same one every time -- the same reproducibility
    `parse_node_chains` gives the repository layer.
    """
    rendered: dict[str, str] = {}
    for name in sorted(declared):
        value = declared[name]
        if not is_structured_text(value=value):
            rendered[name] = value
            continue
        adapter, refusal = rendered_structured_text(
            value=value,
            key=f"workflow input {name}",
            catalogs=catalogs,
            read_only=_read_only(name=name),
        )
        if refusal is not None:
            return refusal
        rendered[name] = adapter
    return rendered


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
