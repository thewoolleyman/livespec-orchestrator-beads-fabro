"""A judgement that cites an EXISTING subsection is a judgement, not a refusal.

`bd-ib-n2drk5`: the shared judgement's prompt asks for verbatim H2 headings, and
`judge` refuses a `stated_by` naming anything its tree does not carry as an H2.
But the ratified text cites its own subsections by name, so a model that reads a
clause correctly names the H3 or H4 SUBSECTION it read — written with a leading
H2 marker — and that correct reading is refused as unreadable.

Measured 2026-10-22 on released v0.234.2, `ledger-intent-scan --since-version
v197` with a Codex judge: every judge call exited 0 and 9 of 15 judgements were
then refused with "stated_by names headings the spec tree does not carry", the
scan exited 4 and no completed-coverage record was written. Each rejected name
exists one level down in `SPECIFICATION/contracts.md` and was in the condensed
prompt with its body, so this is neither a condensation failure nor a judge
failure: it is the citation being read at the wrong heading level.

SO THE RESOLUTION IS DETERMINISTIC AND THE PROMPT IS NOT THE REMEDY. The prompt
ALREADY demands verbatim H2 headings; the model's habit of naming the subsection
it actually read is predictable, and an instruction that is already there cannot
be strengthened into a fix. The citation is resolved to the enclosing H2 before
the shared judgement validates it.

AND THE NEGATIVE IS WHAT MAKES THAT SAFE. Resolving an existing subsection and
accepting anything are the same observation from the citing side; only a heading
that exists at NO level of the governed tree, still refused, tells them apart.
`judge`'s refusal is the property that makes a verdict naming a clause nobody
can open worse than no verdict at all, and the resolution must not spend it.

THE REAL-TREE CASES ARE THE MEASURED ONES, named here with their measured
enclosing clauses, rather than synthetic stand-ins: a synthetic H3 proves the
mapping exists, and only this repository's own tree proves it maps the citations
the live scan was refused for. The synthetic tree beside them carries the two
shapes the real tree has none of — a subsection no H2 encloses, and one two
clauses carry — because both must stay REFUSED: a citation that cannot be
resolved to exactly one governing clause is worse resolved than left alone.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._spec_tree_condensation import (
    judge_within_ceiling,
)
from livespec_orchestrator_beads_fabro.spec_reader import read_current_specification
from livespec_runtime.spec_stated import SpecStatedParseError, SpecStatedVerdict
from returns.pipeline import is_successful
from returns.result import Result

_SPEC_ROOT = Path(__file__).resolve().parents[3] / "SPECIFICATION"

# The two measured citations, with the clauses that enclose them. Both were
# refused by the live scan; both exist in `SPECIFICATION/contracts.md`.
_H3_CITATION = "## Effective acceptance criteria"
_H3_ENCLOSING = "## Dispatcher admission, WIP cap, and post-merge acceptance"
_H4_CITATION = "## Detection coverage records and staleness facts"
_H4_ENCLOSING = "## The skill surface"

# The one heading the same scan cited that exists at NO level of the tree.
_INVENTED = "## Named workflow variants"

_STATEMENT = (
    "Work item bd-ib-n2drk5\n\nTitle: periwinkle quokka telemetry rehoming\n\n"
    "Description: the periwinkle quokka telemetry is rehomed onto the "
    "quokka transponder."
)

_UNENCLOSED = "### A subsection before any governing clause"
_SHARED = "### A subsection two clauses carry"
_FIRST = "## The first governing clause"
_SECOND = "## The second governing clause"
_TREE = {
    "contracts.md": (
        f"{_UNENCLOSED}\n\nSome preamble prose.\n\n"
        f"{_FIRST}\n\n{_SHARED}\n\nSome prose.\n\n"
        f"{_SECOND}\n\n{_SHARED}\n\nSome other prose.\n"
    )
}
_TIGHT_CEILING = 20_000


@dataclass(kw_only=True)
class _Citing:
    """A `ModelRunner` answering `stated`, citing the headings it was given."""

    stated_by: tuple[str, ...]
    generalization_target: str | None = None
    prompts: list[str] = field(default_factory=list)

    def __call__(self, prompt: str) -> str:
        self.prompts.append(prompt)
        return json.dumps(
            {
                "kind": "stated",
                "stated_by": list(self.stated_by),
                "generalization_target": self.generalization_target,
                "rationale": "the ratified text states it",
            }
        )


@dataclass(frozen=True, kw_only=True)
class _Answering:
    """A `ModelRunner` returning one fixed response, well-formed or not."""

    response: str

    def __call__(self, _prompt: str) -> str:
        return self.response


def _judged_against_the_real_tree(
    *, model: _Citing
) -> Result[SpecStatedVerdict, SpecStatedParseError]:
    """One judgement of `_STATEMENT` against this repository's governed tree."""
    return judge_within_ceiling(
        spec_tree=read_current_specification(spec_root=_SPEC_ROOT).files,
        statement=_STATEMENT,
        run_model=model,
    )


