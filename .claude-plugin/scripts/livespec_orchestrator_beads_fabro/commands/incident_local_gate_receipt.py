"""Persist immutable partial hook evidence on its canonical incident item.

Receipt comments are evidence, never generation authority or normal proof.
Server append preserves concurrent writes; identity is re-read after insertion.
"""

# EXPEDITED_INCIDENT_RESPONSE flag: bd-ib-dzbwaq
from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import asdict, dataclass
from typing import TYPE_CHECKING, Any, BinaryIO, cast

from returns.io import impure_safe
from returns.pipeline import is_successful
from returns.unsafe import unsafe_perform_io

from livespec_orchestrator_beads_fabro._incident_authority_payload import attempt_record
from livespec_orchestrator_beads_fabro._incident_authority_types import (
    AuthorityRefusal,
    IncidentReading,
)
from livespec_orchestrator_beads_fabro.effects import parse_json
from livespec_orchestrator_beads_fabro.effects._incident_authority_reader import read_authority

if TYPE_CHECKING:
    from livespec_orchestrator_beads_fabro._beads_client import BeadsClient

__all__: list[str] = [
    "LocalGateReceipt",
    "current_receipt_authority",
    "decode_receipt",
    "matching_receipts",
    "read_receipt_stream",
    "receipt_body",
    "receipt_mapping",
    "record_local_gates",
]
MARKER = "livespec-incident-local-gates-v1\n"
_RECEIPT_KEYS = frozenset(
    ("receipt_id", "hook", "tree", "mode", "evidence_kind", "exit_status", "results")
)
_RESULT_KEYS = frozenset(("name", "status", "reason", "returncode", "duration_seconds", "output"))
_MAX_BYTES = 1048576
_MAX_SECONDS = 60
_MAX_EXIT = 255


@dataclass(frozen=True, kw_only=True)
class LocalGateReceipt:
    """Verified persistence, with no authority to perform a current side effect."""

    receipt_id: str
    checksum: str
    committed_token_id: str
    current_token_id: str


def read_receipt_stream(*, stream: BinaryIO) -> str:
    """Read a receipt from a byte stream, holding at most one byte past the size bound.

    A receipt supplied on a stream is not limited by the 128 KiB argv entry cap,
    so the authority's own bound is the only limit. Reading one byte past it is
    enough for `decode_receipt` to refuse an oversize receipt, and it keeps an
    unbounded producer from filling memory. Bytes that are not UTF-8 become
    replacement characters, which the canonical-text comparison then refuses.
    """
    return stream.read(_MAX_BYTES + 1).decode("utf-8", "replace")


def receipt_mapping(*, value: object) -> dict[str, Any]:
    """Interpret a receipt field without accepting a non-mapping value."""
    return cast("dict[str, Any]", value) if isinstance(value, dict) else {}


def _valid_result(*, raw: object) -> bool:
    row = receipt_mapping(value=raw)
    if frozenset(row) != _RESULT_KEYS:
        return False
    if not all(isinstance(row[k], str) and row[k] for k in ("name", "reason")) or not isinstance(
        row["output"], str
    ):
        return False
    duration, code, status = row["duration_seconds"], row["returncode"], row["status"]
    if (
        type(duration) not in {int, float}
        or not math.isfinite(duration)
        or duration < 0
        or not isinstance(status, str)
    ):
        return False
    if status == "passed":
        return type(code) is int and code == 0 and duration < _MAX_SECONDS
    if status == "failed":
        return type(code) is int and code != 0
    return (
        (status == "deferred" and duration == 0)
        or (status == "deferred-timeout" and duration >= _MAX_SECONDS)
    ) and code is None


def decode_receipt(*, text: str, observed: IncidentReading) -> dict[str, Any] | None:
    """Validate canonical partial results against their observed incident phase."""
    if len(text.encode("utf-8", "surrogatepass")) > _MAX_BYTES:
        return None
    value = receipt_mapping(value=parse_json(text=text))
    if frozenset(value) != _RECEIPT_KEYS or text != json.dumps(
        value, sort_keys=True, separators=(",", ":")
    ):
        return None
    phase = observed.attempt.phase
    mode = (
        "expedited-repair"
        if phase == "repair"
        else "emergency-revert"
        if phase == "reverting"
        else None
    )
    if (
        mode is None
        or value["mode"] != mode
        or not isinstance(value["receipt_id"], str)
        or not value["receipt_id"].strip()
        or not isinstance(value["hook"], str)
        or value["hook"] not in {"pre-commit", "commit-msg", "pre-push"}
        or not isinstance(value["tree"], str)
        or re.fullmatch(r"(?:[0-9a-f]{40}|[0-9a-f]{64})", value["tree"]) is None
        or value["evidence_kind"] != "expedited-local-partial"
        or type(value["exit_status"]) is not int
        or not 0 <= value["exit_status"] <= _MAX_EXIT
        or not isinstance(value["results"], list)
        or not value["results"]
    ):
        return None
    rows = cast("list[dict[str, Any]]", value["results"])
    if not all(_valid_result(raw=row) for row in rows) or len({r["name"] for r in rows}) != len(
        rows
    ):
        return None
    expected = next((row["returncode"] for row in rows if row["returncode"]), 0)
    expected = expected if expected >= 0 else 128 - expected
    valid = value["exit_status"] == expected and (
        mode != "emergency-revert" or all(row["status"] == "deferred" for row in rows)
    )
    return value if valid else None


