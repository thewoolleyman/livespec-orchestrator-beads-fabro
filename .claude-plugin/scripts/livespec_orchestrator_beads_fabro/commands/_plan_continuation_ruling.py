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

WHY THE THREE PREFIXED LINES ARE SOUGHT ANYWHERE IN THE BODY, WHERE THE PARSER
READS THEM BY INDEX. The parser's indexed read is right for the question it
asks — is this the body the primitive wrote — and wrong for this one. Omitting
one line SHIFTS every later line up, so an indexed reader handed a body that
genuinely lacks only its `until:` line reports all three as missing, two of them
while they sit in plain view one line above where it looked. A finding naming a
line an operator can see is a finding an operator stops trusting, and the whole
value of this verdict is that each finding names an act. So each prefix is sought
across the body and the attended marker is read as the LAST line, which is how
the clause words it.

WHAT THAT GIVES UP, stated because the gap is invisible from either side. A
five-line body carrying the three lines in the WRONG ORDER satisfies every arm
here and is still refused by the parser's indexed read, so it is not current and
is not reported. That costs nothing the clause promises — its guarantee runs one
way, that a ruling this check reports is not current — and nothing here may be
read as asserting the converse.

WHY A SIXTH LINE IS REPORTED THOUGH NOTHING IS MISSING. The parser requires
EXACTLY five lines for the reason its own comment gives: a body carrying a sixth
is one a caller appended to by hand, and an indexed read of the fifth line would
treat it as current anyway. So an over-long ruling is not current, and a verdict
keyed only on absent lines would leave the one shape that passes every line test
unreported.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from livespec_orchestrator_beads_fabro.commands._plan_continuation import (
    AUTHORIZED_LINE_COUNT,
    BY_PREFIX,
    DIRECTIVE_PREFIX,
    RECORDED_ATTENDED_LINE,
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
# The three caller-provided lines of an authorization. The attended marker is not
# among them because it is read as the LAST line rather than as a fourth prefix:
# that is how the clause words it, and it is the one line a caller cannot supply.
_AUTHORIZED_LINE_PREFIXES = (UNTIL_PREFIX, BY_PREFIX, DIRECTIVE_PREFIX)


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
    over_length = len(lines) > AUTHORIZED_LINE_COUNT
    if not missing and not over_length:
        return None
    return PlanContinuationRulingFinding(
        check_id=PLAN_CONTINUATION_RULING_CHECK_ID,
        subject=epic_id,
        verdict=_ERROR_VERDICT,
        created_at=entry.created_at,
        missing=missing,
        event=_event(
            prefix=lines[0],
            created_at=entry.created_at,
            missing=missing,
            over_length=over_length,
        ),
        remediation=PLAN_CONTINUATION_RULING_REMEDIATION,
    )


def _missing_lines(*, lines: Sequence[str]) -> tuple[str, ...]:
    """Every required line this ruling body does not carry, in the clause's order.

    `lines[-1]` is safe without a length test because `is_continuation_ruling`
    has already matched the first line, so the body is never empty here.
    """
    missing = [
        prefix.strip()
        for prefix in _AUTHORIZED_LINE_PREFIXES
        if not _carries_line(lines=lines, prefix=prefix)
    ]
    if lines[-1] != RECORDED_ATTENDED_LINE:
        missing.append(RECORDED_ATTENDED_LINE)
    return tuple(missing)


def _carries_line(*, lines: Sequence[str], prefix: str) -> bool:
    """Whether any line of this body is a non-empty line of `prefix`.

    The value is sought through the parser's own `ruling_line_value`, so a line
    whose value is blank counts as ABSENT here exactly as it does there — which
    is the whole reason this asks for the value rather than for the prefix.
    """
    return any(ruling_line_value(line=one, prefix=prefix) is not None for one in lines)


def _event(*, prefix: str, created_at: str, missing: Sequence[str], over_length: bool) -> str:
    """What was observed, as one sentence naming the ruling and every missing line.

    The over-length clause is rendered BESIDE the missing ones rather than instead
    of them, because a hand-appended body is routinely both: the appended line
    displaces the attended marker from the last position, so the operator needs to
    read both faults off one finding.
    """
    clauses = [f"lacks its `{one}` line" for one in missing]
    if over_length:
        clauses.append(f"carries more than {AUTHORIZED_LINE_COUNT} lines")
    return f"malformed `{prefix}` ruling recorded at {created_at}: {'; '.join(clauses)}"
