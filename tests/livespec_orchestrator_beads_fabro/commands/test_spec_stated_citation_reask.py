"""Citation normalization and bounded correction for spec-stated judgements."""

from __future__ import annotations

import json
from dataclasses import dataclass, field

from livespec_orchestrator_beads_fabro.commands._spec_tree_condensation import (
    judge_within_ceiling,
)
from returns.pipeline import is_successful

_STATEMENT = "Work item bd-ib-6ztguf\n\nTitle: citation resolution"
_GOVERNING = "## The governing clause"
_SUBHEADING = "#### `capture-spec-drift`"
_TREE = {
    "contracts.md": f"{_GOVERNING}\n\n{_SUBHEADING}\n\nThe clause text.\n",
}


@dataclass(kw_only=True)
class _Citing:
    """A model that makes one spec-stated response and records its prompt."""

    stated_by: tuple[str, ...]
    generalization_target: str | None
    prompts: list[str] = field(default_factory=list)

    def __call__(self, prompt: str) -> str:
        self.prompts.append(prompt)
        return json.dumps(
            {
                "kind": "stated",
                "stated_by": list(self.stated_by),
                "generalization_target": self.generalization_target,
                "rationale": "the clause states the intent",
            }
        )


@dataclass(kw_only=True)
class _Responses:
    """A model that returns successive responses and retains every prompt."""

    responses: tuple[str, ...]
    prompts: list[str] = field(default_factory=list)

    def __call__(self, prompt: str) -> str:
        self.prompts.append(prompt)
        return self.responses[len(self.prompts) - 1]


def test_case_and_inline_markup_normalize_for_both_citation_fields() -> None:
    """A citation of an existing marked subsection yields its governing H2."""
    model = _Citing(
        stated_by=("## Capture-spec-drift",),
        generalization_target="## Capture-spec-drift",
    )

    verdict = judge_within_ceiling(
        spec_tree=_TREE,
        statement=_STATEMENT,
        run_model=model,
        ceiling=20_000,
    )

    assert is_successful(verdict)
    assert verdict.unwrap().stated_by == (_GOVERNING,)
    assert verdict.unwrap().generalization_target == _GOVERNING


def test_an_unreadable_citation_is_reasked_with_the_valid_clause_inventory() -> None:
    """The replacement answer supplies the usable verdict after one correction."""
    refused = "## A heading that is nowhere"
    model = _Responses(
        responses=(
            json.dumps(
                {
                    "kind": "stated",
                    "stated_by": [refused],
                    "generalization_target": None,
                    "rationale": "first answer",
                }
            ),
            json.dumps(
                {
                    "kind": "stated",
                    "stated_by": [_GOVERNING],
                    "generalization_target": None,
                    "rationale": "corrected answer",
                }
            ),
        )
    )

    verdict = judge_within_ceiling(
        spec_tree=_TREE,
        statement=_STATEMENT,
        run_model=model,
        ceiling=20_000,
    )

    assert is_successful(verdict)
    assert verdict.unwrap().stated_by == (_GOVERNING,)
    assert len(model.prompts) == 2
    assert refused in model.prompts[1]
    assert _GOVERNING in model.prompts[1]


def test_an_unreadable_generalization_target_is_reasked_with_the_valid_clause_inventory() -> None:
    """An invalid target receives the same one correction opportunity as stated_by."""
    refused = "## A heading that is nowhere"
    model = _Responses(
        responses=(
            json.dumps(
                {
                    "kind": "unstated",
                    "stated_by": [_GOVERNING],
                    "generalization_target": refused,
                    "rationale": "first answer",
                }
            ),
            json.dumps(
                {
                    "kind": "unstated",
                    "stated_by": [_GOVERNING],
                    "generalization_target": _GOVERNING,
                    "rationale": "corrected answer",
                }
            ),
        )
    )

    verdict = judge_within_ceiling(
        spec_tree=_TREE,
        statement=_STATEMENT,
        run_model=model,
        ceiling=20_000,
    )

    assert is_successful(verdict)
    assert verdict.unwrap().generalization_target == _GOVERNING
    assert len(model.prompts) == 2
    assert refused in model.prompts[1]
    assert _GOVERNING in model.prompts[1]


def test_a_second_unreadable_citation_is_refused_without_a_third_reask() -> None:
    """A bounded correction retains the shared parser's unreadable verdict."""
    refused = "## A heading that is nowhere"
    model = _Responses(
        responses=tuple(
            json.dumps(
                {
                    "kind": "stated",
                    "stated_by": [refused],
                    "generalization_target": None,
                    "rationale": "still invalid",
                }
            )
            for _ in range(3)
        )
    )

    verdict = judge_within_ceiling(
        spec_tree=_TREE,
        statement=_STATEMENT,
        run_model=model,
        ceiling=20_000,
    )

    assert not is_successful(verdict)
    assert len(model.prompts) == 2


def test_a_second_unreadable_generalization_target_is_refused_without_a_third_reask() -> None:
    """A still-invalid target stays unreadable after its one correction request."""
    refused = "## A heading that is nowhere"
    response = json.dumps(
        {
            "kind": "unstated",
            "stated_by": [_GOVERNING],
            "generalization_target": refused,
            "rationale": "still invalid",
        }
    )
    model = _Responses(responses=(response, response, response))

    verdict = judge_within_ceiling(
        spec_tree=_TREE,
        statement=_STATEMENT,
        run_model=model,
        ceiling=20_000,
    )

    assert not is_successful(verdict)
    assert len(model.prompts) == 2
