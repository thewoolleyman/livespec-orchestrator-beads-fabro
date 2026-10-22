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
from collections import Counter
from dataclasses import dataclass
from typing import TYPE_CHECKING

from livespec_runtime.spec_stated import JUDGE_PROMPT, judge

from livespec_orchestrator_beads_fabro.commands._spec_stated_citation import (
    resolving_subsection_citations,
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
    "condensed_spec_tree",
    "judge_within_ceiling",
]

# The measured refusal, quoted from the failure this module exists to close:
# `Input exceeds the maximum length of 1048576 characters (input_too_large,
# actual_chars 1360329)`.
PROMPT_CHARACTER_CEILING = 1_048_576

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

# The upstream renderer's per-block framing: `--- {path} ---\n{text}`, blocks
# joined by a blank line.
_BLOCK_PREFIX = "--- "
_BLOCK_SUFFIX = " ---\n"
_BLOCK_SEPARATOR = "\n\n"

# One H2 heading line. Deliberately the shared judgement's own pattern: `##`
# followed by a third `#` is an H3 and is not a governing clause.
_H2_HEADING = re.compile(r"^##[ \t][^\n]*?[ \t]*$", re.MULTILINE)

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

    @property
    def key(self) -> tuple[str, int]:
        """This clause's identity within the tree."""
        return (self.path, self.index)


def condensed_spec_tree(
    *,
    spec_tree: Mapping[str, str],
    statement: str,
    ceiling: int = PROMPT_CHARACTER_CEILING,
) -> dict[str, str]:
    """`spec_tree` reduced to a tree whose rendered prompt fits under `ceiling`.

    Every path of `spec_tree` is present in the result and carries every H2
    heading it carried; only the bodies of unselected clauses are withheld.
    """
    sections = [
        section
        for path in sorted(spec_tree)
        for section in _sections_of(path=path, text=spec_tree[path])
    ]
    skeleton = _condensed(sections=sections, chosen=frozenset(), paths=spec_tree)
    remaining = (
        ceiling
        - _SAFETY_MARGIN
        - _TEMPLATE_OVERHEAD
        - len(statement)
        - _rendered_length(tree=skeleton)
    )
    chosen: set[tuple[str, int]] = set()
    for section in _relevance_order(sections=sections, statement=statement):
        cost = len(section.full) - len(section.elided)
        if cost <= remaining:
            chosen.add(section.key)
            remaining -= cost
    return _condensed(sections=sections, chosen=chosen, paths=spec_tree)


def judge_within_ceiling(
    *,
    spec_tree: Mapping[str, str],
    statement: str,
    run_model: ModelRunner,
    ceiling: int = PROMPT_CHARACTER_CEILING,
) -> Result[SpecStatedVerdict, SpecStatedParseError]:
    """The shared spec-stated judgement, taken against the condensed tree.

    The ONE entry point every consumer of the judgement in this repository
    takes, so the condensation cannot be remembered at one call site and
    forgotten at the next — a dispatch that forgot it is not a smaller
    judgement but no judgement at all, since the provider refuses the prompt.

    And the SAME reason puts the citation resolution of `_spec_stated_citation`
    here rather than at either consumer: a citation of an existing subsection
    that nothing resolves is refused as unreadable, so a call site that forgot
    the resolution would report an item it judged correctly as one it could not
    judge. The resolution reads the UNREDUCED tree while the prompt carries the
    condensed one, because a clause whose body the condensation withheld still
    encloses the subsections the specification states it through.
    """
    return judge(
        spec_tree=condensed_spec_tree(spec_tree=spec_tree, statement=statement, ceiling=ceiling),
        statement=statement,
        run_model=resolving_subsection_citations(run_model=run_model, spec_tree=spec_tree),
    )


def _sections_of(*, path: str, text: str) -> list[_Section]:
    """One file split at its H2 headings, preamble first when it carries one."""
    matches = list(_H2_HEADING.finditer(text))
    starts = [match.start() for match in matches]
    ends = [*starts[1:], len(text)]
    preamble = text[: starts[0]] if starts else text
    sections = (
        [_section(path=path, index=0, full=preamble, elided=f"{ELIDED_BODY_MARKER}\n")]
        if preamble
        else []
    )
    for ordinal, (match, end) in enumerate(zip(matches, ends, strict=True)):
        sections.append(
            _section(
                path=path,
                index=ordinal + 1,
                full=text[match.start() : end],
                elided=f"{match.group()}\n{ELIDED_BODY_MARKER}\n",
            )
        )
    return sections


def _section(*, path: str, index: int, full: str, elided: str) -> _Section:
    """One section with its retrieval terms taken from the text it carries."""
    return _Section(
        path=path,
        index=index,
        full=full,
        elided=elided,
        terms=frozenset(_TERM.findall(full.casefold())),
    )


def _relevance_order(*, sections: list[_Section], statement: str) -> list[_Section]:
    """Every section, most relevant to `statement` first, ties broken by position.

    The weight is inverse clause frequency, which is what keeps a term every
    clause carries — `the`, `MUST`, this repository's own name — from ranking
    clauses that merely share the specification's vocabulary above the clause
    that shares the statement's subject.
    """
    wanted = frozenset(_TERM.findall(statement.casefold()))
    frequency = Counter(term for section in sections for term in section.terms & wanted)
    decorated = [
        (
            (
                -sum(1.0 / (1 + frequency[term]) for term in section.terms & wanted),
                section.path,
                section.index,
            ),
            section,
        )
        for section in sections
    ]
    decorated.sort(key=lambda pair: pair[0])
    return [section for _, section in decorated]


def _condensed(
    *,
    sections: list[_Section],
    chosen: Collection[tuple[str, int]],
    paths: Collection[str],
) -> dict[str, str]:
    """The tree these sections render into, with only `chosen` bodies carried."""
    parts: dict[str, list[str]] = {path: [] for path in paths}
    for section in sections:
        parts[section.path].append(section.full if section.key in chosen else section.elided)
    return {path: "".join(pieces) for path, pieces in parts.items()}


def _rendered_length(*, tree: Mapping[str, str]) -> int:
    """How many characters the upstream renderer turns `tree` into."""
    if not tree:
        return 0
    blocks = [
        len(_BLOCK_PREFIX) + len(path) + len(_BLOCK_SUFFIX) + len(tree[path]) for path in tree
    ]
    return sum(blocks) + len(_BLOCK_SEPARATOR) * (len(blocks) - 1)
