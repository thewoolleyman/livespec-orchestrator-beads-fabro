"""The shape of a recovery-attempt record, and the grade of bytes that claim to be one.

Split from `_session_recovery_records` by cohesion: that module owns the
TRANSITIONS a consumer writes, and this one owns what a record IS — the schema
version it carries, the fields it must hold, and the three ways bytes can fail
to be one. The two questions have different readers, and keeping the grade here
means every unusable shape can be exercised without writing a store.

WHY A MISSING FIELD IS INVALID RATHER THAN DEFAULTED. `contracts.md` section
"Launch obligations and consumed recovery" makes the epoch, the original
deadline and the generation authority a consumer READS rather than supplies, so
a record missing one is a record this build cannot grade: defaulting the
generation to zero would hand a stale consumer a fresh-looking claim, and
defaulting the deadline would invent the bound the whole clause is about.

WHY THE THREE DIAGNOSTICS ARE KEPT APART. An unreadable FILE, bytes that are not
a record, and a record from a schema this build does not know have three
different remedies — a permission or device fault, a corrupted write, and a
build older than its store. Collapsing them reports one as another and points
the reader at the wrong fix, which is the failure mode the same section names
when it insists unreadable authority be "unobservable, not no obligations".
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import cast

__all__: list[str] = [
    "DIAGNOSTIC_INVALID_RECORD",
    "DIAGNOSTIC_UNREADABLE_RECORD",
    "DIAGNOSTIC_UNSUPPORTED_SCHEMA",
    "RECOVERY_SCHEMA_VERSION",
    "RecoveryRead",
    "graded_recovery_payload",
]

RECOVERY_SCHEMA_VERSION = 1

DIAGNOSTIC_UNREADABLE_RECORD = "unreadable-record"
DIAGNOSTIC_INVALID_RECORD = "invalid-record"
DIAGNOSTIC_UNSUPPORTED_SCHEMA = "unsupported-schema"

# Every field a version-1 record carries. This tuple IS the schema: a payload
# missing one of these names, or holding it at another type, is a record this
# build cannot grade rather than one it may read halfway.
_REQUIRED_FIELDS = frozenset(
    {
        "attempt_id",
        "duplicate_count",
        "effect",
        "fenced_count",
        "generation",
        "holder",
        "lease_expires_at",
        "operation_id",
        "original_deadline",
        "required_result_identity",
        "result_epoch",
        "transitions",
    }
)


@dataclass(frozen=True, kw_only=True)
class RecoveryRead:
    """One attempt as read: its payload, or the reason there is none.

    The two fields are never both populated. A caller distinguishes an absent
    record from an unreadable one by the diagnostic rather than by the payload,
    because both carry no payload and only one of them means "no attempt was
    ever opened here".
    """

    payload: dict[str, object] | None
    diagnostic: str | None


def graded_recovery_payload(*, loaded: object) -> RecoveryRead:
    """Grade one already-decoded JSON value as a version-1 attempt record."""
    if not isinstance(loaded, dict):
        return RecoveryRead(payload=None, diagnostic=DIAGNOSTIC_INVALID_RECORD)
    payload = cast("dict[str, object]", loaded)
    if payload.get("schema_version") != RECOVERY_SCHEMA_VERSION:
        return RecoveryRead(payload=None, diagnostic=DIAGNOSTIC_UNSUPPORTED_SCHEMA)
    if not _well_formed(payload=payload):
        return RecoveryRead(payload=None, diagnostic=DIAGNOSTIC_INVALID_RECORD)
    return RecoveryRead(payload=payload, diagnostic=None)


def _well_formed(*, payload: dict[str, object]) -> bool:
    """Whether a version-1 record carries every field at an indexable type."""
    return all(
        (
            payload.keys() >= _REQUIRED_FIELDS,
            isinstance(payload.get("attempt_id"), str),
            isinstance(payload.get("original_deadline"), str),
            isinstance(payload.get("required_result_identity"), str),
            isinstance(payload.get("transitions"), list),
            _is_count(value=payload.get("duplicate_count")),
            _is_count(value=payload.get("fenced_count")),
            _is_count(value=payload.get("generation")),
            _is_count(value=payload.get("result_epoch")),
        )
    )


def _is_count(*, value: object) -> bool:
    """Whether a field holds a real nonnegative integer.

    `bool` is excluded explicitly because it is an `int` subclass, so `True`
    would otherwise read as generation one — a well-typed record carrying a
    generation no consumer ever claimed.
    """
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0
