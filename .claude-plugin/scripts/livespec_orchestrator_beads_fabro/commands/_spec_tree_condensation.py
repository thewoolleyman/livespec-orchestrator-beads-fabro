"""The spec tree a spec-stated judgement is actually taken against.

PURE. `livespec_runtime.spec_stated.judge` renders the WHOLE current spec tree
into every judgement prompt, which against this repository is 1354623
characters (measured 2026-10-22) — and a Codex judge refuses an input over
1048576 outright, `input_too_large`, before any judgement happens. So a scan
over nine work-items judged none of them, recorded a failed attempt against its
coverage anchor, and exited 4. A Claude judge with a million-token context
accepts the same prompt, at roughly 340000 input tokens per judged item, which
is the same defect paid for rather than refused.

The renderer lives upstream and is vendored here, so this module condenses the
TREE the shared judgement is handed rather than changing how that tree is
rendered: one block per path, exactly as before, carrying every H2 heading the
file carries and the full body of only the clauses a cheap lexical retrieval
selects for the statement under judgement.

FIVE PROPERTIES AN EDITOR MUST NOT INVERT.

EVERY H2 HEADING SURVIVES, VERBATIM, WHETHER OR NOT ITS BODY DOES, and that is
the whole reason an unselected clause keeps its heading line rather than being
dropped. `judge` derives the citable clause set from the TREE IT IS HANDED and
REFUSES a `stated_by` naming a heading that tree does not carry — so a
condensation that dropped headings would turn a correct `stated` verdict into
an unreadable response, which every consumer reports as an item it could not
judge. That failure is silent in the expensive direction: the scan's own output
says the judgement could not be read, never that the condensation removed the
clause the model was right to cite.

THE ELISION IS IN-BAND AND SELF-DESCRIBING. A heading whose body is absent, with
nothing saying so, invites the model to report `unstated` for a clause it was
simply not shown. The marker says the heading exists and its text was withheld,
so an unselected clause reads as unexamined rather than as absent.

THE SPLIT USES THE SAME HEADING PATTERN THE SHARED JUDGEMENT USES, because the
heading set this module preserves and the heading set that module validates a
verdict against must be the same set. The pattern is restated here rather than
imported, since the upstream name is private; the heading-inventory test is the
control that the two still agree, taken THROUGH `judge` over this repository's
real tree rather than by comparing two regexes.

THE BUDGET IS SPENT ON AS MUCH SPEC TEXT AS FITS, in relevance order, rather
than on a fixed number of clauses. A fixed count is wrong in both directions at
once — it withholds text a 1-megabyte budget would have paid for, and it
overflows on a tree whose clauses are long — while a budget leaves the
judgement reading everything the ceiling allows.

A CLAUSE THAT DOES NOT FIT IS PASSED OVER AND THE WALK CONTINUES. Stopping at
the first clause too large for the remaining budget would let one enormous
low-ranked clause withhold every smaller clause behind it, which is the
opposite of what the relevance order is for.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, cast

from livespec_runtime.spec_stated import JUDGE_PROMPT

from livespec_orchestrator_beads_fabro.commands._dispatcher_definition_of_done import (
    definition_of_done,
    reference_line_headings,
)
from livespec_orchestrator_beads_fabro.commands._spec_tree_clause_resolution import (
    clauses_named as _clauses_named,
)
from livespec_orchestrator_beads_fabro.commands._spec_tree_clause_resolution import (
    headings_resolved,
)
from livespec_orchestrator_beads_fabro.commands._spec_tree_condensation_models import (
    CondensedClause,
    CondensedSpecTree,
)
from livespec_orchestrator_beads_fabro.commands._spec_tree_identifier_paragraphs import (
    identified_paragraphs,
    merged_selection,
)
from livespec_orchestrator_beads_fabro.commands._spec_tree_partial import (
    FUNCTION_TERMS,
    partially_selected_section,
)
from livespec_orchestrator_beads_fabro.commands._spec_tree_referenced_selection import (
    ReferencedSection,
    select_referenced_sections,
)
from livespec_orchestrator_beads_fabro.commands._spec_tree_relevance import (
    relevance_order as _relevance_order,
)
from livespec_orchestrator_beads_fabro.commands._spec_tree_rendering import (
    rendered_tree_length as _rendered_length,
)
from livespec_orchestrator_beads_fabro.commands._spec_tree_scenario_governing import (
    pinned_sections,
)
from livespec_orchestrator_beads_fabro.commands._spec_tree_sections import (
    sections_of as _split_sections,
)

if TYPE_CHECKING:
    from collections.abc import Collection, Mapping

    from livespec_runtime.spec_stated import (
        ModelRunner,
        SpecStatedParseError,
        SpecStatedVerdict,
    )
    from returns.result import Result

__all__: list[str] = [
    "ELIDED_BODY_MARKER",
    "PROMPT_CHARACTER_CEILING",
    "CondensedClause",
    "CondensedSpecTree",
    "clauses_named",
    "condensed_spec_tree",
    "headings_resolved",
    "judge_within_ceiling",
]

# The measured refusal, quoted from the failure this module exists to close:
# `Input exceeds the maximum length of 1048576 characters (input_too_large,
# actual_chars 1360329)`.
PROMPT_CHARACTER_CEILING = 200_000

# What stands where an unselected clause's body would be. It NAMES the omission
# rather than leaving a bare heading, so the model reads the clause as one it
# was not shown instead of one the specification does not carry.
ELIDED_BODY_MARKER = (
    "(body omitted from this prompt: this clause was not selected as a candidate "
    "for this judgement, so its heading is listed but its text is not shown)"
)

# Headroom between the budget this module spends and the ceiling it is bounded
# by. The template overhead and the statement are measured exactly; the block
# framing below reproduces the upstream renderer's shape, and the margin is what
# absorbs a small change to that shape arriving through a re-vendor.
_SAFETY_MARGIN = 8192

# Every character of the rendered prompt that is neither the tree nor the
# statement, measured through the template itself rather than estimated.
_TEMPLATE_OVERHEAD = len(JUDGE_PROMPT.format(spec_tree="", statement=""))

# A retrieval term. Three characters or more, because a one- or two-character
# token carries no topic and matches nearly every clause.
_TERM = re.compile(r"[a-z0-9_]{3,}")


@dataclass(frozen=True, kw_only=True)
class _Section:
    """One clause of one spec file, in both the forms the condensation may use.

    `full` is the clause exactly as the file carries it, heading line included,
    so concatenating every section's `full` reproduces the file byte for byte.
    `elided` is the same clause reduced to its heading line and the marker.
    """

    path: str
    index: int
    full: str
    elided: str
    terms: frozenset[str]
    heading: str | None = None
    body: str = ""

    @property
    def key(self) -> tuple[str, int]:
        """This clause's identity within the tree."""
        return (self.path, self.index)

    def prompt_provenance_for(self, *, rendered: str) -> CondensedClause:
        """The provenance of this section as it appears in a condensed prompt."""
        if self.heading is None:
            return CondensedClause(heading="", body=rendered, path=self.path)
        return CondensedClause(
            heading=self.heading,
            body=rendered.removeprefix(self.heading),
            path=self.path,
        )


