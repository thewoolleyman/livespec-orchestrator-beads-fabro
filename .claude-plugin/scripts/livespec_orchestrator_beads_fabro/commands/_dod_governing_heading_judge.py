"""Taking the spec-stated judgement for ONE item's governing-heading verdict.

The IMPURE half of `_dod_governing_heading`, split the way every
pure-from-impure pair in this tree is: the findings and the subject block are a
function of a verdict handed to them, and a decision that reached for a model
itself could not be exercised without one.

WHAT IT ASKS, AND OF WHOM. `contracts.md` section "Dispatcher admission, WIP
cap, and post-merge acceptance" makes the spec-stated judgement the COMPONENT
the Definition-of-Done judgement consults for the governing-heading verdict, so
the question put to the model is the shared runtime's own — "does the ratified
tree state this behaviour, and which H2 clauses state it" — rendered by
`livespec_runtime.spec_stated.judge` and nothing of this module's devising.

THROUGH `judge_within_ceiling` AND NEVER THROUGH `spec_stated.judge`, for the
reason both existing consumers record: the shared judgement renders the whole
spec tree into every prompt and this repository's tree exceeds the judging
model's input ceiling, so a caller reaching the bare entry point takes NO
judgement rather than a bigger one, and the refusal surfaces as a verdict
nobody could read.

FOUR PROPERTIES AN EDITOR MUST NOT INVERT.

THE READER IS AN INJECTED SEAM, AND ITS ABSENT ARM IS NAMED RATHER THAN
DEFAULTED, exactly as `attachment_digest_reader`'s `unverified_attachment` is.
The surfaces that consult the governing-heading verdict do not all have a model
call to spare: the `needs-attention` hygiene lane grades every item in the
tenant, and a reader that reached for a judge there would turn one listing into
a model call per item. So `unjudged_governing_heading` exists for the caller
that must not spend one, and answers "no verdict" — which every consumer reads
as the absence of evidence and none reads as a clean citation.

BUT A REFUSING SURFACE DEFAULTS TO THE HOST READER, not to that arm. Both the
pre-admission/pre-dispatch gate and the filing display grade ONE item and are
read as the authority on whether its reference line governs, so a default that
silently took no judgement would report a clean citation for an item the other
surface holds. The two walls therefore name this host's reader as their own
default and let a caller pass the absent arm explicitly, which is the opposite
of what a seam defaulting to absent would give them.

EVERY FAILURE IS AN ABSENT VERDICT RATHER THAN AN EXCEPTION. The three ways
this can fail — an unreadable spec tree, a judge that will not run, a response
the shared parser refuses — are each a failure to MEASURE, and all three reach
callers sitting on the dispatch path, the intake path and the approve valve. An
exception there is a bug-class escape from a surface whose whole job is to
render an actionable refusal, and the honest answer is the one the pure half
already fails open on.

THE MODEL BINDING IS BORROWED RATHER THAN RESTATED. `drift_judge` is this
repository's one `ModelRunner` over the shared judgement: it resolves the judge
executable and the credential through the Definition-of-Done judge's own
resolvers, and it puts the prompt on STANDARD INPUT, which is a correctness
requirement rather than a style — the rendered prompt carries the entire
ratified tree, measured at 1.36 MB here, against a 131072-byte single-argv-entry
kernel cap, so an argv-borne prompt makes every taking die at `execve`. A second
account of either would drift from the first with both answers looking
plausible.

AN ITEM WITH NO SECTION IS NEVER JUDGED. There is no assertion to ask about, the
absent section is the mechanical wall's own finding, and spending a model call
to be told that nothing is stated would report a reference-line defect on an
item that has no reference line.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from typing import TYPE_CHECKING, Protocol

from livespec_runtime.spec_stated import ClauseEvidence
from returns.result import Failure

from livespec_orchestrator_beads_fabro.commands._dispatcher_definition_of_done import (
    definition_of_done,
)
from livespec_orchestrator_beads_fabro.commands._dod_governing_heading import (
    GoverningHeadingVerdict,
    governing_heading_statement,
    verdict_named_headings,
)
from livespec_orchestrator_beads_fabro.commands._drift_run_judge import drift_judge
from livespec_orchestrator_beads_fabro.commands._spec_stated_citation import (
    judged_prompt_ceiling,
)
from livespec_orchestrator_beads_fabro.commands._spec_tree_condensation import (
    PROMPT_CHARACTER_CEILING,
    CondensedClause,
    clauses_named,
    condensed_spec_tree,
    headings_resolved,
    judge_within_ceiling,
)
from livespec_orchestrator_beads_fabro.effects import AttemptFailure, attempt
from livespec_orchestrator_beads_fabro.spec_reader import read_current_specification

if TYPE_CHECKING:
    from pathlib import Path

    from livespec_runtime.spec_stated import ModelRunner

    from livespec_orchestrator_beads_fabro.commands._dispatcher_dod_judgement_candidates import (
        CandidateChainResult,
    )
    from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandRunner
    from livespec_orchestrator_beads_fabro.types import WorkItem

__all__: list[str] = [
    "SPECIFICATION_DIRNAME",
    "GoverningHeadingReader",
    "governing_heading_verdict",
    "host_governing_heading_reader",
    "unjudged_governing_heading",
]

# Where the governed spec tree sits under a repository root. Named once here
# because both the judgement's own read and the spec identity the reuse digest
# is taken over have to name the SAME tree: two spellings would let a verdict be
# reused across a change to a tree the digest was not watching.
SPECIFICATION_DIRNAME = "SPECIFICATION"
_EVIDENCE_REQUEST = (
    "\n\nFor every heading in stated_by, also include evidence as a JSON list of objects "
    "with that heading and one non-empty, verbatim single-line quote from its clause that "
    "states the behaviour."
)
_CONTENT_TERM = re.compile(r"[^\W\d_]{3,}", re.UNICODE)
_MINIMUM_SHARED_TERMS = 2
_REFERENCES_LINE_PREFIX = "References:"
_NON_CONTENT_TERMS = frozenset(
    {
        "all",
        "and",
        "are",
        "asserts",
        "but",
        "clause",
        "clauses",
        "each",
        "for",
        "from",
        "governing",
        "has",
        "have",
        "heading",
        "headings",
        "into",
        "its",
        "line",
        "not",
        "one",
        "reference",
        "references",
        "that",
        "the",
        "their",
        "this",
        "title",
        "was",
        "when",
        "which",
        "with",
    }
)


class GoverningHeadingReader(Protocol):
    """How a surface asks for one item's governing-heading verdict.

    A Protocol rather than a `Callable` alias so the keyword-only call shape is
    part of the type: every seam in this package is keyword-only, and a
    positional alias is one refactor away from a caller binding `repo` to the
    item.
    """

    def __call__(self, *, item: WorkItem, repo: Path) -> GoverningHeadingVerdict | None:
        """One item's governing-heading verdict, or `None` when none was taken."""


