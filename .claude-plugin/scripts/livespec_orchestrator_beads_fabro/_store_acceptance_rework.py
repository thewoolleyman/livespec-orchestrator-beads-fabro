"""Ledger persistence for failed AI acceptance-pass rework state."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, cast

from livespec_orchestrator_beads_fabro._beads_client import make_beads_client

if TYPE_CHECKING:
    from livespec_orchestrator_beads_fabro.types import StoreConfig

__all__: list[str] = [
    "AcceptanceFailureState",
    "update_acceptance_failed_ai_passes",
]

_META_ACCEPTANCE_FAILED_AI_PASSES = "acceptance_failed_ai_passes"


@dataclass(frozen=True, kw_only=True)
class AcceptanceFailureState:
    """Persisted AI-acceptance failure state read from the ledger row."""

    failed_ai_passes: int
    raw_labels: tuple[str, ...]


def update_acceptance_failed_ai_passes(
    *, path: StoreConfig, item_id: str
) -> AcceptanceFailureState:
    """Increment and persist this item's failed AI acceptance-pass count."""
    client = make_beads_client(config=path)
    record = client.show_issue(issue_id=item_id)
    metadata = dict(cast("dict[str, Any]", record.get("metadata", {})))
    failed_ai_passes = _non_negative_int(value=metadata.get(_META_ACCEPTANCE_FAILED_AI_PASSES)) + 1
    metadata[_META_ACCEPTANCE_FAILED_AI_PASSES] = failed_ai_passes
    client.update_issue(issue_id=item_id, metadata=metadata)
    return AcceptanceFailureState(
        failed_ai_passes=failed_ai_passes,
        raw_labels=_raw_labels(record=record),
    )


def _raw_labels(*, record: dict[str, Any]) -> tuple[str, ...]:
    labels = cast("list[Any]", record.get("labels", []))
    return tuple(label for label in labels if isinstance(label, str))


def _non_negative_int(*, value: object) -> int:
    if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
        return value
    return 0