def condensed_spec_tree(
    *,
    spec_tree: Mapping[str, str],
    statement: str,
    ceiling: int = PROMPT_CHARACTER_CEILING,
) -> CondensedSpecTree:
    """`spec_tree` reduced to a tree whose rendered prompt fits under `ceiling`.

    Every path of `spec_tree` is present in the result and carries every H2
    heading it carried; only the bodies of unselected clauses are withheld.
    """
    sections = [
        section
        for path in sorted(spec_tree)
        for section in _sections_of(path=path, text=spec_tree[path])
    ]
    skeleton = _condensed(sections=sections, selected={}, paths=spec_tree)
    remaining = (
        ceiling
        - _SAFETY_MARGIN
        - _TEMPLATE_OVERHEAD
        - len(statement)
        - _rendered_length(tree=skeleton)
    )
    selected: dict[tuple[str, int], str] = {}
    complete: set[tuple[str, int]] = set()
    statement_terms = frozenset(_TERM.findall(statement.casefold()))
    definition = definition_of_done(description=statement)
    asked_text = "\n".join(
        line for line in statement.splitlines() if not line.lstrip().startswith("References:")
    )
    asked_terms = frozenset(_TERM.findall(asked_text.casefold())) - FUNCTION_TERMS
    references = (
        definition.references if definition.present else reference_line_headings(text=statement)
    )
    pinned, governing_terms = pinned_sections(
        sections=sections, references=references, spec_tree=spec_tree, term_pattern=_TERM
    )
    asked_terms |= governing_terms
    identified, remaining = identified_paragraphs(
        sections=sections, asked_text=asked_text, remaining=remaining
    )
    pinned_selected, pinned_complete, remaining = select_referenced_sections(
        sections=[
            ReferencedSection(
                key=section.key,
                heading=section.heading,
                body=section.body,
                full=section.full,
                elided=section.elided,
                terms=section.terms,
            )
            for section in pinned
        ],
        terms=asked_terms,
        remaining=remaining,
    )
    selected.update(pinned_selected)
    complete.update(pinned_complete)
    relevance = _relevance_order(sections=sections, statement=statement, term_pattern=_TERM)
    for section in (section for section in relevance if section not in pinned):
        cost = len(section.full) - len(section.elided)
        if cost <= remaining:
            selected[section.key] = section.full
            complete.add(section.key)
            remaining -= cost
            continue
        matching_terms = section.terms & statement_terms - FUNCTION_TERMS
        partial = (
            partially_selected_section(
                heading=section.heading,
                body=section.body,
                full=section.full,
                elided=section.elided,
                remaining=remaining,
            )
            if section in pinned or matching_terms
            else None
        )
        if partial is not None:
            selected[section.key] = partial
            remaining -= len(partial) - len(section.elided)
    selected = merged_selection(
        sections=sections, selected=selected, complete=complete, identified=identified
    )
    return CondensedSpecTree(
        tree=_condensed(sections=sections, selected=selected, paths=spec_tree),
        clauses=tuple(
            section.prompt_provenance_for(rendered=section.full)
            for path in spec_tree
            for section in sections
            if section.path == path and section.key in complete
        ),
    )