def unjudged_governing_heading(*, item: WorkItem, repo: Path) -> GoverningHeadingVerdict | None:
    """The default reader: no judgement is taken and no verdict is returned.

    Named rather than written as a lambda at each call site, because a surface
    that takes no judgement is making a DECISION about spend and the name is
    where that decision is read off the call.
    """
    del item, repo
    return None


def host_governing_heading_reader(
    *,
    runner: CommandRunner,
    on_chain: Callable[[CandidateChainResult], None] | None = None,
) -> GoverningHeadingReader:
    """A reader that puts the shared judgement to this host's headless judge.

    `runner` is required rather than defaulted, because the surfaces that take
    the judgement already hold one and a default here would be a second place
    this package decides how a subprocess is run.

    `on_chain` is optional because only the surface that displays the judgement
    needs the candidates; every other taking keeps them on standard error.
    """

    def read(*, item: WorkItem, repo: Path) -> GoverningHeadingVerdict | None:
        return governing_heading_verdict(
            item=item,
            repo=repo,
            run_model=drift_judge(
                project_root=repo,
                runner=runner,
                caller="dod_governing_heading",
                on_chain=on_chain,
            ),
        )

    return read


def governing_heading_verdict(
    *, item: WorkItem, repo: Path, run_model: ModelRunner
) -> GoverningHeadingVerdict | None:
    """One item's governing-heading verdict, or `None` when it could not be taken."""
    section = definition_of_done(description=item.description)
    if not section.present:
        return None
    # `UnicodeDecodeError` as well as `OSError`, and it is the arm that bites:
    # the reader opens every spec file with `read_text(encoding="utf-8")`, and a
    # file carrying one invalid byte raises a `ValueError` subclass rather than
    # an `OSError` — so a catch naming only `OSError` lets that escape through
    # the pre-dispatch wall, the intake router and the approve valve as a
    # traceback. An ABSENT tree raises neither: `rglob` on a missing directory
    # yields nothing, so it reads as an empty tree and is refused one step down
    # by the shared parser, which cites a heading no tree carries.
    read = attempt(
        action=lambda: read_current_specification(spec_root=repo / SPECIFICATION_DIRNAME).files,
        exceptions=(OSError, UnicodeDecodeError),
    )
    if isinstance(read, AttemptFailure):
        return None
    statement = governing_heading_statement(item=item, section=section)
    condensed = condensed_spec_tree(
        spec_tree=read,
        statement=statement,
        ceiling=judged_prompt_ceiling(spec_tree=read, ceiling=PROMPT_CHARACTER_CEILING),
    )
    judged = attempt(
        action=lambda: judge_within_ceiling(
            spec_tree=read,
            statement=statement,
            run_model=lambda prompt: run_model(f"{prompt}{_EVIDENCE_REQUEST}"),
        ),
        exceptions=(OSError,),
    )
    if isinstance(judged, AttemptFailure | Failure):
        return None
    verdict = judged.unwrap()
    target = verdict.generalization_target
    # The shared parser type-checks the target and nothing more. One spanning
    # lines would be written into the receipt as extra `key: value` lines, so
    # it is treated exactly as a response the parser refused.
    if target is not None and len(target.splitlines()) > 1:
        return None
    headings = verdict_named_headings(stated_by=verdict.stated_by, generalization_target=target)
    named = clauses_named(spec_tree=read, headings=headings)
    if not _evidence_matches_named_clauses(
        stated_by=verdict.stated_by,
        evidence=verdict.evidence,
        named=named,
        statement=statement,
    ):
        return None
    return GoverningHeadingVerdict(
        kind=verdict.kind,
        stated_by=verdict.stated_by,
        generalization_target=target,
        selected_clauses=condensed.clauses,
        named_clauses=named,
        provenance_complete=headings_resolved(headings=headings, clauses=named),
        evidence=verdict.evidence,
    )


def _evidence_matches_named_clauses(
    *,
    stated_by: tuple[str, ...],
    evidence: tuple[ClauseEvidence, ...],
    named: tuple[CondensedClause, ...],
    statement: str,
) -> bool:
    """Require each named heading to quote the item's asserted behaviour."""
    clauses = {clause.heading: clause.body for clause in named}
    behaviour = "\n".join(
        line for line in statement.splitlines() if not line.startswith(_REFERENCES_LINE_PREFIX)
    )
    statement_terms = _content_terms(text=behaviour)
    required_terms = min(_MINIMUM_SHARED_TERMS, max(len(statement_terms), 1))
    for heading in stated_by:
        quotations = [entry.quote for entry in evidence if entry.heading == heading]
        if len(quotations) != 1:
            return False
        quote = quotations[0]
        if "\n" in quote or quote not in clauses.get(heading, ""):
            return False
        if len(statement_terms.intersection(_content_terms(text=quote))) < required_terms:
            return False
    return len(evidence) == len(stated_by)


def _content_terms(*, text: str) -> frozenset[str]:
    """Meaningful terms a clause must share with the judged item statement."""
    return frozenset(
        term for term in _CONTENT_TERM.findall(text.lower()) if term not in _NON_CONTENT_TERMS
    )
