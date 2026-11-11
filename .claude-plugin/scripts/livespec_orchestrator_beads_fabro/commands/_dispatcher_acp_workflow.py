"""The workflow layer of ACP resolution, read from one committed manifest."""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any, cast

from livespec_orchestrator_beads_fabro.commands._acp_candidate_forms import parse_structured_entry
from livespec_orchestrator_beads_fabro.commands._acp_catalogs import AcpCatalogs
from livespec_orchestrator_beads_fabro.commands._acp_node_adapters import NODE_INPUT_CANDIDATES
from livespec_orchestrator_beads_fabro.commands._acp_structured_text import is_structured_text
from livespec_orchestrator_beads_fabro.commands._acp_workflow_defaults import (
    rendered_workflow_defaults,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_acp_publication_policy import (
    GROOM_ONLY_ACP_NODES,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_integration_projection import (
    workflow_declared_inputs,
)
from livespec_orchestrator_beads_fabro.commands._workflow_variant_kind import (
    WORKFLOW_KIND_IMPLEMENT,
    declared_workflow_kind,
)
from livespec_orchestrator_beads_fabro.effects import AttemptFailure, attempt

__all__: list[str] = ["workflow_adapter_inputs", "workflow_configuration", "workflow_layer"]

_ADAPTER_INPUT_NAMES: frozenset[str] = frozenset(
    name for candidates in NODE_INPUT_CANDIDATES.values() for name in candidates
)


def workflow_adapter_inputs(*, committed_text: str) -> Mapping[str, str]:
    """The adapter defaults that a committed run config declares."""
    return {
        key: value
        for key, value in workflow_declared_inputs(committed_text=committed_text).items()
        if key in _ADAPTER_INPUT_NAMES
    }


def workflow_layer(*, committed: Path, catalogs: AcpCatalogs) -> Mapping[str, str] | str:
    """The workflow layer's rendered adapter inputs, or its refusal."""
    configured = workflow_configuration(committed=committed, catalogs=catalogs)
    return configured if isinstance(configured, str) else configured[0]


def workflow_configuration(
    *, committed: Path, catalogs: AcpCatalogs
) -> tuple[Mapping[str, str], str, Mapping[str, str]] | str:
    """Rendered defaults, workflow kind and structured-agent identities from one read."""
    committed_text = attempt(
        action=lambda: committed.read_text(encoding="utf-8"), exceptions=(OSError,)
    )
    if isinstance(committed_text, AttemptFailure):
        return f"workflow config {committed} is unreadable: {committed_text.error}"
    kind = declared_workflow_kind(committed_text=committed_text) or WORKFLOW_KIND_IMPLEMENT
    declared = workflow_adapter_inputs(committed_text=committed_text)
    agents = _workflow_agent_ids(declared=declared)
    if kind == WORKFLOW_KIND_IMPLEMENT:
        retired = {name for node in GROOM_ONLY_ACP_NODES for name in NODE_INPUT_CANDIDATES[node]}
        declared = {name: value for name, value in declared.items() if name not in retired}
    rendered = rendered_workflow_defaults(declared=declared, catalogs=catalogs)
    return rendered if isinstance(rendered, str) else (rendered, kind, agents)


def _workflow_agent_ids(*, declared: Mapping[str, str]) -> Mapping[str, str]:
    """Explicit structured agents, never identities inferred from adapter bytes."""
    agents: dict[str, str] = {}
    for name, value in declared.items():
        if not is_structured_text(value=value):
            continue
        try:
            decoded: object = json.loads(value)
        except ValueError:
            continue
        parsed = parse_structured_entry(
            entry=cast("Mapping[str, Any]", decoded), key=f"workflow input {name}"
        )
        if not isinstance(parsed, str):
            agents[name] = parsed.agent
    return agents
