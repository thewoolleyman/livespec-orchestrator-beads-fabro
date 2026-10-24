"""The ADVISORY half of the host-side Definition-of-Done wall.

The Definition-of-Done-and-Proof-of-Done clause of `SPECIFICATION/contracts.md`
(v115) splits a filing-time finding in two, and the split decides a lifecycle
transition. A MECHANICAL finding — the section absent, a reference unresolved, a
proof-mode declaration malformed — is `_dispatcher_definition_of_done_findings`'
business and WITHHOLDS `ready`. The forms this module recognises must not: "The
host-side wall MAY recognise the mechanically recognisable forms, and where it
does the finding is ADVISORY ... the judgement is the gate's."

WHY THE TWO HALVES ARE SEPARATE MODULES RATHER THAN ONE LIST CARRYING A FLAG.
The CONSEQUENCE of the two kinds is opposite — one withholds `ready` at intake
and one is forbidden to — so a single list is one dropped flag away from either
flooding the queue with refusals an operator cannot clear or letting a malformed
item through the gate the clause put in front of it. Keeping them apart means a
caller has to NAME the kind it is acting on, and the two callers that act
differently say so in their imports: intake consults both and withholds on the
mechanical half alone, while the needs-attention hygiene lane consults only this
one.

WHY EVERY RULE HERE IS A SHAPE MATCH AND NEVER A JUDGEMENT. The clause gives the
judgement to the `dod_gate` node, which reads the item's deliverable: a
test-existence assertion is LEGITIMATE on an item whose deliverable is itself a
test, and no host-side surface knows that. So each rule here reports a
RECOGNISED FORM and names the remedy, and none of them refuses anything. That is
also why the finding text says which form matched rather than asserting the
assertion is wrong.

WHY THE SCENARIO RULE REPORTS A CANDIDATE RATHER THAN A VERDICT. "A scenario
states this assertion's behaviour" is a semantic question. What a host surface
can observe is a scenario whose own distinctive vocabulary overlaps the
assertion's, which is evidence worth showing and not proof. The rule therefore
fires only when the reference line names NO scenario heading at all — the one
case where the gate's own finding is reachable — and it NAMES the candidate so
the filer can accept or reject it in one read. An unreadable `scenarios.md`
withholds the rule entirely, for the reason the mechanical wall records for its
own reference check: an empty heading set is the absence of evidence, not
evidence that no scenario governs the assertion.

WHY THE SCORE READS EACH SCENARIO'S BODY AND NOT ONLY ITS HEADING. A
`## Scenario NN — ...` title is one sentence of summary; the behaviour is stated
in the Gherkin beneath it, down to the sub-scenario titles and the Then steps.
Scoring headings alone therefore missed exactly the scenarios this tree states
behaviour in — measured 2026-10-17 on two items that passed this wall and were
then refused at `dod_gate` check 6 on scenario coverage, Scenario 60 governing
four of one item's five assertions and Scenario 127 all five of the other's,
every match sitting in the body while the heading's vocabulary stayed under the
bound. A false candidate costs the filer one read; a miss costs a factory run,
so the recall is worth the precision. The body each scenario is scored on ends
at the next `## ` heading, which is what keeps a match attributable: a score
taken over the whole file reaches the bound on every scenario at once and names
whichever comes first in document order.

WHY THE CARRIER RULE READS THE SECTION ONLY. The clause permits a child of a
plan to repeat the carrier relation "as prose before the Definition of Done
heading" and forbids it INSIDE the section. The section parse starts at the
description's FIRST heading, so the permitted form is never an assertion at all
and the permitted-versus-forbidden distinction costs this module no branch.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

from livespec_orchestrator_beads_fabro.commands._dispatcher_definition_of_done import (
    DefinitionOfDone,
    definition_of_done,
)
from livespec_orchestrator_beads_fabro.commands._dod_governing_heading import (
    governing_heading_findings,
)
from livespec_orchestrator_beads_fabro.effects import AttemptFailure, attempt

if TYPE_CHECKING:
    from pathlib import Path

    from livespec_orchestrator_beads_fabro.commands._dod_governing_heading import (
        GoverningHeadingVerdict,
    )
    from livespec_orchestrator_beads_fabro.types import WorkItem

__all__: list[str] = [
    "SCENARIO_HEADING_PREFIX",
    "advisory_definition_of_done_findings",
    "scenario_headings",
]

# What makes an H2 of the governed spec tree a SCENARIO heading. Public because
# the surfaces that render the finding and the prose that tells a filer what to
# write both name the form, and a second hand-typed copy is how the two would
# come to disagree about which headings the rule can ever point at.
SCENARIO_HEADING_PREFIX = "Scenario "

_SCENARIOS_RELPATH = ("SPECIFICATION", "scenarios.md")
_H2 = re.compile(r"^##\s+(.+?)\s*$")
_HEADING_MARKER = "## "
# A DISTINCTIVE term is five characters or longer, which drops every article,
# preposition and auxiliary without needing to enumerate them, and is then
# filtered by the small set below of long words that carry no subject matter.
_TERM = re.compile(r"[a-z][a-z0-9_]{4,}")
_UNDISTINCTIVE = frozenset(
    {
        "about",
        "above",
        "after",
        "against",
        "being",
        "cannot",
        "could",
        "every",
        "instead",
        "other",
        "rather",
        "their",
        "there",
        "these",
        "those",
        "under",
        "where",
        "which",
        "while",
        "whose",
        "within",
        "without",
        "would",
    }
)
# How many distinctive terms an assertion and a scenario must SHARE before that
# scenario is worth naming as a candidate. Four is deliberately well above
# incidental overlap: a shared subject noun and a shared verb reach two, and the
# rule's whole value is that the filer can accept the candidate without
# re-reading the scenario file.
_MIN_SHARED_TERMS = 4

# The mechanically recognisable TEST-EXISTENCE forms, each paired with the
# wording the finding quotes back. The clause names the first, second and fourth
# verbatim (`tests prove ...`, `regression tests cover ...`, `the aggregate
# passes`); the others are the same claim spelled the ways this fleet's own
# items have spelled it.
_TEST_EXISTENCE_FORMS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("tests prove", re.compile(r"\btests?\s+prove[sd]?\b")),
    ("regression tests", re.compile(r"\bregression\s+tests?\b")),
    ("tests cover", re.compile(r"\btests?\s+cover(?:s|ed|age)?\b")),
    ("aggregate passes", re.compile(r"\baggregate\s+passes\b")),
    ("the suite passes", re.compile(r"\b(?:test\s+)?suite\s+passes\b")),
    ("the checks pass", re.compile(r"\bchecks?\s+pass(?:es)?\b")),
)

# The forms that state a CARRIER RELATION — which plan assertion this child
# carries — inside the section.
_CARRIER_RELATION_FORMS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("plan assertion", re.compile(r"\bplan\s+assertions?\b")),
    ("carrier map", re.compile(r"\bcarrier\s+map\b")),
    ("carries the plan", re.compile(r"\bcarries\s+the\s+plan\b")),
)


@dataclass(frozen=True, kw_only=True)
class _ScenarioSection:
    """One scenario of the governed spec tree, as the candidate rule scores it.

    `terms` is the distinctive vocabulary of the scenario's HEADING together
    with that of its BODY — the lines under the heading up to the next `## `
    heading. The union is computed ONCE, when the file is read, rather than per
    assertion: the hygiene lane grades every item in the tenant and each item
    carries several assertions, so a per-assertion tokenization of every
    scenario body would re-scan the whole file for each of them.
    """

    heading: str
    terms: frozenset[str]


def scenario_headings(*, repo: Path) -> tuple[str, ...]:
    """The scenario H2 titles of the governed spec tree, in document order.

    An empty tuple means the file could not be read OR that it carries no
    scenario heading. The two are the same fact for this module's one consumer,
    which withholds the candidate rule either way rather than concluding that no
    scenario governs the assertion.
    """
    return tuple(section.heading for section in _scenario_sections(repo=repo))


def _scenario_sections(*, repo: Path) -> tuple[_ScenarioSection, ...]:
    """Every scenario of the governed spec tree with its own body, in document order.

    A NON-scenario H2 closes the scenario before it and opens no section of its
    own, so the prose under `## Runtime notes` is scored against no scenario at
    all rather than being carried onto whichever scenario preceded it.
    """
    path = repo.joinpath(*_SCENARIOS_RELPATH)
    read = attempt(action=lambda: path.read_text(encoding="utf-8"), exceptions=(OSError,))
    if isinstance(read, AttemptFailure):
        return ()
    sections: list[_ScenarioSection] = []
    heading: str | None = None
    body: list[str] = []
    for raw in read.splitlines():
        match = _H2.match(raw)
        if match is None:
            if heading is not None:
                body.append(raw)
            continue
        if heading is not None:
            sections.append(_section(heading=heading, body=body))
        title = match.group(1)
        heading = title if title.startswith(SCENARIO_HEADING_PREFIX) else None
        body = []
    if heading is not None:
        sections.append(_section(heading=heading, body=body))
    return tuple(sections)


def _section(*, heading: str, body: list[str]) -> _ScenarioSection:
    return _ScenarioSection(
        heading=heading,
        terms=_distinctive_terms(text=heading) | _distinctive_terms(text="\n".join(body)),
    )


def advisory_definition_of_done_findings(
    *, item: WorkItem, cwd: Path, governing: GoverningHeadingVerdict | None = None
) -> tuple[str, ...]:
    """Every advisory Definition-of-Done finding for one item, or an empty tuple.

    An item with NO section returns early with nothing: the absent section is the
    mechanical wall's finding, and reporting it here as well would name one fault
    twice on two surfaces whose consequences differ.

    One assertion may carry more than one recognised form, and each is reported:
    collapsing them would hide whichever rule matched second, and the remedies
    are different edits.

    `governing` is the spec-stated judgement's own verdict about which clauses
    govern these assertions, and where a caller supplies one it REPLACES the
    lexical candidate rule below rather than standing beside it. The two answer
    the same question — which heading governs this assertion — and the
    judgement's answer is the one Scenario 206 makes the remedy, so reporting
    both would hand a filer two headings to add and no way to tell which surface
    will hold the item for the other.

    It DEFAULTS to absent, and the default is a spend decision rather than an
    oversight: the `needs-attention` hygiene lane composes this over every item
    in the tenant, and a judgement taken here would turn one listing into a
    model call per item. With no verdict the lexical candidate stands, which is
    exactly what this surface reported before the judgement existed.
    """
    section = definition_of_done(description=item.description)
    if not section.present:
        return ()
    findings: list[str] = []
    for assertion in section.assertions:
        findings.extend(_form_findings(item=item, assertion=assertion.text))
    if governing is None:
        findings.extend(_scenario_reference_findings(item=item, section=section, cwd=cwd))
    else:
        findings.extend(governing_heading_findings(item=item, section=section, verdict=governing))
    return tuple(findings)


def _form_findings(*, item: WorkItem, assertion: str) -> list[str]:
    """The per-assertion shape findings, in the order the clause introduces them."""
    findings: list[str] = []
    test_existence = _matched_form(text=assertion, forms=_TEST_EXISTENCE_FORMS)
    if test_existence is not None:
        findings.append(
            _test_existence_finding(item=item, assertion=assertion, form=test_existence)
        )
    carrier = _matched_form(text=assertion, forms=_CARRIER_RELATION_FORMS)
    if carrier is not None:
        findings.append(_carrier_relation_finding(item=item, assertion=assertion, form=carrier))
    return findings


def _matched_form(*, text: str, forms: tuple[tuple[str, re.Pattern[str]], ...]) -> str | None:
    """The first recognised form the text carries, as the wording to quote back."""
    folded = text.casefold()
    for wording, pattern in forms:
        if pattern.search(folded) is not None:
            return wording
    return None


def _scenario_reference_findings(
    *, item: WorkItem, section: DefinitionOfDone, cwd: Path
) -> list[str]:
    """The candidate-scenario findings, or nothing when the rule cannot apply.

    The rule is withheld in two cases, and the asymmetry is deliberate. A
    reference line that ALREADY names a scenario cannot produce the gate's
    finding, so pointing at a second candidate would be noise on a conforming
    item. An unreadable scenario file means no candidate was looked for at all,
    which is not evidence that none exists.
    """
    if _names_a_scenario(references=section.references):
        return []
    sections = _scenario_sections(repo=cwd)
    if not sections:
        return []
    findings: list[str] = []
    for assertion in section.assertions:
        candidate = _governing_scenario(assertion=assertion.text, sections=sections)
        if candidate is not None:
            findings.append(
                _scenario_reference_finding(
                    item=item, assertion=assertion.text, candidate=candidate
                )
            )
    return findings


def _names_a_scenario(*, references: tuple[str, ...]) -> bool:
    """Whether any reference names a scenario heading, marker or not."""
    return any(
        _bare_heading(text=reference).startswith(SCENARIO_HEADING_PREFIX)
        for reference in references
    )


def _bare_heading(*, text: str) -> str:
    """One reference with its optional `## ` marker removed."""
    stripped = text.strip()
    if stripped.startswith(_HEADING_MARKER):
        return stripped[len(_HEADING_MARKER) :].strip()
    return stripped


def _governing_scenario(*, assertion: str, sections: tuple[_ScenarioSection, ...]) -> str | None:
    """The scenario sharing the most distinctive vocabulary, past the bound.

    Each scenario is scored on its HEADING's distinctive terms together with
    those of its own BODY, and the heading of the best-scoring one is returned
    as the candidate. Document order breaks a tie, because the first match is
    the one a reader encounters when they go and check, and a tie-break by text
    would reorder the candidate for reasons the filer cannot see.
    """
    terms = _distinctive_terms(text=assertion)
    best: str | None = None
    best_shared = 0
    for section in sections:
        shared = len(terms & section.terms)
        if shared > best_shared:
            best = section.heading
            best_shared = shared
    if best_shared < _MIN_SHARED_TERMS:
        return None
    return best


def _distinctive_terms(*, text: str) -> frozenset[str]:
    return frozenset(term for term in _TERM.findall(text.casefold()) if term not in _UNDISTINCTIVE)


def _test_existence_finding(*, item: WorkItem, assertion: str, form: str) -> str:
    return (
        f"work-item {item.id}: the Definition of Done assertion {assertion!r} carries"
        f" the test-existence form {form!r}, which proves a behaviour only where the"
        " item's deliverable is itself a test, a check or a gate; restate it as the"
        " behaviour the tests were meant to establish, or leave it for the gate to"
        " judge against the deliverable"
    )


def _carrier_relation_finding(*, item: WorkItem, assertion: str, form: str) -> str:
    return (
        f"work-item {item.id}: the Definition of Done assertion {assertion!r} states a"
        f" carrier relation ({form!r}) inside the section; which plan assertions a"
        " child carries is recorded only in the epic's carrier map, so move the"
        " statement to prose before the Definition of Done heading"
    )


def _scenario_reference_finding(*, item: WorkItem, assertion: str, candidate: str) -> str:
    return (
        f"work-item {item.id}: the Definition of Done reference line names no scenario"
        f" heading while {candidate!r} shares this assertion's subject"
        f" ({assertion!r}); name that scenario on the reference line where it governs"
        " the assertion, so the capture steps exercise its own Given/When/Then"
    )
