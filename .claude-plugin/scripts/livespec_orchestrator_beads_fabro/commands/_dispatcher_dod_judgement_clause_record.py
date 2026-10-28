"""How one typed condensed clause is written into, and read back out of, a record.

Split out of `_dispatcher_dod_judgement_record` by cohesion: that module decides
WHICH clauses a governing-heading receipt records and whether a recorded one
still matches, while this owns only the ENCODING of a clause as one record line.
The render sits beside the parse deliberately, exactly as the proof-record
attachment codec keeps its own pair together — one record format must not be
stated in two files, because the two then drift in the direction nothing
announces: every record still writes, every record still reads, and the values
no longer round-trip.

It takes the raw VALUES of a repeated key rather than the record body, which is
what keeps the clause codec from needing the record module's field reader and so
keeps the dependency one-way. The reader stays where the rest of the record
parsing lives.

Two properties an editor must not invert.

The value is JSON with SORTED keys, which is what makes one clause's recorded
line depend on the clause alone. The body may carry newlines, colons and the
field separator itself, so a bare `<heading>: <body>` encoding would be
ambiguous against the record's own line grammar; and an unsorted mapping would
make two encodings of one clause differ as text, which the reuse comparison one
module up reads as a changed clause.

Every malformed value yields NO READING for the whole set rather than the
clauses that happened to decode. A partial tuple is the dangerous answer: the
comparison it feeds is a multiset equality against the clauses in hand, so a
dropped unreadable clause makes a record of DIFFERENT provenance compare equal,
and the verdict is then reused on evidence nobody could read.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from typing import cast

from livespec_orchestrator_beads_fabro.commands._spec_tree_condensation import CondensedClause

__all__: list[str] = [
    "clause_line",
    "clauses_from",
]

_HEADING_KEY = "heading"
_BODY_KEY = "body"


def clause_line(*, key: str, separator: str, clause: CondensedClause) -> str:
    """One unambiguous recorded clause value, including a multiline body."""
    value = json.dumps({_HEADING_KEY: clause.heading, _BODY_KEY: clause.body}, sort_keys=True)
    return f"{key}{separator}{value}"


def clauses_from(*, values: Sequence[str]) -> tuple[CondensedClause, ...] | None:
    """The complete typed provenance those recorded values carry, or no reading."""
    clauses: list[CondensedClause] = []
    for raw in values:
        try:
            decoded = json.loads(raw)
        except json.JSONDecodeError:
            return None
        if not isinstance(decoded, dict):
            return None
        fields = cast("dict[str, object]", decoded)
        heading = fields.get(_HEADING_KEY)
        clause_body = fields.get(_BODY_KEY)
        if not isinstance(heading, str) or not isinstance(clause_body, str):
            return None
        clauses.append(CondensedClause(heading=heading, body=clause_body))
    return tuple(clauses)
