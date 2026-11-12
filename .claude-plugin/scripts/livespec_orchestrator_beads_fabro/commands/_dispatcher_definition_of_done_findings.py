"""The MECHANICAL half of the Definition-of-Done gate, graded on the host.

The Definition-of-Done-and-Proof-of-Done clause of `SPECIFICATION/contracts.md`
(v114) splits the gate in two: the SEMANTIC half — is this definition coherent
with the item's title and its referenced scenario — runs inside the `dod_gate`
node, and the MECHANICAL half "MUST also run in the host-side wall so a
malformed item never spends a sandbox". This module is that mechanical half:
section present, reference line present, every reference resolves, and (once the
proof-mode parse lands) every mode declaration well-formed.

A finding is ONE line naming the item, the offending element, and the remedy,
which is the shape the clause specifies for all three surfaces that can report
one — the wall's refusal text, the node's needs-human question, and the capture
and groom displays.

WHICH REVISION THE REFERENCE CHECK READS (work-item bd-ib-ahtcng). References
resolve against the target repository's `origin/master`, never the primary
checkout's working tree, which lags after any merge burst and so refused headings
that a merged revise had already added. The filing display and the dispatch-time
wall both reach the check through `definition_of_done_findings`, so they judge one
revision. When that revision cannot be read the item is REFUSED with a finding
naming it: falling back to the primary checkout would be exactly the stale read
this module no longer makes. `_dispatcher_definition_of_done_origin_spec` records
why that reverses this module's earlier choice to skip the check on an unreadable
tree. The pure-parse checks are unaffected.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from livespec_orchestrator_beads_fabro.commands._dispatcher_definition_of_done import (
    PROOF_MODE_HOST_CAPTURED,
    PROOF_MODE_HUMAN_ATTESTED,
    REASON_PREFIX,
    REFERENCES_PREFIX,
    declared_proof_mode,
    definition_of_done,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_definition_of_done_origin_spec import (
    OriginSpecUnreadable,
    origin_spec_h2_headings,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_goal import (
    minijinja_openers_in_item_fields,
)

if TYPE_CHECKING:
    from pathlib import Path

    from livespec_orchestrator_beads_fabro.types import WorkItem

__all__: list[str] = [
    "definition_of_done_findings",
    "goal_template_opening_delimiter_findings",
]

# What each opt-out mode's `Reason:` line owes, in the clause's own words. Keyed
# by MODE rather than by sub-heading title so the title-to-mode mapping stays the
# parser's one table: a second mapping here is how the wall would come to report
# a `Host-captured` sub-heading's fault as a `human_attested` one.
# The two opt-out sub-headings as a reader of the finding must TYPE them. The
# parser's own constants are case-folded match keys rather than display text, so
# interpolating them would print a heading nobody should write.
_OPT_OUT_SUB_HEADINGS = "`### Host-captured` and `### Human-attested`"
_REASON_SUBJECTS = {
    PROOF_MODE_HOST_CAPTURED: (
        "the host surface the proof needs, or the released-build requirement"
    ),
    PROOF_MODE_HUMAN_ATTESTED: "the capability no factory sandbox has",
}


def definition_of_done_findings(
    *,
    item: WorkItem,
    cwd: Path,
    include_goal_template_openers: bool = True,
) -> tuple[str, ...]:
    """Every mechanical Definition-of-Done finding for one item, or an empty tuple.

    An absent section returns EARLY with the one finding that matters: every
    later check reads a section that is not there, so reporting "no section" and
    "no reference line" for the same item would name one fault twice and bury the
    remedy the operator actually needs.
    """
    findings = list(goal_template_opening_delimiter_findings(item=item))
    if not include_goal_template_openers:
        findings = []
    section = definition_of_done(description=item.description)
    if not section.present:
        return (*findings, _absent_section_finding(item=item))
    if not section.references:
        findings.append(_absent_reference_line_finding(item=item))
    findings.extend(_reference_findings(item=item, references=section.references, cwd=cwd))
    findings.extend(
        _malformed_proof_mode_finding(item=item, sub_heading=sub_heading)
        for sub_heading in section.malformed_proof_modes
    )
    findings.extend(_stray_line_finding(item=item, line=line) for line in section.stray_lines)
    return tuple(findings)


def goal_template_opening_delimiter_findings(*, item: WorkItem) -> tuple[str, ...]:
    """Report every editable field that would become MiniJinja syntax in a goal.

    The field text is never quoted: a filing finding is copied to an immutable
    ledger comment, so echoing the delimiter would turn the record of a repair
    into a future goal-rendering hazard.  The character offset gives the filer
    a precise, editable repair location without carrying the unsafe bytes.
    """
    return tuple(
        _goal_template_finding(item=item, source=finding.source, offset=finding.offset)
        for finding in minijinja_openers_in_item_fields(item=item)
    )


def _goal_template_finding(*, item: WorkItem, source: str, offset: int) -> str:
    """Render one safe finding without copying the delimiter into immutable text."""
    subject = f"work-item {item.id}: {source} carries a goal-template opening delimiter"
    return f"{subject} at 0-based character offset {offset}; edit that field"


def _reference_findings(
    *, item: WorkItem, references: tuple[str, ...], cwd: Path
) -> tuple[str, ...]:
    """One finding per reference `origin/master` carries no heading for, in order.

    An unreadable remote revision yields the ONE finding naming it, because no
    reference can be judged and the primary checkout is not an authority.
    """
    if not references:
        return ()
    headings = origin_spec_h2_headings(repo=cwd)
    if isinstance(headings, OriginSpecUnreadable):
        return (_unreadable_origin_finding(item=item, unreadable=headings),)
    return tuple(
        _unresolved_reference_finding(item=item, reference=reference)
        for reference in references
        if reference not in headings
    )


def _unreadable_origin_finding(*, item: WorkItem, unreadable: OriginSpecUnreadable) -> str:
    return (
        f"work-item {item.id}: the Definition of Done references cannot be checked because"
        f" the remote revision {unreadable.revision} of the governed spec tree is unreadable"
        f" ({unreadable.detail}); restore access to the repository's origin and retry"
    )


def _absent_section_finding(*, item: WorkItem) -> str:
    return (
        f"work-item {item.id}: the description carries no Definition of Done section"
        " as its first heading; author a `## Definition of Done` section whose"
        " bullets are the gradeable assertions and whose"
        f" `{REFERENCES_PREFIX}` line names an existing spec heading"
    )


def _absent_reference_line_finding(*, item: WorkItem) -> str:
    return (
        f"work-item {item.id}: the Definition of Done section carries no valid"
        f" `{REFERENCES_PREFIX}` line; add one naming the verbatim text of an"
        " existing H2 heading of the governed spec tree"
    )


def _unresolved_reference_finding(*, item: WorkItem, reference: str) -> str:
    return (
        f"work-item {item.id}: the Definition of Done reference {reference!r} does not"
        " resolve to an H2 heading of the governed spec tree; correct the heading"
        " text and its `## ` marker to match the spec tree verbatim"
    )


def _stray_line_finding(*, item: WorkItem, line: str) -> str:
    """The finding for one line the section's grammar does not admit.

    The line is quoted VERBATIM, because the remedy is to move or delete that
    one line and a paraphrase would send its author hunting for it. The remedy
    names BOTH routes — move it out of the section, or make it a bullet — because
    which one is right is the author's call: a provenance paragraph belongs
    outside the section, while a sentence the author meant as an assertion
    belongs on a bullet of its own.
    """
    return (
        f"work-item {item.id}: the Definition of Done section carries the line"
        f" {line!r}, which is neither a `- ` bullet, one of the"
        f" {_OPT_OUT_SUB_HEADINGS} sub-headings or its `{REASON_PREFIX}` line,"
        f" nor the `{REFERENCES_PREFIX}` line; move it out of the section, under"
        " a heading of its own, or make it a `- ` bullet carrying one gradeable"
        " assertion"
    )


def _malformed_proof_mode_finding(*, item: WorkItem, sub_heading: str) -> str:
    """The finding for one opt-out sub-heading that stated no reason.

    The REMEDY differs per mode, and the mode is recovered from the sub-heading
    through the parser's own table rather than re-derived here: a `Host-captured`
    sub-heading owes the host surface or the released-build requirement, and a
    `Human-attested` one owes the capability no sandbox has. A finding that named
    the wrong one would send the author to write a sentence that cannot clear it.
    """
    mode = declared_proof_mode(sub_heading=sub_heading)
    return (
        f"work-item {item.id}: the Definition of Done `{sub_heading}` sub-heading"
        f" carries no non-empty `{REASON_PREFIX}` line, so its `{mode}`"
        f" proof-mode declaration is malformed; add a `{REASON_PREFIX} <text>` line"
        f" naming {_REASON_SUBJECTS[mode]}"
    )
