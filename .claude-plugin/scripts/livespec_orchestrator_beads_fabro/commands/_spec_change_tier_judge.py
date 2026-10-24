"""Taking the spec-change-tier classification of ONE work-item.

The IMPURE half of `_spec_change_tier`, split the way every pure-from-impure
pair in this tree is: the decision and the record are a function of a verdict
handed to them, and a reader that reached for a model itself could not be
exercised without one.

WHAT IT ASKS, AND OF WHOM. The autonomy-tier bullet makes the classification
the shared judgement's — "the spec-change tier is DECIDED by the spec-stated
judgement ..., the stored type being evidence rather than the answer" — so both
questions put to the model are `livespec_runtime.spec_stated`'s own, and
nothing of this module's devising. The stored type travels into the
classification prompt as EVIDENCE, which is the shared prompt's own wording.

FIVE PROPERTIES AN EDITOR MUST NOT INVERT.

AN EXEMPT CLASS TAKES NO BEHAVIOUR JUDGEMENT AT ALL. "An item classified `bug`,
`chore` or `non_functional` is never spec-change tier and routes as every other
factory-dispatchable item", so the second model call is not made for one. That
is not only a saving: the record's `stated_kind` is then `None`, which says
honestly that no behaviour verdict was MEASURED rather than that the behaviour
is stated.

THE BEHAVIOUR VERDICT IS THE GOVERNING-HEADING COMPONENT'S, reached through
`governing_heading_verdict` rather than through a second reading of its own.
That function already renders the statement from the item's Definition of Done,
reads the governed tree, resolves a subsection citation and goes through
`judge_within_ceiling` — and a second account of any of those would drift from
the one the Definition-of-Done judgement uses, with both answers looking
plausible.

A HALF-TAKEN CLASSIFICATION IS NOT A TIER. A feature whose behaviour verdict
could not be taken answers `None`, because a verdict carrying a class and no
stated kind would decide `spec-change` for every such item — the fail-CLOSED
direction, which the clause explicitly does not want: "When the classification
cannot run ..., intake MUST record that on the item and route it as it would
without the classification."

EVERY FAILURE IS AN ABSENT CLASSIFICATION RATHER THAN AN EXCEPTION, for the
reason `_dod_governing_heading_judge` gives for its own: the surfaces that
consult this sit on the dispatch path, the intake path and the approve valve,
and an exception there is a bug-class escape from a surface whose whole job is
to render an actionable refusal.

THE MODEL BINDING IS BORROWED RATHER THAN RESTATED. `drift_judge` is this
repository's one `ModelRunner` over the shared judgement, and it puts the
prompt on STANDARD INPUT, which is a correctness requirement rather than a
style — the rendered behaviour prompt carries the whole ratified tree against a
131072-byte single-argv-entry kernel cap.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

from livespec_runtime.spec_stated import classify
from returns.result import Failure

from livespec_orchestrator_beads_fabro.commands._dod_governing_heading_judge import (
    governing_heading_verdict,
)
from livespec_orchestrator_beads_fabro.commands._drift_run_judge import drift_judge
from livespec_orchestrator_beads_fabro.commands._spec_change_tier import (
    CLASS_FEATURE,
    SpecChangeTierVerdict,
)
from livespec_orchestrator_beads_fabro.effects import AttemptFailure, attempt

if TYPE_CHECKING:
    from pathlib import Path

    from livespec_runtime.spec_stated import ModelRunner

    from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandRunner
    from livespec_orchestrator_beads_fabro.types import WorkItem

__all__: list[str] = [
    "SpecChangeTierReader",
    "host_spec_change_tier_reader",
    "spec_change_tier_classification",
    "unclassified_spec_change_tier",
]


class SpecChangeTierReader(Protocol):
    """How a surface asks for one item's spec-change-tier classification.

    A Protocol rather than a `Callable` alias so the keyword-only call shape is
    part of the type: every seam in this package is keyword-only, and a
    positional alias is one refactor away from a caller binding `repo` to the
    item.
    """

    def __call__(
        self, *, item: WorkItem, repo: Path, linked_topic: str | None, topic_ratified: bool
    ) -> SpecChangeTierVerdict | None:
        """One item's classification, or `None` when none could be taken."""


def unclassified_spec_change_tier(
    *, item: WorkItem, repo: Path, linked_topic: str | None, topic_ratified: bool
) -> SpecChangeTierVerdict | None:
    """The default reader: no classification is taken and none is returned.

    Named rather than written as a lambda at each call site, because a surface
    that takes no classification is making a DECISION about spend and the name
    is where that decision is read off the call.
    """
    del item, repo, linked_topic, topic_ratified
    return None


def host_spec_change_tier_reader(*, runner: CommandRunner) -> SpecChangeTierReader:
    """A reader that puts both questions to this host's headless judge.

    `runner` is required rather than defaulted, because the surfaces that take
    the classification already hold one and a default here would be a second
    place this package decides how a subprocess is run.
    """

    def read(
        *, item: WorkItem, repo: Path, linked_topic: str | None, topic_ratified: bool
    ) -> SpecChangeTierVerdict | None:
        return spec_change_tier_classification(
            item=item,
            repo=repo,
            linked_topic=linked_topic,
            topic_ratified=topic_ratified,
            run_model=drift_judge(project_root=repo, runner=runner),
        )

    return read


def spec_change_tier_classification(
    *,
    item: WorkItem,
    repo: Path,
    linked_topic: str | None,
    topic_ratified: bool,
    run_model: ModelRunner,
) -> SpecChangeTierVerdict | None:
    """One item's classification, or `None` when it could not be taken."""
    item_class = _classified(item=item, run_model=run_model)
    if item_class is None:
        return None
    if item_class != CLASS_FEATURE:
        return SpecChangeTierVerdict(item_class=item_class)
    governing = governing_heading_verdict(item=item, repo=repo, run_model=run_model)
    if governing is None:
        return None
    return SpecChangeTierVerdict(
        item_class=item_class,
        stated_kind=governing.kind,
        generalization_target=governing.generalization_target,
        linked_proposal_topic=linked_topic,
        topic_ratified=topic_ratified,
    )


def _classified(*, item: WorkItem, run_model: ModelRunner) -> str | None:
    """The class the shared judgement returns, or `None` when it could not run.

    The `OSError` catch is the host half of the seam: the model binding writes
    the prompt to a file before it spawns the judge, so the call can fail at the
    filesystem rather than at the model, and that failure must reach a caller as
    the absent measurement it is.
    """
    classified = attempt(
        action=lambda: classify(
            title=item.title,
            description=item.description,
            item_type=item.type,
            run_model=run_model,
        ),
        exceptions=(OSError,),
    )
    if isinstance(classified, AttemptFailure | Failure):
        return None
    return classified.unwrap()
