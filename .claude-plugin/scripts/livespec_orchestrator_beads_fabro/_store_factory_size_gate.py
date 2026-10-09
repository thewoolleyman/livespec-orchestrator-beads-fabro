"""Ledger mutation for a factory-size decomposition route."""

from __future__ import annotations

from typing import TYPE_CHECKING

from livespec_orchestrator_beads_fabro._beads_client import make_beads_client

if TYPE_CHECKING:
    from livespec_orchestrator_beads_fabro.types import StoreConfig

__all__: list[str] = ["route_factory_size_decomposition"]


def route_factory_size_decomposition(*, path: StoreConfig, work_item_id: str, reason: str) -> None:
    """Move one oversized item to backlog and retain the auditable reason."""
    client = make_beads_client(config=path)
    client.update_issue(issue_id=work_item_id, status="backlog")
    client.add_comment(issue_id=work_item_id, body=reason)
