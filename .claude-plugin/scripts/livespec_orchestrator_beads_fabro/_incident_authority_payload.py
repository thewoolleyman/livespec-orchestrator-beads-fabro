"""Strict versioned incident authority records; caller JSON is never authority."""

# EXPEDITED_INCIDENT_RESPONSE flag: bd-ib-dzbwaq
from __future__ import annotations

import json
import re
from dataclasses import asdict, fields
from pathlib import PurePosixPath
from typing import Any, cast

from livespec_orchestrator_beads_fabro._incident_authority_types import IncidentAttempt
from livespec_orchestrator_beads_fabro._incident_carrier import (
    BranchReserved,
    HeadPublished,
    IncidentCarrier,
    decode_carrier,
    is_object_id,
)
from livespec_orchestrator_beads_fabro._incident_phases import PRE_PR_PHASES
from livespec_orchestrator_beads_fabro.effects import JsonParseFailure, parse_json

__all__: list[str] = [
    "GENESIS_MARKER",
    "HEAD_HINT_KEY",
    "TOKEN_TITLE",
    "TRANSITION_MARKER",
    "attempt_record",
    "decode_attempt",
    "decode_record",
    "query_matches",
    "unsupported_carrier",
]

GENESIS_MARKER = "livespec-incident-authority-v1\n"
TRANSITION_MARKER = "livespec-incident-transition-v1\n"
# Item metadata naming the latest closed token: where a current read starts its walk.
# A start point only, never authority; the chain's own links decide the head.
HEAD_HINT_KEY = "incident_authority_head"
TOKEN_TITLE = "livespec incident authority epoch token"  # noqa: S105 - record title
_PHASES = frozenset(
    (
        "repair",
        "master-observation",
        "reverting",
        "rollback-conflict",
        "collecting-failures",
        "repayment-admission",
        "repayment-ready",
        "repayment-active",
        "repayment-acceptance",
        "closed",
        "drill-closed",
    )
)
_TEXT_FIELDS = (
    "repository",
    "item_id",
    "attempt_id",
    "phase",
    "operation_id",
    "owner",
    "base",
    "head",
)
_QUERY_FIELDS = frozenset(("attempt_id", "phase", "operation_id", "generation", "owner"))
_ATTEMPT_FIELDS = frozenset(f.name for f in fields(IncidentAttempt))
_LEGACY_FIELDS = _ATTEMPT_FIELDS - {"carrier"}


def decode_record(*, text: object, marker: str, keys: frozenset[str]) -> dict[str, Any] | None:
    """Reject unknown schemas, extra keys, duplicate JSON keys and non-records."""
    if not isinstance(text, str) or not text.startswith(marker):
        return None
    raw = text[len(marker) :]
    value = parse_json(text=raw)
    if isinstance(value, JsonParseFailure) or not isinstance(value, dict):
        return None
    record = cast("dict[str, Any]", value)
    if frozenset(record) != keys or type(record.get("schema")) is not int or record["schema"] != 1:
        return None
    # Canonical bytes prevent duplicate keys from disappearing during decoding.
    return record if raw == json.dumps(record, sort_keys=True, separators=(",", ":")) else None


def _texts(*, raw: object, unique: bool = True) -> tuple[str, ...] | None:
    if not isinstance(raw, list) or not all(
        isinstance(v, str) and v.strip() == v and v for v in cast("list[object]", raw)
    ):
        return None
    values = tuple(cast("list[str]", raw))
    return values if not unique or len(values) == len(set(values)) else None


def _sha(*, value: str) -> bool:
    return is_object_id(value=value)


def _paths(*, values: tuple[str, ...]) -> bool:
    return bool(values) and all(
        v != "."
        and not PurePosixPath(v).is_absolute()
        and ".." not in PurePosixPath(v).parts
        and str(PurePosixPath(v)) == v
        for v in values
    )


def _valid_identity(*, row: dict[str, Any]) -> bool:
    return (
        all(isinstance(row[k], str) and row[k].strip() == row[k] and row[k] for k in _TEXT_FIELDS)
        and re.fullmatch(r"[^/\s]+/[^/\s]+", row["repository"]) is not None
        and row["phase"] in _PHASES
        and _sha(value=row["base"])
        and _sha(value=row["head"])
        and type(row["generation"]) is int
        and row["generation"] > 0
        and type(row["pr_number"]) is int
        and type(row["repayment_required"]) is bool
    )


def _pre_pr(*, row: dict[str, Any]) -> bool:
    return (
        row["pr_number"] == 0
        and row["phase"] in PRE_PR_PHASES
        and row["landed_commits"] == []
        and row["landed_trees"] == []
    )


def _pr_agrees(*, row: dict[str, Any], carrier: IncidentCarrier | None) -> bool:
    """A PR number exists exactly when the carrier is bound to one."""
    if carrier is None:
        # A schema-1 record from before the carrier model keeps its exact meaning.
        return row["pr_number"] > 0 or _pre_pr(row=row)
    if isinstance(carrier, BranchReserved | HeadPublished):
        return _pre_pr(row=row)
    return row["pr_number"] > 0


def unsupported_carrier(*, value: object) -> bool:
    """A record that names a carrier this build cannot decode needs a named refusal."""
    if not isinstance(value, dict):
        return False
    raw = cast("dict[str, object]", value).get("carrier")
    return raw is not None and decode_carrier(value=raw) is None


def decode_attempt(*, value: object) -> IncidentAttempt | None:
    """Decode the complete snapshot without accepting bools as numeric ids."""
    if not isinstance(value, dict) or frozenset(cast("dict[str, object]", value)) not in {
        _ATTEMPT_FIELDS,
        _LEGACY_FIELDS,
    }:
        return None
    row = cast("dict[str, Any]", value)
    raw_carrier = row.get("carrier")
    carrier = None if raw_carrier is None else decode_carrier(value=raw_carrier)
    if (raw_carrier is not None and carrier is None) or not _valid_identity(row=row):
        return None
    if not _pr_agrees(row=row, carrier=carrier):
        return None
    commits = _texts(raw=row["landed_commits"])
    trees = _texts(raw=row["landed_trees"], unique=False)
    paths = _texts(raw=row["original_paths"])
    deferred = _texts(raw=row["deferred_work"])
    if commits is None or trees is None or paths is None or deferred is None:
        return None
    if (
        len(commits) != len(trees)
        or not all(_sha(value=v) for v in commits + trees)
        or not _paths(values=paths)
    ):
        return None
    return IncidentAttempt(
        repository=row["repository"],
        item_id=row["item_id"],
        attempt_id=row["attempt_id"],
        phase=row["phase"],
        operation_id=row["operation_id"],
        generation=row["generation"],
        owner=row["owner"],
        base=row["base"],
        head=row["head"],
        pr_number=row["pr_number"],
        landed_commits=commits,
        landed_trees=trees,
        original_paths=paths,
        deferred_work=deferred,
        repayment_required=row["repayment_required"],
        carrier=carrier,
    )


def attempt_record(*, attempt: IncidentAttempt) -> dict[str, Any]:
    """Serialize a snapshot; a schema-1 attempt without a carrier keeps its exact bytes."""
    record = asdict(attempt)
    if attempt.carrier is None:
        del record["carrier"]
    return record


def query_matches(*, attempt: IncidentAttempt, query: dict[str, object]) -> bool:
    """A consumer must select the whole fenced identity, including its owner."""
    values = asdict(attempt)
    return frozenset(query) == _QUERY_FIELDS and all(
        type(value) is type(values[key]) and value == values[key] for key, value in query.items()
    )
