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

THE READER IS AN INJECTED SEAM DEFAULTING TO ABSENT, exactly as
`attachment_digest_reader` defaults to `unverified_attachment`. The surfaces
that consult the governing-heading verdict do not all have a model call to
spare: the `needs-attention` hygiene lane grades every item in the tenant, and
a default that reached for a judge would turn one listing into a model call per
item. The default therefore answers "no verdict", which every consumer reads as
the absence of evidence and none reads as a clean citation.

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

from typing import TYPE_CHECKING, Protocol

from returns.result import Failure

from livespec_orchestrator_beads_fabro.commands._dispatcher_definition_of_done import (
    definition_of_done,
)
from livespec_orchestrator_beads_fabro.commands._dod_governing_heading import (
    GoverningHeadingVerdict,
    governing_heading_statement,
)
from livespec_orchestrator_beads_fabro.commands._drift_run_judge import drift_judge
from livespec_orchestrator_beads_fabro.commands._spec_tree_condensation import (
    judge_within_ceiling,
)
from livespec_orchestrator_beads_fabro.effects import AttemptFailure, attempt
from livespec_orchestrator_beads_fabro.spec_reader import read_current_specification

if TYPE_CHECKING:
    from pathlib import Path

    from livespec_runtime.spec_stated import ModelRunner

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


def host_governing_heading_reader(*, runner: CommandRunner) -> GoverningHeadingReader:
    """A reader that puts the shared judgement to this host's headless judge.

    `runner` is required rather than defaulted, because the surfaces that take
    the judgement already hold one and a default here would be a second place
    this package decides how a subprocess is run.
    """

    def read(*, item: WorkItem, repo: Path) -> GoverningHeadingVerdict | None:
        return governing_heading_verdict(
            item=item, repo=repo, run_model=drift_judge(project_root=repo, runner=runner)
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
    judged = attempt(
        action=lambda: judge_within_ceiling(
            spec_tree=read,
            statement=governing_heading_statement(item=item, section=section),
            run_model=run_model,
        ),
        exceptions=(OSError,),
    )
    if isinstance(judged, AttemptFailure | Failure):
        return None
    verdict = judged.unwrap()
    return GoverningHeadingVerdict(
        kind=verdict.kind,
        stated_by=verdict.stated_by,
        generalization_target=verdict.generalization_target,
    )
