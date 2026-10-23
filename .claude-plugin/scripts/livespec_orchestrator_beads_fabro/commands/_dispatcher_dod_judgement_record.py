"""The LEDGER RECORD of one Definition-of-Done judgement, written and read back.

"Judged before admission" requires a held verdict, "with each remedy", to be
appended to the item as a ledger comment, and requires a judgement that could
not run to record on the item that it did not and why. "Judged again before
dispatch" then adds two CAPS on top of those writes: a reused verdict appends no
second comment, and the did-not-run record is written "at most once per distinct
cause until the judgement next runs". This module owns both directions — the
render and the parse — because a cap that cannot be read back is not a cap.

WHY THE LEDGER COMMENT IS THE STORE, AND NOT A HOST FILE. Ledger writers here
may share nothing but the Beads server (`.ai/ledger-writers-are-multi-host.md`),
so a verdict cached under a host state root would be invisible to the next
writer and the judgement would re-run — and re-comment — once per host. The
comment is the only durable, append-only record every writer can see.

WHY AN ADMITTED VERDICT IS RECORDED TOO, THOUGH NO CLAUSE DEMANDS ITS COMMENT.
The reuse rule is stated over "the most recent verdict recorded for the item,
the pre-admission verdict or an earlier pre-dispatch verdict", and an admitted
verdict that left no record is one the drain must take again on every pass — a
model call per item per pass, which is the cost the rule exists to avoid. It is
bounded by the same digest: one record per distinct criteria text, not one per
pass.

THE TWO MARKERS ARE RE-EXPORTED rather than owned here. They moved to
`_dispatcher_dod_judgement_markers` when the subject and the goal renderer
needed the same question, and that leaf's docstring records why; every existing
importer still reads them from this module, which is where a reader of the
record format looks for them.

WHY A RECORD NAMING NO DIGEST IS NOT A REUSABLE VERDICT. The reuse condition is
byte-identity with the subject the verdict was TAKEN against, so a record that
cannot name that subject supports no comparison. Treating it as reusable would
reuse a verdict for text it may never have read, which on a refusing verdict
blocks an item whose author has already repaired it.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from livespec_orchestrator_beads_fabro.commands._dispatcher_dod_judgement import (
    JUDGEMENT_UNAVAILABLE,
    DodJudgement,
    first_remedy,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_dod_judgement_markers import (
    JUDGEMENT_COMMENT_MARKER,
    UNAVAILABLE_COMMENT_MARKER,
    comment_marker,
)
from livespec_orchestrator_beads_fabro.commands._dod_governing_heading import (
    GoverningHeadingVerdict,
)

__all__: list[str] = [
    "JUDGEMENT_COMMENT_MARKER",
    "STAGE_PRE_ADMISSION",
    "STAGE_PRE_DISPATCH",
    "UNAVAILABLE_COMMENT_MARKER",
    "RecordedJudgement",
    "did_not_run_comment",
    "recorded_did_not_run_causes",
    "recorded_governing_heading",
    "reusable_verdict",
    "verdict_comment",
]

# The two call sites the clause names, as self-describing values rather than
# numbered positions: the record says WHERE the judgement was taken, which is
# what tells an operator reading the item whether a dispatch or an admission
# produced it.
STAGE_PRE_ADMISSION = "pre-admission"
STAGE_PRE_DISPATCH = "pre-dispatch"

_WORK_ITEM_FIELD = "work-item"
_STAGE_FIELD = "stage"
_OUTCOME_FIELD = "outcome"
_DIGEST_FIELD = "subject-digest"
# The rubric the verdict was taken UNDER, which is the other half of the reuse
# condition. It is a field of its own rather than part of the subject digest
# because the two change for unrelated reasons and a reader of the record has to
# be able to say which one retired a verdict: an item edit, or a plugin release.
_RUBRIC_DIGEST_FIELD = "rubric-digest"
_FINDING_FIELD = "finding"
_REMEDY_FIELD = "first-remedy"
# Deliberately NOT the bare `cause`. The did-not-run scan below walks back over
# whatever comments sit between the newest record and the last taken verdict —
# operator riders among them — and a field name a rider could plausibly carry
# would let that rider suppress a did-not-run record, which hides an outage
# behind a comment that has nothing to do with the judgement. The field name is
# the discriminator, so it has to be one nothing else writes.
_CAUSE_FIELD = "judgement-unavailable-cause"
# The spec-stated judgement's own verdict, recorded so the `dod_gate` node can
# be briefed with the verdict the host taking used rather than with a second
# one taken at the goal render. The heading key is REPEATED, one line per
# governing clause, exactly as `finding` is.
_GOVERNING_KIND_FIELD = "governing-heading-kind"
_GOVERNING_HEADING_FIELD = "governing-heading"
_FIELD_SEPARATOR = ": "
# Every key a record may carry more than once, which the field map must leave
# to the repeated-value reader rather than collapsing to its last occurrence.
_REPEATED_FIELDS = frozenset({_FINDING_FIELD, _GOVERNING_HEADING_FIELD})


@dataclass(frozen=True, kw_only=True)
class RecordedJudgement:
    """One verdict read back off the item, as the reuse rule compares it."""

    outcome: str
    digest: str
    rubric_digest: str
    findings: tuple[str, ...] = ()

    @property
    def first_remedy(self) -> str | None:
        """The remedy the hygiene listing names, derived as the verdict's own."""
        return first_remedy(findings=self.findings)


