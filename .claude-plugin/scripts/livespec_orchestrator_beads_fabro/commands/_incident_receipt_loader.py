"""The production source of trusted incident receipts for the provenance consumers.

Both the factory-provenance gate and the retrospective bypass audit judge a pull
request against receipts returned by the canonical incident-authority reader.
This module is the one place those receipts are loaded, so neither consumer can
default to an empty set. A ledger that cannot be read is a named refusal, never
"no receipts": a gauge that reads as empty when blinded would turn every
unreadable authority into a clean verdict.
"""

# EXPEDITED_INCIDENT_RESPONSE flag: bd-ib-y7ryj3
from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING

from livespec_orchestrator_beads_fabro._beads_client import make_beads_client
from livespec_orchestrator_beads_fabro.commands._dispatcher_paths import store_config
from livespec_orchestrator_beads_fabro.commands._incident_provenance import (
    IncidentReceipt,
    receipt_from_authority_reading,
)
from livespec_orchestrator_beads_fabro.errors import (
    BeadsCommandError,
    BeadsConnectionError,
    BeadsCredentialMissingError,
    BeadsMappingError,
    BeadsTenantMissingError,
    ConnectionPrefixMissingError,
    LivespecConfigUnreadableError,
)
from livespec_orchestrator_beads_fabro.incident_authority import (
    AuthorityRefusal,
    read_incident_history,
)

if TYPE_CHECKING:
    from livespec_orchestrator_beads_fabro._beads_client import BeadsClient

__all__: list[str] = [
    "ReceiptLoader",
    "load_retained_receipts",
    "read_retained_receipts",
    "refusal_text",
    "resolve_receipts",
]

ReceiptLoader = Callable[..., "tuple[IncidentReceipt, ...] | AuthorityRefusal"]


def read_retained_receipts(
    *, client: BeadsClient, repository: str | None
) -> tuple[IncidentReceipt, ...] | AuthorityRefusal:
    """Every exact repayable repair or revert exception the retained chains record."""
    readings = read_incident_history(client=client, repository=repository)
    if isinstance(readings, AuthorityRefusal):
        return readings
    receipts = (receipt_from_authority_reading(reading=reading) for reading in readings)
    return tuple(receipt for receipt in receipts if receipt is not None)


def load_retained_receipts(
    *, repo: Path, repository: str | None
) -> tuple[IncidentReceipt, ...] | AuthorityRefusal:
    """Open the repository's own tenant and read its retained receipts, or refuse by name."""
    try:
        client = make_beads_client(config=store_config(repo=repo))
        return read_retained_receipts(client=client, repository=repository)
    except (
        BeadsCommandError,
        BeadsConnectionError,
        BeadsCredentialMissingError,
        BeadsMappingError,
        BeadsTenantMissingError,
        ConnectionPrefixMissingError,
        LivespecConfigUnreadableError,
    ) as exc:
        return AuthorityRefusal(code="incident-authority-unavailable", detail=str(exc))


def refusal_text(*, refusal: AuthorityRefusal) -> str:
    """The operator-facing line naming why retained receipts could not be read."""
    return (
        f"could not read the retained incident receipts ({refusal.code}: {refusal.detail}), "
        "so it refuses rather than treating an unreadable ledger as having no exceptions.\n"
    )


def resolve_receipts(
    *,
    declared: tuple[IncidentReceipt, ...] | None,
    needed: bool,
    loader: ReceiptLoader,
    repo: Path,
    repository: str | None,
) -> tuple[IncidentReceipt, ...] | AuthorityRefusal:
    """Declared receipts, else the retained ones, read only when the verdict could use them."""
    if declared is not None:
        return declared
    return loader(repo=repo, repository=repository) if needed else ()
