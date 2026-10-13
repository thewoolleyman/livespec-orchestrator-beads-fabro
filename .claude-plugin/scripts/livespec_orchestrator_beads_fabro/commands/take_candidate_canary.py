"""`take-candidate-canary` — file one FIXTURE canary work-item and dispatch it.

A candidate canary measures the ENGINE: a candidate Fabro build, a re-pinned
carrier, a restarted factory host. Whatever brief it carries is therefore
instrumentation, not work, and the one property that instrumentation must have
is that it cannot fail for a reason of its own. Canaries 5 and 6 of plan
`fabro-currency` did exactly that — both reached the `dod_gate` node and were
refused, because the canary reused a real backlog item whose `References` line
named a heading that governs something else. An item-quality refusal is
indistinguishable, at the surface an operator watches, from the engine fault the
canary was taken to look for; the second canary repeated the first's mistake for
that reason.

So the brief is a COMMITTED FIXTURE, reviewed once through the ordinary gates
and thereafter rendered mechanically. This module is the renderer and the filing
seam; the operator-facing procedure that files one and dispatches it to a named
factory is the runbook recipe, which shells to this module rather than
assembling a brief of its own.

WHY THE PLACEHOLDERS ARE NOT DOUBLED-BRACE TOKENS. A doubled-brace
template-interpolation pair anywhere in a work-item's own text makes that item
undispatchable: dispatch graph construction fails on a template variable whose
name appears only in the record and never in the workflow, and the Dispatcher's
escaper is self-cancelling because the goal is rendered twice. A fixture whose
whole purpose is to be dispatchable cannot carry that hazard, so the two
substitution points are spelled `@@…@@` and are plain string replacement.
"""

from __future__ import annotations

from dataclasses import dataclass

__all__: list[str] = [
    "CANARY_MARKER_RELPATH",
    "CanaryFixture",
    "marker_entry_findings",
    "render_canary_fixture",
]

# The dedicated marker file the fixture's one assertion names. The canary's
# WHOLE change is one appended line here, which is what keeps a canary's diff
# incapable of failing for a reason of its own.
CANARY_MARKER_RELPATH = "orchestrator-image/candidate-canary-log.md"

# The two field markers of the committed template, each matched as a line of its
# own. The template's own prose refers to them in backticks for exactly that
# reason: a sentence about a marker must not be readable AS the marker.
_TITLE_MARKER = "TITLE:"
_DESCRIPTION_MARKER = "DESCRIPTION:"
_ID_PLACEHOLDER = "@@CANARY_ID@@"
_FACTORY_PLACEHOLDER = "@@CANARY_FACTORY@@"
_NEWLINE = "\n"

# The marker file's own grammar, which is the whole of what the check suite has
# to accept for a canary's edit to merge: one heading, then one `- ` line per
# canary taken.
_MARKER_ENTRIES_HEADING = "## Entries"
_MARKER_ENTRY_PREFIX = "- "


@dataclass(frozen=True, kw_only=True)
class CanaryFixture:
    """One rendered canary brief: the work-item title and description to file.

    The description is carried whole rather than as a parsed Definition of Done,
    because the ratified clause allows exactly one parse of that section and it
    is not this module's. What reaches the ledger is the text; what grades it is
    the sanctioned parse, reading the same bytes.
    """

    title: str
    description: str


def render_canary_fixture(*, template_text: str, item_id: str, factory: str) -> CanaryFixture:
    """Render the committed fixture template for one canary.

    Pure: a function of the template text and the two substitution values, so
    the brief a dispatch would carry is gradeable without filing anything.

    A template missing either field marker is a BUG, not an expected failure —
    the file is committed and the test suite parses it — so the lookups below
    raise rather than returning a half-rendered brief that would reach the
    ledger looking plausible.
    """
    lines = template_text.splitlines()
    title_line = next(line for line in lines if line.startswith(_TITLE_MARKER))
    body_start = 1 + next(
        index for index, line in enumerate(lines) if line.strip() == _DESCRIPTION_MARKER
    )
    return CanaryFixture(
        title=_substituted(
            text=title_line.removeprefix(_TITLE_MARKER).strip(),
            item_id=item_id,
            factory=factory,
        ),
        description=_substituted(
            text=_NEWLINE.join(lines[body_start:]).strip() + _NEWLINE,
            item_id=item_id,
            factory=factory,
        ),
    )


def marker_entry_findings(*, marker_text: str) -> tuple[str, ...]:
    """Every way the candidate-canary log's entry list is malformed, or an empty tuple.

    This is what makes "the check suite accepts the canary's edit" a measured
    property rather than an absence of objection. The suite grades the COMMITTED
    log through this function and grades it again with the fixture's own entry
    appended, so the one edit a canary makes is known-accepted before any canary
    makes it; the malformed cases are what stop that acceptance from being
    vacuous.

    Findings rather than a boolean, and one line each naming the offending
    element and the remedy, because that is the shape every other grading
    surface in this repository reports — an operator reading a janitor failure
    needs the line that is wrong, not a verdict on the file.
    """
    lines = marker_text.splitlines()
    heading_index = next(
        (index for index, line in enumerate(lines) if line.strip() == _MARKER_ENTRIES_HEADING),
        None,
    )
    if heading_index is None:
        return (_absent_heading_finding(),)
    entries = [line for line in lines[heading_index + 1 :] if line.strip()]
    if not entries:
        return (_empty_entry_list_finding(),)
    return tuple(
        _malformed_entry_finding(line=line)
        for line in entries
        if not line.startswith(_MARKER_ENTRY_PREFIX)
    )


def _absent_heading_finding() -> str:
    return (
        f"the candidate-canary log carries no `{_MARKER_ENTRIES_HEADING}` heading,"
        " so there is no entry list for a canary to append to; restore the heading"
        " rather than appending beneath the prose"
    )


def _empty_entry_list_finding() -> str:
    return (
        f"the candidate-canary log carries no entry under `{_MARKER_ENTRIES_HEADING}`;"
        " the file is append-only and keeps at least its seed entry, so an empty"
        " list means entries were removed rather than added"
    )


def _malformed_entry_finding(*, line: str) -> str:
    return (
        f"the candidate-canary log line {line!r} does not begin with"
        f" `{_MARKER_ENTRY_PREFIX}`, so it is not one entry; make the canary's change"
        " exactly one appended entry line and edit nothing else"
    )


def _substituted(*, text: str, item_id: str, factory: str) -> str:
    return text.replace(_ID_PLACEHOLDER, item_id).replace(_FACTORY_PLACEHOLDER, factory)
