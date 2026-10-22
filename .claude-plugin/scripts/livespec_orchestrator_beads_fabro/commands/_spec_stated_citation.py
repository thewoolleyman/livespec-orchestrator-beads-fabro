"""The clause a spec-stated judgement cited, read at the level that governs.

PURE. `livespec_runtime.spec_stated.judge` derives the citable clause set from
the H2 headings of the tree it is handed and REFUSES a `stated_by` naming
anything else, because a verdict citing a clause nobody can open is worse than
no verdict: a consumer would file a proposal against it. That refusal is right,
and this module does not spend it.

What it repairs is the level the citation is read at. The ratified text cites
its own SUBSECTIONS by name, so a model that reads a clause correctly names the
H3 or H4 subsection it actually read — written with a leading H2 marker,
because the prompt asks for one. The shared judgement then refuses a correct
reading, and every consumer reports it as an item whose verdict could not be
read. Measured 2026-10-22 on released v0.234.2: a ledger-intent scan over
fifteen work-items had nine judgements refused that way, exited 4 and wrote no
completed-coverage record, while each rejected name existed one level down in
`SPECIFICATION/contracts.md` and was in the prompt with its body.

So a citation naming an EXISTING subsection is resolved to the governing clause
that encloses it, before the shared judgement validates it, for `stated_by` and
`generalization_target` alike.

FIVE PROPERTIES AN EDITOR MUST NOT INVERT.

THE PROMPT IS NOT THE REMEDY. It already demands verbatim H2 headings and
already forbids naming a heading the tree does not carry, so there is no
instruction left to add; the model's habit of naming the subsection it read is
predictable rather than aberrant, and a deterministic resolution is what makes
the correct reading expressible at all.

A HEADING THE TREE CARRIES AT NO LEVEL IS STILL REFUSED. Resolving existing
subsections and accepting whatever a response names are the same observation
from the citing side, and the negative is the only thing that tells them apart.
An invented heading is not in the subsection map either, so it is carried
through unchanged and the shared judgement refuses it exactly as before.

A CITATION NO SINGLE CLAUSE ENCLOSES IS REFUSED TOO, which is the direction a
convenience here would get wrong. A subsection title two clauses carry has no
one enclosing clause, and a subsection no clause encloses has none at all;
picking one, or inventing one, would name a clause the model never cited and
send a proposal there. Both are ABSENT from the map rather than guessed, so
both keep the refusal they have today.

AN ALREADY-GOVERNING CITATION IS CARRIED THROUGH BEFORE THE MAP IS CONSULTED.
The map is keyed by title, so a title a clause and some subsection happened to
share would otherwise rewrite the clause's own citation into the subsection's
enclosing clause — a correct citation turned into a different one.

A RESPONSE THIS CANNOT READ IS RETURNED VERBATIM, never repaired and never
reported. The shared parser owns what a malformed response means, and it names
the offending field; a second account of that here would report one shape of
malformedness as another, and a repair would hide it.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, cast

if TYPE_CHECKING:
    from collections.abc import Mapping

    from livespec_runtime.spec_stated import ModelRunner

__all__: list[str] = ["resolving_subsection_citations"]

# One heading line of any citable depth, captured WITHOUT its trailing
# whitespace so an H2 capture is byte-identical to what the shared judgement
# derives its clause set from. Levels below H2 are captured because they are
# exactly what this module resolves; `#` alone is a document title and encloses
# nothing a verdict may cite.
_HEADING = re.compile(r"^(#{2,6}[ \t][^\n]*?)[ \t]*$", re.MULTILINE)

# A heading's leading marker, which the prompt asks the model to copy out and
# which therefore travels with the citation. Stripping it is what lets a
# subsection cited as `## Title` match the `### Title` the tree carries.
_MARKER = re.compile(r"^#+[ \t]*")

_GOVERNING_LEVEL = 2
_STATED_BY = "stated_by"
_GENERALIZATION_TARGET = "generalization_target"


def resolving_subsection_citations(
    *, run_model: ModelRunner, spec_tree: Mapping[str, str]
) -> ModelRunner:
    """`run_model`, with each response's subsection citations read as clauses.

    `spec_tree` is the GOVERNED tree, not the condensed one a prompt renders: a
    subsection whose body was withheld still exists in the specification, and
    the clause enclosing it is carried into every prompt whatever the
    condensation withholds.
    """
    return _ResolvingRunner(
        run_model=run_model,
        governing=_governing_clauses(spec_tree=spec_tree),
        enclosing=_enclosing_clauses(spec_tree=spec_tree),
    )


@dataclass(frozen=True, kw_only=True)
class _ResolvingRunner:
    """A `ModelRunner` whose responses' citations are read at clause level.

    A callable OBJECT rather than a closure, because the shared `ModelRunner`
    alias the library calls through is POSITIONAL by contract — a nested `def`
    taking one positional argument is the one shape this package's keyword-only
    rule has no exemption for, while `__call__` is a dunder and is exempt.
    """

    run_model: ModelRunner
    governing: frozenset[str]
    enclosing: Mapping[str, str]

    def __call__(self, prompt: str) -> str:
        return _resolved_response(
            text=self.run_model(prompt),
            governing=self.governing,
            enclosing=self.enclosing,
        )


def _governing_clauses(*, spec_tree: Mapping[str, str]) -> frozenset[str]:
    """Every H2 heading the tree carries: the clause set a verdict may cite."""
    return frozenset(
        heading
        for path in sorted(spec_tree)
        for heading in _HEADING.findall(spec_tree[path])
        if _level_of(heading=heading) == _GOVERNING_LEVEL
    )


def _enclosing_clauses(*, spec_tree: Mapping[str, str]) -> dict[str, str]:
    """Each subsection title mapped to the ONE governing clause enclosing it.

    A title more than one clause carries is absent rather than mapped to
    whichever was seen last, and so is a subsection standing before any clause
    of its file: a citation that cannot be resolved to exactly one governing
    clause keeps the refusal it has today.
    """
    found: dict[str, set[str]] = {}
    for path in sorted(spec_tree):
        governing: str | None = None
        for heading in _HEADING.findall(spec_tree[path]):
            if _level_of(heading=heading) == _GOVERNING_LEVEL:
                governing = heading
            elif governing is not None:
                found.setdefault(_title_of(heading=heading), set()).add(governing)
    return {title: next(iter(clauses)) for title, clauses in found.items() if len(clauses) == 1}


def _resolved_response(
    *, text: str, governing: frozenset[str], enclosing: Mapping[str, str]
) -> str:
    """One response's citations resolved, or the response returned verbatim.

    The `json.JSONDecodeError` catch is the narrow seam this boundary is: a
    model response is foreign input, and its malformedness belongs to the
    shared parser, which names the field it could not read. So an unreadable
    response is handed on untouched rather than described a second time here.
    """
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return text
    if not isinstance(parsed, dict):
        return text
    payload = cast("dict[str, object]", parsed)
    cited = payload.get(_STATED_BY)
    if isinstance(cited, list):
        payload[_STATED_BY] = [
            _resolved(citation=entry, governing=governing, enclosing=enclosing)
            if isinstance(entry, str)
            else entry
            for entry in cast("list[object]", cited)
        ]
    target = payload.get(_GENERALIZATION_TARGET)
    if isinstance(target, str):
        payload[_GENERALIZATION_TARGET] = _resolved(
            citation=target, governing=governing, enclosing=enclosing
        )
    return json.dumps(payload)


def _resolved(*, citation: str, governing: frozenset[str], enclosing: Mapping[str, str]) -> str:
    """One citation read at the level that governs, or carried through as it is."""
    if citation in governing:
        return citation
    return enclosing.get(_title_of(heading=citation), citation)


def _level_of(*, heading: str) -> int:
    """How deep one heading line sits, counted from its leading markers."""
    return len(heading) - len(heading.lstrip("#"))


def _title_of(*, heading: str) -> str:
    """One heading line with its leading marker removed, so levels compare."""
    return _MARKER.sub("", heading)
