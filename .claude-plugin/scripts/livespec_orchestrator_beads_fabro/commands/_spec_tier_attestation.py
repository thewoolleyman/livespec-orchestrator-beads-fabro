"""A human's attestation that an existing clause states a held item's behaviour.

The autonomy-tier bullet of `SPECIFICATION/contracts.md` gives a held
spec-change-tier item "a human way through that needs no ratification and no
agreeing model run", because the judgement can miss a clause the ratified
specification already carries. The human names an existing H2 heading and
attests that it states the item's asked-for behaviour; this module is that
attestation's LEDGER RECORD and the reading that decides whether it still
stands.

THE ATTESTATION IS A HUMAN OVERRIDE, NOT A CACHED MODEL VERDICT, so it is stored
beside the classification records rather than in them and is read by a rule of
its own. The classification records retire on every new specification revision,
which is the right rule for a verdict a model produced; an attestation is
voided only by a change to the two things it attests about.

IT STANDS WHILE TWO THINGS ARE UNCHANGED, and only those two. The ATTESTED INPUT
is the item's asked-for behaviour, compared by the digest the classification
already takes of it; the CITED CLAUSE is compared by a digest of its heading and
body. A revision that touches neither leaves the attestation standing "even when
it adds, removes or changes clauses elsewhere", so an item released once is not
re-held by an unrelated amendment — and a rejected linked proposal does not
re-hold it either, because the release "is not a ratification".

THE DIGEST IS OF THE CLAUSE'S HEADING AND BODY ALONE. The clause may move to
another file without being rewritten, and a move changes nothing the human
attested about, so the file is recorded for the reader and is not compared.

THE RECORD SEPARATES ITS COMPARISON FIELDS FROM THE FREE TEXT IT QUOTES. The
asked-for behaviour and each assertion are quoted in full because the clause
requires the record to carry what the human attested, and that text is
arbitrary: a description line shaped like `input-digest: ...` would override the
real field in a parse that took the last occurrence. The fields therefore sit in
the leading block, the parse stops at its first blank line, and everything below
is prose no reader looks at.

A RECORD MISSING A COMPARISON FIELD IS NOT AN ATTESTATION, and the newest
attestation comment decides: a newer malformed one makes the item unattested
rather than falling back to an older valid one, because the fail-closed reading
of "I cannot tell what was attested" is that nothing was.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import TYPE_CHECKING

from livespec_orchestrator_beads_fabro.commands._dispatcher_definition_of_done import (
    definition_of_done,
)
from livespec_orchestrator_beads_fabro.commands._spec_change_tier import (
    asked_for_behaviour,
    behaviour_digest,
)
from livespec_orchestrator_beads_fabro.commands._spec_tree_condensation import clauses_named

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from livespec_orchestrator_beads_fabro.commands._spec_tree_condensation import CondensedClause
    from livespec_orchestrator_beads_fabro.types import WorkItem

__all__: list[str] = [
    "SPEC_TIER_ATTESTATION_MARKER",
    "SpecTierAttestation",
    "attestation_comment",
    "clause_digest",
    "recorded_attestation",
    "standing_attestation",
]

SPEC_TIER_ATTESTATION_MARKER = "livespec-spec-tier-attestation"

_FIELD_SEPARATOR = ": "
_QUOTE = "> "
_WORK_ITEM_FIELD = "work-item"
_ACTOR_FIELD = "actor"
_HEADING_FIELD = "heading"
_SPEC_FILE_FIELD = "spec-file"
_SPEC_VERSION_FIELD = "spec-version"
_CLAUSE_DIGEST_FIELD = "clause-digest"
_INPUT_DIGEST_FIELD = "input-digest"
_COMPARISON_FIELDS = (
    _ACTOR_FIELD,
    _HEADING_FIELD,
    _SPEC_FILE_FIELD,
    _SPEC_VERSION_FIELD,
    _CLAUSE_DIGEST_FIELD,
    _INPUT_DIGEST_FIELD,
)


@dataclass(frozen=True, kw_only=True)
class SpecTierAttestation:
    """One attestation read back off the item, as every consumer compares it."""

    actor: str
    heading: str
    spec_file: str
    spec_version: str
    clause_digest: str
    input_digest: str


def clause_digest(*, clause: CondensedClause) -> str:
    """The identity of one clause's heading and body, algorithm named in the value."""
    text = f"{clause.heading.rstrip()}\n{clause.body}"
    return f"sha256:{hashlib.sha256(text.encode('utf-8')).hexdigest()}"