def verdict_comment(
    *,
    item_id: str,
    stage: str,
    digest: str,
    rubric_digest: str,
    judgement: DodJudgement,
    governing: GoverningHeadingVerdict | None = None,
) -> str:
    """The ledger comment recording one taken verdict, findings and all.

    `governing` is the spec-stated judgement's own verdict, recorded BESIDE the
    outcome rather than folded into it. It is here because the `dod_gate` node
    reads it out of the goal and the Dispatcher has no other durable place to
    put it: resolving it again at the goal render would be a second model call
    over a prompt carrying the whole ratified tree, on every dispatch including
    the groom-variant ones the judgement exempts — which is not a smaller
    version of this, but the exemption silently spending the judgement it
    exempts.

    It is OPTIONAL because a record written before this field existed carries
    none, and because a taking whose component could not run records the
    outcome it did reach rather than nothing at all.
    """
    lines = [
        JUDGEMENT_COMMENT_MARKER,
        "",
        f"{_WORK_ITEM_FIELD}{_FIELD_SEPARATOR}{item_id}",
        f"{_STAGE_FIELD}{_FIELD_SEPARATOR}{stage}",
        f"{_OUTCOME_FIELD}{_FIELD_SEPARATOR}{judgement.outcome}",
        f"{_DIGEST_FIELD}{_FIELD_SEPARATOR}{digest}",
        f"{_RUBRIC_DIGEST_FIELD}{_FIELD_SEPARATOR}{rubric_digest}",
    ]
    if governing is not None:
        lines.append(f"{_GOVERNING_KIND_FIELD}{_FIELD_SEPARATOR}{governing.kind}")
        lines.extend(
            f"{_GOVERNING_HEADING_FIELD}{_FIELD_SEPARATOR}{heading}"
            for heading in governing.stated_by
        )
    lines.extend(f"{_FINDING_FIELD}{_FIELD_SEPARATOR}{finding}" for finding in judgement.findings)
    remedy = first_remedy(findings=judgement.findings)
    if remedy is not None:
        lines.append(f"{_REMEDY_FIELD}{_FIELD_SEPARATOR}{remedy}")
    return "\n".join(lines)


def recorded_governing_heading(*, comments: Sequence[str]) -> GoverningHeadingVerdict | None:
    """The governing-heading verdict the NEWEST taken verdict recorded, or `None`.

    `None` for an item with no verdict record, for a record written before the
    field existed, and for a taking whose component could not run — all three
    are the same fact for the one consumer, which is the goal renderer, and it
    renders the block's explicit absence so the node keeps its own search.

    The NEWEST record governs rather than the earliest, which is the opposite of
    the reuse rule one function down and deliberately so: reuse asks which
    verdict BINDS and must answer the same way however often it is asked, while
    this asks what the last taking SAW of the ratified tree, and a dispatch is
    briefed from the most recent reading of it.
    """
    for body in reversed(tuple(comments)):
        if comment_marker(body=body) != JUDGEMENT_COMMENT_MARKER:
            continue
        kind = _fields_of(body=body).get(_GOVERNING_KIND_FIELD)
        if kind is None:
            return None
        return GoverningHeadingVerdict(
            kind=kind, stated_by=_repeated(body=body, key=_GOVERNING_HEADING_FIELD)
        )
    return None


