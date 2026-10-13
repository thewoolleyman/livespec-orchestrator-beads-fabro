"""The `plan_continuation_ruling` conformance verdict: every malformed ruling.

The plan-record conformance clause of `SPECIFICATION/contracts.md` states the
whole rule: "A `plan_continuation_ruling` check (error) MUST report a
`plan-continuation: authorized` ruling lacking any of its `until:`, `by:`,
`directive:` or `recorded-attended: true` lines, or a `plan-continuation:
revoked` ruling lacking its `by:` line; a ruling the check reports is not
current."

WHY THIS READS EVERY RULING WHERE THE PARSER READS ONE. `_plan_continuation`'s
`current_continuation_ruling_from_entries` answers "may this resume act?", and
only the LATEST ruling can govern that, so a malformed ruling with a later
sibling is invisible to it — correctly, because the later one is the
maintainer's latest word. This verdict answers a different question: which
rulings does a human have to look at. A stale malformed ruling is exactly as
hand-written as a current one, and it is the one nothing else surfaces, so the
whole timeline is in scope.

WHY THE LINES ARE READ AT THE POSITIONS A RULING CARRIES THEM. The clause's
guarantee runs one way — a ruling this check reports is not current — and the
cheapest way to hold it is to ask the same question the parser asks, which is an
INDEXED read: the attended marker is written after every caller-provided field,
so the primitive's own output has `until:`, `by:` and `directive:` at the
second, third and fourth lines and nothing else does. A presence-anywhere scan
would certify the five permutations of those three lines that the parser refuses,
and a hand-written ruling — which is the whole population this check exists to
surface — is precisely where a reordering comes from. The cost is that a line
present out of position reports as missing, which is why the finding says the
ruling lacks the line rather than that the line appears nowhere.

WHY A SIXTH LINE IS REPORTED THOUGH NOTHING IS MISSING. The parser requires
EXACTLY five lines for the reason its own comment gives: a body carrying a sixth
is one a caller appended to by hand, and an indexed read would treat it as
current anyway. So an over-long ruling is not current, and a verdict keyed only
on absent lines would leave the one shape that passes every line test
unreported.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from livespec_orchestrator_beads_fabro.commands._plan_continuation import (
    UNTIL_PREFIX,
    is_continuation_ruling,
    ruling_line_value,
)

if TYPE_CHECKING:
    from collections.abc import Sequence

    from livespec_orchestrator_beads_fabro.commands._plan_timeline import PlanTimelineEntry

__all__: list[str] = [
    "PLAN_CONTINUATION_RULING_CHECK_ID",
    "PLAN_CONTINUATION_RULING_REMEDIATION",
    "OpenPlanEpic",
    "PlanContinuationRulingFinding",
    "plan_continuation_ruling_findings",
]

PLAN_CONTINUATION_RULING_CHECK_ID = "plan_continuation_ruling"
PLAN_CONTINUATION_RULING_REMEDIATION = (
    "a continuation ruling is authority only while it carries every line the plan"
    " scope-event primitive writes. Have an attended session re-record the ruling"
    " through that primitive, or revoke it; a ledger comment cannot be edited, so"
    " the malformed one stays on the timeline as history."
)

_ERROR_VERDICT = "error"
_UNTIL_INDEX = 1


@dataclass(frozen=True, kw_only=True)
class OpenPlanEpic:
    """One open plan epic whose `plan_slug` names a live directory, with its timeline.

    `plan_slug` is carried even though no verdict renders it, because it is what
    made the epic in scope — an OPEN epic naming a LIVE plan directory — and a
    value object that dropped it would let a caller hand in an epic whose scope it
    had decided somewhere this module cannot see.

    `entries` is the whole parsed timeline in APPEND ORDER, which is the order the
    parser treats as authority order. The ruling parse is this module's to do,
    through the same predicates the parser uses, so a check and a resume can never
    disagree about what counts as a ruling.
    """

    epic_id: str
    plan_slug: str
    entries: tuple[PlanTimelineEntry, ...]


@dataclass(frozen=True, kw_only=True)
class PlanContinuationRulingFinding:
    """One reported verdict, in the shape the conformance family reports.

    `check_id`, `subject`, `verdict`, `event` and `remediation` are the five
    fields the shipped plan-record family emits. `created_at` and `missing` are
    carried as values beside the rendered `event` because an epic can hold several
    malformed rulings, so the ruling's own instant is what tells two findings on
    one epic apart, and a caller that had to recover the missing lines by reading
    the prose would be re-parsing this module's own output.
    """

    check_id: str
    subject: str
    verdict: str
    created_at: str
    missing: tuple[str, ...]
    event: str
    remediation: str


def plan_continuation_ruling_findings(
    *, epics: Sequence[OpenPlanEpic]
) -> tuple[PlanContinuationRulingFinding, ...]:
    """Every malformed continuation ruling on these epics' timelines.

    `epics` is already narrowed to OPEN epics whose `plan_slug` names a LIVE plan
    directory — the two conditions a caller must resolve against the tenant and
    the filesystem. What this decides is which timeline entries are rulings and
    which of those are malformed, which is the whole of the clause's own rule.
    """
    findings: list[PlanContinuationRulingFinding] = []
    for epic in epics:
        for entry in epic.entries:
            finding = _finding(epic_id=epic.epic_id, entry=entry)
            if finding is not None:
                findings.append(finding)
    return tuple(findings)


def _finding(*, epic_id: str, entry: PlanTimelineEntry) -> PlanContinuationRulingFinding | None:
    """This entry's verdict, or `None` when it is not a malformed ruling."""
    if not is_continuation_ruling(entry=entry):
        return None
    lines = entry.body.splitlines()
    missing = _missing_lines(lines=lines)
    if not missing:
        return None
    return PlanContinuationRulingFinding(
        check_id=PLAN_CONTINUATION_RULING_CHECK_ID,
        subject=epic_id,
        verdict=_ERROR_VERDICT,
        created_at=entry.created_at,
        missing=missing,
        event=_event(prefix=lines[0], created_at=entry.created_at, missing=missing),
        remediation=PLAN_CONTINUATION_RULING_REMEDIATION,
    )


def _missing_lines(*, lines: Sequence[str]) -> tuple[str, ...]:
    """Every line this ruling does not carry where a ruling carries it."""
    if _line_at(lines=lines, index=_UNTIL_INDEX, prefix=UNTIL_PREFIX) is None:
        return (UNTIL_PREFIX.strip(),)
    return ()


def _line_at(*, lines: Sequence[str], index: int, prefix: str) -> str | None:
    """One ruling line's value by position, `None` when the body is that short.

    A short body is the one shape an indexed read cannot be handed directly: the
    parser reaches its own index reads only after a length test, and this verdict
    has no length to test because reporting a short ruling is its job.
    """
    if index >= len(lines):
        return None
    return ruling_line_value(line=lines[index], prefix=prefix)


def _event(*, prefix: str, created_at: str, missing: Sequence[str]) -> str:
    """What was observed, as one sentence naming the ruling and every missing line."""
    clauses = "; ".join(f"lacks its `{one}` line" for one in missing)
    return f"malformed `{prefix}` ruling recorded at {created_at}: {clauses}"