def attestation_comment(
    *, item: WorkItem, actor: str, clause: CondensedClause, spec_version: str
) -> str:
    """The ledger comment recording one attestation, with what was attested.

    The asked-for behaviour and each assertion text are quoted below the
    comparison block, because the clause requires the record to carry them and
    because a later reader asking what the human actually vouched for has no
    other place to find it once the item has been edited.
    """
    assertions = definition_of_done(description=item.description).assertions
    lines = [
        SPEC_TIER_ATTESTATION_MARKER,
        "",
        f"{_WORK_ITEM_FIELD}{_FIELD_SEPARATOR}{item.id}",
        f"{_ACTOR_FIELD}{_FIELD_SEPARATOR}{actor}",
        f"{_HEADING_FIELD}{_FIELD_SEPARATOR}{clause.heading.rstrip()}",
        f"{_SPEC_FILE_FIELD}{_FIELD_SEPARATOR}{clause.path}",
        f"{_SPEC_VERSION_FIELD}{_FIELD_SEPARATOR}{spec_version}",
        f"{_CLAUSE_DIGEST_FIELD}{_FIELD_SEPARATOR}{clause_digest(clause=clause)}",
        f"{_INPUT_DIGEST_FIELD}{_FIELD_SEPARATOR}{behaviour_digest(item=item)}",
        "",
        "Attested asked-for behaviour:",
        *(f"{_QUOTE}{line}" for line in asked_for_behaviour(item=item).splitlines()),
        "",
        "Attested assertions:",
        *(f"- {' '.join(assertion.text.split())}" for assertion in assertions),
    ]
    return "\n".join(lines)


def recorded_attestation(*, comments: Sequence[str]) -> SpecTierAttestation | None:
    """The NEWEST attestation comment, parsed, or `None` when it cannot be read."""
    for body in reversed(tuple(comments)):
        lines = body.strip().splitlines()
        if lines and lines[0].strip() == SPEC_TIER_ATTESTATION_MARKER:
            return _parsed(fields=_comparison_fields(lines=lines[1:]))
    return None


def standing_attestation(
    *, item: WorkItem, comments: Sequence[str], spec_tree: Mapping[str, str]
) -> CondensedClause | None:
    """The cited clause, when the newest attestation still stands for this item.

    `None` for an item nobody attested, for one whose asked-for behaviour has
    changed since, and for one whose cited clause no longer resolves to the
    heading and body the human attested — each is an attestation that no longer
    describes the item or the specification in front of it.
    """
    recorded = recorded_attestation(comments=comments)
    if recorded is None or recorded.input_digest != behaviour_digest(item=item):
        return None
    for clause in clauses_named(spec_tree=spec_tree, headings=[recorded.heading]):
        if clause_digest(clause=clause) == recorded.clause_digest:
            return clause
    return None


def _comparison_fields(*, lines: Sequence[str]) -> dict[str, str]:
    """The leading `key: value` block, ended by its first blank line."""
    fields: dict[str, str] = {}
    started = False
    for raw in lines:
        stripped = raw.strip()
        if not stripped:
            if started:
                break
            continue
        started = True
        key, separator, value = stripped.partition(_FIELD_SEPARATOR)
        if separator:
            fields[key] = value
    return fields


def _parsed(*, fields: Mapping[str, str]) -> SpecTierAttestation | None:
    """One attestation, or `None` when a comparison field is absent or blank."""
    if any(not fields.get(name, "").strip() for name in _COMPARISON_FIELDS):
        return None
    return SpecTierAttestation(
        actor=fields[_ACTOR_FIELD],
        heading=fields[_HEADING_FIELD],
        spec_file=fields[_SPEC_FILE_FIELD],
        spec_version=fields[_SPEC_VERSION_FIELD],
        clause_digest=fields[_CLAUSE_DIGEST_FIELD],
        input_digest=fields[_INPUT_DIGEST_FIELD],
    )
