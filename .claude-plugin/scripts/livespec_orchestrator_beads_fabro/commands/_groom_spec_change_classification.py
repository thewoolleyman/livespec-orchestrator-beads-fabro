"""The GROOM cadence point of the spec-change-tier classification.

The autonomy-tier bullet of `SPECIFICATION/contracts.md` names three positions —
"At filing, at groom and again on every dispatch path, every implement-kind item
MUST be classified" — and says the tier is "DECIDED by the spec-stated
judgement ... never declared by the filer". At groom the FILER IS THE DRAFT, and
`CandidateSlice.is_spec_change` is exactly such a declaration: the groom
front-end pre-fills it, and `file_approved_slices` routes on it, sending a
declared spec-change slice to `/livespec:propose-change` and filing every other
slice into the factory ledger.

So the draft's flag is EVIDENCE here in the same sense the stored type is
evidence at filing — it is what somebody happened to record — and the judgement
is the answer. The defect it repairs is two-sided, which is why both directions
matter: a slice the maintainer drafted as factory work whose behaviour the spec
does not state must be ROUTED to propose-change, and a slice drafted as
spec-change whose behaviour the ratified text already states must be FILED as
the ordinary follow-up it is.

WHY THIS IS A CADENCE POINT OF ITS OWN RATHER THAN A CONSEQUENCE OF FILING.
Groom's local slices ARE filed through the intake primitive, which classifies —
so a reader may reasonably ask what this adds. It adds the two slices intake
never sees: a slice the draft declared spec-change is never filed at all (it is
routed out, and no id is ever minted for it), and a cross-repo slice is minted
but filed in another tenant. A classification that happened only at filing
therefore could not reach the one decision groom actually makes.

WHY THERE IS NO LEDGER RECORD HERE. A candidate is not a work-item: it has no
id, so there is nothing to record a classification ON, and a record written here
would have to invent an identity the record reader could never match. The
verdict's durable home is the record intake writes when the slice is FILED —
which is a fresh judgement of the same behaviour rather than a reuse of this
one, precisely because the statement a candidate renders cannot carry the id the
filed statement opens with.

A JUDGEMENT THAT CANNOT RUN LEAVES THE DRAFT'S OWN DECLARATION STANDING, which
is the clause's route-as-before direction at this position. The groom cut is the
MAINTAINER's, approved slice by slice, so a classifier outage must not silently
re-route a slice they declared — and the backstops are unchanged: a filed slice
is classified again at filing, and the `dod_gate` node refuses an unstated
feature before any implementation spend.
"""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING

from livespec_runtime import spec_stated
from returns.pipeline import is_successful

from livespec_orchestrator_beads_fabro.commands._dispatcher_io import ShellCommandRunner
from livespec_orchestrator_beads_fabro.commands._drift_run_judge import drift_judge
from livespec_orchestrator_beads_fabro.commands._spec_change_tier import (
    FEATURE_CLASS,
    SPEC_CHANGE_KINDS,
    SPEC_DIRNAME,
)
from livespec_orchestrator_beads_fabro.commands._spec_tree_condensation import (
    judge_within_ceiling,
)
from livespec_orchestrator_beads_fabro.effects import AttemptFailure, attempt
from livespec_orchestrator_beads_fabro.spec_reader import read_current_specification

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence
    from pathlib import Path

    from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandRunner
    from livespec_orchestrator_beads_fabro.commands._groom_types import CandidateSlice

__all__: list[str] = ["classified_candidate_slices"]

_FIELD_ABSENT = "(none recorded)"
# How the draft's own declaration is rendered into the classifier's evidence
# slot. Self-describing words rather than a boolean, because the prompt renders
# the value into a sentence an operator reads back in the rationale.
_DRAFT_DECLARED_SPEC_CHANGE = "spec-change"
_DRAFT_DECLARED_FACTORY = "factory"


