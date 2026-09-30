"""BOTH catalogs as one resolved value, plus the snapshot record a reader checks.

`SPECIFICATION/contracts.md` section "Agent and model catalogs" makes a
structured candidate resolve `agent` in the agent catalog and then `model` in
the model catalog "for that agent's provider", so the two are never useful
apart: a resolution holding one of them cannot finish. Pairing them in one
frozen value is what makes "the same catalog snapshot renders byte-identical
adapter bytes" -- the determinism clause of section "ACP node adapter
configuration" -- a property of ONE object a caller passes around rather than
of two it has to keep in step.

THE SNAPSHOT RECORD EXISTS FOR THE READER, NOT FOR RESOLUTION. Nothing in a
render consults the digests; they are what a journal carries so a reader can
tell whether two dispatches rendered against the same committed bytes. Keeping
them out of the resolution path is deliberate: a digest that gated a render
would turn a re-seed into a dispatch failure, and the contract makes a re-seed
an ordinary committed change.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from livespec_orchestrator_beads_fabro.commands._acp_agent_catalog import (
    REGISTRY_SNAPSHOT_DATE,
    agent_catalog_digest,
    builtin_agent_catalog,
    resolve_agent_catalog,
)
from livespec_orchestrator_beads_fabro.commands._acp_agent_entry import AcpAgentEntry
from livespec_orchestrator_beads_fabro.commands._acp_model_catalog import (
    builtin_model_catalog,
    model_catalog_digest,
    resolve_model_catalog,
)
from livespec_orchestrator_beads_fabro.commands._acp_model_entry import AcpModelEntry

__all__: list[str] = [
    "AcpCatalogs",
    "builtin_catalogs",
    "catalog_snapshot_record",
    "resolve_acp_catalogs",
]


@dataclass(frozen=True, kw_only=True)
class AcpCatalogs:
    """The agent and model catalogs one dispatch resolves against."""

    agents: Mapping[str, AcpAgentEntry]
    models: Mapping[str, AcpModelEntry]

    @property
    def snapshot(self) -> Mapping[str, str]:
        """The digests and seed date identifying these exact committed bytes."""
        return {
            "agent_catalog_digest": agent_catalog_digest(catalog=self.agents),
            "model_catalog_digest": model_catalog_digest(catalog=self.models),
            "registry_snapshot_date": REGISTRY_SNAPSHOT_DATE,
        }


def builtin_catalogs() -> AcpCatalogs:
    """The shipped snapshot of both catalogs, with no repository additions."""
    return AcpCatalogs(agents=builtin_agent_catalog(), models=builtin_model_catalog())


def resolve_acp_catalogs(*, block: Mapping[str, Any]) -> AcpCatalogs | str:
    """Both catalogs resolved against one dispatcher block, or ONE refusal.

    A fault in EITHER catalog refuses the whole resolution rather than
    degrading to the half that parsed. A dispatch holding a valid agent catalog
    and a broken model catalog cannot resolve a single structured candidate, so
    returning it would only move the same refusal later -- past the point where
    the message can still name the configuration key.
    """
    agents = resolve_agent_catalog(block=block)
    if isinstance(agents, str):
        return agents
    models = resolve_model_catalog(block=block)
    if isinstance(models, str):
        return models
    return AcpCatalogs(agents=agents, models=models)


def catalog_snapshot_record() -> Mapping[str, str]:
    """The shipped snapshot's own record, for a journal or an operator read."""
    return builtin_catalogs().snapshot
