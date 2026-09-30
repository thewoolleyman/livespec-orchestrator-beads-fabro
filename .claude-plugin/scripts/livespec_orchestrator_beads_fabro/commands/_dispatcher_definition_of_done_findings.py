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

WHY AN UNREADABLE SPEC TREE SKIPS THE REFERENCE CHECK RATHER THAN REFUSING.
Every other fail-direction decision in this wall's neighbourhood chooses the
ARMED side, and `_dispatcher_criteria_wall_variant` explains why. This one is
deliberately the other way, and the asymmetry is the point: an unresolvable
workflow variant refuses ONE item that also happens to lack criteria, while an
unreadable spec tree would refuse EVERY implement-kind item in the repository —
a whole-factory outage produced by an environment fault, whose refusal text
would name a heading that is perfectly valid. An empty H2 set is not evidence
that a reference is wrong; it is the absence of evidence either way, and the
clause's own evidence rule forbids manufacturing a verdict from that. The
pure-parse checks are unaffected, so a genuinely malformed item is still refused
on the checks that CAN be observed.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from livespec_orchestrator_beads_fabro.commands._dispatcher_definition_of_done import (
    REFERENCES_PREFIX,
    definition_of_done,
)
from livespec_orchestrator_beads_fabro.effects import AttemptFailure, attempt

if TYPE_CHECKING:
    from pathlib import Path

    from livespec_orchestrator_beads_fabro.types import WorkItem

__all__: list[str] = [
    "definition_of_done_findings",
    "spec_h2_headings",
]

# The governed spec tree's directory name, as the repository layout fixes it and
# as `_needs_attention_detection_staleness` already reads it.
_SPEC_DIRNAME = "SPECIFICATION"
# Only the tree's OWN top-level files. `history/` and `proposed_changes/` are
# deliberately out: a reference must name a heading of the CURRENT ratified spec,
# and admitting a historical snapshot's headings would let a reference resolve
# against a clause that has since been replaced.
_SPEC_FILE_GLOB = "*.md"
_H2 = re.compile(r"^##\s+(.+?)\s*$")


def spec_h2_headings(*, repo: Path) -> frozenset[str]:
    """The H2 headings of the governed spec tree's own top-level files.

    Each heading enters the set twice, as the verbatim `## <title>` line and as
    the bare `<title>`, so a reference that omits the marker resolves against the
    same real heading. That is not a loosened check: both forms still have to
    name a heading the tree actually carries.

    An empty set means the tree could not be read (absent directory, unreadable
    file), NOT that the tree carries no heading — see this module's docstring for
    what the caller must do with that distinction.
    """
    spec_root = repo / _SPEC_DIRNAME
    if not spec_root.is_dir():
        return frozenset()
    headings: set[str] = set()
    for path in sorted(spec_root.glob(_SPEC_FILE_GLOB)):
        read = attempt(action=lambda p=path: p.read_text(encoding="utf-8"), exceptions=(OSError,))
        if isinstance(read, AttemptFailure):
            continue
        for raw in read.splitlines():
            match = _H2.match(raw)
            if match is not None:
                title = match.group(1)
                headings.add(title)
                headings.add(f"## {title}")
    return frozenset(headings)


def definition_of_done_findings(*, item: WorkItem, cwd: Path) -> tuple[str, ...]:
    """Every mechanical Definition-of-Done finding for one item, or an empty tuple.

    An absent section returns EARLY with the one finding that matters: every
    later check reads a section that is not there, so reporting "no section" and
    "no reference line" for the same item would name one fault twice and bury the
    remedy the operator actually needs.
    """
    section = definition_of_done(description=item.description)
    if not section.present:
        return (_absent_section_finding(item=item),)
    findings: list[str] = []
    if not section.references:
        findings.append(_absent_reference_line_finding(item=item))
    findings.extend(
        _unresolved_reference_finding(item=item, reference=reference)
        for reference in _unresolved_references(section_references=section.references, cwd=cwd)
    )
    return tuple(findings)


def _unresolved_references(*, section_references: tuple[str, ...], cwd: Path) -> tuple[str, ...]:
    """The references that name no heading the spec tree carries, in order."""
    headings = spec_h2_headings(repo=cwd)
    if not headings:
        return ()
    return tuple(reference for reference in section_references if reference not in headings)


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
        " text to match the spec tree verbatim"
    )
