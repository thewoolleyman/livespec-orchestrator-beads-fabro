"""Where the provenance gate and the bypass audit obtain trusted incident receipts.

Both consumers LOCATE a candidate incident by the work-item id an operator
names (`--incident-item`, repeatable) and AUTHORIZE it only by reading that
item's retained authority chain through the canonical reader.  Nothing in a
label, an environment variable, a commit trailer or a code marker reaches this
module.  A named item whose chain cannot be read is a refusal the consumer
must treat as unobserved evidence — the gate exits unobservable and the audit
keeps the carrier flagged — never as the absence of a receipt.

The ledger is reached through the project's own store configuration, so the
historical verification still works once the pull request's labels and the
invocation environment that produced the repair are gone.  The CI wrappers
declare no tenant credential, so an unauthenticated read refuses with
`incident-authority-unavailable` rather than passing.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path

from livespec_orchestrator_beads_fabro._beads_client import BeadsClient, make_beads_client
from livespec_orchestrator_beads_fabro.commands._dispatcher_paths import store_config
from livespec_orchestrator_beads_fabro.commands._incident_provenance import (
    IncidentReceipt,
    receipts_from_history,
)
from livespec_orchestrator_beads_fabro.incident_authority import (
    AuthorityRefusal,
    read_incident_history,
)

__all__: list[str] = [
    "IncidentReceiptRefusal",
    "add_incident_item_argument",
    "describe_refusal",
    "incident_authority_client",
    "resolve_incident_receipts",
]


@dataclass(frozen=True, slots=True, kw_only=True)
class IncidentReceiptRefusal:
    """The named reason one incident item's retained chain could not be verified."""

    item_id: str
    code: str
    detail: str


def add_incident_item_argument(*, parser: argparse.ArgumentParser) -> None:
    """The one way a consumer names candidate incidents: explicit ids, never a title match."""
    _ = parser.add_argument(
        "--incident-item",
        dest="incident_items",
        action="append",
        default=None,
        help=(
            "a canonical incident work-item id whose retained authority chain is "
            "read for exact receipts; repeatable"
        ),
    )


def incident_authority_client(*, repo: Path, client: BeadsClient | None) -> BeadsClient:
    """The injected tenant, else the one the project at `repo` configures."""
    if client is not None:
        return client
    return make_beads_client(config=store_config(repo=repo))


def resolve_incident_receipts(
    *,
    client: BeadsClient,
    repository: str,
    item_ids: tuple[str, ...],
) -> tuple[IncidentReceipt, ...] | IncidentReceiptRefusal:
    """Every PR-bound receipt of the named items, or the first chain that refused."""
    receipts: list[IncidentReceipt] = []
    for item_id in item_ids:
        history = read_incident_history(client=client, repository=repository, item_id=item_id)
        if isinstance(history, AuthorityRefusal):
            return IncidentReceiptRefusal(item_id=item_id, code=history.code, detail=history.detail)
        receipts.extend(receipts_from_history(history=history))
    return tuple(receipts)


def describe_refusal(*, refusal: IncidentReceiptRefusal) -> str:
    """One line naming the item and the reader's refusal code."""
    return (
        f"incident item {refusal.item_id} could not be verified against its retained "
        f"authority chain: {refusal.code} ({refusal.detail})"
    )
