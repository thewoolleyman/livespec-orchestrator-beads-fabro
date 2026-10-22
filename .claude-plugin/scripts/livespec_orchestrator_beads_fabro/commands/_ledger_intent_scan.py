"""The ledger-intent scan's own decisions: the population, the statement, the finding.

PURE. The `capture-spec-drift` clause of `SPECIFICATION/contracts.md` makes the
scan "a
read-only pass over recent work-items in the Ledger that surfaces work-item
intent (its `title`, `description`, `acceptance_criteria`, and closure
`reason`) encoding an observable behavior, decision, or invariant NOT reflected
in the current spec", decided "by the same spec-stated judgement, over every
live work-item and every work-item captured on or after the latest version's
cut ... an item's type is never a detection exclusion".

Three properties an editor must not invert.

THE FOUR FIELDS ARE JUDGED AS ONE STATEMENT, not four. The clause names them as
one item's intent, and a per-field judgement would spend four model calls per
item to answer a question none of the four fields answers alone — a title and
its acceptance criteria are halves of one behaviour, so judging either in
isolation reports `unstated` for intent the other states.

THE TYPE IS NOT RENDERED INTO THE STATEMENT AND NEVER FILTERS. The clause says
outright that an item's type is never a detection exclusion, and `bug` / `chore`
/ `non_functional` is a DISPATCH exemption that lives elsewhere. Rendering the
stored type would hand the judge the one piece of evidence the ratified
population rule tells it to ignore — and the stored type is routinely wrong
here, which is what made the exclusion a defect in the first place.

A `stated` VERDICT PRODUCES NO FINDING, and that filter lives in ONE place.
"MUST NOT emit a finding for intent already reflected in the spec" is the
clause's own wording, so a caller that decided emission itself would be a
second authority on it — and the failure is silent, because a finding for a
stated item is well-formed and routes through the per-finding consent flow
exactly as a real one does, costing the operator a proposal against a clause
that already says it.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from livespec_runtime.spec_stated import SpecStatedVerdict, StatedKind

from livespec_orchestrator_beads_fabro.types import WorkItem

__all__: list[str] = [
    "DONE_STATUS",
    "LEDGER_INTENT_KINDS",
    "LedgerIntentFinding",
    "finding_for",
    "intent_statement",
    "scan_population",
]

# The two verdicts that are drift. `stated` is the third and produces nothing.
LEDGER_INTENT_KINDS: tuple[StatedKind, ...] = ("partial", "unstated")

# The one status that is not live. Read as "not live" rather than enumerating
# the live set, because a lifecycle status added later is live by default and
# an enumeration would silently drop every item carrying it.
DONE_STATUS = "done"

_FIELD_ABSENT = "(none recorded)"


@dataclass(frozen=True, kw_only=True)
class LedgerIntentFinding:
    """One work-item whose recorded intent the ratified spec does not state.

    `generalization_target` is the heading whose generalization would state the
    behaviour, carried so the propose-change handoff can name it rather than
    making the operator re-derive it from the rationale.
    """

    item_id: str
    kind: StatedKind
    stated_by: tuple[str, ...]
    generalization_target: str | None
    rationale: str

    def projection(self) -> dict[str, object]:
        """This finding as the one machine envelope the CLI emits."""
        return {
            "item_id": self.item_id,
            "kind": self.kind,
            "stated_by": list(self.stated_by),
            "generalization_target": self.generalization_target,
            "rationale": self.rationale,
        }


def intent_statement(*, item: WorkItem) -> str:
    """One work-item's recorded intent, rendered as the statement under judgement."""
    return "\n\n".join(
        [
            f"Work item {item.id}",
            f"Title: {_recorded(value=item.title)}",
            f"Description: {_recorded(value=item.description)}",
            f"Acceptance criteria: {_recorded(value=item.acceptance_criteria)}",
            f"Closure reason: {_recorded(value=item.reason)}",
        ]
    )


def scan_population(
    *, items: Iterable[WorkItem], cut: str, include_live: bool
) -> tuple[WorkItem, ...]:
    """The work-items one invocation judges, in a stable order.

    `include_live` is True exactly when no `--since-version` scoped the scan,
    which is the one condition under which the ratified population adds every
    live item to the captured-since set. With the flag set the clause says
    "only work-items captured on or after the cut of spec version `<vN>`", so
    the live set does not widen it.

    The instants are compared as STRINGS, which is exact for the one encoding
    both sides carry — an ISO-8601 UTC instant with a `Z` suffix — and is the
    same comparison the shared record reducer already makes over `captured_at`.

    The order is by id rather than the tenant's own, because the tenant's order
    is whatever the backend's listing happened to be and a finding list that
    reorders between two runs over one population reads as a changed answer.
    """
    selected = [
        item
        for item in items
        if item.captured_at >= cut or (include_live and item.status != DONE_STATUS)
    ]
    return tuple(sorted(selected, key=lambda item: item.id))


def finding_for(*, item: WorkItem, verdict: SpecStatedVerdict) -> LedgerIntentFinding | None:
    """This item's finding, or `None` when the ratified text already states it.

    `None` rather than a finding carrying a `stated` kind: a caller that had to
    read the kind to decide whether to emit would be the second authority this
    module's docstring forbids, and the kind a caller forgot to read is the one
    that costs the operator a proposal.
    """
    if verdict.kind not in LEDGER_INTENT_KINDS:
        return None
    return LedgerIntentFinding(
        item_id=item.id,
        kind=verdict.kind,
        stated_by=verdict.stated_by,
        generalization_target=verdict.generalization_target,
        rationale=verdict.rationale,
    )


def _recorded(*, value: str | None) -> str:
    """One intent field as the judge sees it, or the mark that it is unrecorded.

    An absent field is NAMED rather than dropped, because a statement that
    simply omits the acceptance criteria is indistinguishable from one whose
    criteria the renderer failed to read.
    """
    if value is None or value.strip() == "":
        return _FIELD_ABSENT
    return value.strip()
