"""Server-mediated compare-and-swap protocol for dispatch claim writes."""

from __future__ import annotations

import json
import time
from collections.abc import Callable, MutableMapping
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, cast

from livespec_orchestrator_beads_fabro.commands._plan_epoch_tokens import (
    attempt_close,
    token_reading,
)

if TYPE_CHECKING:
    from livespec_orchestrator_beads_fabro._beads_client import BeadsClient, BeadsRecord

__all__: list[str] = [
    "CLAIM_TOKEN_METADATA_KEY",
    "ClaimChangeResult",
    "change_claim",
    "create_claim_token",
]

CLAIM_TOKEN_METADATA_KEY = "dispatch_claim_token"  # noqa: S105 - metadata key

_CLAIM_TOKEN_LABEL = "claim-token"  # noqa: S105 - record label
_CLOSE_REASON_KIND = "claim-token-transition"
_DISCARD_REASON_KIND = "claim-token-discard"
_LEASE_SECONDS = 120.0
_TRANSITION_WAIT_SECONDS = 180.0


@dataclass(frozen=True, kw_only=True)
class ClaimChangeResult:
    """The guarded write's observable protocol outcome."""

    outcome: str
    successor_token_id: str | None = None


def create_claim_token(*, client: BeadsClient) -> str:
    """Mint an open, server-assigned successor record labelled ``claim-token``."""
    token_id = client.create_no_history_issue(
        title="livespec dispatch claim token",
        description="Single-use dispatch-claim token; never a work item.",
    )
    client.update_issue(issue_id=token_id, add_labels=[_CLAIM_TOKEN_LABEL])
    return token_id


def change_claim(  # noqa: PLR0911, PLR0913
    *,
    client: BeadsClient,
    work_item_id: str,
    writer: str,
    intent: str,
    claim_tokens: bool,
    status: str | None = None,
    assignee: str | None = None,
    clear_assignee: bool = False,
    add_labels: list[str] | None = None,
    remove_labels: list[str] | None = None,
    metadata: dict[str, Any] | None = None,
    clock: Callable[[], float] = time.monotonic,
    transition_observations: MutableMapping[tuple[str, str, str], float] | None = None,
) -> ClaimChangeResult:
    """Write an item only after the caller owns its current claim token."""
    update = _update_arguments(
        work_item_id=work_item_id,
        status=status,
        assignee=assignee,
        clear_assignee=clear_assignee,
        add_labels=add_labels,
        remove_labels=remove_labels,
        metadata=metadata,
    )
    if not claim_tokens:
        client.update_issue(**update)
        return ClaimChangeResult(outcome="applied")

    record = client.show_issue(issue_id=work_item_id)
    token_id = _current_token(record=record)
    if token_id is None:
        return ClaimChangeResult(outcome="claim-token-missing")
    takeover = _takeover_token(
        client=client,
        work_item_id=work_item_id,
        token_id=token_id,
        clock=clock,
        observations=transition_observations if transition_observations is not None else {},
    )
    if isinstance(takeover, ClaimChangeResult):
        return takeover
    token_id, record, taking_over = takeover

    successor = create_claim_token(client=client)
    started = clock()
    close_reason = _close_reason(writer=writer, intent=intent, successor=successor)
    attempt_close(client=client, token_id=token_id, reason=close_reason)
    verdict = token_reading(client=client, token_id=token_id)
    if verdict.close_reason != close_reason:
        _discard_claim_token(client=client, token_id=successor, writer=writer)
        return ClaimChangeResult(
            outcome="claim-unobservable" if verdict.close_reason is None else "claim-changed"
        )
    if clock() - started >= _LEASE_SECONDS:
        return ClaimChangeResult(outcome="claim-lease-expired", successor_token_id=successor)
    if taking_over:
        record = _stand_down_if_original_writer_landed(
            client=client,
            work_item_id=work_item_id,
            token_id=token_id,
            successor=successor,
            writer=writer,
        )
        if record is None:
            return ClaimChangeResult(outcome="claim-changed")

    update["metadata"] = _with_successor(record=record, metadata=metadata, successor=successor)
    client.update_issue(**update)
    return ClaimChangeResult(outcome="applied", successor_token_id=successor)


