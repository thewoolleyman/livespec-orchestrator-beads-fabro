"""The plan Proof of Done records on one epic's timeline, read in append order.

The plan-record clause of `SPECIFICATION/contracts.md` (v115) fixes the first
line of a plan record — `Plan Proof of Done — <captured|verified|
not_reproduced|human_attested> — <session <session-identity> | human
<identity>> — <UTC timestamp>` — and says why the verdict words are the factory
ones rather than the `host_*` ones: "a plan has one leg: every plan assertion
that is not `human_attested` is exercised on a host".

WHY THE PARSE IS THE ITEM READER WITH TWO ARGUMENTS, not a second parser. A plan
record and an item record differ in their TITLE, in their admissible VERDICT set,
and in where they are posted. They do NOT differ in body structure: the
per-assertion sections, the fence-aware section split and the load-bearing
`Reproduced:` line are the same bytes, written by the same renderer
(`_dispatcher_host_record_render`). A second parser of that body would drift from
the first in the one direction nobody sees — every record would still parse, and
every assertion would read as UNEVIDENCED, which is the exact failure the
fence-awareness repair was measured against on two correctly published records.

WHY POSITION, AND NOT THE RECORD'S OWN TIMESTAMP. The archive proof leg turns on
three orderings: the verified record must postdate the latest captured record and
the last carrier-map event. The header carries a timestamp, but the PUBLISHER
writes it, so ordering by it lets a record claim to postdate an event it precedes
— and the claim would be invisible, because a record with a plausible timestamp
is a well-formed record. A ledger comment list is append-only, so its INDEX is
the ledger's own ordering and nothing a publisher writes can reorder it. Position
is therefore the ordering authority, and the header timestamp is kept only for
what it is: the publisher's statement of when the steps ran.

WHY EACH COMMENT IS OFFERED TO THE READER ON ITS OWN. `proof_records` answers for
a whole comment list, and this module needs to know WHICH comment each record
came from. Handing it the list would return the records with their positions
lost, so each comment is read singly and paired with its index. The cost is one
call per comment; the alternative is reaching for the item reader's private
single-comment helper, which pyright strict and the `private_calls` check both
reject — and which would couple this module to that one's internals rather than
to its published surface.

WHY THE LEDGER'S `text` KEY IS RENAMED TO `body`. `bd comments --json` keys a
comment body under `text`; the forge keys a pull-request comment under `body`,
which is what the shared reader asks for. The rename happens here, once, at the
boundary — an accessor reaching for the wrong one of those two names reads every
comment as empty, which is the same observation a genuinely lost write produces.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from livespec_orchestrator_beads_fabro.commands._dispatcher_proof_record import (
    VERDICT_CAPTURED,
    VERDICT_HUMAN_ATTESTED,
    VERDICT_NOT_REPRODUCED,
    VERDICT_VERIFIED,
    ProofRecord,
    proof_records,
)

__all__: list[str] = [
    "PLAN_PROOF_RECORD_TITLE",
    "PLAN_PROOF_RECORD_VERDICTS",
    "PLAN_REPLAY_VERDICTS",
    "PlanProofEntry",
    "latest_plan_proof_entry",
    "plan_proof_entries",
]

PLAN_PROOF_RECORD_TITLE = "Plan Proof of Done"
# The four verdicts a PLAN record may carry. The three `host_*` words are
# deliberately absent: the clause reuses the factory words for a plan because a
# plan has exactly one leg, and admitting a `host_recorded` first line here would
# make one record kind readable as either.
PLAN_PROOF_RECORD_VERDICTS = (
    VERDICT_CAPTURED,
    VERDICT_VERIFIED,
    VERDICT_NOT_REPRODUCED,
    VERDICT_HUMAN_ATTESTED,
)
# The two verdicts a party with no role in the implementation publishes, replaying
# the captured steps. `captured` is the first leg and decides nothing; a
# `human_attested` record is its own independent leg and is not a replay of
# anything, which is why it is absent from this pair and why a later one cannot
# unseat an earlier `verified` record.
PLAN_REPLAY_VERDICTS = (VERDICT_VERIFIED, VERDICT_NOT_REPRODUCED)

_LEDGER_BODY_KEY = "text"
_RECORD_BODY_KEY = "body"


@dataclass(frozen=True, kw_only=True)
class PlanProofEntry:
    """One plan Proof of Done record and its index in the epic's comment list.

    `position` is the ordering authority for every "postdates" question the proof
    leg asks, for the reason the module docstring records: a ledger comment list
    is append-only, so its index cannot be rewritten by what a publisher chose to
    put in the record's own timestamp field.
    """

    record: ProofRecord
    position: int


def plan_proof_entries(*, comments: Sequence[Mapping[str, object]]) -> tuple[PlanProofEntry, ...]:
    """Every plan Proof of Done record on one epic's timeline, with its position.

    A comment that is not a plan record — a handoff entry, a scope event, an
    item-side `Proof of Done` record quoted into prose — contributes nothing and
    does not consume a position: the index is the comment's own place in the
    timeline, so the positions a caller compares are stable under any filtering.
    """
    entries: list[PlanProofEntry] = []
    for position, comment in enumerate(comments):
        parsed = proof_records(
            comments=[{_RECORD_BODY_KEY: comment.get(_LEDGER_BODY_KEY)}],
            title=PLAN_PROOF_RECORD_TITLE,
            verdicts=PLAN_PROOF_RECORD_VERDICTS,
        )
        entries.extend(PlanProofEntry(record=one, position=position) for one in parsed)
    return tuple(entries)


def latest_plan_proof_entry(
    *, entries: Sequence[PlanProofEntry], verdicts: Sequence[str]
) -> PlanProofEntry | None:
    """The last entry carrying any of `verdicts`, or `None` when none does.

    "Last" is by POSITION rather than by list order, so a caller that has already
    filtered the entries still gets the answer the ledger's append order gives.
    A record "MUST NOT be edited after posting; a correction is a new record", so
    the newest one is the one that stands.
    """
    matching = [one for one in entries if one.record.verdict in verdicts]
    if not matching:
        return None
    return max(matching, key=lambda one: one.position)
