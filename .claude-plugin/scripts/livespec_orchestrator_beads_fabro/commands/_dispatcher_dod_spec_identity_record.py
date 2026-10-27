"""Definition-of-Done spec-identity receipt rendering and reading."""

from __future__ import annotations

import hashlib
from collections.abc import Sequence
from dataclasses import dataclass

from livespec_orchestrator_beads_fabro.commands._dispatcher_dod_judgement_markers import (
    JUDGEMENT_COMMENT_MARKER,
    comment_marker,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_dod_spec_identity import SpecIdentity

__all__: list[str] = [
    "SPEC_IDENTITY_BLOCK_HEADING",
    "RecordedSpecIdentity",
    "identity_record_lines",
    "recorded_spec_identity",
    "spec_identity_block",
]

_FIELD_SEPARATOR = ": "
_FORM_FIELD = "spec-identity-form"
_VALUE_FIELD = "spec-identity"
_CLAUSE_PATH_FIELD = "spec-clause-path"
_CLAUSE_HEADING_FIELD = "spec-clause-heading"
_CLAUSE_DIGEST_FIELD = "spec-clause-digest"
_REPEATED_FIELDS = frozenset({_CLAUSE_PATH_FIELD, _CLAUSE_HEADING_FIELD, _CLAUSE_DIGEST_FIELD})

SPEC_IDENTITY_BLOCK_HEADING = "## Definition-of-Done spec identity (from the pre-dispatch taking)"
_UNOBSERVED_BODY = (
    "(no pre-dispatch Definition-of-Done spec identity was recorded; use the whole-tree identity)"
)


@dataclass(frozen=True, kw_only=True)
class RecordedSpecIdentity:
    """The form, value, and digest-addressed clause provenance of one taking."""

    form: str
    value: str
    provenance: tuple[tuple[str, str, str], ...] = ()


def identity_record_lines(*, identity: SpecIdentity) -> list[str]:
    """Render the compact, complete identity receipt a ledger comment carries."""
    lines = [
        f"{_FORM_FIELD}{_FIELD_SEPARATOR}{identity.form}",
        f"{_VALUE_FIELD}{_FIELD_SEPARATOR}{identity.value}",
    ]
    for clause in identity.provenance:
        lines.extend(
            (
                f"{_CLAUSE_PATH_FIELD}{_FIELD_SEPARATOR}{clause.path}",
                f"{_CLAUSE_HEADING_FIELD}{_FIELD_SEPARATOR}{clause.heading}",
                f"{_CLAUSE_DIGEST_FIELD}{_FIELD_SEPARATOR}sha256:{hashlib.sha256(clause.body).hexdigest()}",
            )
        )
    return lines


def recorded_spec_identity(*, comments: Sequence[str]) -> RecordedSpecIdentity | None:
    """Read the newest complete identity receipt, failing closed on partial provenance."""
    for body in reversed(tuple(comments)):
        if comment_marker(body=body) != JUDGEMENT_COMMENT_MARKER:
            continue
        fields = _fields(body=body)
        form, value = fields.get(_FORM_FIELD), fields.get(_VALUE_FIELD)
        if form is None or value is None:
            return None
        paths = _repeated(body=body, key=_CLAUSE_PATH_FIELD)
        headings = _repeated(body=body, key=_CLAUSE_HEADING_FIELD)
        digests = _repeated(body=body, key=_CLAUSE_DIGEST_FIELD)
        if form == "tree":
            return RecordedSpecIdentity(form=form, value=value)
        if form != "clauses" or not paths or len({len(paths), len(headings), len(digests)}) != 1:
            return None
        return RecordedSpecIdentity(
            form=form,
            value=value,
            provenance=tuple(zip(paths, headings, digests, strict=True)),
        )
    return None


def spec_identity_block(*, identity: RecordedSpecIdentity | None) -> str:
    """Render the supplied identity for the run's gate, absence included."""
    if identity is None:
        return f"{SPEC_IDENTITY_BLOCK_HEADING}\n{_UNOBSERVED_BODY}"
    lines = [
        SPEC_IDENTITY_BLOCK_HEADING,
        f"form{_FIELD_SEPARATOR}{identity.form}",
        f"identity{_FIELD_SEPARATOR}{identity.value}",
    ]
    lines.extend("clause provenance: " + " | ".join(one) for one in identity.provenance)
    return "\n".join(lines)


def _fields(*, body: str) -> dict[str, str]:
    fields: dict[str, str] = {}
    for raw in body.splitlines():
        key, separator, value = raw.strip().partition(_FIELD_SEPARATOR)
        if separator and key not in _REPEATED_FIELDS:
            fields[key] = value
    return fields


def _repeated(*, body: str, key: str) -> tuple[str, ...]:
    prefix = f"{key}{_FIELD_SEPARATOR}"
    return tuple(
        raw.strip()[len(prefix) :] for raw in body.splitlines() if raw.strip().startswith(prefix)
    )
