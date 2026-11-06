"""The value types of the factory-bypass audit: its policy, findings, exceptions and report."""

from __future__ import annotations

from dataclasses import dataclass

from livespec_orchestrator_beads_fabro.commands._factory_bypass_product_paths import (
    ProductPathPolicy,
)
from livespec_orchestrator_beads_fabro.commands._incident_provenance import IncidentReceipt

__all__: list[str] = ["AuditPolicy", "AuditReport", "BypassFinding", "RecordedException"]


@dataclass(frozen=True, slots=True, kw_only=True)
class AuditPolicy:
    """The audit's two axes: what counts as product code, and who is never flagged."""

    factory_app_login: str
    allow_authors: frozenset[str]
    allow_labels: frozenset[str]
    product_paths: ProductPathPolicy
    repository: str = ""
    incident_receipts: tuple[IncidentReceipt, ...] = ()


@dataclass(frozen=True, slots=True, kw_only=True)
class BypassFinding:
    """A merged PR that changed product code without going through the factory."""

    number: int
    title: str
    author_login: str
    product_paths: tuple[str, ...]


@dataclass(frozen=True, slots=True, kw_only=True)
class RecordedException:
    """A recorded exception, including whether normal repayment remains outstanding."""

    number: int
    title: str
    author_login: str
    item_id: str = ""
    repayment_outstanding: bool = False


@dataclass(frozen=True, slots=True, kw_only=True)
class AuditReport:
    """The audit outcome: how many PRs were scanned, which were flagged, which were declared."""

    scanned: int
    findings: tuple[BypassFinding, ...]
    exceptions: tuple[RecordedException, ...]
