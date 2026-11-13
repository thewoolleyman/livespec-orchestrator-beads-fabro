"""The lifecycle adapter for the incident writer's recorded-drill close action."""

from __future__ import annotations

import argparse
from typing import TYPE_CHECKING

from livespec_orchestrator_beads_fabro._incident_authority_types import (
    AuthorityRefusal,
    IncidentReading,
)
from livespec_orchestrator_beads_fabro.incident_drill_close import DrillClose, close_drill

if TYPE_CHECKING:
    from livespec_orchestrator_beads_fabro._beads_client import BeadsClient
    from livespec_orchestrator_beads_fabro.commands._dispatcher_engine_types import CommandRunner

__all__: list[str] = ["run_drill_close"]


def run_drill_close(
    *,
    args: argparse.Namespace,
    client: BeadsClient,
    reading: IncidentReading,
    runner: CommandRunner,
) -> DrillClose | AuthorityRefusal:
    """Run the drill-only close action against the fenced lifecycle identity."""
    return close_drill(
        client=client,
        reading=reading,
        runner=runner,
        repo=args.repo,
        repository=args.repository,
    )
