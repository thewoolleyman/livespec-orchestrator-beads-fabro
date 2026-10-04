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
heading states this assertion's behaviour" is a semantic question. What a host
surface can observe is a heading whose own distinctive vocabulary overlaps the
assertion's, which is evidence worth showing and not proof. The rule therefore
fires only when the reference line names NO scenario heading at all — the one
case where the gate's own finding is reachable — and it NAMES the candidate so
the filer can accept or reject it in one read. An unreadable `scenarios.md`
withholds the rule entirely, for the reason the mechanical wall records for its
own reference check: an empty heading set is the absence of evidence, not
evidence that no scenario governs the assertion.

WHY THE CARRIER RULE READS THE SECTION ONLY. The clause permits a child of a
plan to repeat the carrier relation "as prose before the Definition of Done
heading" and forbids it INSIDE the section. The section parse starts at the
description's FIRST heading, so the permitted form is never an assertion at all
and the permitted-versus-forbidden distinction costs this module no branch.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from livespec_orchestrator_beads_fabro.commands._dispatcher_definition_of_done import (
    DefinitionOfDone,
    definition_of_done,
)
from livespec_orchestrator_beads_fabro.effects import AttemptFailure, attempt

if TYPE_CHECKING:
    from pathlib import Path

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
# How many distinctive terms an assertion and a scenario heading must SHARE
# before the heading is worth naming as a candidate. Four is deliberately well
# above incidental overlap: a shared subject noun and a shared verb reach two,
# and the rule's whole value is that the filer can accept the candidate without
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


def scenario_headings(*, repo: Path) -> tuple[str, ...]:
    """The scenario H2 titles of the governed spec tree, in document order.

    An empty tuple means the file could not be read OR that it carries no
    scenario heading. The two are the same fact for this module's one consumer,
    which withholds the candidate rule either way rather than concluding that no
    scenario governs the assertion.
    """
    path = repo.joinpath(*_SCENARIOS_RELPATH)
    read = attempt(action=lambda: path.read_text(encoding="utf-8"), exceptions=(OSError,))
    if isinstance(read, AttemptFailure):
        return ()
    titles: list[str] = []
    for raw in read.splitlines():
        match = _H2.match(raw)
        if match is None:
            continue
        title = match.group(1)
        if title.startswith(SCENARIO_HEADING_PREFIX):
            titles.append(title)
    return tuple(titles)


def advisory_definition_of_done_findings(*, item: WorkItem, cwd: Path) -> tuple[str, ...]:
    """Every advisory Definition-of-Done finding for one item, or an empty tuple.

    An item with NO section returns early with nothing: the absent section is the
    mechanical wall's finding, and reporting it here as well would name one fault
    twice on two surfaces whose consequences differ.

    One assertion may carry more than one recognised form, and each is reported:
    collapsing them would hide whichever rule matched second, and the remedies
    are different edits.
    """
    section = definition_of_done(description=item.description)
    if not section.present:
        return ()
    findings: list[str] = []
    for assertion in section.assertions:
        findings.extend(_form_findings(item=item, assertion=assertion.text))
    findings.extend(_scenario_reference_findings(item=item, section=section, cwd=cwd))
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
    headings = scenario_headings(repo=cwd)
    if not headings:
        return []
    findings: list[str] = []
    for assertion in section.assertions:
        candidate = _governing_scenario(assertion=assertion.text, headings=headings)
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


def _governing_scenario(*, assertion: str, headings: tuple[str, ...]) -> str | None:
    """The scenario heading sharing the most distinctive vocabulary, past the bound.

    Document order breaks a tie, because the first match is the one a reader
    encounters when they go and check, and a tie-break by text would reorder the
    candidate for reasons the filer cannot see.
    """
    terms = _distinctive_terms(text=assertion)
    best: str | None = None
    best_shared = 0
    for heading in headings:
        shared = len(terms & _distinctive_terms(text=heading))
        if shared > best_shared:
            best = heading
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
