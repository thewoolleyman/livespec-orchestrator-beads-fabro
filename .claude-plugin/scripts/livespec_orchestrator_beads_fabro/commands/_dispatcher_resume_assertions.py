"""Compare a current item's assertions with the assertions a proof records.

The comparison is deliberately independent of the resume observation's ledger,
forge, and factory reads: a proof record is the sole evidence it needs.
"""

from __future__ import annotations

import re

from livespec_orchestrator_beads_fabro.commands._dispatcher_effective_criteria import (
    effective_criteria,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_proof_record import ProofRecord
from livespec_orchestrator_beads_fabro.types import WorkItem

__all__: list[str] = ["unproved_assertions"]

_WHITESPACE = re.compile(r"\s+")
_ASSERTION_HEADING = re.compile(
    r"^## Assertion \d+ — (?P<assertion>[^\n]+(?:\n(?![ \t]*$)[^\n]+)*)$", re.MULTILINE
)


def unproved_assertions(*, item: WorkItem, record: ProofRecord) -> tuple[str, ...]:
    """Every named assertion that establishes the item and anchoring record differ.

    Current-only assertions arrived after the earlier run and keep the
    established refusal wording; they come first.  A record-only assertion was
    removed while the item rested, which is the other direction of the
    exact-match precondition, and follows them, so an addition never hides a
    removal.  Either makes a plain dispatch the safe route.
    """
    assertions = effective_criteria(item=item).assertions
    body = _normalized(text=record.body)
    current = frozenset(_normalized(text=one) for one in assertions)
    missing = tuple(one for one in assertions if _normalized(text=one) not in body)
    removed = tuple(
        one for one in _recorded_assertions(record=record) if _normalized(text=one) not in current
    )
    return missing + removed


def _recorded_assertions(*, record: ProofRecord) -> tuple[str, ...]:
    """The assertion text the standard headings carry, including a wrapped tail."""
    return tuple(
        " ".join(match.group("assertion").split())
        for match in _ASSERTION_HEADING.finditer(record.body)
    )


def _normalized(*, text: str) -> str:
    """One string with its whitespace collapsed and its case folded."""
    return _WHITESPACE.sub(" ", text).strip().casefold()
