"""The governing-heading component of a Definition-of-Done judgement.

The component has inputs and reuse provenance distinct from the enclosing
Definition-of-Done rubric.  Keeping its retrieval, comparison and finding
composition together makes that boundary explicit while the gate owns the
shared decision and ledger write.
"""

from __future__ import annotations

import hashlib
from collections.abc import Sequence
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_definition_of_done import (
    definition_of_done,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_dod_judgement import (
    JUDGEMENT_HELD,
    JUDGEMENT_UNAVAILABLE,
    DodJudgement,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_dod_judgement_record import (
    recorded_named_headings,
    reusable_governing_heading,
)
from livespec_orchestrator_beads_fabro.commands._dod_governing_heading import (
    GoverningHeadingVerdict,
    governing_heading_findings,
    governing_heading_holds,
    governing_heading_statement,
)
from livespec_orchestrator_beads_fabro.commands._spec_tree_condensation import (
    clauses_named,
    condensed_spec_tree,
)
from livespec_orchestrator_beads_fabro.spec_reader import read_current_specification
from livespec_orchestrator_beads_fabro.types import WorkItem

__all__: list[str] = [
    "governing_heading_subject_digest",
    "reusable_governing_heading_verdict",
    "with_governing_findings",
]


def governing_heading_subject_digest(*, item: WorkItem, comments: Sequence[str]) -> str:
    """The component input: its statement plus every operator rider.

    The full spec identity is deliberately absent. The component compares the
    full clause bodies its condensed prompt carried instead, while an appended
    rider remains a new input and therefore forces a fresh taking.
    """
    section = definition_of_done(description=item.description)
    statement = governing_heading_statement(item=item, section=section)
    riders = "\n".join(
        comment for comment in comments if not comment.startswith("livespec-dod-judgement")
    )
    return hashlib.sha256(f"{statement}\n{riders}".encode()).hexdigest()


def reusable_governing_heading_verdict(
    *, item: WorkItem, repo: Path, comments: Sequence[str]
) -> GoverningHeadingVerdict | None:
    """Read a component receipt against this revision without spending a model call."""
    section = definition_of_done(description=item.description)
    if not section.present:
        return None
    try:
        spec_tree = read_current_specification(spec_root=repo / "SPECIFICATION").files
    except (OSError, UnicodeDecodeError):
        return None
    statement = governing_heading_statement(item=item, section=section)
    condensed = condensed_spec_tree(spec_tree=spec_tree, statement=statement)
    subject_digest = governing_heading_subject_digest(item=item, comments=comments)
    for body in comments:
        verdict = reusable_governing_heading(
            comments=(body,),
            subject_digest=subject_digest,
            selected_clauses=condensed.clauses,
            named_clauses=clauses_named(
                spec_tree=spec_tree,
                headings=recorded_named_headings(body=body),
            ),
        )
        if verdict is not None:
            return verdict
    return None


def with_governing_findings(
    *, item: WorkItem, verdict: DodJudgement, governing: GoverningHeadingVerdict | None
) -> DodJudgement:
    """Combine a rubric verdict with the governing-heading component's findings.

    A judgement that did not run remains untouched: attaching a mechanical
    finding to it would publish a hold the gate reports as an outage instead.
    """
    if verdict.outcome == JUDGEMENT_UNAVAILABLE:
        return verdict
    section = definition_of_done(description=item.description)
    findings = governing_heading_findings(item=item, section=section, verdict=governing)
    if not findings:
        return verdict
    outcome = (
        JUDGEMENT_HELD
        if governing_heading_holds(section=section, verdict=governing)
        else verdict.outcome
    )
    return DodJudgement(outcome=outcome, findings=verdict.findings + findings, cause=verdict.cause)
