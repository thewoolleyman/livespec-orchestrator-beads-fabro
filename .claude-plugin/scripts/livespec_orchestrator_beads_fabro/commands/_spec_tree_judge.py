"""The shared spec-stated judge transport for a condensed specification tree."""

from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Protocol, cast

from livespec_runtime.spec_stated import judge

from livespec_orchestrator_beads_fabro.commands._spec_stated_citation import (
    judged_prompt_ceiling,
    resolving_subsection_citations,
)

if TYPE_CHECKING:
    from livespec_runtime.spec_stated import (
        ModelRunner,
        SpecStatedParseError,
        SpecStatedVerdict,
    )
    from returns.result import Result

__all__: list[str] = ["judge_within_ceiling"]


class _Condense(Protocol):
    """The pure condensation surface this judging transport needs."""

    def __call__(self, *, spec_tree: Mapping[str, str], statement: str, ceiling: int) -> object: ...


def judge_within_ceiling(
    *,
    condense: _Condense,
    spec_tree: Mapping[str, str],
    statement: str,
    run_model: ModelRunner,
    ceiling: int,
    rubric: str = "",
) -> Result[SpecStatedVerdict, SpecStatedParseError]:
    """Judge a condensed tree, while citations continue to resolve from the full tree."""
    return judge(
        spec_tree=cast(
            "Mapping[str, str]",
            condense(
                spec_tree=spec_tree,
                statement=statement,
                ceiling=judged_prompt_ceiling(spec_tree=spec_tree, ceiling=ceiling),
            ),
        ),
        statement=f"{statement}{rubric}",
        run_model=resolving_subsection_citations(run_model=run_model, spec_tree=spec_tree),
    )