def classified_candidate_slices(
    *,
    slices: Sequence[CandidateSlice],
    repo: Path,
    runner: CommandRunner | None = None,
) -> list[CandidateSlice]:
    """Each candidate with `is_spec_change` decided by the shared judgement.

    The spec tree is read ONCE for the whole draft and the model runner resolved
    once, so a cut of ten slices pays one tree read and one credential
    resolution rather than ten of each — the same resolve-once reason
    `drift_judge` gives for returning a closure.

    An unreadable or empty spec tree returns the slices UNTOUCHED, identically
    to how a single unjudgeable slice keeps its own declaration: there is no
    governing clause to judge against, so every verdict would be `unstated` and
    the whole cut would be re-routed to propose-change on the strength of a
    specification nobody could read.
    """
    tree = _spec_tree(repo=repo)
    if tree is None:
        return list(slices)
    run_model = drift_judge(project_root=repo, runner=runner or ShellCommandRunner())
    return [_classified(candidate=one, tree=tree, run_model=run_model) for one in slices]


def _classified(
    *,
    candidate: CandidateSlice,
    tree: Mapping[str, str],
    run_model: spec_stated.ModelRunner,
) -> CandidateSlice:
    """One candidate's tier, or the candidate unchanged when nothing decided it.

    The CLASSIFICATION runs before the judgement for the reason the gate's own
    order gives: three of the four classes are exempt outright, so a `bug` or a
    `chore` never pays for the judgement at all.
    """
    classification = spec_stated.classify(
        title=candidate.title,
        description=candidate.description,
        # The draft's own declaration, rendered as the evidence it is. The
        # classifier is told in as many words that the stored type "is evidence
        # ABOUT the item and never the answer", and this is the groom-time
        # equivalent of that type.
        item_type=(
            _DRAFT_DECLARED_SPEC_CHANGE if candidate.is_spec_change else _DRAFT_DECLARED_FACTORY
        ),
        run_model=run_model,
    )
    if not is_successful(classification):
        return candidate
    if classification.unwrap() != FEATURE_CLASS:
        return replace(candidate, is_spec_change=False)
    verdict = judge_within_ceiling(
        spec_tree=tree, statement=_behaviour(candidate=candidate), run_model=run_model
    )
    if not is_successful(verdict):
        return candidate
    return replace(candidate, is_spec_change=verdict.unwrap().kind in SPEC_CHANGE_KINDS)


def _behaviour(*, candidate: CandidateSlice) -> str:
    """One candidate's asked-for behaviour, as the statement under judgement.

    The same three fields `_spec_change_tier.asked_for_behaviour` renders for a
    filed item — title, description, acceptance criteria — so that a groom
    verdict and the filing verdict of the same slice are judgements of the same
    behaviour rather than of two different statements.

    It is NOT byte-identical to that renderer's output and cannot be: that one
    opens with the item's ID, which a candidate does not have yet. So the filing
    classification RE-TAKES the judgement rather than reusing this one, and this
    verdict's only consumer is the routing decision immediately below. That is
    the honest reading of a cadence point that runs before any work-item exists,
    and it is why nothing here writes a ledger record.
    """
    return "\n\n".join(
        [
            f"Drafted slice {candidate.title}",
            f"Title: {_recorded(value=candidate.title)}",
            f"Description: {_recorded(value=candidate.description)}",
            f"Acceptance criteria: {_recorded(value=candidate.acceptance)}",
        ]
    )


def _recorded(*, value: str | None) -> str:
    """One statement field as the judge sees it, or the mark that it is unset."""
    if value is None or value.strip() == "":
        return _FIELD_ABSENT
    return value.strip()


def _spec_tree(*, repo: Path) -> Mapping[str, str] | None:
    """The governed spec tree, or `None` when there is none to judge against."""
    read = attempt(
        action=lambda: read_current_specification(spec_root=repo / SPEC_DIRNAME),
        exceptions=(OSError,),
    )
    if isinstance(read, AttemptFailure) or not read.files:
        return None
    return read.files