def _takeover_token(
    *,
    client: BeadsClient,
    work_item_id: str,
    token_id: str,
    clock: Callable[[], float],
    observations: MutableMapping[tuple[str, str, str], float],
) -> tuple[str, BeadsRecord, bool] | ClaimChangeResult:
    """Return the current token, or wait/stand down on a stranded transition."""
    reading = token_reading(client=client, token_id=token_id)
    record = client.show_issue(issue_id=work_item_id)
    if not reading.closed:
        return token_id, record, False
    successor = _successor_from_reason(reason=reading.close_reason)
    if successor is None:
        return ClaimChangeResult(outcome="claim-unobservable")
    observation_key = (work_item_id, token_id, successor)
    first_seen = observations.setdefault(observation_key, clock())
    if clock() - first_seen < _TRANSITION_WAIT_SECONDS:
        return ClaimChangeResult(outcome="claim-transition-pending")
    if _current_token(record=record) != token_id:
        return ClaimChangeResult(outcome="claim-changed")
    reread = token_reading(client=client, token_id=token_id)
    if not reread.closed or _successor_from_reason(reason=reread.close_reason) != successor:
        return ClaimChangeResult(outcome="claim-changed")
    return successor, record, True


def _stand_down_if_original_writer_landed(
    *, client: BeadsClient, work_item_id: str, token_id: str, successor: str, writer: str
) -> BeadsRecord | None:
    """Avoid overwriting the delayed item write that made the transition current."""
    record = client.show_issue(issue_id=work_item_id)
    if _current_token(record=record) != token_id:
        return record
    _discard_claim_token(client=client, token_id=successor, writer=writer)
    return None


def _update_arguments(  # noqa: PLR0913
    *,
    work_item_id: str,
    status: str | None,
    assignee: str | None,
    clear_assignee: bool,
    add_labels: list[str] | None,
    remove_labels: list[str] | None,
    metadata: dict[str, Any] | None,
) -> dict[str, Any]:
    return {
        "issue_id": work_item_id,
        "status": status,
        "assignee": assignee,
        "clear_assignee": clear_assignee,
        "add_labels": add_labels,
        "remove_labels": remove_labels,
        "metadata": metadata,
    }


def _with_successor(
    *, record: BeadsRecord, metadata: dict[str, Any] | None, successor: str
) -> dict[str, Any]:
    merged = _metadata_of(record=record)
    if metadata is not None:
        merged.update(metadata)
    merged[CLAIM_TOKEN_METADATA_KEY] = successor
    return merged


def _current_token(*, record: BeadsRecord) -> str | None:
    return _text(value=_metadata_of(record=record).get(CLAIM_TOKEN_METADATA_KEY))


def _close_reason(*, writer: str, intent: str, successor: str) -> str:
    return json.dumps(
        {
            "kind": _CLOSE_REASON_KIND,
            "writer": writer,
            "intent": intent,
            "successor": successor,
            "closed_at": datetime.now(timezone.utc).isoformat(),
        },
        separators=(",", ":"),
        sort_keys=True,
    )


def _successor_from_reason(*, reason: str | None) -> str | None:
    try:
        parsed = json.loads(reason) if reason is not None else None
    except json.JSONDecodeError:
        return None
    if not isinstance(parsed, dict):
        return None
    parsed_mapping = cast("dict[str, object]", parsed)
    if parsed_mapping.get("kind") != _CLOSE_REASON_KIND:
        return None
    return _text(value=parsed_mapping.get("successor"))


def _discard_claim_token(*, client: BeadsClient, token_id: str, writer: str) -> None:
    attempt_close(
        client=client,
        token_id=token_id,
        reason=json.dumps(
            {"kind": _DISCARD_REASON_KIND, "writer": writer},
            separators=(",", ":"),
            sort_keys=True,
        ),
    )


def _metadata_of(*, record: BeadsRecord) -> dict[str, Any]:
    raw = record.get("metadata")
    return dict(cast("dict[str, Any]", raw)) if isinstance(raw, dict) else {}


def _text(*, value: object) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() != "" else None
