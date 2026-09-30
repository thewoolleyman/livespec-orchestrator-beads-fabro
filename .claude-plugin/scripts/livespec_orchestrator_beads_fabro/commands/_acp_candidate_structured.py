"""ONE STRUCTURED candidate, all the way from its table to a resolved candidate.

This is the structured-form counterpart of `_acp_candidate_schema`'s
`parse_fallback_candidate`: it reads one table, refuses it if the closed grammar
says so, renders it through the catalogs, derives its identity, and returns the
same `AcpCandidate` the manual path returns. Downstream nothing can tell which
form produced it, which is the whole point of
`SPECIFICATION/contracts.md` section "ACP node adapter configuration"'s
render-before-anything rule.

IT LIVES APART FROM `_acp_candidate_schema` TO KEEP THE IMPORT GRAPH ACYCLIC, and
the direction is worth stating because it is easy to get backwards. The closed
form grammar (`_acp_candidate_forms`) needs the identity type and the
per-field identity validation, both of which `_acp_candidate_schema` owns. So the
structured path depends on the schema, not the other way round, and the DISPATCH
between the two forms belongs to a module downstream of both --
`_acp_node_chains`, which is where a node's entry and its fallback array are both
read.

PRICING AND SIGNATURES COME FROM THE MODEL CATALOG, WITH THE CANDIDATE'S OWN
OVERRIDE WINNING. Section "Agent and model catalogs": "A per-candidate `pricing`
or `availability_signatures` override on a structured entry wins over the catalog
value". The override is parsed through the same grammar the manual form uses, so
the all-or-none pricing rule applies to both without either restating it.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from livespec_orchestrator_beads_fabro.commands._acp_candidate_forms import (
    candidate_form_refusal,
    parse_partial_identity,
    parse_structured_entry,
)
from livespec_orchestrator_beads_fabro.commands._acp_candidate_schema import (
    AcpCandidate,
    parse_candidate_metadata,
)
from livespec_orchestrator_beads_fabro.commands._acp_catalogs import AcpCatalogs
from livespec_orchestrator_beads_fabro.commands._acp_structured_identity import derived_identity
from livespec_orchestrator_beads_fabro.commands._acp_structured_render import (
    render_structured_entry,
)

__all__: list[str] = [
    "parse_structured_candidate",
]


def parse_structured_candidate(
    *,
    entry: Mapping[str, Any],
    key: str,
    catalogs: AcpCatalogs,
    read_only: bool = False,
    extra_allowed: frozenset[str] = frozenset(),
) -> AcpCandidate | str:
    """Parse, render and identify one structured candidate, or refuse.

    The order is the contract's own: the closed grammar first (so a mixed or
    unknown-keyed object never reaches a catalog lookup), then the catalog
    resolution that can refuse on an unresolvable agent, model or effort, then
    the derivation and the optional overrides.
    """
    form = candidate_form_refusal(entry=entry, key=key, extra_allowed=extra_allowed)
    if form is not None:
        return form
    parsed = parse_structured_entry(entry=entry, key=key)
    if isinstance(parsed, str):
        return parsed
    rendered = render_structured_entry(
        entry=parsed, catalogs=catalogs, key=key, read_only=read_only
    )
    if isinstance(rendered, str):
        return rendered
    override = parse_partial_identity(entry=entry, key=key)
    if isinstance(override, str):
        return override
    metadata = parse_candidate_metadata(entry=entry, key=key)
    if isinstance(metadata, str):
        return metadata
    return AcpCandidate(
        adapter=rendered.adapter,
        identity=derived_identity(resolved=rendered, override=override),
        signatures=metadata.signatures or rendered.model.signatures,
        pricing=metadata.pricing or rendered.model.pricing,
        config_options=rendered.config_options,
    )