def did_not_run_comment(
    *, item_id: str, stage: str, digest: str, rubric_digest: str, cause: str
) -> str:
    """The ledger comment recording that the judgement did not run, and why."""
    return "\n".join(
        (
            UNAVAILABLE_COMMENT_MARKER,
            "",
            f"The {stage} Definition-of-Done judgement did not run for this item.",
            "",
            f"{_WORK_ITEM_FIELD}{_FIELD_SEPARATOR}{item_id}",
            f"{_STAGE_FIELD}{_FIELD_SEPARATOR}{stage}",
            f"{_OUTCOME_FIELD}{_FIELD_SEPARATOR}{JUDGEMENT_UNAVAILABLE}",
            f"{_DIGEST_FIELD}{_FIELD_SEPARATOR}{digest}",
            f"{_RUBRIC_DIGEST_FIELD}{_FIELD_SEPARATOR}{rubric_digest}",
            f"{_CAUSE_FIELD}{_FIELD_SEPARATOR}{cause}",
        )
    )


def reusable_verdict(
    *, comments: Sequence[str], digest: str, rubric_digest: str
) -> RecordedJudgement | None:
    """The most recent TAKEN verdict, when BOTH digests still equal these.

    A did-not-run record is passed over rather than treated as the most recent
    verdict: it records that no judgement happened, so reading it as one would
    make an outage permanent — the item would reuse "nothing was decided"
    forever and the judgement would never run again.

    A record naming no RUBRIC digest is not reusable either, for the reason the
    module docstring gives about the subject digest: it cannot say which rubric
    it was taken under, so reusing it is reusing a verdict against rules that may
    since have changed. Such a record is what every verdict written before the
    rubric digest existed looks like, so the fail-closed reading retires each of
    them once rather than honouring them forever.
    """
    for body in reversed(tuple(comments)):
        if comment_marker(body=body) != JUDGEMENT_COMMENT_MARKER:
            continue
        fields = _fields_of(body=body)
        recorded = fields.get(_DIGEST_FIELD)
        recorded_rubric = fields.get(_RUBRIC_DIGEST_FIELD)
        outcome = fields.get(_OUTCOME_FIELD)
        if recorded is None or recorded_rubric is None or outcome is None:
            return None
        if (recorded, recorded_rubric) != (digest, rubric_digest):
            return None
        return RecordedJudgement(
            outcome=outcome,
            digest=recorded,
            rubric_digest=recorded_rubric,
            findings=_findings_of(body=body),
        )
    return None


def recorded_did_not_run_causes(*, comments: Sequence[str]) -> frozenset[str]:
    """Every did-not-run cause recorded SINCE the judgement last actually ran.

    The walk stops at the first taken verdict, because the clause caps the
    record "until the judgement next runs": a cause recorded before that verdict
    describes an outage the verdict itself disproves, and letting it suppress a
    fresh occurrence would silence an item about a judgement that has stopped
    working.
    """
    causes: set[str] = set()
    for body in reversed(tuple(comments)):
        if comment_marker(body=body) == JUDGEMENT_COMMENT_MARKER:
            break
        causes.add(_fields_of(body=body).get(_CAUSE_FIELD, ""))
    return frozenset(causes - {""})


def _fields_of(*, body: str) -> dict[str, str]:
    """Every `key: value` line of one record, LAST occurrence winning.

    The REPEATED keys are read separately, because a last-wins map would keep
    only the final one of each — which is the opposite of what "with each
    remedy" asks the record to carry, and would reduce a multi-clause governing
    verdict to whichever heading the renderer happened to write last.
    """
    fields: dict[str, str] = {}
    for raw in body.splitlines():
        key, separator, value = raw.strip().partition(_FIELD_SEPARATOR)
        if separator and key not in _REPEATED_FIELDS:
            fields[key] = value
    return fields


def _findings_of(*, body: str) -> tuple[str, ...]:
    return _repeated(body=body, key=_FINDING_FIELD)


def _repeated(*, body: str, key: str) -> tuple[str, ...]:
    """Every value one repeated key carries, in the order the record wrote them."""
    prefix = f"{key}{_FIELD_SEPARATOR}"
    return tuple(
        raw.strip()[len(prefix) :] for raw in body.splitlines() if raw.strip().startswith(prefix)
    )
