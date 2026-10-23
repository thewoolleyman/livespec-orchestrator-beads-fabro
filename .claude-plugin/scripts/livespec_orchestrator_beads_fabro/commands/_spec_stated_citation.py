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

__all__: list[str] = [
    "correction_prompt_headroom",
    "resolving_subsection_citations",
]

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
_INLINE_MARKUP = re.compile(r"`+|\*+|(?<!\w)_{1,3}|_{1,3}(?!\w)")

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
        headings=_h2_headings(spec_tree=spec_tree),
    )


def correction_prompt_headroom(*, spec_tree: Mapping[str, str]) -> int:
    """The largest ordinary correction suffix this tree's H2 inventory needs."""
    headings = _h2_headings(spec_tree=spec_tree)
    return len(_correction_prompt(prompt="", refused=headings, headings=headings))


@dataclass(frozen=True, kw_only=True)
class _ResolvingRunner:
    """A `ModelRunner` whose responses' citations are read at clause level.

    A callable OBJECT rather than a closure, because the shared `ModelRunner`
    alias the library calls through is POSITIONAL by contract — a nested `def`
    taking one positional argument is the one shape this package's keyword-only
    rule has no exemption for, while `__call__` is a dunder and is exempt.
    """

    run_model: ModelRunner
    governing: Mapping[str, str]
    enclosing: Mapping[str, str]
    headings: tuple[str, ...]

    def __call__(self, prompt: str) -> str:
        response = self.run_model(prompt)
        refused = _refused_headings(
            text=response,
            governing=self.governing,
            enclosing=self.enclosing,
        )
        if refused:
            response = self.run_model(
                _correction_prompt(
                    prompt=prompt,
                    refused=refused,
                    headings=self.headings,
                )
            )
        return _resolved_response(
            text=response,
            governing=self.governing,
            enclosing=self.enclosing,
        )


def _governing_clauses(*, spec_tree: Mapping[str, str]) -> dict[str, str]:
    """Each unambiguous normalized H2 title mapped to its exact heading."""
    found: dict[str, set[str]] = {}
    for path in sorted(spec_tree):
        for heading in _HEADING.findall(spec_tree[path]):
            if _level_of(heading=heading) == _GOVERNING_LEVEL:
                found.setdefault(_citation_key(heading=heading), set()).add(heading)
    return {key: next(iter(headings)) for key, headings in found.items() if len(headings) == 1}


def _h2_headings(*, spec_tree: Mapping[str, str]) -> tuple[str, ...]:
    """Every exact H2 heading a correction prompt may offer to the judge."""
    return tuple(
        sorted(
            {
                heading
                for text in spec_tree.values()
                for heading in _HEADING.findall(text)
                if _level_of(heading=heading) == _GOVERNING_LEVEL
            }
        )
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
                found.setdefault(_citation_key(heading=heading), set()).add(governing)
    return {key: next(iter(clauses)) for key, clauses in found.items() if len(clauses) == 1}


def _resolved_response(
    *, text: str, governing: Mapping[str, str], enclosing: Mapping[str, str]
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


def _refused_headings(
    *, text: str, governing: Mapping[str, str], enclosing: Mapping[str, str]
) -> tuple[str, ...]:
    """The first response's unresolvable `stated_by` citations, if readable."""
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return ()
    if not isinstance(parsed, dict):
        return ()
    payload = cast("dict[str, object]", parsed)
    cited = payload.get(_STATED_BY)
    if not isinstance(cited, list):
        return ()
    valid = frozenset(governing.values())
    refused = [
        citation
        for citation in cast("list[object]", cited)
        if isinstance(citation, str)
        and _resolved(citation=citation, governing=governing, enclosing=enclosing) not in valid
    ]
    return tuple(dict.fromkeys(refused))


def _correction_prompt(*, prompt: str, refused: tuple[str, ...], headings: tuple[str, ...]) -> str:
    """One complete retry prompt, with no fuzzy expansion of a bad citation."""
    refused_list = "\n".join("- " + citation for citation in refused)
    heading_list = "\n".join("- " + heading for heading in headings)
    instruction = " ".join(
        (
            "Reply once with a replacement JSON verdict whose stated_by only cites",
            "these valid H2 headings:",
        )
    )
    return "\n".join(
        (
            prompt,
            "",
            "Your preceding response cited heading(s) that do not exist:",
            refused_list,
            instruction,
            heading_list,
        )
    )


def _resolved(*, citation: str, governing: Mapping[str, str], enclosing: Mapping[str, str]) -> str:
    """One citation read at the level that governs, or carried through as it is."""
    key = _citation_key(heading=citation)
    return governing.get(key, enclosing.get(key, citation))


def _level_of(*, heading: str) -> int:
    """How deep one heading line sits, counted from its leading markers."""
    return len(heading) - len(heading.lstrip("#"))


def _citation_key(*, heading: str) -> str:
    """A deterministic heading identity ignoring case and inline markup."""
    title = _MARKER.sub("", heading)
    return " ".join(_INLINE_MARKUP.sub("", title).casefold().split())
