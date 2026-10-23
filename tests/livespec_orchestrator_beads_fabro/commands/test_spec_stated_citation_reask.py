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