def clauses_named(
    *, spec_tree: Mapping[str, str], headings: Collection[str]
) -> tuple[CondensedClause, ...]:
    """Every full clause named by a verdict, independent of source position."""
    return cast(
        "tuple[CondensedClause, ...]",
        _clauses_named(spec_tree=spec_tree, headings=headings, sections_of=_sections_of),
    )


def judge_within_ceiling(
    *,
    spec_tree: Mapping[str, str],
    statement: str,
    run_model: ModelRunner,
    ceiling: int = PROMPT_CHARACTER_CEILING,
    rubric: str = "",
) -> Result[SpecStatedVerdict, SpecStatedParseError]:
    """The shared spec-stated judgement, taken against the condensed tree."""
    from livespec_orchestrator_beads_fabro.commands._spec_tree_judge import (
        judge_within_ceiling as _judge_within_ceiling,
    )

    return _judge_within_ceiling(
        condense=condensed_spec_tree,
        spec_tree=spec_tree,
        statement=statement,
        run_model=run_model,
        ceiling=ceiling,
        rubric=rubric,
    )


def _sections_of(*, path: str, text: str) -> list[_Section]:
    """One file split at its H2 headings, preamble first when it carries one."""
    return _split_sections(path=path, text=text, make_section=_section)


def _section(
    *,
    path: str,
    index: int,
    full: str,
    elided: str,
    heading: str | None = None,
    body: str = "",
) -> _Section:
    """One section with its retrieval terms taken from the text it carries."""
    return _Section(
        path=path,
        index=index,
        full=full,
        elided=elided,
        terms=frozenset(_TERM.findall(full.casefold())),
        heading=heading,
        body=body,
    )


def _condensed(
    *,
    sections: list[_Section],
    selected: Mapping[tuple[str, int], str],
    paths: Collection[str],
) -> dict[str, str]:
    """The tree these sections render into, with only selected bodies carried."""
    parts: dict[str, list[str]] = {path: [] for path in paths}
    for section in sections:
        parts[section.path].append(selected.get(section.key, section.elided))
    return {path: "".join(pieces) for path, pieces in parts.items()}
