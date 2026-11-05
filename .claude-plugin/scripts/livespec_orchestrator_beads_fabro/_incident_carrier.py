"""Discriminated incident carrier identity before and after its PR exists.

A carrier is `branch-reserved` (an exact target ref, input parent and staged
tree, with no PR), `head-published` (that reservation plus the confirmed remote
head) or `pr-bound` (the same history plus a real positive PR number on the
attempt). Later states retain earlier identity; a carrier never regresses, never
changes its target ref and never drops out of a chain once present. This module
models and validates the state only: it neither pushes, observes a forge nor
binds a PR.
"""

# EXPEDITED_INCIDENT_RESPONSE flag: bd-ib-dzbwaq
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Literal, cast

__all__: list[str] = [
    "CARRIER_UNSUPPORTED",
    "BranchReserved",
    "HeadPublished",
    "IncidentCarrier",
    "PrBound",
    "carrier_successor_allowed",
    "decode_carrier",
    "is_object_id",
]

CARRIER_UNSUPPORTED = "incident-carrier-unsupported"


@dataclass(frozen=True, kw_only=True)
class BranchReserved:
    """The exact pre-commit boundary of a carrier that has no PR yet."""

    state: Literal["branch-reserved"] = "branch-reserved"
    target_ref: str
    input_parent: str
    staged_tree: str


@dataclass(frozen=True, kw_only=True)
class HeadPublished:
    """A confirmed first publication that still has no PR number."""

    state: Literal["head-published"] = "head-published"
    target_ref: str
    input_parent: str
    staged_tree: str
    remote_head: str


@dataclass(frozen=True, kw_only=True)
class PrBound:
    """A carrier bound to the real PR its attempt names."""

    state: Literal["pr-bound"] = "pr-bound"
    target_ref: str
    input_parent: str
    staged_tree: str
    remote_head: str


IncidentCarrier = BranchReserved | HeadPublished | PrBound

_RESERVATION = ("state", "target_ref", "input_parent", "staged_tree")
_KEYS: dict[str, frozenset[str]] = {
    "branch-reserved": frozenset(_RESERVATION),
    "head-published": frozenset((*_RESERVATION, "remote_head")),
    "pr-bound": frozenset((*_RESERVATION, "remote_head")),
}
_RANK = {"branch-reserved": 0, "head-published": 1, "pr-bound": 2}


def is_object_id(*, value: object) -> bool:
    """A full lowercase SHA-1 or SHA-256 Git object id."""
    return (
        isinstance(value, str) and re.fullmatch(r"(?:[0-9a-f]{40}|[0-9a-f]{64})", value) is not None
    )


def _target_ref(*, value: object) -> bool:
    if not isinstance(value, str) or not value.startswith("refs/heads/"):
        return False
    name = value[len("refs/heads/") :]
    return (
        bool(name)
        and re.fullmatch(r"[A-Za-z0-9._/-]+", name) is not None
        and ".." not in name
        and "//" not in name
        and not name.startswith("/")
        and not name.endswith(("/", ".", ".lock"))
    )


def decode_carrier(*, value: object) -> IncidentCarrier | None:
    """Decode one exact carrier record; an unknown state or key is unsupported."""
    if not isinstance(value, dict):
        return None
    row = cast("dict[str, Any]", value)
    state = row.get("state")
    if not isinstance(state, str) or state not in _KEYS or frozenset(row) != _KEYS[state]:
        return None
    ids = [row["input_parent"], row["staged_tree"]]
    if state != "branch-reserved":
        ids.append(row["remote_head"])
    if not _target_ref(value=row["target_ref"]) or not all(is_object_id(value=v) for v in ids):
        return None
    if state == "branch-reserved":
        return BranchReserved(
            target_ref=row["target_ref"],
            input_parent=row["input_parent"],
            staged_tree=row["staged_tree"],
        )
    published = {
        "target_ref": row["target_ref"],
        "input_parent": row["input_parent"],
        "staged_tree": row["staged_tree"],
        "remote_head": row["remote_head"],
    }
    return HeadPublished(**published) if state == "head-published" else PrBound(**published)


def carrier_successor_allowed(
    *,
    before: IncidentCarrier | None,
    after: IncidentCarrier | None,
    before_pr: int,
    after_pr: int,
) -> bool:
    """A successor may advance a carrier but never regress or rewrite its history."""
    if before is None:
        return True
    if after is None or _RANK[after.state] < _RANK[before.state]:
        return False
    if after.target_ref != before.target_ref:
        return False
    refreshed_reservation = before.state == after.state == "branch-reserved"
    if not refreshed_reservation and (after.input_parent, after.staged_tree) != (
        before.input_parent,
        before.staged_tree,
    ):
        return False
    return before.state != "pr-bound" or after_pr == before_pr