def test_an_h3_citation_is_read_as_its_enclosing_h2() -> None:
    """The measured H3 citation yields a verdict naming the clause around it."""
    verdict = _judged_against_the_real_tree(model=_Citing(stated_by=(_H3_CITATION,)))

    assert is_successful(verdict), (
        "a citation of an existing H3 subsection is still refused, so a model "
        "that read the ratified text correctly is reported as unreadable"
    )
    assert verdict.unwrap().stated_by == (_H3_ENCLOSING,)


def test_an_h4_citation_is_read_as_its_enclosing_h2() -> None:
    """The mapping reaches H4, not only the level immediately below H2."""
    verdict = _judged_against_the_real_tree(model=_Citing(stated_by=(_H4_CITATION,)))

    assert is_successful(verdict)
    assert verdict.unwrap().stated_by == (_H4_ENCLOSING,)


def test_a_heading_the_tree_carries_at_no_level_is_still_refused() -> None:
    """Resolving existing subsections is not accepting invented clauses."""
    verdict = _judged_against_the_real_tree(model=_Citing(stated_by=(_INVENTED,)))

    assert not is_successful(verdict)
    assert verdict.failure().field == "stated_by"


def test_a_generalization_target_is_resolved_the_same_way() -> None:
    """The target names a clause a proposal can be filed against, or nothing."""
    model = _Citing(stated_by=(_H3_ENCLOSING,), generalization_target=_H4_CITATION)

    verdict = _judged_against_the_real_tree(model=model)

    assert is_successful(verdict)
    unwrapped = verdict.unwrap()
    assert unwrapped.stated_by == (_H3_ENCLOSING,), (
        "a citation that already names a governing clause was rewritten, so the "
        "resolution is reaching citations it has no business touching"
    )
    assert unwrapped.generalization_target == _H4_ENCLOSING


def _judged_against_the_synthetic_tree(
    *, model: _Citing | _Answering
) -> Result[SpecStatedVerdict, SpecStatedParseError]:
    """One judgement of `_STATEMENT` against the two unresolvable shapes."""
    return judge_within_ceiling(
        spec_tree=_TREE,
        statement=_STATEMENT,
        run_model=model,
        ceiling=_TIGHT_CEILING,
    )


def test_a_subsection_no_governing_clause_encloses_is_refused() -> None:
    """A preamble subsection resolves to no clause, so it resolves to none."""
    verdict = _judged_against_the_synthetic_tree(model=_Citing(stated_by=(_UNENCLOSED,)))

    assert not is_successful(verdict)
    assert verdict.failure().field == "stated_by"


def test_a_subsection_two_governing_clauses_carry_is_refused() -> None:
    """Picking one of two enclosing clauses would name a clause nobody cited."""
    verdict = _judged_against_the_synthetic_tree(model=_Citing(stated_by=(_SHARED,)))

    assert not is_successful(verdict)
    assert verdict.failure().field == "stated_by"


def test_a_response_that_is_not_json_is_left_for_the_shared_parser() -> None:
    """The resolution rewrites citations; it does not report malformedness."""
    verdict = _judged_against_the_synthetic_tree(model=_Answering(response="not JSON at all"))

    assert not is_successful(verdict)
    assert verdict.failure().field is None


def test_a_response_that_is_not_a_json_object_is_left_alone_too() -> None:
    """A JSON array carries no citation field to resolve."""
    verdict = _judged_against_the_synthetic_tree(model=_Answering(response="[]"))

    assert not is_successful(verdict)
    assert verdict.failure().field is None


def test_a_stated_by_that_is_not_a_list_is_left_for_the_shared_parser() -> None:
    """The field's SHAPE is the shared parser's finding, not this module's."""
    response = json.dumps(
        {
            "kind": "stated",
            "stated_by": _H3_CITATION,
            "generalization_target": None,
            "rationale": "one heading, unlisted",
        }
    )

    verdict = _judged_against_the_synthetic_tree(model=_Answering(response=response))

    assert not is_successful(verdict)
    assert verdict.failure().field == "stated_by"


def test_a_non_string_entry_of_stated_by_is_carried_through() -> None:
    """An entry that is not a heading is not a heading to resolve."""
    response = json.dumps(
        {
            "kind": "stated",
            "stated_by": [17],
            "generalization_target": None,
            "rationale": "a number, not a heading",
        }
    )

    verdict = _judged_against_the_synthetic_tree(model=_Answering(response=response))

    assert not is_successful(verdict)
    assert verdict.failure().field == "stated_by"
