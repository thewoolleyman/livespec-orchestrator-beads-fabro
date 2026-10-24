"""Read Definition-of-Done receipts and identify each conflicting digest pair once."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from livespec_orchestrator_beads_fabro.commands._dispatcher_dod_judgement_markers import (
    JUDGEMENT_COMMENT_MARKER,
    comment_marker,
)

if TYPE_CHECKING:
    from collections.abc import Sequence

__all__: list[str] = [
    "DISAGREEMENT_COMMENT_MARKER",
    "DodJudgementDisagreement",
    "disagreement_record",
    "disagreements",
    "verdict_record",
]

DISAGREEMENT_COMMENT_MARKER = "dod-judgement-disagreement"
_OUTCOMES = frozenset({"admitted", "rests-at-needs-human"})


@dataclass(frozen=True, kw_only=True)
class _Verdict:
    """One completed taking that can disagree with another taking."""

    taking: str
    outcome: str
    subject_digest: str
    rubric_digest: str
    timestamp: str
    findings: tuple[str, ...]


@dataclass(frozen=True, kw_only=True)
class DodJudgementDisagreement:
    """The two opposite completed takings for one immutable digest pair."""

    subject_digest: str
    rubric_digest: str
    takings: tuple[str, str]
    outcomes: tuple[str, str]
    timestamps: tuple[str, str]
    findings: tuple[str, ...]


def verdict_record(**fields: object) -> str:
    """Render one completed taking in the receipt grammar the reader consumes."""
    taking = _required_text(fields=fields, name="taking")
    outcome = _required_text(fields=fields, name="outcome")
    subject_digest = _required_text(fields=fields, name="subject_digest")
    rubric_digest = _required_text(fields=fields, name="rubric_digest")
    timestamp = _required_text(fields=fields, name="timestamp")
    run_id = fields.get("run_id")
    findings = fields.get("findings", ())
    if run_id is not None and not isinstance(run_id, str):
        raise TypeError
    if not isinstance(findings, tuple) or not all(isinstance(one, str) for one in findings):
        raise TypeError
    named_taking = taking if run_id is None else f"{taking} run-{run_id.removeprefix('run-')}"
    lines = [
        JUDGEMENT_COMMENT_MARKER,
        "",
        f"taking: {named_taking}",
        f"outcome: {outcome}",
        f"subject-digest: {subject_digest}",
        f"rubric-digest: {rubric_digest}",
        f"taken-at: {timestamp}",
    ]
    lines.extend(f"finding: {finding}" for finding in findings)
    return "\n".join(lines)


def disagreements(*, comments: Sequence[str]) -> tuple[DodJudgementDisagreement, ...]:
    """Every unrecorded opposite-outcome pair, in ledger order.

    A disagreement receipt carries the stable identity of its pair, so another
    read of the same comments returns no work.  This deliberately scans all
    records rather than only adjacent records: records for another digest pair
    may occur between the two takings without changing either disagreement.
    """
    seen = _recorded_identities(comments=comments)
    verdicts = tuple(_verdict(body=body) for body in comments)
    complete = tuple(one for one in verdicts if one is not None)
    found: list[DodJudgementDisagreement] = []
    for index, first in enumerate(complete):
        for second in complete[index + 1 :]:
            if (first.subject_digest, first.rubric_digest) != (
                second.subject_digest,
                second.rubric_digest,
            ) or first.outcome == second.outcome:
                continue
            disagreement = DodJudgementDisagreement(
                subject_digest=first.subject_digest,
                rubric_digest=first.rubric_digest,
                takings=(first.taking, second.taking),
                outcomes=(first.outcome, second.outcome),
                timestamps=(first.timestamp, second.timestamp),
                findings=first.findings + second.findings,
            )
            identity = _identity(disagreement=disagreement)
            if identity not in seen:
                found.append(disagreement)
                seen.add(identity)
    return tuple(found)


def disagreement_record(*, disagreement: DodJudgementDisagreement) -> str:
    """Render the item receipt that prevents the same pair being recorded twice."""
    return "\n".join(
        (
            f"{JUDGEMENT_COMMENT_MARKER}-{DISAGREEMENT_COMMENT_MARKER}",
            "",
            f"subject-digest: {disagreement.subject_digest}",
            f"rubric-digest: {disagreement.rubric_digest}",
            f"first-taking: {disagreement.takings[0]}",
            f"first-outcome: {disagreement.outcomes[0]}",
            f"first-taken-at: {disagreement.timestamps[0]}",
            f"second-taking: {disagreement.takings[1]}",
            f"second-outcome: {disagreement.outcomes[1]}",
            f"second-taken-at: {disagreement.timestamps[1]}",
            *(f"finding: {finding}" for finding in disagreement.findings),
        )
    )


def _verdict(*, body: str) -> _Verdict | None:
    """Read one completed taking, never a did-not-run or disagreement receipt."""
    if comment_marker(body=body) != JUDGEMENT_COMMENT_MARKER:
        return None
    fields = _fields(body=body)
    outcome = fields.get("outcome")
    required = ("taking", "subject-digest", "rubric-digest", "taken-at")
    if outcome not in _OUTCOMES or any(fields.get(name) is None for name in required):
        return None
    return _Verdict(
        taking=fields["taking"],
        outcome=outcome,
        subject_digest=fields["subject-digest"],
        rubric_digest=fields["rubric-digest"],
        timestamp=fields["taken-at"],
        findings=tuple(_repeated(body=body, key="finding")),
    )


def _recorded_identities(*, comments: Sequence[str]) -> set[tuple[str, ...]]:
    """The pairs an existing item disagreement receipt has already named."""
    identities: set[tuple[str, ...]] = set()
    marker = f"{JUDGEMENT_COMMENT_MARKER}-{DISAGREEMENT_COMMENT_MARKER}"
    for body in comments:
        if comment_marker(body=body) != marker:
            continue
        fields = _fields(body=body)
        keys = (
            "subject-digest",
            "rubric-digest",
            "first-taking",
            "first-outcome",
            "first-taken-at",
            "second-taking",
            "second-outcome",
            "second-taken-at",
        )
        if all(fields.get(key) is not None for key in keys):
            identities.add(tuple(fields[key] for key in keys))
    return identities


def _identity(*, disagreement: DodJudgementDisagreement) -> tuple[str, ...]:
    """The immutable identity shared by a journal row and its item receipt."""
    return (
        disagreement.subject_digest,
        disagreement.rubric_digest,
        disagreement.takings[0],
        disagreement.outcomes[0],
        disagreement.timestamps[0],
        disagreement.takings[1],
        disagreement.outcomes[1],
        disagreement.timestamps[1],
    )


def _fields(*, body: str) -> dict[str, str]:
    """The first value of each scalar receipt field."""
    fields: dict[str, str] = {}
    for line in body.splitlines()[1:]:
        key, separator, value = line.partition(": ")
        if separator:
            fields.setdefault(key, value)
    return fields


def _required_text(*, fields: dict[str, object], name: str) -> str:
    """One required text renderer input, rejecting malformed records early."""
    value = fields.get(name)
    if not isinstance(value, str):
        raise TypeError
    return value


def _repeated(*, body: str, key: str) -> list[str]:
    """Every occurrence of one repeated receipt field, in record order."""
    prefix = f"{key}: "
    return [line.removeprefix(prefix) for line in body.splitlines()[1:] if line.startswith(prefix)]