def current_receipt_authority(
    *, client: BeadsClient, observed: IncidentReading
) -> IncidentReading | AuthorityRefusal:
    """Re-read the exact current identity for an evidence operation."""
    attempt = observed.attempt
    current = read_authority(
        client=client,
        repository=attempt.repository,
        item_id=attempt.item_id,
        query={
            key: asdict(attempt)[key]
            for key in ("attempt_id", "phase", "operation_id", "generation", "owner")
        },
        historical=False,
    )
    if isinstance(current, AuthorityRefusal):
        return current
    return (
        current
        if current == observed and observed.is_current
        else AuthorityRefusal(code="incident-receipt-stale-observation", detail=attempt.item_id)
    )


def matching_receipts(
    *, client: BeadsClient, observed: IncidentReading, receipt_id: str
) -> set[str]:
    """Read every distinct retained canonical comment naming one receipt id."""
    matches: set[str] = set()
    for row in client.list_comments(issue_id=observed.attempt.item_id):
        text = row.get("text")
        if not isinstance(text, str) or not text.startswith(MARKER):
            continue
        record = receipt_mapping(value=parse_json(text=text[len(MARKER) :]))
        receipt = receipt_mapping(value=record.get("receipt"))
        if receipt.get("receipt_id") == receipt_id:
            matches.add(text)
    return matches


def receipt_body(*, observed: IncidentReading, receipt: dict[str, Any]) -> str:
    """Encode the full immutable envelope shared by append and readback."""
    return MARKER + json.dumps(
        dict(
            schema=1,
            attempt=attempt_record(attempt=observed.attempt),
            committed_token_id=observed.committed_token_id,
            current_token_id=observed.current_token_id,
            receipt=receipt,
            normal_factory_proof=False,
        ),
        sort_keys=True,
        separators=(",", ":"),
    )


@impure_safe
def _record(
    *, client: BeadsClient, observed: IncidentReading, text: str
) -> LocalGateReceipt | AuthorityRefusal:
    value = decode_receipt(text=text, observed=observed)
    if value is None:
        return AuthorityRefusal(code="incident-receipt-invalid", detail=observed.attempt.item_id)
    current = current_receipt_authority(client=client, observed=observed)
    if isinstance(current, AuthorityRefusal):
        return current
    body = receipt_body(observed=observed, receipt=value)
    matches = matching_receipts(client=client, observed=observed, receipt_id=value["receipt_id"])
    if matches and matches != {body}:
        return AuthorityRefusal(
            code="incident-receipt-operation-conflict", detail=value["receipt_id"]
        )
    if not matches:
        client.add_comment(issue_id=observed.attempt.item_id, body=body)
    if matching_receipts(client=client, observed=observed, receipt_id=value["receipt_id"]) != {
        body
    }:
        return AuthorityRefusal(
            code="incident-receipt-readback-conflict", detail=value["receipt_id"]
        )
    standing = current_receipt_authority(client=client, observed=observed)
    if isinstance(standing, AuthorityRefusal):
        return standing
    return LocalGateReceipt(
        receipt_id=value["receipt_id"],
        checksum="sha256:" + hashlib.sha256(body.encode()).hexdigest(),
        committed_token_id=observed.committed_token_id,
        current_token_id=observed.current_token_id,
    )


def record_local_gates(
    *, client: BeadsClient, observed: IncidentReading, text: str
) -> LocalGateReceipt | AuthorityRefusal:
    """Append/read back exact evidence; outages and stale observations refuse."""
    result = _record(client=client, observed=observed, text=text)
    if not is_successful(result):
        error = unsafe_perform_io(result.failure())
        return AuthorityRefusal(code="incident-receipt-unavailable", detail=str(error))
    return unsafe_perform_io(result.unwrap())
