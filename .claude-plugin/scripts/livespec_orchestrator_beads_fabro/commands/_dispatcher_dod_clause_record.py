"""One clause of a governing-heading receipt, written to and read from a record line.

A clause carries its heading and full body, and the body may span lines, so a
clause is recorded as one JSON object on one line: unambiguous to read back
whatever the body holds. The spec-relative path of a clause is deliberately not
recorded here, because a reader recomputes the clauses against the current
revision and only the heading and body decide whether a recorded verdict still
applies.
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

_FIELD_SEPARATOR = ": "


def clause_line(*, key: str, clause: CondensedClause) -> str:
    """One unambiguous recorded clause value, including a multiline body."""
    value = json.dumps({"heading": clause.heading, "body": clause.body}, sort_keys=True)
    return f"{key}{_FIELD_SEPARATOR}{value}"


def clauses_from(*, values: Sequence[str]) -> tuple[CondensedClause, ...] | None:
    """The complete typed provenance carried by one record, or no reading."""
    clauses: list[CondensedClause] = []
    for raw in values:
        try:
            decoded = json.loads(raw)
        except json.JSONDecodeError:
            return None
        if not isinstance(decoded, dict):
            return None
        fields = cast("dict[str, object]", decoded)
        heading = fields.get("heading")
        clause_body = fields.get("body")
        if not isinstance(heading, str) or not isinstance(clause_body, str):
            return None
        clauses.append(CondensedClause(heading=heading, body=clause_body))
    return tuple(clauses)
